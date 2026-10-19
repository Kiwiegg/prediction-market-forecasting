#!/usr/bin/env python3
"""Build a blinded, retrospective 2025-26 NBA dataset (stdlib, Python 3.10+)."""

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from collect_team_sources import collect
from dataset_sources import SPORT, Sources, source_id
from investigate_kalshi import close, iso, midpoint, number, select_candle, select_trade, timestamp, write_csv
from team_evidence import extract_history, make_packet

SEED = "nba-2025-26-v1"
EASTERN = ZoneInfo("America/New_York")
ALIASES = {"NY": "NYK", "NO": "NOP", "SA": "SAS", "GS": "GSW", "UTAH": "UTA", "WSH": "WAS"}
MONTHS = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")


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
           "point_in_time_verified": False}
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
    # Do not carry a prior candle to T. Trade observations have their own clock.
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
                "missing_last_trade": sum(r["last_trade_price"] is None for r in part),
                "stale_last_trade": sum(r["last_trade_stale"] is True for r in part),
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
        raise RuntimeError("Selection changed; use a new output directory rather than overwrite the locked manifest")
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
    sources = [api.provenance(p.stem) for p in sorted(api.raw.glob("*.json"))]
    save_jsonl(out / "sources.jsonl", sources)
    summary = {"schema_version": 1, "frame_regular_season_games": sum(g["counts_in_regular_season"] for g in frame),
        "selected_games": len(rows), "selection_seed": SEED, "quotas": quotas,
        "outcomes": sum(r["home_yes_outcome"] is not None for r in rows),
        "midpoints": sum(r["midpoint_price"] is not None for r in rows),
        "last_trades": sum(r["last_trade_price"] is not None for r in rows),
        "stale_last_trades": sum(r["last_trade_stale"] is True for r in rows),
        "freshness_threshold_seconds": 900, "historical_cutoff": cutoff,
        "source_requests": len(sources), "source_statuses": dict(Counter(s["http_status"] for s in sources)),
        "history_issues": dict(Counter(h["issue"] for h in history if h["issue"])),
        "schedule_disagreements": sum(r["schedule_sources_agree"] is False for r in rows),
        "schedule_asof_verified": 0, "point_in_time_verified": False,
        "flags": dict(Counter(f for r in rows for f in r["flags"].split(";"))),
        "features": {k: sum(r[k] for r in rows) for k in rows[0] if k.endswith("_available")},
        "retrieved_from": min(s["retrieved_at_utc"] for s in sources),
        "retrieved_through": max(s["retrieved_at_utc"] for s in sources)}
    save_json(out / "summary.json", summary)
    write_report(out, summary, cover)
    print(json.dumps(summary, indent=2), flush=True)


def write_report(out, s, cover):
    monthly = [c for c in cover if c["group_type"] == "month"]
    lines = ["# Historical NBA dataset coverage", "",
        f"Selected {s['selected_games']} distinct games from a {s['frame_regular_season_games']}-game frame. "
        f"Outcomes: {s['outcomes']}; cutoff midpoints: {s['midpoints']}; last trades: {s['last_trades']}; "
        f"last trades older than 15 minutes: {s['stale_last_trades']}.", "",
        f"Missing cutoff midpoints: {s['selected_games'] - s['midpoints']}; missing last-trade prices: "
        f"{s['selected_games'] - s['last_trades']}. Of the latter, "
        f"{s['flags'].get('ambiguous_latest_trade_timestamp', 0)} have conflicting prices at the same latest "
        "trade timestamp. No arbitrary ordering resolves those ties.", "",
        "These are retrospective reconstructions. Zero games have a verified as-of schedule version. "
        "Raw retrieval times, source event/publication clocks, and reconstructed assumptions are distinct. "
        "See the methodology in ../../reports/dataset_methodology.md.", "",
        "| Month | Selected | Missing outcome | Missing midpoint | Missing trade | Stale trade | Missing home/away record | Missing home/away recent | Missing home/away rest | Start disagreements |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- | --- | --- | ---: |"]
    for c in monthly:
        lines.append(f"| {c['group']} | {c['selected_games']} | {c['missing_outcome']} | {c['missing_midpoint']} | "
                     f"{c['missing_last_trade']} | {c['stale_last_trade']} | {c['missing_home_record']}/{c['missing_away_record']} | "
                     f"{c['missing_home_recent']}/{c['missing_away_recent']} | {c['missing_home_rest']}/{c['missing_away_rest']} | "
                     f"{c['recorded_start_disagreement']} |")
    lines += ["", "## Missingness by selected game date", "",
              "H/A columns count missing features separately for home and away teams. All selected games remain in the denominator.", "",
              "| Date | Selected | Missing outcome | Missing midpoint | Missing trade | Stale trade | Record H/A | Recent H/A | Rest H/A |",
              "| --- | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |"]
    for c in cover:
        if c["group_type"] == "date":
            lines.append(f"| {c['group']} | {c['selected_games']} | {c['missing_outcome']} | {c['missing_midpoint']} | "
                         f"{c['missing_last_trade']} | {c['stale_last_trade']} | {c['missing_home_record']}/{c['missing_away_record']} | "
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
        "* Midpoints require a valid two-sided candle ending exactly at the cutoff. No carry-forward or substitution is used. "
        "Quote-update age is unknown. Stale trades remain stored and flagged.",
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
