#!/usr/bin/env python3
"""Small, unauthenticated NBA market audit. Python 3.10+, standard library only."""

import argparse
import csv
import gzip
import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

BASE = "https://api.elections.kalshi.com/trade-api/v2"
ESPN = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
DATES = ("20251022", "20251201", "20260115", "20260315")
SERIES = "KXNBAGAME"
ALIASES = {"NY": "NYK", "NO": "NOP", "SA": "SAS", "GS": "GSW",
           "UTAH": "UTA", "WSH": "WAS"}


def timestamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def iso(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat().replace("+00:00", "Z")


def number(value):
    return None if value is None else Decimal(str(value))


def close(candle, side):
    obj = candle.get(side) or {}
    return number(obj.get("close_dollars", obj.get("close")))


def volume(candle):
    return number(candle.get("volume_fp", candle.get("volume")))


def select_candle(candles, target):
    # Never use a bucket that ends after the target, including one straddling it.
    eligible = [c for c in candles if c["end_period_ts"] <= target]
    return max(eligible, key=lambda c: c["end_period_ts"], default=None)


def midpoint(candle):
    if candle is None:
        return None
    bid, ask = close(candle, "yes_bid"), close(candle, "yes_ask")
    # Zero bids and dollar asks can be empty book sentinels, not tradable quotes.
    if bid is None or ask is None or not (0 < bid <= ask < 1):
        return None
    return (bid + ask) / 2


def select_trade(trades, target):
    eligible = [t for t in trades if timestamp(t["created_time"]) <= target
                and t.get("is_block_trade") is not True
                and number(t.get("yes_price_dollars")) is not None]
    if not eligible:
        return None, False
    latest = max(timestamp(t["created_time"]) for t in eligible)
    tied = [t for t in eligible if timestamp(t["created_time"]) == latest]
    # IDs do not establish execution order for conflicting equal-time trades.
    ambiguous = len({t["yes_price_dollars"] for t in tied}) > 1
    return (None if ambiguous else sorted(tied, key=lambda t: t["trade_id"])[0]), ambiguous


class Client:
    """Store response bytes, URLs, times and errors; replay without network."""

    def __init__(self, out, offline):
        self.raw = out / "raw"
        self.raw.mkdir(parents=True, exist_ok=True)
        self.offline = offline

    def get(self, path, params=None):
        url = path if path.startswith("https://") else BASE + path
        if params:
            url += "?" + urllib.parse.urlencode(sorted(params.items()))
        key = hashlib.sha256(url.encode()).hexdigest()
        meta_file = self.raw / (key + ".json")
        body_file = self.raw / (key + ".body.gz")
        if meta_file.exists():
            meta = json.loads(meta_file.read_text())
            body = gzip.decompress(body_file.read_bytes())
            if hashlib.sha256(body).hexdigest() != meta["body_sha256"]:
                raise RuntimeError(f"Response hash mismatch: {url}")
        else:
            if self.offline:
                raise RuntimeError(f"Not in saved evidence: {url}")
            attempts = []
            for attempt in range(4):
                started = iso(time.time())
                try:
                    req = urllib.request.Request(url, headers={"User-Agent": "nba-market-feasibility/1.0"})
                    with urllib.request.urlopen(req, timeout=35) as response:
                        body = response.read()
                        status = response.status
                        headers = {k: response.headers[k] for k in ("Date", "Content-Type")
                                   if k in response.headers}
                except urllib.error.HTTPError as exc:
                    body, status, headers = exc.read(), exc.code, {}
                except (urllib.error.URLError, TimeoutError, OSError) as exc:
                    body, status, headers = str(exc).encode(), 0, {}
                attempts.append({"started_at": started, "finished_at": iso(time.time()),
                                 "status": status})
                if status not in (0, 429, 500, 502, 503, 504) or attempt == 3:
                    break
                time.sleep(2 ** attempt)
            meta = {"url": url, "status": status, "headers": headers, "attempts": attempts,
                    "body_sha256": hashlib.sha256(body).hexdigest()}
            body_file.write_bytes(gzip.compress(body, mtime=0))
            meta_file.write_text(json.dumps(meta, indent=2) + "\n")
            print(f"GET {status} {url}", flush=True)
            time.sleep(0.12)
        if meta["status"] != 200:
            return None
        try:
            return json.loads(body)
        except (ValueError, UnicodeDecodeError):
            return None

    def pages(self, path, params, field):
        rows, seen = [], set()
        while True:
            response = self.get(path, params)
            if response is None or field not in response:
                return rows, False
            rows.extend(response[field])
            cursor = response.get("cursor")
            if not cursor:
                return rows, True
            if cursor in seen:
                raise RuntimeError(f"Repeated pagination cursor: {path}")
            seen.add(cursor)
            params = dict(params, cursor=cursor)


def write_csv(path, rows):
    if not rows:
        raise RuntimeError(f"No rows for {path}")
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def run(args):
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    api = Client(out, args.offline)
    series = api.get(f"/series/{SERIES}")
    cutoff = api.get("/historical/cutoff")
    if not series or not cutoff:
        raise RuntimeError("Cannot retrieve series or historical cutoff; see raw evidence")
    markets, complete = api.pages("/historical/markets", {"series_ticker": SERIES, "limit": 1000}, "markets")
    if not complete:
        raise RuntimeError("Incomplete archive discovery; see raw evidence")
    by_event = {}
    for market in markets:
        by_event.setdefault(market["event_ticker"], []).append(market)

    # A fixed calendar sample, chosen before inspecting prices or outcomes.
    # Five earliest ESPN games on each date; home-team YES gives 20 distinct games.
    manifest, samples, selected_metadata, candles_export, trades_export, failures = [], [], [], [], [], []
    for day in DATES:
        board = api.get(ESPN, {"dates": day, "limit": 100})
        if not board:
            raise RuntimeError(f"Missing schedule for {day}")
        games = sorted(board.get("events", []), key=lambda e: (e["date"], e["id"]))[:5]
        if len(games) != 5:
            raise RuntimeError(f"Expected at least five games on {day}")
        for game in games:
            comp = game["competitions"][0]
            teams = {c["homeAway"]: c for c in comp["competitors"]}
            home = ALIASES.get(teams["home"]["team"]["abbreviation"], teams["home"]["team"]["abbreviation"])
            away = ALIASES.get(teams["away"]["team"]["abbreviation"], teams["away"]["team"]["abbreviation"])
            date_code = datetime.strptime(day, "%Y%m%d").strftime("%y%b%d").upper()
            event = f"{SERIES}-{date_code}{away}{home}"
            ticker = f"{event}-{home}"
            manifest.append({"date": day, "espn_id": game["id"], "event_ticker": event,
                             "ticker": ticker, "selection": "home YES; first five by ESPN date,id"})
            market = next((m for m in by_event.get(event, []) if m["ticker"] == ticker), None)
            season = game["season"]
            if season.get("year") != 2026 or season.get("type") != 2:
                raise RuntimeError(f"Not 2025-26 regular season: {game['id']}")
            if not market or market.get("result") not in ("yes", "no") or market.get("status") != "finalized":
                failures.append({"ticker": ticker, "reason": "missing finalized binary market"})
                continue
            selected_metadata.append(market)
            milestones, milestones_complete = api.pages("/milestones", {
                "related_event_ticker": event, "limit": 100}, "milestones")
            matches = [m for m in milestones if m.get("type") == "basketball_game"
                       and event in m.get("related_event_tickers", [])]
            milestone = matches[0] if milestones_complete and len(matches) == 1 else None
            espn_start = timestamp(game["date"])
            kalshi_start = timestamp(milestone["start_date"]) if milestone else None
            agreement = kalshi_start is not None and kalshi_start == espn_start
            # ESPN is a separately labelled analysis anchor even if Kalshi disagrees.
            target = int(espn_start - 86400)
            opened = timestamp(market["open_time"])
            issues = ["schedule_as_known_at_target_unverified", "quote_update_age_unknown"]
            if milestone is None:
                issues.append("missing_or_ambiguous_milestone")
            elif not agreement:
                issues.append("schedule_source_disagreement")
            if not comp.get("timeValid"):
                issues.append("espn_time_not_validated")
            if milestone and market.get("custom_strike", {}).get("basketball_team") != milestone.get("details", {}).get("home_team_id"):
                raise RuntimeError(f"Home-team mapping mismatch: {ticker}")
            if opened > target:
                issues.append("market_not_open_at_target")

            # Save hourly pregame history (at most seven days), plus minute data at T.
            hour_start = max(int(opened), int(espn_start - 7 * 86400))
            minute_start = target - 2 * 3600
            hourly = api.get(f"/historical/markets/{ticker}/candlesticks", {
                "start_ts": hour_start, "end_ts": int(espn_start), "period_interval": 60})
            minute = api.get(f"/historical/markets/{ticker}/candlesticks", {
                "start_ts": minute_start, "end_ts": target, "period_interval": 1})
            hourly_c = hourly.get("candlesticks", []) if hourly else []
            minute_c = minute.get("candlesticks", []) if minute else []
            for interval, candles in ((60, hourly_c), (1, minute_c)):
                for c in candles:
                    candles_export.append({"ticker": ticker, "period_minutes": interval,
                        "end_period_ts": c["end_period_ts"], "end_period_utc": iso(c["end_period_ts"]),
                        "yes_bid_close": close(c, "yes_bid"), "yes_ask_close": close(c, "yes_ask"),
                        "trade_price_close": close(c, "price"), "volume": volume(c),
                        "eligible_at_target": c["end_period_ts"] <= target})
            if hourly is None:
                issues.append("hourly_request_failed")
            if minute is None:
                issues.append("minute_request_failed")
            elif not minute_c:
                issues.append("empty_minute_history_window")
            candle = select_candle(minute_c, target)
            mid = midpoint(candle)
            if mid is None:
                issues.append("no_valid_two_sided_quote_at_target")
            # A narrow quote need not have traded recently. Retrieve every trade page
            # in the last hour; expand only if empty, up to listing/24 hours before T.
            trades, trades_complete = api.pages("/historical/trades", {
                "ticker": ticker, "min_ts": target - 3600, "max_ts": target,
                "limit": 1000}, "trades")
            trade_window = target - 3600
            if not trades and trades_complete and opened <= target:
                trade_window = max(int(opened), target - 86400)
                trades, trades_complete = api.pages("/historical/trades", {
                    "ticker": ticker, "min_ts": trade_window, "max_ts": target,
                    "limit": 1000}, "trades")
            for t in trades:
                trades_export.append({"ticker": ticker, **t})
            trade, tie = select_trade(trades, target)
            if not trades_complete:
                issues.append("incomplete_trade_pagination")
                trade = None
            if tie:
                issues.append("conflicting_trades_at_same_latest_timestamp")
            if trade is None:
                issues.append("no_unambiguous_non_block_trade_in_window")
            age = target - timestamp(trade["created_time"]) if trade else None
            if age is not None and age > args.stale_seconds:
                issues.append("last_trade_stale")
            candle_lag = target - candle["end_period_ts"] if candle else None
            if candle_lag != 0:
                issues.append("no_minute_bucket_ending_at_target")
            if candle_lag is not None and candle_lag > 60:
                issues.append("quote_bucket_lag_exceeds_one_minute")
            # An estimate needs an on-time, valid book and matching recorded starts.
            usable = agreement and comp.get("timeValid") and opened <= target and candle_lag == 0
            probability = mid if usable else None
            home_won = teams["home"].get("winner")
            outcome_match = home_won is not None and (market["result"] == "yes") == home_won
            if not outcome_match:
                issues.append("outcome_disagreement_or_unverified")
            samples.append({
                "ticker": ticker, "event_ticker": event, "title": market["title"],
                "yes_team": market["yes_sub_title"], "status": market["status"],
                "result": market["result"], "yes_outcome": int(market["result"] == "yes"),
                "settlement_value_dollars": market.get("settlement_value_dollars"),
                "settlement_ts": market.get("settlement_ts"), "espn_id": game["id"],
                "season_year": season["year"], "season_type": season["type"],
                "outcome_matches_espn": outcome_match, "open_time": market["open_time"],
                "close_time": market["close_time"],
                "expected_expiration_time": market.get("expected_expiration_time"),
                "occurrence_datetime": market.get("occurrence_datetime"),
                "milestone_id": milestone["id"] if milestone else None,
                "kalshi_recorded_start_utc": iso(kalshi_start) if kalshi_start else None,
                "milestone_last_updated_ts": milestone.get("last_updated_ts") if milestone else None,
                "espn_recorded_start_utc": iso(espn_start),
                "schedule_sources_agree": agreement, "schedule_asof_target_verified": False,
                "analysis_target_utc": iso(target), "analysis_target_ts": target,
                "market_open_at_target": opened <= target,
                "hourly_candles": len(hourly_c), "minute_candles": len(minute_c),
                "missing_minute_buckets_in_window": len(set(range(minute_start, target + 1, 60)) -
                    {c["end_period_ts"] for c in minute_c}),
                "minute_null_trade_closes": sum(close(c, "price") is None for c in minute_c),
                "minute_zero_volume_buckets": sum(volume(c) == 0 for c in minute_c),
                "minute_window_start_utc": iso(minute_start),
                "quote_bucket_end_utc": iso(candle["end_period_ts"]) if candle else None,
                "quote_bucket_lag_seconds": candle_lag,
                "yes_bid": close(candle, "yes_bid") if candle else None,
                "yes_ask": close(candle, "yes_ask") if candle else None,
                "spread": (close(candle, "yes_ask") - close(candle, "yes_bid")) if mid is not None else None,
                "recorded_schedule_midpoint_p24h": probability,
                "quote_update_age_seconds": None,
                "point_in_time_verified_p24h": None,
                "trade_window_start_utc": iso(trade_window),
                "trade_history_complete_in_window": trades_complete,
                "last_trade_id": trade["trade_id"] if trade else None,
                "last_trade_utc": trade["created_time"] if trade else None,
                "last_trade_yes_price": trade["yes_price_dollars"] if trade else None,
                "last_trade_age_seconds": age,
                "last_trade_stale": age > args.stale_seconds if age is not None else None,
                "issues": ";".join(issues),
            })

    # Diagnostic probes: store success/empty/error responses, not just successful data.
    first = samples[0]
    api.get(f"/markets/{first['ticker']}")
    api.get(f"/events/{first['event_ticker']}")
    api.get(f"/historical/markets/{first['ticker']}")
    api.get(f"/series/{SERIES}/markets/{first['ticker']}/candlesticks", {
        "start_ts": first["analysis_target_ts"] - 7200,
        "end_ts": first["analysis_target_ts"], "period_interval": 1})
    api.get("https://cdn.nba.com/static/json/staticData/scheduleLeagueV2_1.json")
    # Deliberately retain a known schedule ambiguity outside the 20-game sample.
    api.get("/milestones", {"related_event_ticker": "KXNBAGAME-25OCT22SASDAL", "limit": 100})

    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (out / "market_metadata.json").write_text(json.dumps(selected_metadata, indent=2) + "\n")
    write_csv(out / "markets.csv", samples)
    write_csv(out / "candles.csv", candles_export)
    if trades_export:
        write_csv(out / "trades.csv", trades_export)
    issues = Counter(issue for row in samples for issue in row["issues"].split(";"))
    metadata = [json.loads(p.read_text()) for p in sorted(api.raw.glob("*.json"))]
    write_csv(out / "requests.csv", [{
        "url": m["url"], "status": m["status"],
        "retrieved_at": m["attempts"][-1]["finished_at"],
        "metadata_file": "raw/" + hashlib.sha256(m["url"].encode()).hexdigest() + ".json",
        "response_file": "raw/" + hashlib.sha256(m["url"].encode()).hexdigest() + ".body.gz",
        "body_sha256": m["body_sha256"],
    } for m in metadata])
    summary = {
        "series": series["series"], "historical_cutoff": cutoff,
        "sample_dates": DATES, "stale_threshold_seconds": args.stale_seconds,
        "discovered_archived_markets": len(markets),
        "sample_markets": len(samples), "distinct_games": len({s["event_ticker"] for s in samples}),
        "recorded_schedule_midpoints": sum(s["recorded_schedule_midpoint_p24h"] is not None for s in samples),
        "last_trade_prices": sum(s["last_trade_yes_price"] is not None for s in samples),
        "stale_last_trades": sum(s["last_trade_stale"] is True for s in samples),
        "point_in_time_verified_probabilities": 0,
        "candle_rows": len(candles_export), "trade_rows": len(trades_export),
        "issue_counts": dict(sorted(issues.items())), "selection_failures": failures,
        "missing_metadata_counts": {key: sum(s[key] is None for s in samples) for key in (
            "occurrence_datetime", "expected_expiration_time", "settlement_ts", "milestone_id")},
        "requests": len(metadata),
        "request_statuses": dict(Counter(str(m["status"]) for m in metadata)),
        "retrieved_from": min(m["attempts"][0]["started_at"] for m in metadata),
        "retrieved_through": max(m["attempts"][-1]["finished_at"] for m in metadata),
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({k: v for k, v in summary.items() if k != "series"}, indent=2))
    if len(samples) != 20 or failures:
        raise RuntimeError("Could not establish all 20 resolved markets; see selection_failures")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="data/kalshi_nba_2025_26")
    parser.add_argument("--offline", action="store_true", help="rebuild exports from saved responses only")
    parser.add_argument("--stale-seconds", type=int, default=900,
                        help="flag a last trade older than this many seconds (default: 900)")
    run(parser.parse_args())
