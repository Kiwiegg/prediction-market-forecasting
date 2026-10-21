#!/usr/bin/env python3
"""Offline-only descriptive diagnostics and sanitized replay for development 50."""
import argparse
import csv
import io
import json
import math
import random
import statistics
from collections import Counter
from pathlib import Path

import direct_forecast as direct
import leap_forecast as leap
from compare_forecasts import METHODS, compare_rows
from evaluate_forecasts import brier, log_loss, scores
from evidence_documents import canonical, digest
from forecast_split import ROOT, DEFAULT_DATA, DEFAULT_SPLIT, immutable_json, load_split
from leap_evidence import GROUPS, VARIANTS, aggregate, frozen_assets, likelihood_ratio

PLAN_PATH = ROOT / "experiments/development_50_analysis_plan.json"
COMPARISONS = (("leap_raw", "direct"), ("leap_conservative", "direct"), ("direct", "kalshi"),
    ("leap_raw", "kalshi"), ("leap_conservative", "kalshi"))


def quantile(values, q):
    if not 0 <= q <= 1:
        raise ValueError("Quantile must be in [0,1]")
    if not values:
        return None
    ordered = sorted(values)
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in ordered):
        raise ValueError("Finite observations required")
    at = (len(ordered) - 1) * q
    lo, hi = math.floor(at), math.ceil(at)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (at - lo)


def distribution(values):
    values = list(values)
    return {"n": len(values), "mean": statistics.fmean(values) if values else None,
        "population_stddev": statistics.pstdev(values) if values else None,
        "quantiles": {str(q): quantile(values, q) for q in (0.0, .1, .25, .5, .75, .9, .95, 1.0)}}


def paired_bootstrap(rows, seed=20261021, replicates=10000):
    if type(seed) is not int or type(replicates) is not int or replicates < 1:
        raise ValueError("Fixed integer seed and positive replicate count required")
    if len({r["game_id"] for r in rows}) != len(rows) or any(not r["paired_eligible"] for r in rows):
        raise ValueError("Unique identical eligible paired games required")
    n = len(rows)
    diffs = {a + "_minus_" + b: [brier(r[a], r["outcome"]) - brier(r[b], r["outcome"]) for r in rows]
        for a, b in COMPARISONS}
    draws = {k: [] for k in diffs}
    rng = random.Random(seed)
    if n:
        for _ in range(replicates):
            indices = [rng.randrange(n) for _ in range(n)]
            for key, values in diffs.items():
                draws[key].append(math.fsum(values[i] for i in indices) / n)
    return {"seed": seed, "replicates": replicates, "n": n, "game_ids": [r["game_id"] for r in rows],
        "confidence_level": .95, "procedure": "Paired game resampling with replacement; shared row indices across comparisons; percentile interval with linear (B-1)*q interpolation.",
        "descriptive_only": True,
        "comparisons": {k: {"mean_brier_difference": statistics.fmean(v) if v else None,
            "lower_95": quantile(draws[k], .025), "upper_95": quantile(draws[k], .975)} for k, v in diffs.items()}}


def strength_diagnostic(packet, ratio):
    features = {}
    for side in ("home", "away"):
        record = packet[side].get("regular_season_record", {})
        n, wins = record.get("games_completed"), record.get("wins")
        pd = packet[side].get("regular_season_scoring", {}).get("average_point_differential")
        valid = (type(n) is int and n > 0 and type(wins) is int and 0 <= wins <= n
            and type(pd) in (int, float) and math.isfinite(pd))
        features[side] = {"season_win_fraction": wins / n if valid else None,
            "average_point_differential": pd if valid else None}
    a, b = features["home"], features["away"]
    if any(v is None for f in features.values() for v in f.values()):
        weaker, reason = None, "missing_or_zero_game_statistics"
    elif all(a[k] < b[k] for k in a):
        weaker, reason = "home", None
    elif all(a[k] > b[k] for k in a):
        weaker, reason = "away", None
    else:
        weaker, reason = None, "ties_or_discordant_indicators"
    if ratio is not None:
        likelihood_ratio(ratio)
    return {"game_id": packet["game_id"], "features": features, "weaker_team": weaker,
        "unassessable_reason": reason, "strength_lr": ratio,
        "lr_available": ratio is not None,
        "favors_weaker_team": None if weaker is None or ratio is None else
            (ratio > 1 if weaker == "home" else ratio < 1),
        "diagnostic_only_forecast_unchanged": True}


def subset_scores(rows):
    return {"n": len(rows), "game_ids": [r["game_id"] for r in rows],
        "scores": {m: scores(rows, m) for m in METHODS}}


def diagnostics(rows, packets, group_records, analysis_plan):
    paired = [r for r in rows if r["paired_eligible"]]
    if set(packets) != {r["game_id"] for r in rows} or set(group_records) != set(packets):
        raise ValueError("Diagnostic packet/group/game identities differ")
    groups = {}
    for index, group in enumerate(GROUPS):
        observations = [group_records[r["game_id"]][index] for r in rows]
        if any(o["group"] != group for o in observations):
            raise ValueError("Unordered diagnostic group records")
        valid = [r for r in observations if r["status"] == "success"]
        ratios = [likelihood_ratio(r["likelihood_ratio"]) for r in valid]
        with_group = [r for r in paired if group_records[r["game_id"]][index]["usable"]]
        without_group = [r for r in paired if not group_records[r["game_id"]][index]["usable"]]
        contributions = {}
        for variant in VARIANTS:
            changes = [abs(r[variant] - .5) - abs(r["variants"][variant]["leave_one_group_out"][group]["home_win_probability"] - .5) for r in paired]
            omitted = [{"outcome": r["outcome"], "p": r["variants"][variant]["leave_one_group_out"][group]["home_win_probability"]} for r in paired]
            omission_scores, full_scores = scores(omitted, "p"), scores(paired, variant)
            contributions[variant] = {"paired_n": len(paired),
                "weighted_log_lr_including_skipped_zeros": distribution(r["variants"][variant]["group_log_odds_contributions"][group] for r in paired),
                "increase_in_distance_from_half": distribution(changes),
                "pushes_more_extreme_count": sum(v > 1e-12 for v in changes),
                "pulls_toward_half_count": sum(v < -1e-12 for v in changes),
                "unchanged_distance_count": sum(abs(v) <= 1e-12 for v in changes),
                "leave_one_out_scores": omission_scores,
                "omission_minus_full_scores": {k: omission_scores[k] - full_scores[k] if paired else None for k in ("brier_score", "log_loss")}}
        labels = {}
        for label in ("adequate", "limited"):
            chosen = [o for o in valid if o["evidence_sufficiency"] == label]
            selected = [r for r in paired if group_records[r["game_id"]][index]["status"] == "success"
                and group_records[r["game_id"]][index]["evidence_sufficiency"] == label]
            labels[label] = {"count": len(chosen), "likelihood_ratios": distribution(o["likelihood_ratio"] for o in chosen),
                "absolute_log_lr": distribution(abs(math.log(o["likelihood_ratio"])) for o in chosen),
                "paired_full_forecast_scores": subset_scores(selected)}
        groups[group] = {"planned": len(observations), "usable_before_inference": sum(o["usable"] for o in observations),
            "status_counts": dict(Counter(o["status"] for o in observations)),
            "source_missingness": dict(Counter(o["missing_reason"] for o in observations if not o["usable"])),
            "model_failure_reasons": dict(Counter((o.get("error") or {}).get("message", "unknown") for o in observations if o["status"] == "failed")),
            "likelihood_ratios_success_only": distribution(ratios),
            "directions_success_only": {"home_lr_gt_1": sum(v > 1 for v in ratios), "away_lr_lt_1": sum(v < 1 for v in ratios),
                "neutral_lr_eq_1": sum(v == 1 for v in ratios)},
            "extreme_observations": [{"game_id": o["game_id"], "lr": o["likelihood_ratio"], "sufficiency": o["evidence_sufficiency"]}
                for o in valid if o["likelihood_ratio"] <= .1 or o["likelihood_ratio"] >= 10],
            "log_lr_inferred_only": distribution(math.log(v) for v in ratios),
            "sufficiency": labels, "contributions": contributions,
            "paired_availability_strata": {"usable": subset_scores(with_group), "unavailable": subset_scores(without_group)}}
    directionality = []
    for row in rows:
        strength = group_records[row["game_id"]][0]
        directionality.append(strength_diagnostic(packets[row["game_id"]], strength["likelihood_ratio"] if strength["status"] == "success" else None))
    calibration = {}
    for method in METHODS:
        confidence = [max(r[method], 1 - r[method]) for r in paired]
        accuracy = [int((r[method] >= .5) == bool(r["outcome"])) for r in paired]
        calibration[method] = {"n": len(paired), "mean_confidence": statistics.fmean(confidence) if paired else None,
            "classification_accuracy": statistics.fmean(accuracy) if paired else None,
            "confidence_minus_accuracy": statistics.fmean(confidence) - statistics.fmean(accuracy) if paired else None,
            "distance_from_half": distribution(abs(r[method] - .5) for r in paired),
            "probabilities_le_0_1_or_ge_0_9": sum(r[method] <= .1 or r[method] >= .9 for r in paired)}
    if any(abs(r["leap_conservative"] - .5) > abs(r["leap_raw"] - .5) + 1e-12 for r in paired):
        raise ValueError("Prespecified shrinkage did not move probability toward half")
    return {"paired_n": len(paired), "paired_game_ids": [r["game_id"] for r in paired], "groups": groups,
        "directionality": {"criterion": analysis_plan["directionality"], "per_game": directionality,
            "assessable_with_lr": sum(d["weaker_team"] is not None and d["lr_available"] for d in directionality),
            "favors_weaker_count": sum(d["favors_weaker_team"] is True for d in directionality),
            "flagged_game_ids": [d["game_id"] for d in directionality if d["favors_weaker_team"] is True]},
        "injury_strata": groups[GROUPS[2]]["paired_availability_strata"], "calibration_diagnostics": calibration,
        "bootstrap": paired_bootstrap(paired, analysis_plan["bootstrap"]["seed"], analysis_plan["bootstrap"]["replicates"])}


RECORD_FIELDS = ("game_id", "group", "evidence_sha256", "group_evidence_sha256", "request_sha256", "provider", "requested_model",
    "returned_model", "prompt_version", "prompt_sha256", "generation_settings", "status", "usable", "missing_reason",
    "likelihood_ratio", "evidence_sufficiency", "extreme_lr", "home_win_probability", "request_started_at_utc",
    "response_retrieved_at_utc", "record_created_at_utc", "usage", "latency_seconds", "estimated_cost_usd", "estimated_cost_kind", "prices", "error")


def sanitize(record):
    return {**{k: record[k] for k in RECORD_FIELDS if k in record},
        "raw_response_sha256": record["raw_response"]["body_sha256"] if record.get("raw_response") else None,
        "http_status": record["raw_response"]["http_status"] if record.get("raw_response") else None}


def resource_summary(records, fresh_keys):
    output = {}
    for name, chosen in (("all_saved", records), ("additional", [r for r in records if r["request_sha256"] in fresh_keys]),
            ("reused", [r for r in records if r["request_sha256"] not in fresh_keys and r.get("raw_response_sha256")])):
        output[name] = {"observations": len(chosen), "captured_requests": sum(bool(r.get("raw_response_sha256")) for r in chosen),
            "statuses": dict(Counter(r["status"] for r in chosen)),
            "usage": {k: sum(r["usage"].get(k, 0) for r in chosen if isinstance(r.get("usage"), dict)) for k in ("input_tokens", "output_tokens")},
            "estimated_cost_usd": math.fsum(r["estimated_cost_usd"] for r in chosen),
            "summed_latency_seconds": math.fsum(r.get("latency_seconds") or 0 for r in chosen),
            "missing_usage": sum(r.get("usage") is None and r["status"] == "failed" for r in chosen),
            "request_started_at_utc": min((r["request_started_at_utc"] for r in chosen if r.get("request_started_at_utc")), default=None),
            "last_retrieved_at_utc": max((r["response_retrieved_at_utc"] for r in chosen if r.get("response_retrieved_at_utc")), default=None)}
    return output


def reconstruct(observations, dataset=DEFAULT_DATA, split_path=DEFAULT_SPLIT):
    split = load_split(split_path, dataset)
    expected = split["run_order"]["development"]
    if ([r["game_id"] for r in observations["direct"]] != expected or
            [r["game_id"] for r in observations["leap"]] != expected):
        raise ValueError("Only all 50 fixed development IDs are permitted")
    if observations["frozen_leap_assets"] != frozen_assets() or observations["split_sha256"] != digest(canonical(split)):
        raise ValueError("Frozen assets or split changed")
    dp, ds = direct.plan_experiment(dataset, split_path, observations["configs"]["direct"], limit=50)
    lp, ls = leap.plan_experiment(dataset, split_path, observations["configs"]["leap"], limit=50)
    if dp["config"]["model"] != lp["config"]["model"]:
        raise ValueError("Comparison model mismatch")
    packets = {gid: direct.load_evidence(dataset, gid) for gid in expected}
    leap_games, group_records = [], {}
    for record, spec in zip(observations["direct"], ds):
        if (record["request_sha256"], record["evidence_sha256"], record["prompt_sha256"]) != (spec["key"], spec["evidence_sha256"], direct.PROMPT_HASH):
            raise ValueError("Direct sanitized request differs from frozen evidence/settings")
        if record["status"] == "success": direct.probability(record["home_win_probability"])
        elif record["home_win_probability"] is not None: raise ValueError("Failed direct prediction is not missing")
    for game in observations["leap"]:
        specs = [s for s in ls if s["game_id"] == game["game_id"]]
        if len(game["groups"]) != 4: raise ValueError("Four group observations required")
        for r, s in zip(game["groups"], specs):
            if any(r[k] != s[k] for k in ("game_id", "group", "evidence_sha256", "group_evidence_sha256", "usable", "missing_reason")) or r["request_sha256"] != s["key"]:
                raise ValueError("Sanitized LR request/group identity differs")
        group_records[game["game_id"]] = game["groups"]
        leap_games.append({**game, **aggregate(game["groups"])})
    labels = {}
    with (Path(dataset) / "evaluation.csv").open() as f:
        for row in csv.DictReader(f):
            if row["game_id"] in packets:
                if row["game_id"] in labels: raise ValueError("Duplicate selected outcome")
                labels[row["game_id"]] = row
    rows, summary = compare_rows(observations["direct"], leap_games, labels, {gid: p["cutoff_utc"] for gid, p in packets.items()})
    return rows, summary, packets, group_records


def immutable_text(path, text):
    path = Path(path); data = text.encode()
    if path.exists():
        if path.read_bytes() != data: raise ValueError("Refusing to overwrite derived report: " + str(path))
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as f: f.write(data)


def results_csv(rows, packets):
    fields = ["game_id", "home", "away", "tipoff_utc", "cutoff_utc", "evidence_sha256", "outcome", "paired_eligible", *METHODS,
        "direct_status", "leap_status", "market_missing_reason", "outcome_missing_reason"]
    fields += [g + "_" + k for g in GROUPS for k in ("lr", "status", "sufficiency", "missing_reason")]
    fields += [m + "_" + k for m in METHODS for k in ("brier", "log_loss")]
    fields += [a + "_minus_" + b + "_brier" for a, b in COMPARISONS]
    buffer = io.StringIO(newline=""); writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n"); writer.writeheader()
    for r in rows:
        p = packets[r["game_id"]]
        row = {k: r[k] for k in fields if k in r}
        row.update(home=p["home"]["team_name"], away=p["away"]["team_name"], tipoff_utc=p["recorded_tipoff_utc"], cutoff_utc=p["cutoff_utc"])
        for group in r["groups"]:
            for key, source in (("lr", "likelihood_ratio"), ("status", "status"), ("sufficiency", "evidence_sufficiency"), ("missing_reason", "missing_reason")):
                row[group["group"] + "_" + key] = group[source]
        for m in METHODS:
            for metric in ("brier", "log_loss"): row[m + "_" + metric] = r["scores"][m][metric] if r["scores"][m] else None
        for a, b in COMPARISONS:
            key = a + "_minus_" + b
            row[key + "_brier"] = r["paired_score_differences"].get(key, {}).get("brier")
        writer.writerow(row)
    return buffer.getvalue()


def export_experiment(direct_run, leap_run, comparison, preflight, output, dataset=DEFAULT_DATA):
    direct_run, leap_run, comparison, output = map(Path, (direct_run, leap_run, comparison, output))
    # Reject reserved scope before reading forecast results or labels.
    for folder in (direct_run, leap_run):
        if json.loads((folder/"run.json").read_text())["subset"] != "development":
            raise ValueError("This analyzer never accesses reserved evaluation results")
    direct.verify_experiment(direct_run, dataset)
    leap.verify_experiment(leap_run, dataset)
    drun, records, dcomplete = direct.load_experiment(direct_run)
    lrun, games, lcomplete = leap.load_experiment(leap_run)
    for protected in (direct_run, leap_run, comparison, Path(drun["cache_directory"]), Path(lrun["cache_directory"])):
        leap.protect_paths(output, protected, dataset)
    before = json.loads(Path(preflight).read_text())
    plan = json.loads(PLAN_PATH.read_text())
    observations = {"schema_version": 1, "kind": "sanitized_development_50_derived_observations",
        "configs": {"direct": drun["config"], "leap": lrun["config"]}, "split_sha256": drun["split_sha256"],
        "frozen_leap_assets": lrun["frozen_assets"], "direct": [sanitize(r) for r in records],
        "leap": [{"game_id": g["game_id"], "evidence_sha256": g["evidence_sha256"], "groups": [sanitize(r) for r in g["groups"]]} for g in games]}
    rows, expected_summary, packets, group_records = reconstruct(observations, dataset)
    summary = json.loads((comparison/"summary.json").read_text())
    if rows != json.loads((comparison/"per_game.json").read_text()) or any(summary[k] != v for k, v in expected_summary.items()):
        raise ValueError("Original evaluator results do not reproduce")
    resources = {"direct": resource_summary(observations["direct"], set(before["methods"]["direct"]["new_request_sha256"])),
        "leap": resource_summary([r for g in observations["leap"] for r in g["groups"]], set(before["methods"]["leap"]["new_request_sha256"]))}
    if (dcomplete["paid_call_reservations"] > 45 or lcomplete["paid_call_reservations"] > 180 or
            sum(v["additional"]["estimated_cost_usd"] for v in resources.values()) > 10):
        raise ValueError("Additional inference exceeded authorized limits")
    details = diagnostics(rows, packets, group_records, plan)
    reproduction = {"inference_base_commit": before["git_commit"], "analysis_plan_sha256": digest(PLAN_PATH.read_bytes()),
        "private_raw_responses_included": False, "public_replay_scope": "derived observations, request identities, aggregation, scores, diagnostics; no private HTTP-byte authentication",
        "run_completion_sha256": {"direct": digest((direct_run/"completion.json").read_bytes()), "leap": digest((leap_run/"completion.json").read_bytes())},
        "new_paid_reservations": {"direct": dcomplete["paid_call_reservations"], "leap": lcomplete["paid_call_reservations"]},
        "additional_reserved_cost_usd": dcomplete["reserved_cost_usd"] + lcomplete["reserved_cost_usd"], "resources": resources}
    for name, value in {"observations.json": observations, "summary.json": summary, "per_game.json": rows,
            "diagnostics.json": details, "reproduction.json": reproduction, "preflight.json": before, "analysis_plan.json": plan}.items():
        immutable_json(output/name, value)
    immutable_text(output/"results.csv", results_csv(rows, packets))
    manifest = {"schema_version": 1, "kind": "evaluation_only_development_50", "files": {p.name: digest(p.read_bytes()) for p in sorted(output.iterdir())
        if p.is_file() and p.name not in ("manifest.json", "report.md")}}
    immutable_json(output/"manifest.json", manifest)
    return details, summary, reproduction


def replay(folder, dataset=DEFAULT_DATA):
    folder = Path(folder)
    manifest = json.loads((folder/"manifest.json").read_text())
    required = {"observations.json", "summary.json", "per_game.json", "diagnostics.json", "reproduction.json", "preflight.json", "analysis_plan.json", "results.csv"}
    if manifest["kind"] != "evaluation_only_development_50" or set(manifest["files"]) != required:
        raise ValueError("Invalid sanitized development manifest")
    for name, sha in manifest["files"].items():
        if digest((folder/name).read_bytes()) != sha: raise ValueError("Sanitized development artifact hash mismatch")
    plan = json.loads((folder/"analysis_plan.json").read_text())
    if plan != json.loads(PLAN_PATH.read_text()): raise ValueError("Descriptive analysis plan changed")
    obs = json.loads((folder/"observations.json").read_text())
    rows, summary, packets, groups = reconstruct(obs, dataset)
    saved = json.loads((folder/"summary.json").read_text())
    if any(saved[k] != v for k, v in summary.items()) or rows != json.loads((folder/"per_game.json").read_text()):
        raise ValueError("Saved scores do not reproduce")
    detail = diagnostics(rows, packets, groups, plan)
    if detail != json.loads((folder/"diagnostics.json").read_text()) or results_csv(rows, packets).encode() != (folder/"results.csv").read_bytes():
        raise ValueError("Derived development diagnostics/CSV do not reproduce")
    preflight = json.loads((folder/"preflight.json").read_text())
    for name, sha in preflight["frozen_assets"].items():
        if digest((ROOT/name).read_bytes()) != sha:
            raise ValueError("Preflight-frozen forecasting asset changed")
    reproduction = json.loads((folder/"reproduction.json").read_text())
    resources = {"direct": resource_summary(obs["direct"], set(preflight["methods"]["direct"]["new_request_sha256"])),
        "leap": resource_summary([r for g in obs["leap"] for r in g["groups"]], set(preflight["methods"]["leap"]["new_request_sha256"]))}
    if reproduction["resources"] != resources:
        raise ValueError("Saved usage/cost/latency do not reconcile with observations")
    if saved["provenance"]["evaluation_file_sha256"] != digest((Path(dataset)/"evaluation.csv").read_bytes()):
        raise ValueError("Outcome/market source file changed")
    return {"verified": True, "games": len(rows), "paired_games": detail["paired_n"], "network_calls": 0,
        "private_raw_reparse": False, "paired_scores": summary["paired"]["scores"]}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--direct-run", type=Path)
    p.add_argument("--leap-run", type=Path)
    p.add_argument("--comparison", type=Path)
    p.add_argument("--preflight", type=Path)
    p.add_argument("--output", type=Path)
    p.add_argument("--replay", type=Path)
    p.add_argument("--dataset", type=Path, default=DEFAULT_DATA)
    a = p.parse_args()
    if a.replay:
        if any((a.direct_run, a.leap_run, a.comparison, a.preflight, a.output)):
            p.error("Replay is read-only; do not combine with export arguments")
        result = replay(a.replay, a.dataset)
    else:
        if not all((a.direct_run, a.leap_run, a.comparison, a.preflight, a.output)):
            p.error("Export requires sealed runs, comparison, preflight and separate output")
        d, s, r = export_experiment(a.direct_run, a.leap_run, a.comparison, a.preflight, a.output, a.dataset)
        result = {"paired_n": d["paired_n"], "scores": s["paired"]["scores"], "resources": r["resources"]}
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
