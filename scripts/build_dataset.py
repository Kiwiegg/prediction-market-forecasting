#!/usr/bin/env python3
"""Build a blinded, retrospective 2025-26 NBA dataset (stdlib, Python 3.10+)."""

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from decimal import InvalidOperation
from math import isfinite
from pathlib import Path
from statistics import median
from zoneinfo import ZoneInfo

from collect_team_sources import collect
from dataset_sources import SPORT, Sources, source_id
from investigate_kalshi import close, iso, midpoint, number, select_candle, select_trade, timestamp, write_csv
from team_evidence import extract_history, make_packet

SEED = "nba-2025-26-v1"
EASTERN = ZoneInfo("America/New_York")
ALIASES = {"NY": "NYK", "NO": "NOP", "SA": "SAS", "GS": "GSW", "UTAH": "UTA", "WSH": "WAS"}
MONTHS = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")
PREFERRED_QUOTE_MAX_LAG_SECONDS = 1200
QUOTE_LAGS = (60, 300, 900, PREFERRED_QUOTE_MAX_LAG_SECONDS)


def valid_quote(candle):
    """Parse observed quote closes; reject missing, malformed or nonfinite data."""
    try:
        bid, ask = close(candle, "yes_bid"), close(candle, "yes_ask")
        if bid is not None and ask is not None and bid.is_finite() and ask.is_finite() and 0 < bid <= ask < 1:
            return bid, ask
    except (InvalidOperation, ValueError, TypeError, AttributeError):
        pass
    return None


def select_quote(candles, target, max_lag_seconds=PREFERRED_QUOTE_MAX_LAG_SECONDS, strictly_before=False):
    """Latest valid observed candle within an inclusive lag bound; no imputation.

    Identical timestamp/quote duplicates agree. Conflicting valid quote closes at
    the latest eligible timestamp are ambiguous; do not choose by input order or
    retreat to an older timestamp to conceal that ambiguity.
    """
    if max_lag_seconds < 0:
        raise ValueError("Candle-end lag must be nonnegative")
    preceding, within, eligible = [], [], []
    for candle in candles:
        end = candle.get("end_period_ts")
        if isinstance(end, bool) or not isinstance(end, (int, float)) or not isfinite(end):
            continue
        lag = target - end
        if lag < 0 or (strictly_before and lag == 0):
            continue
        preceding.append(candle)
        if lag > max_lag_seconds:
            continue
        within.append(candle)
        quote = valid_quote(candle)
        if quote is not None:
            eligible.append((end, quote))
    if not eligible:
        return None, ("no_candle_at_or_before_cutoff" if not preceding else
                      "no_candle_within_lag_limit" if not within else "no_valid_two_sided_quote_within_lag_limit")
    latest = max(end for end, quote in eligible)
    quotes = {quote for end, quote in eligible if end == latest}
    if len(quotes) != 1:
        return None, "ambiguous_latest_valid_candle"
    bid, ask = quotes.pop()
    return {"end_period_ts": latest, "candle_end_lag_seconds": target - latest,
            "bid": bid, "ask": ask, "spread": ask - bid, "midpoint": (bid + ask) / 2}, None


def quote_fields(candles, target, market_open, request_ok):
    fields = {"preferred_quote_candle_end_utc": None, "preferred_quote_candle_end_lag_seconds": None,
              "preferred_quote_bid": None, "preferred_quote_ask": None, "preferred_quote_spread": None,
              "preferred_midpoint_price": None, "preferred_quote_actual_age_seconds": None,
              "preferred_quote_missing_reason": None,
              "earlier_quote_candle_end_utc": None, "earlier_quote_candle_end_lag_seconds": None,
              "earlier_quote_bid": None, "earlier_quote_ask": None, "earlier_quote_spread": None,
              "earlier_midpoint_price": None, "earlier_quote_missing_reason": None,
              **{f"quote_available_{lag // 60}m": False for lag in QUOTE_LAGS}}
    if not market_open or not request_ok:
        reason = "market_not_open_at_cutoff" if not market_open else "candle_request_failed"
        fields["preferred_quote_missing_reason"] = fields["earlier_quote_missing_reason"] = reason
        return fields
    for lag in QUOTE_LAGS:
        selected, _ = select_quote(candles, target, lag)
        fields[f"quote_available_{lag // 60}m"] = selected is not None
    for prefix, strictly_before in (("preferred", False), ("earlier", True)):
        quote, reason = select_quote(candles, target, PREFERRED_QUOTE_MAX_LAG_SECONDS, strictly_before)
        fields[prefix + "_quote_missing_reason"] = reason
        if quote is not None:
            fields.update({prefix + "_quote_candle_end_utc": iso(quote["end_period_ts"]),
                           prefix + "_quote_candle_end_lag_seconds": quote["candle_end_lag_seconds"],
                           prefix + "_quote_bid": quote["bid"], prefix + "_quote_ask": quote["ask"],
                           prefix + "_quote_spread": quote["spread"], prefix + "_midpoint_price": quote["midpoint"]})
    return fields


def price_comparisons(rows):
    """Paired descriptive price differences only, in probability points."""
    result = []
    pairs = (("preferred_minus_exact", "preferred_midpoint_price", "midpoint_price"),
             ("earlier_minus_exact", "earlier_midpoint_price", "midpoint_price"),
             ("preferred_minus_fresh_trade", "preferred_midpoint_price", "fresh_last_trade_price"),
             ("earlier_minus_fresh_trade", "earlier_midpoint_price", "fresh_last_trade_price"),
             ("exact_minus_fresh_trade", "midpoint_price", "fresh_last_trade_price"))
    for group_type, groups in (("all", {"all": rows}), ("month", {
            month: [r for r in rows if r["month"] == month] for month in sorted({r["month"] for r in rows})})):
        for group, part in groups.items():
            for name, left, right in pairs:
                differences = []
                for row in part:
                    a = row[left]
                    if right == "fresh_last_trade_price":
                        b = row["last_trade_price"] if row["fresh_last_trade_available"] else None
                    else:
                        b = row[right]
                    if a is not None and b is not None:
                        differences.append((number(a) - number(b)) * 100)
                absolute = [abs(d) for d in differences]
                result.append({"group_type": group_type, "group": group, "comparison": name,
                    "paired_games": len(differences),
                    "mean_signed_difference_pp": float(sum(differences) / len(differences)) if differences else None,
                    "mean_absolute_difference_pp": float(sum(absolute) / len(absolute)) if absolute else None,
                    "median_absolute_difference_pp": float(median(absolute)) if absolute else None,
                    "max_absolute_difference_pp": float(max(absolute)) if absolute else None})
    return result


def save_json(path, obj):
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")


def save_jsonl(path, rows):
    path.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))


def schedule_projection(event):
    """Selection can see only identities, dates, season/type and venue status."""
    comp = event["competitions"][0]
    teams = {t["homeAway"]: t for t in comp["competitors"]}
    local = datetime.fromtimestamp(timestamp(event["date"]), EASTERN)
    cup_final = str(comp["type"]["id"]) == "39"
    excluded_fixture = comp.get("status", {}).get("type", {}).get("name") in (
        "STATUS_POSTPONED", "STATUS_CANCELED", "STATUS_CANCELLED")
    row = {"game_id": str(event["id"]), "recorded_start_utc": iso(timestamp(event["date"])),
           "game_date": local.date().isoformat(), "month": local.strftime("%Y-%m"),
           "season_year": event["season"]["year"],
           "season_type": int(event["seasonType"]["type"]),
           "competition_type": str(comp["type"]["id"]),
           "excluded_fixture": excluded_fixture,
           "counts_in_regular_season": not cup_final and not excluded_fixture,
           "neutral_site": comp.get("neutralSite"),
           "time_valid": bool(event.get("timeValid") and comp.get("timeValid"))}
    for side in ("home", "away"):
        t = teams[side]["team"]
        row.update({side + "_id": str(t["id"]), side + "_name": t["displayName"],
                    side + "_code": ALIASES.get(t["abbreviation"], t["abbreviation"])})
    return row


def make_frame(boards):
    games = {}
    for team_id, board in enumerate(boards, 1):
        if str(board["team"]["id"]) != str(team_id):
            raise RuntimeError(f"Team schedule identity mismatch: {team_id}")
        key = source_id(f"{SPORT}/teams/{team_id}/schedule", {"season": 2026, "seasontype": 2})
        for event in board["events"]:
            if event.get("season", {}).get("year") != 2026:
                continue
            row = schedule_projection(event)
            if row["season_type"] != 2 or not ("2025-10-21" <= row["game_date"] <= "2026-04-12"):
                continue
            gid = row["game_id"]
            if gid in games:
                comparison = {k: v for k, v in games[gid].items() if k != "schedule_source_ids"}
                if comparison != row:
                    raise RuntimeError(f"Conflicting independent team schedules: {gid}")
                games[gid]["schedule_source_ids"].append(key)
            else:
                games[gid] = dict(row, schedule_source_ids=[key])
    rows = sorted(games.values(), key=lambda g: (g["recorded_start_utc"], g["game_id"]))
    regular = [g for g in rows if g["counts_in_regular_season"]]
    counts = Counter(t for g in regular for t in (g["home_id"], g["away_id"]))
    # Stop on an incomplete source frame instead of sampling whichever games loaded.
    if len(regular) != 1230 or len(counts) != 30 or set(counts.values()) != {82}:
        raise RuntimeError(f"Incomplete regular-season frame: games={len(regular)}, team counts={dict(counts)}")
    for row in rows:
        row["schedule_source_ids"].sort()
    return rows


def select_games(frame, maximum):
    eligible = [g for g in frame if g["counts_in_regular_season"]]
    groups = defaultdict(list)
    for game in eligible:
        groups[game["month"]].append(game)
    size = min(maximum, len(eligible))
    quotas = {m: size * len(g) // len(eligible) for m, g in groups.items()}
    leftovers = size - sum(quotas.values())
    order = sorted(groups, key=lambda m: (-(size * len(groups[m]) % len(eligible)), m))
    for month in order[:leftovers]:
        quotas[month] += 1
    selected = []
    for month in sorted(groups):
        ranked = sorted(groups[month], key=lambda g: (
            hashlib.sha256((SEED + "|" + g["game_id"]).encode()).hexdigest(), g["game_id"]))
        for game in ranked[:quotas[month]]:
            selected.append(dict(game, selection_hash=hashlib.sha256((SEED + "|" + game["game_id"]).encode()).hexdigest()))
    return sorted(selected, key=lambda g: (g["recorded_start_utc"], g["game_id"])), quotas


def event_ticker(game):
    day = datetime.fromisoformat(game["game_date"])
    return f"KXNBAGAME-{day.year % 100:02d}{MONTHS[day.month - 1]}{day.day:02d}{game['away_code']}{game['home_code']}"


def market_observation(api, game, markets, cutoff):
    event = event_ticker(game)
    ticker = event + "-" + game["home_code"]
    target = int(timestamp(game["recorded_start_utc"]) - 86400)
    row = {"game_id": game["game_id"], "game_date": game["game_date"], "month": game["month"],
           "recorded_tipoff_utc": game["recorded_start_utc"], "cutoff_utc": iso(target),
           "home_team_id": game["home_id"], "away_team_id": game["away_id"],
           "event_ticker": event, "home_yes_ticker": ticker,
           "schedule_source_ids": ";".join(game["schedule_source_ids"]),
           "schedule_asof_cutoff_verified": False, "schedule_sources_agree": None,
           "kalshi_recorded_start_utc": None, "milestone_updated_utc": None,
           "market_found": ticker in markets, "home_mapping_verified": False,
           "market_status": None, "home_yes_outcome": None, "settlement_utc": None,
           "settlement_value_dollars": None,
           "market_open_at_cutoff": None, "outcome_matches_history": None,
           "midpoint_price": None, "last_trade_price": None, "last_trade_utc": None,
           "last_trade_age_seconds": None, "last_trade_stale": None,
           "quote_bucket_end_utc": None, "quote_bucket_lag_seconds": None,
           "yes_bid": None, "yes_ask": None, "quote_update_age_seconds": None,
           "minute_rows": 0, "missing_minute_buckets": None,
           "trade_window_start_utc": None, "trade_query_complete": None,
           "point_in_time_verified": False, "fresh_last_trade_available": False,
           **quote_fields([], target, False, True)}
    flags = ["historical_schedule_version_unverified", "quote_update_age_unknown"]
    lineage = {"game_id": game["game_id"], "market_source_ids": [], "milestone_source_ids": []}
    ms_params = {"related_event_ticker": event, "limit": 100}
    milestones, ms_complete = api.pages("/milestones", ms_params, "milestones")
    lineage["milestone_source_ids"] = api.page_source_ids[source_id("/milestones", ms_params)]
    matches = [m for m in milestones if m.get("type") == "basketball_game"
               and event in m.get("related_event_tickers", [])]
    milestone = matches[0] if ms_complete and len(matches) == 1 else None
    if milestone:
        row["kalshi_recorded_start_utc"] = milestone["start_date"]
        row["milestone_updated_utc"] = milestone.get("last_updated_ts")
        row["schedule_sources_agree"] = timestamp(milestone["start_date"]) == target + 86400
        if not row["schedule_sources_agree"]:
            flags.append("recorded_start_disagreement")
    else:
        flags.append("milestone_missing_or_ambiguous")
    if not game["time_valid"]:
        flags.append("schedule_time_not_validated")
    market = markets.get(ticker)
    if market is None:
        flags.append("home_yes_market_missing")
        row["preferred_quote_missing_reason"] = row["earlier_quote_missing_reason"] = "home_yes_market_missing"
        row["flags"] = ";".join(flags)
        return row, lineage, []
    market, market_sources = market
    lineage["market_source_ids"] += market_sources
    row["market_status"] = market.get("status")
    row["settlement_utc"] = market.get("settlement_ts")
    row["home_mapping_verified"] = bool(milestone and
        market.get("custom_strike", {}).get("basketball_team") == milestone.get("details", {}).get("home_team_id"))
    if not row["home_mapping_verified"]:
        flags.append("home_team_identity_not_independently_verified")
        if milestone and market.get("custom_strike", {}).get("basketball_team"):
            flags.append("home_team_identity_conflict")
            row["preferred_quote_missing_reason"] = row["earlier_quote_missing_reason"] = "home_team_identity_conflict"
            row["flags"] = ";".join(flags)
            return row, lineage, []
    if market.get("result") in ("yes", "no") and market.get("status") == "finalized":
        row["home_yes_outcome"] = int(market["result"] == "yes")
        row["settlement_value_dollars"] = market.get("settlement_value_dollars")
    else:
        flags.append("market_outcome_unavailable")
    opened = timestamp(market["open_time"])
    closed = timestamp(market["close_time"])
    row["market_open_at_cutoff"] = opened <= target < closed
    if not row["market_open_at_cutoff"]:
        flags.append("market_not_open_at_cutoff")
    archived = market.get("settlement_ts") and timestamp(market["settlement_ts"]) < timestamp(cutoff["market_settled_ts"])
    candle_path = (f"/historical/markets/{ticker}/candlesticks" if archived
                   else f"/series/KXNBAGAME/markets/{ticker}/candlesticks")
    candle_params = {"start_ts": target - 7200, "end_ts": target, "period_interval": 1}
    response = api.get(candle_path, candle_params)
    lineage["candle_source_id"] = source_id(candle_path, candle_params)
    candles = response.get("candlesticks", []) if response else []
    row["minute_rows"] = len(candles)
    if response is None:
        flags.append("candle_request_failed")
    else:
        row["missing_minute_buckets"] = len(set(range(target - 7200, target + 1, 60)) -
                                              {c["end_period_ts"] for c in candles})
    candle = select_candle(candles, target)
    lag = target - candle["end_period_ts"] if candle else None
    row["quote_bucket_lag_seconds"] = lag
    if candle:
        row["quote_bucket_end_utc"] = iso(candle["end_period_ts"])
        row["yes_bid"], row["yes_ask"] = close(candle, "yes_bid"), close(candle, "yes_ask")
    if lag == 0 and row["market_open_at_cutoff"]:
        row["midpoint_price"] = midpoint(candle)
    if row["midpoint_price"] is None:
        flags.append("cutoff_midpoint_missing")
    row.update(quote_fields(candles, target, row["market_open_at_cutoff"], response is not None))
    if row["preferred_midpoint_price"] is None:
        flags.append("preferred_quote_missing")
    for prefix in ("preferred", "earlier"):
        if row[prefix + "_quote_candle_end_utc"] is not None:
            lineage[prefix + "_quote_candle_end_utc"] = row[prefix + "_quote_candle_end_utc"]
    # Earlier quotes retain their actual candle-end time. Trades remain separate.
    trade_start = target - 3600
    trade_path = "/historical/trades" if target < timestamp(cutoff["trades_created_ts"]) else "/markets/trades"
    trade_sources = []
    def trades_in_window(start):
        params = {"ticker": ticker, "min_ts": start, "max_ts": target, "limit": 1000}
        trades, complete = api.pages(trade_path, params, "trades")
        trade_sources.extend(api.page_source_ids[source_id(trade_path, params)])
        return trades, complete
    trades, complete = trades_in_window(trade_start)
    trade, tie = select_trade(trades, target)
    if trade is None and complete and not tie and opened <= target:
        trade_start = int(opened)
        trades, complete = trades_in_window(trade_start)
        trade, tie = select_trade(trades, target)
    row["trade_window_start_utc"] = iso(trade_start)
    row["trade_query_complete"] = complete
    lineage["trade_source_ids"] = trade_sources
    if not complete:
        flags.append("incomplete_trade_history")
        trade = None
    if tie:
        flags.append("ambiguous_latest_trade_timestamp")
    if trade and row["market_open_at_cutoff"]:
        price = number(trade["yes_price_dollars"])
        if 0 <= price <= 1:
            row["last_trade_price"] = price
            row["last_trade_utc"] = trade["created_time"]
            row["last_trade_age_seconds"] = round(target - timestamp(trade["created_time"]), 6)
            row["last_trade_stale"] = row["last_trade_age_seconds"] > 900
            lineage["selected_trade_id"] = trade["trade_id"]
    if row["last_trade_price"] is None:
        flags.append("last_trade_missing_in_queried_window")
    elif row["last_trade_stale"]:
        flags.append("last_trade_stale_over_15m")
    row["fresh_last_trade_available"] = row["last_trade_price"] is not None and row["last_trade_stale"] is False
    row["flags"] = ";".join(flags)
    normalized = [{"game_id": game["game_id"], "source_id": lineage["candle_source_id"],
                   "end_period_utc": iso(c["end_period_ts"]),
                   "yes_bid_close": close(c, "yes_bid"), "yes_ask_close": close(c, "yes_ask"),
                   "trade_close": close(c, "price")} for c in candles]
    return row, lineage, normalized


def discover_markets(api):
    markets = {}
    for path in ("/historical/markets", "/markets"):
        params, seen = {"series_ticker": "KXNBAGAME", "limit": 1000}, set()
        while True:
            result = api.get(path, params)
            if result is None or "markets" not in result:
                raise RuntimeError(f"Incomplete market discovery: {path}")
            key = source_id(path, params)
            for m in result["markets"]:
                if m["ticker"] in markets:
                    old, sources = markets[m["ticker"]]
                    # Prefer archived metadata for old markets, retain both source IDs.
                    sources.append(key)
                else:
                    markets[m["ticker"]] = (m, [key])
            cursor = result.get("cursor")
            if not cursor:
                break
            if cursor in seen:
                raise RuntimeError("Repeated market-discovery cursor")
            seen.add(cursor)
            params = dict(params, cursor=cursor)
    return markets


def coverage(rows):
    result = []
    for kind, key in (("date", "game_date"), ("month", "month")):
        for group in sorted({r[key] for r in rows}):
            part = [r for r in rows if r[key] == group]
            result.append({"group_type": kind, "group": group, "selected_games": len(part),
                "missing_market": sum(not r["market_found"] for r in part),
                "missing_outcome": sum(r["home_yes_outcome"] is None for r in part),
                "missing_midpoint": sum(r["midpoint_price"] is None for r in part),
                "preferred_midpoints": sum(r["preferred_midpoint_price"] is not None for r in part),
                "missing_preferred_midpoint": sum(r["preferred_midpoint_price"] is None for r in part),
                **{f"quote_coverage_{lag // 60}m": sum(r[f"quote_available_{lag // 60}m"] for r in part)
                   for lag in QUOTE_LAGS},
                "preferred_quote_missing_reasons": json.dumps(dict(sorted(Counter(
                    r["preferred_quote_missing_reason"] for r in part if r["preferred_midpoint_price"] is None).items())), sort_keys=True),
                "missing_last_trade": sum(r["last_trade_price"] is None for r in part),
                "stale_last_trade": sum(r["last_trade_stale"] is True for r in part),
                "fresh_last_trades": sum(r["fresh_last_trade_available"] for r in part),
                "missing_or_stale_last_trade": sum(not r["fresh_last_trade_available"] for r in part),
                "missing_home_record": sum(not r["home_record_available"] for r in part),
                "missing_away_record": sum(not r["away_record_available"] for r in part),
                "missing_home_recent": sum(not r["home_recent_available"] for r in part),
                "missing_away_recent": sum(not r["away_recent_available"] for r in part),
                "missing_home_rest": sum(not r["home_rest_available"] for r in part),
                "missing_away_rest": sum(not r["away_rest_available"] for r in part),
                "recorded_start_disagreement": sum(r["schedule_sources_agree"] is False for r in part),
                "schedule_asof_unverified": len(part)})
    return result


def run(args):
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    api = Sources(out, args.offline, reuse=[] if args.no_reuse else ["data/kalshi_nba_2025_26"])
    boards = collect(api, args.workers)
    frame = make_frame(boards)
    selected, quotas = select_games(frame, args.max_games)
    save_jsonl(out / "schedule_frame.jsonl", frame)
    manifest = {"schema_version": 1, "selection_seed": SEED, "maximum_games": args.max_games,
                "rule": "monthly largest-remainder proportional quotas; lowest SHA256(seed|ESPN game ID) within month",
                "quotas": quotas, "games": selected}
    # Lock identities before any market discovery/price/outcome requests or joins.
    path = out / "selection_manifest.json"
    if path.exists() and json.loads(path.read_text()) != manifest:
        raise RuntimeError("Selection changed; refusing to overwrite the locked manifest")
    save_json(path, manifest)
    print(f"LOCKED {len(selected)} games, monthly quotas {quotas}", flush=True)
    history = [extract_history(g, api.get(f"{SPORT}/summary", {"event": g["game_id"]}),
               source_id(f"{SPORT}/summary", {"event": g["game_id"]})) for g in frame]
    save_jsonl(out / "game_history.jsonl", history)
    packets, evidence_lineage = zip(*(make_packet(g, history) for g in selected))
    save_jsonl(out / "evidence_packets.jsonl", packets)
    save_jsonl(out / "evidence_lineage.jsonl", evidence_lineage)
    cutoff = api.get("/historical/cutoff")
    if not cutoff:
        raise RuntimeError("Missing Kalshi historical cutoff")
    markets = discover_markets(api)
    observations = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for i, result in enumerate(pool.map(lambda g: market_observation(api, g, markets, cutoff), selected), 1):
            observations.append(result)
            if i % 25 == 0:
                print(f"PROGRESS market observations {i}/{len(selected)}", flush=True)
    rows, market_lineage, candle_rows = [], [], []
    history_by_id = {h["game_id"]: h for h in history}
    for (row, lineage, candles), packet in zip(observations, packets):
        h = history_by_id[row["game_id"]]
        if row["home_yes_outcome"] is not None and h["home_won"] is not None:
            row["outcome_matches_history"] = row["home_yes_outcome"] == int(h["home_won"])
            if not row["outcome_matches_history"]:
                row["flags"] += ";outcome_disagreement_with_timestamped_history"
        for side in ("home", "away"):
            for field, feature in (("record", "regular_season_record"), ("recent", "recent_regular_season"),
                                   ("rest", "rest_at_cutoff")):
                row[side + "_" + field + "_available"] = feature in packet[side]
        rows.append(row)
        market_lineage.append(lineage)
        candle_rows.extend(candles)
    write_csv(out / "evaluation.csv", rows)
    if candle_rows:
        write_csv(out / "candle_observations.csv", candle_rows)
    save_jsonl(out / "market_lineage.jsonl", market_lineage)
    save_json(out / "market_metadata.json", [markets[event_ticker(g) + "-" + g["home_code"]][0]
              for g in selected if event_ticker(g) + "-" + g["home_code"] in markets])
    cover = coverage(rows)
    write_csv(out / "coverage.csv", cover)
    comparisons = price_comparisons(rows)
    write_csv(out / "price_comparisons.csv", comparisons)
    sources = [api.provenance(p.stem) for p in sorted(api.raw.glob("*.json"))]
    save_jsonl(out / "sources.jsonl", sources)
    summary = {"schema_version": 1, "frame_regular_season_games": sum(g["counts_in_regular_season"] for g in frame),
        "selected_games": len(rows), "selection_seed": SEED, "quotas": quotas,
        "outcomes": sum(r["home_yes_outcome"] is not None for r in rows),
        "midpoints": sum(r["midpoint_price"] is not None for r in rows),
        "preferred_midpoints": sum(r["preferred_midpoint_price"] is not None for r in rows),
        "preferred_quote_max_candle_end_lag_seconds": PREFERRED_QUOTE_MAX_LAG_SECONDS,
        "quote_coverage_by_max_candle_end_lag_seconds": {
            str(lag): sum(r[f"quote_available_{lag // 60}m"] for r in rows) for lag in QUOTE_LAGS},
        "preferred_quote_missing_reasons": dict(sorted(Counter(
            r["preferred_quote_missing_reason"] for r in rows if r["preferred_midpoint_price"] is None).items())),
        "fresh_last_trades": sum(r["fresh_last_trade_available"] for r in rows),
        "price_comparisons": [c for c in comparisons if c["group_type"] == "all"],
        "last_trades": sum(r["last_trade_price"] is not None for r in rows),
        "stale_last_trades": sum(r["last_trade_stale"] is True for r in rows),
        "freshness_threshold_seconds": 900, "historical_cutoff": cutoff,
        "source_requests": len(sources), "source_statuses": dict(Counter(s["http_status"] for s in sources)),
        "history_issues": dict(Counter(h["issue"] for h in history if h["issue"])),
        "schedule_disagreements": sum(r["schedule_sources_agree"] is False for r in rows),
        "schedule_asof_verified": 0, "point_in_time_verified": False,
        "flags": dict(Counter(f for r in rows for f in r["flags"].split(";"))),
        "features": {k: sum(r[k] for r in rows) for k in rows[0]
                     if k.endswith("_available") and k.startswith(("home_", "away_"))},
        "retrieved_from": min(s["retrieved_at_utc"] for s in sources),
        "retrieved_through": max(s["retrieved_at_utc"] for s in sources)}
    save_json(out / "summary.json", summary)
    write_report(out, summary, cover, rows)
    print(json.dumps(summary, indent=2), flush=True)


def write_report(out, s, cover, rows):
    monthly = [c for c in cover if c["group_type"] == "month"]
    lines = ["# Historical NBA dataset coverage", "",
        f"Selected {s['selected_games']} distinct games from a {s['frame_regular_season_games']}-game frame. "
        f"Outcomes: {s['outcomes']}; exact-cutoff midpoints: {s['midpoints']}; preferred midpoints: {s['preferred_midpoints']}; "
        f"last trades: {s['last_trades']}; fresh last trades: {s['fresh_last_trades']}; "
        f"last trades older than 15 minutes: {s['stale_last_trades']}.", "",
        f"Missing cutoff midpoints: {s['selected_games'] - s['midpoints']}; missing last-trade prices: "
        f"{s['selected_games'] - s['last_trades']}. Of the latter, "
        f"{s['flags'].get('ambiguous_latest_trade_timestamp', 0)} have conflicting prices at the same latest "
        "trade timestamp. No arbitrary ordering resolves those ties.", "",
        "These are retrospective reconstructions. Zero games have a verified as-of schedule version. "
        "Raw retrieval times, source event/publication clocks, and reconstructed assumptions are distinct. "
        "See the methodology in ../../reports/dataset_methodology.md.", "",
        "## Quote coverage and before/after comparison", "",
        f"The exact-cutoff calculation is retained at {s['midpoints']}/{s['selected_games']} "
        f"({100 * s['midpoints'] / s['selected_games']:.1f}%). The new preferred proxy covers "
        f"{s['preferred_midpoints']}/{s['selected_games']} ({100 * s['preferred_midpoints'] / s['selected_games']:.1f}%), "
        f"an increase of {s['preferred_midpoints'] - s['midpoints']} games over exact-cutoff coverage. "
        "The sample, original price calculations, outcomes, packets, and raw sources are preserved in place.", "",
        "| Observation / maximum candle-end lag | Games | Coverage |",
        "| --- | ---: | ---: |",
        f"| Exact-cutoff midpoint / 0 seconds (retained) | {s['midpoints']} | {100 * s['midpoints'] / s['selected_games']:.1f}% |"]
    for lag in QUOTE_LAGS:
        n = s["quote_coverage_by_max_candle_end_lag_seconds"][str(lag)]
        unit = "minute" if lag == 60 else "minutes"
        lines.append(f"| Valid quote / {lag // 60} {unit}{' (preferred)' if lag == PREFERRED_QUOTE_MAX_LAG_SECONDS else ''} | {n} | {100 * n / s['selected_games']:.1f}% |")
    lines += [f"| Fresh last trade / execution age <=15 minutes | {s['fresh_last_trades']} | {100 * s['fresh_last_trades'] / s['selected_games']:.1f}% |", "",
        "The quote sets for 1, 5, 15 and 20 minutes are nested. The preferred proxy selects the newest valid observed quote close "
        "ending at or before the cutoff, including the exact-cutoff candle where available. It does not project the "
        "selected candle to the cutoff. No trade fills a missing quote.", "",
        "**Candle-end lag is not actual quote age.** Saved historical candles expose period ends and OHLC quote levels, "
        "without reliable quote-update timestamps. A recent candle, unchanged prices, or zero trading volume cannot establish "
        "when the book last changed or that quotes were refreshed at the candle end. Actual quote age remains missing.", "",
        "## Market coverage and missingness by month", "",
        "Exact and quote columns count observed prices; missing/stale columns retain all selected games in their denominator.", "",
        "| Month | Selected | Exact | Quote <=1m | Quote <=5m | Quote <=15m | Preferred <=20m | Missing preferred | Fresh trade | Stale trade | Missing trade | Missing outcome | Start disagreements |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for c in monthly:
        lines.append(f"| {c['group']} | {c['selected_games']} | {c['selected_games'] - c['missing_midpoint']} | "
                     f"{c['quote_coverage_1m']} | {c['quote_coverage_5m']} | {c['quote_coverage_15m']} | {c['preferred_midpoints']} | "
                     f"{c['missing_preferred_midpoint']} | {c['fresh_last_trades']} | {c['stale_last_trade']} | "
                     f"{c['missing_last_trade']} | {c['missing_outcome']} | {c['recorded_start_disagreement']} |")
    lines += ["", "## Remaining missing observations", "",
        "Preferred-quote missing reasons: `" + json.dumps(s["preferred_quote_missing_reasons"], sort_keys=True) + "`. "
        "The saved two-hour windows bound this diagnosis; missing bars do not identify the exchange's reason for sparse output.", "",
        "| Date | Game ID | Reason | Nearest preceding returned candle-end lag (seconds) |",
        "| --- | --- | --- | ---: |"]
    for row in rows:
        if row["preferred_midpoint_price"] is None:
            lag = row["quote_bucket_lag_seconds"]
            lines.append(f"| {row['game_date']} | {row['game_id']} | {row['preferred_quote_missing_reason']} | {lag if lag is not None else 'missing'} |")
    lines += ["", f"Fresh trade coverage excludes {s['stale_last_trades']} observed trades older than 900 seconds "
        f"and {s['selected_games'] - s['last_trades']} missing/ambiguous latest prices. "
        "All observed stale trade values remain in evaluation.csv with their age and flag.", "",
        "## Paired price sensitivity", "",
        "Differences are left minus right in **percentage points**, computed only when both prices exist. "
        "Fresh trades require execution age <=900 seconds. These are descriptive price comparisons, not forecasting scores. "
        "The preferred/exact pair must agree wherever the exact quote is unambiguous. To measure temporal sensitivity "
        "without that tautology, the **earlier** diagnostic selects the newest valid candle strictly before the cutoff "
        "with lag <=1200 seconds, even when an exact quote exists. It is never substituted into the exact column. "
        "Pair counts differ because availability differs; comparisons are conditional on their paired samples.", "",
        "| Left minus right | Paired games | Mean signed pp | Mean absolute pp | Median absolute pp | Max absolute pp |",
        "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for c in s["price_comparisons"]:
        values = [f"{c[k]:.4f}" if c[k] is not None else "missing" for k in (
            "mean_signed_difference_pp", "mean_absolute_difference_pp", "median_absolute_difference_pp", "max_absolute_difference_pp")]
        lines.append(f"| {c['comparison']} | {c['paired_games']} | " + " | ".join(values) + " |")
    lines += ["", "All-season and monthly paired statistics are exported in price_comparisons.csv. "
        "No outcomes are used to compute these differences."]
    lines += ["", "## Missingness by selected game date", "",
              "H/A columns count missing features separately for home and away teams. All selected games remain in the denominator.", "",
              "| Date | Selected | Missing outcome | Missing exact | Missing preferred | Missing trade | Stale trade | Record H/A | Recent H/A | Rest H/A |",
              "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |"]
    for c in cover:
        if c["group_type"] == "date":
            lines.append(f"| {c['group']} | {c['selected_games']} | {c['missing_outcome']} | {c['missing_midpoint']} | "
                         f"{c['missing_preferred_midpoint']} | {c['missing_last_trade']} | {c['stale_last_trade']} | "
                         f"{c['missing_home_record']}/{c['missing_away_record']} | "
                         f"{c['missing_home_recent']}/{c['missing_away_recent']} | {c['missing_home_rest']}/{c['missing_away_rest']} |")
    lines += ["", "## Source and reconstruction limits", "",
        "* Verified in saved responses: identities, recorded schedule values, explicit End Game event timestamps/scores, "
        "game-specific recap publication/modification clocks, Kalshi settlement results and trade timestamps. "
        "This does not authenticate an unchanged historical payload or prove its first public availability.",
        "* Reconstructed: season records and last-five results, filtered by event and publication/update clocks before each cutoff. "
        "Unresolvable histories cause feature omission, not partial records presented as complete records.",
        "* Exact End Game/header score differences are retained as issues when both agree on the winner. "
        "Only the agreed W/L fact is used; exact points and margins are omitted. Missing completion/publication "
        "clocks can suppress later record/recent-form features for the affected teams.",
        "* Rest counts completed 24-hour periods since the latest reliably completed game AT the cutoff, including the Cup final. "
        "It is not a prediction of rest at tipoff. Ongoing or unresolved latest games cause omission.",
        "* Recorded home/away designation and neutral-site flag come from the retrospective schedule. "
        "No historical schedule version is asserted. Last-trade lookup starts with the prior hour and expands back to listing "
        "if no eligible trade is found. An empty response does not establish complete exchange archival retention.",
        "* Exact midpoints require a valid two-sided candle ending exactly at the cutoff. Preferred midpoints retain the "
        "most recent valid observed candle with end lag <=1200 seconds. This relaxes the period-boundary requirement, "
        "not the unknown true quote age; recent bars can contain old quote levels. No interpolation or trade fallback is used.",
        "* LLM-facing evidence_packets.jsonl contains only allowlisted schedule identities and historical team facts. "
        "Market prices, target outcomes, target scores and raw response links live outside that file.",
        "", "Source HTTP statuses: `" + json.dumps(s["source_statuses"], sort_keys=True) + "`. "
        "History extraction issues: `" + json.dumps(s["history_issues"], sort_keys=True) + "`.", ""]
    (out / "coverage_report.md").write_text("\n".join(lines))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="data/nba_2025_26")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--no-reuse", action="store_true", help="do not reuse the original feasibility study's responses")
    parser.add_argument("--max-games", type=int, choices=range(1, 201), default=200, metavar="1..200")
    run(parser.parse_args())
