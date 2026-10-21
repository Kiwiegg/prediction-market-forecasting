#!/usr/bin/env python3
"""Evaluation-only paired direct/LEAP/market comparison of sealed experiments."""
import argparse
import csv
import json
from collections import Counter
from itertools import combinations
from pathlib import Path

from direct_forecast import load_experiment as load_direct, verify_experiment as verify_direct
from evaluate_forecasts import EPSILON, brier, calibration, log_loss, market_probability, scores
from evidence_documents import canonical, digest
from forecast_split import DEFAULT_DATA, DEFAULT_SPLIT, immutable_json, load_split
from leap_evidence import GROUPS, VARIANTS, aggregate, frozen_assets, load_evidence
from leap_forecast import (PILOT, load_experiment as load_leap, verify_experiment as verify_leap,
    protect_paths, plan_experiment)

METHODS = ("direct", "leap_raw", "leap_conservative", "kalshi", "constant_50")


def compare_rows(direct, leap, labels, cutoffs):
    if [r["game_id"] for r in direct] != [r["game_id"] for r in leap]:
        raise ValueError("Methods must use identical ordered game IDs")
    rows = []
    for d, l in zip(direct, leap):
        gid = d["game_id"]
        if d["evidence_sha256"] != l["evidence_sha256"]:
            raise ValueError("Consumers did not receive identical frozen evidence")
        source = labels.get(gid)
        outcome = int(source["home_yes_outcome"]) if (source and source.get("home_yes_outcome") in ("0", "1")
            and source.get("market_status") == "finalized" and source.get("home_mapping_verified") == "True") else None
        market, reason = market_probability(source, cutoffs[gid])
        row = {"game_id": gid, "evidence_sha256": d["evidence_sha256"], "outcome": outcome,
            "direct": d["home_win_probability"] if d["status"] == "success" else None,
            **{v: l["variants"][v]["home_win_probability"] for v in VARIANTS}, "kalshi": market, "constant_50": .5,
            "direct_status": d["status"], "leap_status": l["status"], "market_missing_reason": reason,
            "outcome_missing_reason": None if outcome is not None else "finalized_verified_home_outcome_missing",
            "groups": [{k: r.get(k) for k in ("group", "status", "likelihood_ratio", "evidence_sufficiency", "extreme_lr",
                "missing_reason", "error", "request_sha256", "group_evidence_sha256", "usage", "estimated_cost_usd", "latency_seconds")}
                for r in l["groups"]], "group_log_likelihood_ratios": l["group_log_likelihood_ratios"],
            "variants": l["variants"]}
        row["paired_eligible"] = outcome is not None and all(row[m] is not None for m in METHODS)
        row["scores"] = {m: {"brier": brier(row[m], outcome), "log_loss": log_loss(row[m], outcome)}
            if row[m] is not None and outcome is not None else None for m in METHODS}
        row["paired_score_differences"] = {a + "_minus_" + b: {metric:
            row["scores"][a][metric] - row["scores"][b][metric] for metric in ("brier", "log_loss")}
            for a, b in combinations(METHODS, 2)} if row["paired_eligible"] else {}
        rows.append(row)
    paired = [r for r in rows if r["paired_eligible"]]
    differences = {a + "_minus_" + b: {metric: sum(r["paired_score_differences"][a + "_minus_" + b][metric]
        for r in paired) / len(paired) if paired else None for metric in ("brier", "log_loss")}
        for a, b in combinations(METHODS, 2)}
    loo = {}
    for variant in VARIANTS:
        loo[variant] = {}
        for group in GROUPS:
            subset = [{"outcome": r["outcome"], "p": r["variants"][variant]["leave_one_group_out"][group]["home_win_probability"]} for r in paired]
            loo[variant][group] = {**scores(subset, "p"), "same_paired_game_ids": [r["game_id"] for r in paired]}
    summary = {
        "interpretation": "Exploratory historical pilot; possible memorization, dependent uncalibrated LLM LRs; no skill claim or held-out tuning.",
        "log_loss": {"base": "natural", "epsilon": EPSILON},
        "market_rule": "Unchanged preferred two-sided YES midpoint; candle end <=cutoff and <=1200s lag, quote-refresh age unknown.",
        "coverage": {"planned": len(rows), "paired_games": len(paired),
            "available_probabilities": {m: sum(r[m] is not None for r in rows) for m in METHODS},
            "direct_status_counts": dict(Counter(r["direct_status"] for r in rows)),
            "leap_status_counts": dict(Counter(r["leap_status"] for r in rows)),
            "group_status_counts": dict(Counter(g["status"] for r in rows for g in r["groups"])),
            "missing_outcomes": sum(r["outcome"] is None for r in rows),
            "missing_markets": sum(r["kalshi"] is None for r in rows)},
        "exclusions": [{"game_id": r["game_id"], "direct_status": r["direct_status"], "leap_status": r["leap_status"],
            "market_missing_reason": r["market_missing_reason"], "outcome_missing_reason": r["outcome_missing_reason"]} for r in rows if not r["paired_eligible"]],
        "paired": {"game_ids": [r["game_id"] for r in paired], "scores": {m: scores(paired, m) for m in METHODS},
            "mean_score_differences": differences, "calibration": {m: calibration(paired, m) for m in METHODS}},
        "leave_one_group_out_same_intersection": loo}
    return rows, summary


def compare_experiments(direct_folder, leap_folder, output, dataset=DEFAULT_DATA, split_path=DEFAULT_SPLIT,
        authorize_evaluation=False, allow_mock=False):
    direct_folder, leap_folder, output, dataset = map(Path, (direct_folder, leap_folder, output, dataset))
    initial = [json.loads((p / "run.json").read_text()) for p in (direct_folder, leap_folder)]
    if any(r["subset"] == "evaluation" for r in initial) and not authorize_evaluation:
        raise ValueError("Reserved scoring requires separate --authorize-evaluation")
    if any("mock" in r["method"] for r in initial) and not allow_mock:
        raise ValueError("Mock comparison requires --allow-mock; not paid inference")
    verify_direct(direct_folder, dataset, split_path, authorize_evaluation)
    verify_leap(leap_folder, dataset, split_path, authorize_evaluation, cache_override=initial[1]["cache_directory"])
    d_run, direct, d_complete = load_direct(direct_folder)
    l_run, leap, l_complete = load_leap(leap_folder)
    split = load_split(split_path, dataset)
    if (d_run["subset"] != l_run["subset"] or d_run["split_sha256"] != l_run["split_sha256"]
            or l_run["split_sha256"] != digest(canonical(split))):
        raise ValueError("Experiment splits differ")
    if not any("mock" in r["method"] for r in (d_run, l_run)) and d_run["config"]["model"] != l_run["config"]["model"]:
        raise ValueError("Real direct/LEAP comparison requires the same underlying model")
    expected = split["run_order"][l_run["subset"]][:len(leap)]
    if [r["game_id"] for r in leap] != expected or [r["game_id"] for r in direct] != expected:
        raise ValueError("Both runs must follow the identical fixed subset prefix")
    for protected in (direct_folder, leap_folder, Path(d_run["cache_directory"]), Path(l_run["cache_directory"])):
        protect_paths(output, protected, dataset)
    # Only selected IDs are joined; no held-out outcomes/prices are parsed.
    labels = {}
    wanted = set(expected)
    with (dataset / "evaluation.csv").open() as f:
        for row in csv.DictReader(f):
            if row["game_id"] in wanted:
                if row["game_id"] in labels:
                    raise ValueError("Duplicate selected label")
                labels[row["game_id"]] = row
    bindings = {g["game_id"]: g for g in json.loads((dataset / "evidence_snapshot_manifest.json").read_text())["games"] if g["game_id"] in wanted}
    if any(bindings.get(r["game_id"], {}).get("sha256") != r["evidence_sha256"] for r in direct + leap):
        raise ValueError("Dataset evidence binding differs from forecast")
    rows, summary = compare_rows(direct, leap, labels, {gid: g["cutoff_utc"] for gid, g in bindings.items()})
    summary.update(subset=l_run["subset"], direct_method=d_run["method"], leap_method=l_run["method"],
        models={"direct": d_run["config"]["model"], "leap": l_run["config"]["model"]},
        split_sha256=l_run["split_sha256"], frozen_assets=l_run["frozen_assets"],
        provenance={"direct_completion_sha256": digest((direct_folder / "completion.json").read_bytes()),
            "leap_completion_sha256": digest((leap_folder / "completion.json").read_bytes()),
            "evaluation_file_sha256": digest((dataset / "evaluation.csv").read_bytes())},
        resources={"direct": {"reported_usage": {k: sum(r.get("usage", {}).get(k, 0) for r in direct if isinstance(r.get("usage"), dict))
            for k in ("input_tokens", "output_tokens")},
            "estimated_response_cost_usd": d_complete["estimated_response_cost_usd"],
            "summed_observation_latency_seconds": sum(r.get("latency_seconds") or 0 for r in direct),
            "new_calls_in_this_comparison": 0},
            "leap": {k: v for k, v in l_complete.items() if k not in ("files",)}})
    immutable_json(output / "summary.json", summary)
    immutable_json(output / "per_game.json", rows)
    return summary


def replay_sanitized(folder, dataset=DEFAULT_DATA, split_path=DEFAULT_SPLIT):
    """Public derived-artifact arithmetic replay; does not reparse private HTTP."""
    folder, dataset = Path(folder), Path(dataset)
    manifest = json.loads((folder / "manifest.json").read_text())
    required = {"summary.json", "per_game.json", "observations.json"}
    if (manifest.get("kind") != "evaluation_only_development_pilot" or set(manifest["files"]) != required
            or manifest.get("provider_raw_responses_included") is not False):
        raise ValueError("Only the sanitized development pilot is supported")
    for name, sha in manifest["files"].items():
        if digest((folder / name).read_bytes()) != sha:
            raise ValueError("Sanitized report hash mismatch")
    observations = json.loads((folder / "observations.json").read_text())
    saved_rows = json.loads((folder / "per_game.json").read_text())
    saved_summary = json.loads((folder / "summary.json").read_text())
    if ([g["game_id"] for g in observations["games"]] != PILOT or [g["game_id"] for g in saved_rows] != PILOT
            or observations["frozen_assets"] != frozen_assets() or saved_summary["subset"] != "development"):
        raise ValueError("Sanitized replay is restricted to the frozen five development games")
    plan, specs = plan_experiment(dataset, split_path, observations["config"], limit=5)
    if plan["split_sha256"] != observations["split_sha256"]:
        raise ValueError("Sanitized split differs")
    direct, leap, cutoffs = [], [], {}
    for saved, game in zip(saved_rows, observations["games"]):
        packet = load_evidence(dataset, game["game_id"])
        sha = packet["evidence_snapshot_sha256"]
        if sha != game["evidence_sha256"] or sha != saved["evidence_sha256"]:
            raise ValueError("Sanitized evidence differs from the unchanged dataset")
        cutoffs[game["game_id"]] = packet["cutoff_utc"]
        groups = game["groups"]
        for r, s in zip(groups, [s for s in specs if s["game_id"] == game["game_id"]]):
            if any(r[k] != s[k] for k in ("group", "evidence_sha256", "group_evidence_sha256", "usable", "missing_reason")) or r["request_sha256"] != s["key"]:
                raise ValueError("Sanitized request/group hash differs")
        aggregated = aggregate(groups)
        if aggregated["variants"] != saved["variants"]:
            raise ValueError("Sanitized posteriors do not reproduce")
        leap.append({**game, **aggregated})
        direct.append({"game_id": game["game_id"], "evidence_sha256": sha,
            "status": saved["direct_status"], "home_win_probability": saved["direct"]})
    labels = {}
    with (dataset / "evaluation.csv").open() as f:
        for row in csv.DictReader(f):
            if row["game_id"] in PILOT:
                if row["game_id"] in labels:
                    raise ValueError("Duplicate selected label")
                labels[row["game_id"]] = row
    rows, summary = compare_rows(direct, leap, labels, cutoffs)
    if rows != saved_rows or any(saved_summary[k] != v for k, v in summary.items()):
        raise ValueError("Sanitized scores/contributions do not reproduce")
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--direct-run", type=Path)
    p.add_argument("--leap-run", type=Path)
    p.add_argument("--output", type=Path)
    p.add_argument("--replay-sanitized", type=Path, help="Read-only public five-game arithmetic replay, without private provider bodies")
    p.add_argument("--dataset", type=Path, default=DEFAULT_DATA)
    p.add_argument("--split", type=Path, default=DEFAULT_SPLIT)
    p.add_argument("--authorize-evaluation", action="store_true")
    p.add_argument("--allow-mock", action="store_true")
    a = p.parse_args()
    if a.replay_sanitized:
        if a.direct_run or a.leap_run or a.output or a.authorize_evaluation or a.allow_mock:
            p.error("Sanitized replay is read-only and restricted to the development pilot")
        r = replay_sanitized(a.replay_sanitized, a.dataset, a.split)
        print(json.dumps({"verified": True, "kind": "sanitized_arithmetic_replay", "private_raw_reparse": False,
            "games": r["coverage"]["planned"], "network_calls": 0, "paired_scores": r["paired"]["scores"]}, indent=2)); return
    if not a.direct_run or not a.leap_run or not a.output:
        p.error("Specify both sealed runs and a separate output directory")
    r = compare_experiments(a.direct_run, a.leap_run, a.output, a.dataset, a.split, a.authorize_evaluation, a.allow_mock)
    print(json.dumps({"coverage": r["coverage"], "paired_scores": r["paired"]["scores"]}, indent=2))


if __name__ == "__main__":
    main()
