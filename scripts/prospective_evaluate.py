#!/usr/bin/env python3
"""Evaluation-only live quote capture, final-outcome capture and sealed scoring.

Never imported by the evidence/forecast orchestrator. Market records live in a
separate directory and are never passed to any model.
"""
import argparse
import json
import math
import time
from pathlib import Path

import prospective_study as study
from build_dataset import event_ticker
from evaluate_forecasts import brier, calibration, log_loss
from evidence_documents import canonical, digest
from forecast_split import immutable_json
from investigate_kalshi import BASE as MARKET_BASE, iso, timestamp
from prospective_sources import SPORT, url
from team_evidence import extract_history


def quote_record(game, market, milestones, retrieved):
    target = study.aware(game["recorded_start_utc"]) - 86400
    event = event_ticker(game); expected = event + "-" + game["home_code"]
    reason = None; bid = ask = None
    matches = []
    for m in milestones.get("milestones", []):
        try:
            if m.get("type") == "basketball_game" and event in m.get("related_event_tickers", []) and study.aware(m["start_date"]) == study.aware(game["recorded_start_utc"]): matches.append(m)
        except (ValueError, TypeError, KeyError, AttributeError): pass
    if not target - 300 <= retrieved <= target: reason = "quote_not_captured_in_pre_cutoff_five_minute_window"
    elif milestones.get("cursor") or len(matches) != 1: reason = "milestone_incomplete_or_ambiguous"
    elif (market.get("ticker") != expected or market.get("event_ticker") != event
            or not market.get("custom_strike", {}).get("basketball_team")
            or market.get("custom_strike", {}).get("basketball_team") != matches[0].get("details", {}).get("home_team_id")):
        reason = "home_yes_mapping_unverified"
    elif market.get("status") not in ("active", "open") or not market.get("open_time") or not market.get("close_time"):
        reason = "market_not_verifiably_open"
    else:
        try:
            if not study.aware(market["open_time"]) <= retrieved < study.aware(market["close_time"]): raise ValueError("Invalid market availability clock")
            bid, ask = float(market["yes_bid_dollars"]), float(market["yes_ask_dollars"])
            if not 0 < bid <= ask < 1 or not all(math.isfinite(v) for v in (bid, ask)): raise ValueError("Invalid quote")
        except (KeyError, ValueError, TypeError): reason = "missing_or_invalid_two_sided_dollar_quote"
    return {"game_id": game["game_id"], "game": game, "recorded_tipoff_utc": game["recorded_start_utc"], "ticker": expected,
        "target_cutoff_utc": iso(target), "retrieved_at_utc": iso(retrieved), "deviation_seconds": retrieved - target,
        "exact_cutoff_observation": retrieved == target, "eligible": reason is None, "missing_reason": reason,
        "yes_bid": bid if reason is None else None, "yes_ask": ask if reason is None else None,
        "spread": ask - bid if reason is None else None,
        "midpoint": (bid + ask) / 2 if reason is None else None, "actual_quote_age_seconds": None,
        "method": "live_market_metadata_best_two_sided_yes_quote", "historical_20_minute_candle_rule_changed": False}


def capture_market(game, output, now=None):
    if study.STOP.exists(): raise ValueError("Prior access denial blocks new live requests under this authorization")
    now = time.time() if now is None else now; study.game_guard(game, now)
    if now > timestamp(game["recorded_start_utc"]) - 86400: raise ValueError("Do not capture/backfill a benchmark after T−24h")
    output = Path(output); output.mkdir(parents=True, exist_ok=False)
    event = event_ticker(game); ticker = event + "-" + game["home_code"]
    market_url = MARKET_BASE + "/markets/" + ticker
    milestones_url = url(MARKET_BASE + "/milestones", limit=100, related_event_ticker=event)
    budget = study.PilotBudget(output)
    def guard():
        if time.time() > timestamp(game["recorded_start_utc"]) - 86400: raise study.Halt("Quote request missed cutoff; never backdate")
    store = study.OneShotDocuments(output / "raw", False, lambda u: u in (market_url, milestones_url), budget, guard=guard)
    mm, mb = store.get(milestones_url); qm, qb = store.get(market_url)
    if any(m["http_status"] != 200 or m["truncated"] for m in (mm, qm)): raise ValueError("Market source unavailable")
    record = quote_record(game, json.loads(qb).get("market", {}), json.loads(mb), timestamp(qm["retrieved_at_utc"]))
    immutable_json(output / "quote.json", record)
    immutable_json(output / "manifest.json", {str(p.relative_to(output)): digest(p.read_bytes()) for p in output.rglob("*") if p.is_file()})
    return record


def final_record(game, summary, retrieved):
    if retrieved <= timestamp(game["recorded_start_utc"]): raise ValueError("Outcomes are inaccessible before tipoff")
    header = summary.get("header", {}); comps = header.get("competitions", [])
    if str(header.get("id")) != game["game_id"] or len(comps) != 1: raise ValueError("Target outcome mapping mismatch")
    comp = comps[0]; status = comp.get("status", {}).get("type", {})
    if status.get("name") in ("STATUS_POSTPONED", "STATUS_CANCELED", "STATUS_CANCELLED"):
        return {"game_id": game["game_id"], "game": game, "retrieved_at_utc": iso(retrieved), "eligible": False, "reason": "postponed_or_canceled", "outcome": None}
    if not comp.get("date") or study.aware(comp["date"]) != study.aware(game["recorded_start_utc"]):
        return {"game_id": game["game_id"], "game": game, "retrieved_at_utc": iso(retrieved), "eligible": False, "reason": "rescheduled_or_schedule_unverified", "outcome": None}
    if "neutralSite" in comp and comp["neutralSite"] != game.get("neutral_site"):
        return {"game_id": game["game_id"], "game": game, "retrieved_at_utc": iso(retrieved), "eligible": False, "reason": "venue_conflict", "outcome": None}
    if not status.get("completed"): raise ValueError("Game is not final; evaluation is blocked")
    for field in (summary.get("article", {}).get("published"), summary.get("article", {}).get("lastModified"), summary.get("meta", {}).get("lastUpdatedAt")):
        study.aware(field)
    for play in summary.get("plays", []):
        if str(play.get("type", {}).get("id")) == "402": study.aware(play.get("wallclock"))
    fact = extract_history(game, summary, "prospective-final-outcome")
    if (fact["home_won"] is None or not fact["end_utc"] or not fact["available_by_utc"]
            or timestamp(fact["available_by_utc"]) > retrieved): raise ValueError("Final result lacks consistent identity/end/publication clocks")
    return {"game_id": game["game_id"], "game": game, "recorded_tipoff_utc": game["recorded_start_utc"], "eligible": True,
        "reason": None, "outcome": int(fact["home_won"]), "end_utc": fact["end_utc"],
        "source_available_by_utc": fact["available_by_utc"], "retrieved_at_utc": iso(retrieved)}


def capture_outcome(capture, output):
    verified = study.verify_forecasts(Path(capture) / "evidence", Path(capture) / "forecasts")
    if verified["run"]["mode"] != "prospective_live": raise ValueError("Mock forecasts cannot enter live evaluation")
    game = verified["run"]["game"]; now = time.time()
    if now <= timestamp(game["recorded_start_utc"]): raise ValueError("Do not retrieve target outcome before tipoff")
    if study.STOP.exists(): raise ValueError("Access-denial journal blocks new live requests")
    output = Path(output); output.mkdir(parents=True, exist_ok=False)
    endpoint = url(SPORT + "/summary", event=game["game_id"])
    store = study.OneShotDocuments(output / "raw", False, lambda u: u == endpoint, study.PilotBudget(output))
    meta, body = store.get(endpoint)
    if meta["http_status"] != 200 or meta["truncated"]: raise ValueError("Final source unavailable")
    record = final_record(game, json.loads(body), timestamp(meta["retrieved_at_utc"]))
    immutable_json(output / "outcome.json", record)
    immutable_json(output / "manifest.json", {str(p.relative_to(output)): digest(p.read_bytes()) for p in output.rglob("*") if p.is_file()})
    return record


def verify_source_capture(folder, field):
    folder = Path(folder); manifest = json.loads((folder / "manifest.json").read_text())
    for name, sha in manifest.items():
        path = (folder / name).resolve()
        if folder.resolve() not in path.parents or digest(path.read_bytes()) != sha: raise ValueError("Evaluation capture changed")
    if field + ".json" not in manifest: raise ValueError("Unsealed evaluation source")
    record = json.loads((folder / (field + ".json")).read_text()); game = record["game"]
    from evidence_documents import DocumentStore
    if field == "quote":
        event = event_ticker(game); endpoint = MARKET_BASE + "/markets/" + event + "-" + game["home_code"]
        ms_endpoint = url(MARKET_BASE + "/milestones", limit=100, related_event_ticker=event)
        store = DocumentStore(folder / "raw", True, lambda u: u in (endpoint, ms_endpoint))
        mm, mb = store.get(ms_endpoint); qm, qb = store.get(endpoint)
        if qm["http_status"] != 200 or mm["http_status"] != 200: raise ValueError("Missing valid market response")
        expected = quote_record(game, json.loads(qb).get("market", {}), json.loads(mb), timestamp(qm["retrieved_at_utc"]))
    else:
        endpoint = url(SPORT + "/summary", event=game["game_id"])
        meta, body = DocumentStore(folder / "raw", True, lambda u: u == endpoint).get(endpoint)
        if meta["http_status"] != 200: raise ValueError("Missing valid final response")
        expected = final_record(game, json.loads(body), timestamp(meta["retrieved_at_utc"]))
    if record != expected: raise ValueError("Evaluation data does not reproduce from original capture")
    return record


def score(capture, outcome_capture, market_capture=None, now=None):
    verified = study.verify_forecasts(Path(capture) / "evidence", Path(capture) / "forecasts")
    run, records, seal = verified["run"], verified["records"], verified["completion"]
    now = time.time() if now is None else now
    if run["mode"] != "prospective_live" or now <= timestamp(run["game"]["recorded_start_utc"]): raise ValueError("Postgame live evaluation only")
    if not seal["before_tipoff"] or not run["eligibility"]["eligible"]: raise ValueError("Off-time/incomplete/unsealed forecast is ineligible")
    outcome = verify_source_capture(outcome_capture, "outcome")
    if outcome["game_id"] != run["game"]["game_id"] or not study.same_schedule(outcome["game"], run["game"]): raise ValueError("Different outcome game or rescheduled fixture")
    if not outcome["eligible"]: return {"game_id": outcome["game_id"], "excluded": outcome["reason"]}
    if timestamp(outcome["retrieved_at_utc"]) > now or timestamp(outcome["end_utc"]) > now: raise ValueError("Future outcome capture")
    y = outcome["outcome"]; probabilities = {"direct": records["direct"]["home_win_probability"],
        **{k: v["home_win_probability"] for k, v in records["v2"]["variants"].items()},
        **{k.replace("leap_", "leap_v1_"): v["home_win_probability"] for k, v in records["v1"]["variants"].items()}, "constant_50": .5}
    if market_capture:
        q = verify_source_capture(market_capture, "quote")
        if q["game_id"] != run["game"]["game_id"] or q["recorded_tipoff_utc"] != run["game"]["recorded_start_utc"]: raise ValueError("Different market fixture")
        if q["eligible"] and not (timestamp(q["target_cutoff_utc"]) - 300 <= timestamp(q["retrieved_at_utc"]) <= timestamp(q["target_cutoff_utc"])): raise ValueError("Late benchmark cannot be substituted")
        probabilities["kalshi"] = q["midpoint"] if q["eligible"] else None
    else: probabilities["kalshi"] = None
    score_values = {m: {"brier": brier(p, y), "log_loss": log_loss(p, y)} if p is not None else None for m, p in probabilities.items()}
    primary = probabilities["direct"] is not None and probabilities["leap_v2_raw"] is not None
    return {"game_id": outcome["game_id"], "packet_sha256": run["packet_sha256"], "outcome": y,
        "primary_eligible": probabilities["direct"] is not None and probabilities["leap_v2_raw"] is not None,
        "market_paired_eligible": primary and probabilities["kalshi"] is not None,
        "seven_method_paired_eligible": all(v is not None for v in probabilities.values()),
        "primary_v2_minus_direct": {k: score_values["leap_v2_raw"][k] - score_values["direct"][k] for k in ("brier", "log_loss")} if primary else None,
        "probabilities": probabilities, "scores": score_values,
        "note": "One-game diagnostic; no study-level model selection or tuning. Primary paired Brier uses v2 raw minus direct."}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--capture-market", action="store_true"); p.add_argument("--capture-outcome", action="store_true")
    p.add_argument("--allow-network", action="store_true"); p.add_argument("--schedule", type=Path); p.add_argument("--game-id")
    p.add_argument("--capture", type=Path); p.add_argument("--outcome", type=Path); p.add_argument("--market", type=Path); p.add_argument("--output", type=Path)
    a = p.parse_args()
    if a.capture_market:
        if not a.allow_network or not a.schedule or not a.game_id or not a.output: p.error("Independent live benchmark needs --schedule --game-id --output --allow-network")
        from prospective_sources import SourceSession, discover
        d = json.loads((a.schedule / "discovery.json").read_text())
        games, _ = discover(SourceSession(a.schedule / "raw", True), d["started_at"], 3)
        matches = [g for g in games if g["game_id"] == a.game_id]
        if len(matches) != 1: p.error("Ambiguous/missing schedule game")
        result = capture_market(matches[0], a.output)
    elif a.capture_outcome:
        if not a.allow_network or not a.capture or not a.output: p.error("Final outcome capture needs --capture --output --allow-network")
        result = capture_outcome(a.capture, a.output)
    else:
        if a.allow_network or not a.capture or not a.outcome or not a.output: p.error("Scoring is offline and needs --capture --outcome --output")
        result = score(a.capture, a.outcome, a.market); immutable_json(a.output, result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__": main()
