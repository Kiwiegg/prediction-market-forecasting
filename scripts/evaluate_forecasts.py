#!/usr/bin/env python3
"""Evaluation-only label/market join, permitted only after a forecast run seals."""
import argparse
import csv
import io
import json
import math
from collections import Counter
from pathlib import Path

from direct_forecast import load_experiment, probability
from evidence_documents import canonical, digest
from forecast_split import DEFAULT_DATA, DEFAULT_SPLIT, immutable_json, load_split
from investigate_kalshi import timestamp

EPSILON = 1e-15


def brier(p, outcome):
    if type(outcome) is not int or outcome not in (0, 1):
        raise ValueError("Outcome must be binary")
    return (probability(p) - outcome) ** 2


def log_loss(p, outcome, epsilon=EPSILON):
    p = probability(p)
    if not 0 < epsilon < .5 or type(outcome) is not int or outcome not in (0, 1):
        raise ValueError("Invalid clipping epsilon or binary label")
    p = min(1 - epsilon, max(epsilon, p))
    return -math.log(p) if outcome else -math.log1p(-p)


def scores(rows, field):
    if not rows:
        return {"n": 0, "brier_score": None, "log_loss": None}
    return {"n": len(rows), "brier_score": sum(brier(r[field], r["outcome"]) for r in rows) / len(rows),
            "log_loss": sum(log_loss(r[field], r["outcome"]) for r in rows) / len(rows)}


def calibration(rows, field):
    buckets = [[] for _ in range(10)]
    for row in rows:
        buckets[min(9, int(probability(row[field]) * 10))].append(row)
    return [{"lower_inclusive": i / 10, "upper": (i + 1) / 10, "upper_inclusive": i == 9, "count": len(group),
        "mean_probability": sum(r[field] for r in group) / len(group) if group else None,
        "home_win_frequency": sum(r["outcome"] for r in group) / len(group) if group else None} for i, group in enumerate(buckets)]


def market_probability(row, cutoff):
    """Verify the exported preferred quote, without changing its selection rule."""
    if not row:
        return None, "evaluation_row_missing"
    if row.get("home_mapping_verified") != "True":
        return None, "home_market_mapping_unverified"
    if row.get("market_open_at_cutoff") != "True":
        return None, "market_not_open_at_cutoff"
    if row.get("preferred_quote_missing_reason"):
        return None, row["preferred_quote_missing_reason"]
    try:
        if row.get("cutoff_utc") and timestamp(row["cutoff_utc"]) != timestamp(cutoff):
            return None, "evaluation_cutoff_disagrees_with_evidence"
        p = probability(float(row["preferred_midpoint_price"]))
        bid, ask = float(row["preferred_quote_bid"]), float(row["preferred_quote_ask"])
        lag = float(row["preferred_quote_candle_end_lag_seconds"])
        actual_lag = timestamp(cutoff) - timestamp(row["preferred_quote_candle_end_utc"])
        if (not 0 < bid <= ask < 1 or not math.isfinite(lag) or not 0 <= lag <= 1200
                or abs(lag - actual_lag) > 1e-6 or abs(p - (bid + ask) / 2) > 1e-9):
            return None, "invalid_or_post_cutoff_preferred_quote"
        return p, None
    except (ValueError, KeyError, TypeError):
        return None, "preferred_quote_missing_or_invalid"


def evaluate_rows(records, labels, cutoffs):
    rows = []
    for record in records:
        gid = record["game_id"]
        source = labels.get(gid)
        outcome = int(source["home_yes_outcome"]) if (source and source.get("home_yes_outcome") in ("0", "1")
            and source.get("market_status") == "finalized" and source.get("home_mapping_verified") == "True") else None
        market, reason = market_probability(source, cutoffs[gid])
        row = {"game_id": gid, "evidence_sha256": record["evidence_sha256"], "forecast_status": record["status"],
            "home_win_probability": record["home_win_probability"], "outcome": outcome, "preferred_midpoint_price": market,
            "constant_probability": .5, "outcome_missing_reason": None if outcome is not None else "finalized_home_outcome_missing",
            "market_missing_reason": reason, "forecast_eligible": record["status"] == "success" and outcome is not None,
            "paired_eligible": record["status"] == "success" and outcome is not None and market is not None}
        for method, field in (("direct", "home_win_probability"), ("market", "preferred_midpoint_price"), ("constant", "constant_probability")):
            usable = outcome is not None and row[field] is not None
            row[method + "_brier"] = brier(row[field], outcome) if usable else None
            row[method + "_log_loss"] = log_loss(row[field], outcome) if usable else None
        for metric in ("brier", "log_loss"):
            row["direct_minus_market_" + metric] = row["direct_" + metric] - row["market_" + metric] if row["paired_eligible"] else None
        rows.append(row)
    forecast = [r for r in rows if r["forecast_eligible"]]
    paired = [r for r in rows if r["paired_eligible"]]
    summary = {"historical_interpretation": "Exploratory only: possible model memorization; no prompt/model tuning against evaluation subset.",
        "log_loss": {"base": "natural", "epsilon": EPSILON, "clipping_applies_only_to_log_loss": True},
        "market_rule": "Existing preferred YES quote midpoint, candle end at/before cutoff and lag <=1200 seconds; actual quote age unknown.",
        "coverage": {"planned": len(rows), "successful_responses": sum(r["forecast_status"] == "success" for r in rows),
            "failed_responses": sum(r["forecast_status"] == "failed" for r in rows),
            "not_attempted_budget": sum(r["forecast_status"] == "not_attempted_budget" for r in rows),
            "missing_outcomes": sum(r["outcome"] is None for r in rows), "eligible_forecasts": len(forecast),
            "forecast_coverage_fraction": sum(r["forecast_status"] == "success" for r in rows) / len(rows) if rows else None,
            "missing_or_invalid_markets": sum(r["preferred_midpoint_price"] is None for r in rows), "paired_games": len(paired)},
        "missingness_reasons": dict(Counter(r["market_missing_reason"] for r in rows if r["market_missing_reason"])),
        "forecast_available": {"game_ids": [r["game_id"] for r in forecast], "direct": scores(forecast, "home_win_probability"),
            "constant_50": scores(forecast, "constant_probability")},
        "paired": {"game_ids": [r["game_id"] for r in paired], "direct": scores(paired, "home_win_probability"),
            "kalshi": scores(paired, "preferred_midpoint_price"), "constant_50": scores(paired, "constant_probability"),
            "mean_direct_minus_market_brier": sum(r["direct_minus_market_brier"] for r in paired) / len(paired) if paired else None,
            "mean_direct_minus_market_log_loss": sum(r["direct_minus_market_log_loss"] for r in paired) / len(paired) if paired else None},
        "calibration_forecast_available": calibration(forecast, "home_win_probability"),
        "calibration_paired": {name: calibration(paired, field) for name, field in (
            ("direct", "home_win_probability"), ("kalshi", "preferred_midpoint_price"), ("constant_50", "constant_probability"))}}
    return rows, summary


def evaluate_experiment(folder, output, dataset=DEFAULT_DATA, split_path=DEFAULT_SPLIT,
                        authorize_evaluation=False, allow_mock=False):
    folder, output, dataset = Path(folder), Path(output), Path(dataset)
    # Check authorization before opening any probability/outcome records.
    initial = json.loads((folder / "run.json").read_text())
    if initial["subset"] == "evaluation" and not authorize_evaluation:
        raise ValueError("Reserved evaluation scoring requires --authorize-evaluation")
    if initial["method"] == "mock_constant" and not allow_mock:
        raise ValueError("Mock plumbing checks require --allow-mock; they are not LLM results")
    run, records, completion = load_experiment(folder)  # fails unless ALL inference records sealed
    split = load_split(split_path, dataset)
    if run["split_sha256"] != digest(canonical(split)):
        raise ValueError("Forecast split manifest differs")
    selected = split["run_order"][run["subset"]][:len(records)]
    if [r["game_id"] for r in records] != selected:
        raise ValueError("Forecast run did not follow the fixed subset order")
    for protected in (folder, dataset):
        if output.resolve() == protected.resolve() or output.resolve() in protected.resolve().parents or protected.resolve() in output.resolve().parents:
            raise ValueError("Evaluation output must be separate from forecasts and evidence")
    # This is the only module that reads this file. Nonselected IDs are skipped
    # before parsing labels/prices; the reserved subset is never summarized.
    labels = {}
    wanted = set(selected)
    with (dataset / "evaluation.csv").open() as f:
        for row in csv.DictReader(f):
            if row["game_id"] in wanted:
                if row["game_id"] in labels:
                    raise ValueError("Duplicate selected evaluation game")
                labels[row["game_id"]] = row
    snapshots = json.loads((dataset / "evidence_snapshot_manifest.json").read_text())["games"]
    bindings = {g["game_id"]: g for g in snapshots if g["game_id"] in wanted}
    if any(bindings.get(r["game_id"], {}).get("sha256") != r["evidence_sha256"] for r in records):
        raise ValueError("Forecast evidence differs from the frozen dataset")
    rows, summary = evaluate_rows(records, labels, {gid: g["cutoff_utc"] for gid, g in bindings.items()})
    summary.update(subset=run["subset"], method=run["method"], split_sha256=run["split_sha256"],
        forecast_completion_sha256=digest((folder / "completion.json").read_bytes()),
        evaluation_source_sha256=digest((dataset / "evaluation.csv").read_bytes()),
        evidence_manifest_sha256=digest((dataset / "evidence_snapshot_manifest.json").read_bytes()))
    # Complete scoring is derived before writing; outputs are immutable too.
    summary_bytes = canonical(summary) + b"\n"
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]) if rows else ["game_id"])
    writer.writeheader(); writer.writerows(rows)
    csv_bytes = buffer.getvalue().encode()
    if output.exists():
        if (not (output / "summary.json").exists() or (output / "summary.json").read_bytes() != summary_bytes
                or (output / "per_game.csv").read_bytes() != csv_bytes):
            raise ValueError("Refusing to overwrite evaluation outputs")
        return summary
    output.mkdir(parents=True, exist_ok=False)
    immutable_json(output / "summary.json", summary)
    with (output / "per_game.csv").open("xb") as f:
        f.write(csv_bytes)
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--forecast-run", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--dataset", type=Path, default=DEFAULT_DATA)
    p.add_argument("--split", type=Path, default=DEFAULT_SPLIT)
    p.add_argument("--authorize-evaluation", action="store_true")
    p.add_argument("--allow-mock", action="store_true")
    args = p.parse_args()
    result = evaluate_experiment(args.forecast_run, args.output, args.dataset, args.split, args.authorize_evaluation, args.allow_mock)
    print(json.dumps({k: result[k] for k in ("subset", "method", "coverage", "paired")}, indent=2))


if __name__ == "__main__":
    main()
