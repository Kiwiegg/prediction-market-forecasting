#!/usr/bin/env python3
"""Separate, seal-gated historical held-out evaluation and sanitized replay."""
import argparse
import csv
import io
import json
import math
from collections import Counter
from itertools import combinations
from pathlib import Path

import heldout_forecast as inference
from analyze_v2_development import bootstrap, evaluated, group_diagnostics
from compare_forecasts import compare_rows as compare_v1
from compare_leap_v2 import METHODS, compare_rows as compare_v2
from evidence_documents import canonical, digest
from forecast_split import ROOT, DEFAULT_DATA, immutable_json
from investigate_kalshi import timestamp

PUBLIC = ROOT / "reports/heldout_150"
LABEL_FIELDS = ("game_id", "home_yes_outcome", "market_status", "home_mapping_verified", "market_open_at_cutoff",
    "cutoff_utc", "preferred_quote_missing_reason", "preferred_midpoint_price", "preferred_quote_bid",
    "preferred_quote_ask", "preferred_quote_candle_end_lag_seconds", "preferred_quote_candle_end_utc")
ARTIFACTS = {"per_game.json", "summary.json", "bootstrap.json", "diagnostics.json", "execution_audit.json",
    "development_comparison.json", "results.csv"}


def labels_after_seal(ids):
    # Called by export only after full private verification, or by public replay
    # of a previously sealed run. The inference module never imports this file.
    wanted = set(ids); labels = {}
    with (DEFAULT_DATA / "evaluation.csv").open() as f:
        for row in csv.DictReader(f):
            if row["game_id"] not in wanted: continue
            if row["game_id"] in labels: raise ValueError("Duplicate selected evaluation label")
            labels[row["game_id"]] = {k: row.get(k, "") for k in LABEL_FIELDS}
    return labels


def audit(obs, specs):
    plan = obs["run"]["plan"]; pre = obs["run"]["preflight"]["cost_plan"]
    byid = {n + ":" + s["key"]: s for n, s in inference.sequence(plan, specs)}
    fresh = set(pre["new_request_ids"]); old = set(pre["cached_request_ids"])
    if fresh & old or fresh - set(byid) or old - set(byid): raise ValueError("Cache origin identity mismatch")
    expected_new = {k for k, s in byid.items() if s.get("usable", True)} - old
    if expected_new != fresh or len(fresh) != pre["planned_new_requests"] or not math.isclose(math.fsum(byid[k]["reserved_cost_usd"] for k in fresh), pre["additional_reservation_usd"], abs_tol=1e-12):
        raise ValueError("Original cost plan does not reconcile")
    reservations = obs["reservations"]; claims = obs["claims"]
    ledger = {r["request_id"]: r for r in reservations}
    if len(ledger) != len(reservations) or len(ledger) > 1200 or math.fsum(r["cost_usd"] for r in reservations) > 40 + 1e-12: raise ValueError("Global budget/duplicate reservation violation")
    if len(reservations) != obs["completion"]["paid_call_reservations"] or math.fsum(r["cost_usd"] for r in reservations) != obs["completion"]["reserved_cost_usd"]: raise ValueError("Sealed budget differs")
    for k, r in ledger.items():
        if k not in fresh or r["request_sha256"] != byid[k]["key"] or r["method"] != k.split(":")[0] or r["cost_usd"] != byid[k]["reserved_cost_usd"]: raise ValueError("Reservation differs from frozen request")
    if set(claims) - set(ledger): raise ValueError("Claim without pre-call reservation")
    observed = {}; entries = []
    for name in inference.ORDER:
        for game in obs["games"][name]:
            for r in ([game] if name == "direct" else game["groups"]):
                key = name + ":" + r["request_sha256"]; observed[key] = r; raw = r.get("raw_response")
                if raw and key in fresh and key not in claims: raise ValueError("New response lacks original claim")
                if key in claims:
                    claim = claims[key]
                    if claim["request_sha256"] != r["request_sha256"] or timestamp(ledger[key]["reserved_at_utc"]) > timestamp(claim["claimed_at_utc"]): raise ValueError("Claim/reservation ordering differs")
                    if r.get("request_started_at_utc") and timestamp(claim["claimed_at_utc"]) > timestamp(r["request_started_at_utc"]): raise ValueError("Claim after provider request")
                if r.get("response_retrieved_at_utc") and timestamp(r["response_retrieved_at_utc"]) > timestamp(obs["completion"]["completed_at_utc"]): raise ValueError("Response arrived after seal")
                entries.append({"game_id": r["game_id"], "method": name, "group": r.get("group"), "request_id": key,
                    "origin": "original_cache" if key in old else "additional" if key in claims else "source_missing" if not byid[key].get("usable", True) else "unattempted",
                    "status": r["status"], "http_status": raw["http_status"] if raw else None,
                    "response_category": obs["execution"]["response_categories"][key], "error": r.get("error"),
                    "raw_response_sha256": raw["body_sha256"] if raw else None, "usage": r.get("usage"),
                    "estimated_cost_usd": r["estimated_cost_usd"], "estimated_cost_kind": r.get("estimated_cost_kind", "not_requested"),
                    "latency_seconds": r.get("latency_seconds")})
    ordering = list(byid)
    denials = [e["request_id"] for e in entries if e["response_category"] == "access_denial"]
    if denials:
        first = min(ordering.index(k) for k in denials)
        if any(ordering.index(k) > first for k in claims): raise ValueError("New request after first access denial")
        if obs["execution"]["stop_reason"]["category"] != "access_denial": raise ValueError("Access denial stopping reason lost")
    total = math.fsum(observed[k]["estimated_cost_usd"] for k in claims)
    return {"planned_new_requests": len(fresh), "reserved_requests": len(ledger), "claimed_new_requests": len(claims),
        "unattempted_new_requests": len(fresh - set(claims)), "unattempted_request_ids": sorted(fresh - set(claims)),
        "reused_observations": len(old), "additional_reservation_usd": math.fsum(r["cost_usd"] for r in reservations),
        "additional_recorded_estimate_usd": total, "stop_reason": obs["execution"]["stop_reason"],
        "per_observation": entries}


def development_comparison(cohorts):
    folder = ROOT / "reports/leap_nba_v2_development_50"
    original = json.loads((folder / "summary.json").read_text())
    result = {"development_manifest_sha256": digest((folder / "manifest.json").read_bytes()),
        "interpretation": "Different development and held-out games; score changes are unpaired descriptive differences, never tuning targets.", "cohorts": {}}
    for held, dev in (("A_v2_market", "A_v2_development"), ("B_seven_method", "B_seven_method")):
        current = cohorts[held]; previous = original["comparisons"][dev]
        result["cohorts"][held] = {"heldout_n": current["n"], "development_n": previous["n"],
            "heldout_game_ids": current["game_ids"], "development_game_ids": previous["game_ids"],
            "scores": {m: {"development": previous["scores"][m], "heldout": r,
                "heldout_minus_development": {k: r[k] - previous["scores"][m][k] if r[k] is not None and previous["scores"][m][k] is not None else None
                    for k in ("brier_score", "log_loss", "mean_home_probability", "mean_distance_from_half")}}
                for m, r in current["scores"].items()}}
    return result


def compute(obs, labels, allow_mock=False):
    run = obs["run"]; plan = run["plan"]; mock = plan["plans"]["direct"]["config"]["provider"] == "mock"
    if mock and not allow_mock: raise ValueError("Synthetic mocks cannot be presented as held-out inference")
    expected, specs = inference.frozen_plan(True, mock)
    if plan != expected or obs["provider_raw_bodies_included"] is not False: raise ValueError("Frozen plan differs or unsafe observations")
    inference.validate_games(plan, specs, obs["games"])
    if any(obs["completion"][k] != v for k, v in inference.public_counts(plan, obs["games"], obs["execution"]).items()): raise ValueError("Sealed counters differ")
    if obs["rules"] != inference.rules(): raise ValueError("Evaluation rules changed")
    packets = {gid: inference.direct.load_evidence(DEFAULT_DATA, gid) for gid in plan["game_ids"]}
    first, _ = compare_v1(obs["games"]["direct"], obs["games"]["v1"], labels, {gid: p["cutoff_utc"] for gid, p in packets.items()})
    rows, _ = compare_v2(obs["games"]["v2"], first)
    for r, vg in zip(rows, obs["games"]["v1"]): r["v1_groups"] = vg["groups"]
    cohorts = {key: evaluated(rows, methods) for key, methods in obs["rules"]["cohorts"].items()}
    by_gid = {r["game_id"]: r for r in rows}
    for c in cohorts.values():
        for e in c["exclusions"]:
            r = by_gid[e["game_id"]]; e["direct_status"] = r["direct_status"]
            e["v1_failed_groups"] = [g["group"] for g in r["v1_groups"] if g["status"] not in ("success", "skipped_missing")]
    for r in rows:
        r["cohorts"] = {k: r["game_id"] in c["game_ids"] for k, c in cohorts.items()}
        r["all_available_pairwise_differences"] = {x + "_minus_" + y: {k: r["scores"][x][k] - r["scores"][y][k] for k in ("brier", "log_loss")}
            for x, y in combinations(METHODS, 2) if r["scores"][x] is not None and r["scores"][y] is not None}
    b = obs["rules"]["bootstrap"]
    bootstraps = {k: bootstrap([by_gid[gid] for gid in c["game_ids"]], b["pairs"][k], b["seed"], b["replicates"]) for k, c in cohorts.items()}
    execution = audit(obs, specs)
    summary = {"subset": "evaluation", "planned_games": 150, "coverage": {m: sum(r[m] is not None for r in rows) for m in METHODS},
        "missing_outcomes": sum(r["outcome"] is None for r in rows), "missing_markets": sum(r["kalshi"] is None for r in rows),
        "cohorts": cohorts, "resources": obs["completion"]["resources"], "stop_reason": obs["execution"]["stop_reason"],
        "interpretation": "One-time locked historical hold-out; potential model memorization and source/schedule uncertainty. No post-evaluation tuning."}
    # Existing diagnostic code expects these cohort names. This is naming only;
    # its strength rule, injury and dependence/removal arithmetic are unchanged.
    detail = group_diagnostics(rows, packets, {"A_v2_development": cohorts["A_v2_market"], "B_seven_method": cohorts["B_seven_method"]})
    detail["cohort_name_mapping"] = {"A_v2_development": "held-out A_v2_market (legacy helper label only)", "B_seven_method": "held-out B_seven_method"}
    return {"per_game.json": rows, "summary.json": summary, "bootstrap.json": bootstraps,
        "diagnostics.json": detail, "execution_audit.json": execution,
        "development_comparison.json": development_comparison(cohorts)}, packets


def result_csv(rows, packets):
    fields = ["game_id", "home", "away", "cutoff_utc", "home_won", "primary", "paired_A", "paired_B",
        *METHODS, "direct_status", "v1_status", "v2_status", "outcome_missing_reason", "market_missing_reason"]
    fields += [m + "_" + k for m in METHODS for k in ("brier", "log_loss")]
    fields += [v + "_" + g + "_" + k for v in ("v1", "v2") for g in evidence_groups() for k in ("status", "lr", "sufficiency", "category", "missing_reason")]
    stream = io.StringIO(newline=""); writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n"); writer.writeheader()
    for r in rows:
        p = packets[r["game_id"]]; row = {k: r[k] for k in fields if k in r}
        row.update(home=p["home"]["team_name"], away=p["away"]["team_name"], cutoff_utc=p["cutoff_utc"], home_won=r["outcome"],
            primary=r["cohorts"]["primary"], paired_A=r["cohorts"]["A_v2_market"], paired_B=r["cohorts"]["B_seven_method"])
        for m in METHODS:
            for k in ("brier", "log_loss"): row[m + "_" + k] = (r["scores"][m] or {}).get(k)
        for v in ("v1", "v2"):
            for g in r[v + "_groups"]:
                for k, value in (("status", g["status"]), ("lr", g["likelihood_ratio"]), ("sufficiency", g["evidence_sufficiency"]),
                        ("category", (g.get("assessment") or {}).get("strength")), ("missing_reason", g["missing_reason"])):
                    row[v + "_" + g["group"] + "_" + k] = value
        writer.writerow(row)
    return stream.getvalue()


def evidence_groups(): return inference.evidence_v2.GROUPS


def export(run_path, output, authorize_evaluation=False):
    if not authorize_evaluation: raise ValueError("Scoring requires --authorize-evaluation")
    run_path, output = Path(run_path), Path(output)
    run, specs, games, complete, execution = inference.verify(run_path, True)
    if run["plan"]["plans"]["direct"]["config"]["provider"] == "mock": raise ValueError("Live evaluation does not join real outcomes to mock inference")
    for protected in [run_path, DEFAULT_DATA, *map(Path, run["cache_directories"].values()), ROOT / "reports/leap_nba_v2_development_50"]:
        if output.resolve() == protected.resolve() or output.resolve() in protected.resolve().parents or protected.resolve() in output.resolve().parents: raise ValueError("Separate sanitized analysis directory required")
    fresh = run["preflight"]["cost_plan"]["new_request_ids"]
    claims = {}
    for key in fresh:
        name, sha = key.split(":"); marker = Path(run["cache_directories"][name]) / sha / "attempt.json"
        if marker.exists(): claims[key] = json.loads(marker.read_text())
    obs = {"run": {k: v for k, v in run.items() if k != "cache_directories"}, "games": games,
        "completion": {k: v for k, v in complete.items() if k != "files"}, "execution": execution,
        "reservations": [json.loads(p.read_text()) for p in sorted((run_path / "reservations").glob("*.json"))],
        "claims": claims, "rules": inference.rules(), "private_completion_sha256": digest((run_path / "completion.json").read_bytes()),
        "provider_raw_bodies_included": False, "evaluation_source_sha256": digest((DEFAULT_DATA / "evaluation.csv").read_bytes())}
    labels = labels_after_seal(run["plan"]["game_ids"])
    artifacts, packets = compute(obs, labels)
    for name, value in {"observations.json": obs, "labels.json": labels, **artifacts}.items(): immutable_json(output / name, value)
    (output).mkdir(parents=True, exist_ok=True)
    text = result_csv(artifacts["per_game.json"], packets)
    from analyze_development import immutable_text
    immutable_text(output / "results.csv", text)
    files = {"observations.json", "labels.json", *ARTIFACTS}
    immutable_json(output / "manifest.json", {name: digest((output / name).read_bytes()) for name in sorted(files)})
    return artifacts["summary.json"]


def replay(output, authorize_evaluation=False):
    if not authorize_evaluation: raise ValueError("Held-out replay requires --authorize-evaluation")
    output = Path(output); manifest = json.loads((output / "manifest.json").read_text())
    if set(manifest) != {"observations.json", "labels.json", *ARTIFACTS}: raise ValueError("Public artifact set differs")
    for name, sha in manifest.items():
        if digest((output / name).read_bytes()) != sha: raise ValueError("Sanitized artifact changed")
    obs = json.loads((output / "observations.json").read_text()); labels = json.loads((output / "labels.json").read_text())
    if obs["evaluation_source_sha256"] != digest((DEFAULT_DATA / "evaluation.csv").read_bytes()) or labels != labels_after_seal(obs["run"]["plan"]["game_ids"]): raise ValueError("Evaluation source lineage differs")
    artifacts, packets = compute(obs, labels)
    if any(v != json.loads((output / k).read_text()) for k, v in artifacts.items()) or result_csv(artifacts["per_game.json"], packets).encode() != (output / "results.csv").read_bytes():
        raise ValueError("Frozen evaluation does not reproduce")
    return artifacts["summary.json"]


def main():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument("--authorize-evaluation", action="store_true")
    p.add_argument("--run", type=Path); p.add_argument("--output", type=Path); p.add_argument("--replay", type=Path); a = p.parse_args()
    if not a.authorize_evaluation: p.error("Explicit --authorize-evaluation required")
    if a.replay: result = replay(a.replay, True)
    elif a.run and a.output: result = export(a.run, a.output, True)
    else: p.error("Use --run SEALED --output PUBLIC or --replay PUBLIC")
    print(json.dumps({"coverage": result["coverage"], "cohorts": {k: {"n": c["n"], "scores": c["scores"]} for k, c in result["cohorts"].items()}}, indent=2))


if __name__ == "__main__": main()
