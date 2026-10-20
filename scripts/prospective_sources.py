"""Bounded, captured prospective schedules, past-game facts and official PDFs."""

import json
import re
import urllib.parse
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser

from evidence_documents import DocumentStore
from historical_injuries import PREFIX, ET, parse_pdf
from injury_evidence import official_section
from investigate_kalshi import iso, timestamp
from team_evidence import EXTENDED_FEATURES, extract_history, team_facts

SPORT = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
NBA_SCHEDULES = ("https://cdn.nba.com/static/json/staticData/scheduleLeagueV2_1.json",
                 "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json")
ALIASES = {"GS": "GSW", "NY": "NYK", "SA": "SAS", "NO": "NOP", "UTAH": "UTA", "WSH": "WAS"}


def url(path, **params):
    return path + "?" + urllib.parse.urlencode(sorted(params.items()))


def allowed_source(value):
    return (value in NBA_SCHEDULES or value == SPORT + "/teams" or bool(re.fullmatch(re.escape(SPORT) +
        r"/(?:scoreboard\?dates=\d{8}&limit=1000|teams/\d+/schedule\?season=\d{4}&seasontype=2|summary\?event=\d+)", value))
        or bool(re.fullmatch(r"https://official\.nba\.com/nba-injury-report-\d{4}-\d{2}-season/", value))
        or bool(re.fullmatch(re.escape(PREFIX) + r"Injury-Report_\d{4}-\d{2}-\d{2}_\d{2}_\d{2}[AP]M\.pdf", value)))


class SourceSession:
    def __init__(self, folder, offline=True, max_requests=190, store=None):
        if offline and store is None:
            from pathlib import Path
            if not Path(folder).is_dir():
                raise RuntimeError("Missing offline public-source capture directory")
        self.store = store or DocumentStore(folder, offline, allowed_source)
        self.max_requests, self.used, self.records = max_requests, 0, []

    def get(self, value):
        if not allowed_source(value):
            raise ValueError("Unapproved schedule/history/injury URL")
        if self.used >= self.max_requests:
            raise ValueError("Public source request budget exhausted")
        self.used += 1
        meta, body = self.store.get(value)
        self.records.append(meta)
        return meta, body

    def json(self, value):
        meta, body = self.get(value)
        if meta["http_status"] != 200 or meta.get("truncated"):
            return meta, None
        try:
            return meta, json.loads(body)
        except (ValueError, UnicodeError):
            return meta, None


def event_projection(event):
    """Read identities and schedule metadata, never scores/records/odds/winners."""
    comp = event["competitions"][0]
    teams = {c["homeAway"]: c["team"] for c in comp["competitors"]}
    season = event.get("season", {})
    kind = event.get("seasonType", {}).get("type", season.get("type"))
    cup_final = str(comp.get("type", {}).get("id")) == "39"
    status = comp.get("status", event.get("status", {})).get("type", {})
    excluded = status.get("name") in {"STATUS_POSTPONED", "STATUS_CANCELED", "STATUS_CANCELLED"}
    start = timestamp(event["date"])
    day = datetime.fromtimestamp(start, ET)
    row = {"game_id": str(event["id"]), "recorded_start_utc": iso(start), "season_year": season.get("year"),
        "season_type": kind, "counts_in_regular_season": kind == 2 and not cup_final and not excluded,
        "excluded_fixture": excluded, "neutral_site": comp.get("neutralSite"), "game_date": day.date().isoformat(),
        "time_valid": event.get("timeValid", comp.get("timeValid", False)),
        "scheduled": status.get("name") == "STATUS_SCHEDULED" and not status.get("completed", False)}
    for side in ("home", "away"):
        team = teams[side]
        row.update({side + "_id": str(team["id"]), side + "_name": team["displayName"],
                    side + "_code": ALIASES.get(team["abbreviation"], team["abbreviation"])})
    return row


def nba_projection(document):
    result = []
    for day in document.get("leagueSchedule", {}).get("gameDates", []):
        for game in day.get("games", []):
            if not str(game.get("gameId", "")).startswith("002") or game.get("gameStatus") != 1:
                continue
            try:
                result.append({"nba_game_id": game["gameId"], "recorded_start_utc": iso(timestamp(game["gameDateTimeUTC"])),
                    "home_code": game["homeTeam"]["teamTricode"], "away_code": game["awayTeam"]["teamTricode"]})
            except (KeyError, TypeError, ValueError):
                continue
    return result


def discover(session, now, days=3):
    if type(days) is not int or not 1 <= days <= 7:
        raise ValueError("Discovery is bounded to 1–7 UTC dates")
    official, decisions = [], []
    for value in NBA_SCHEDULES:
        meta, doc = session.json(value)
        rows = nba_projection(doc) if isinstance(doc, dict) else []
        decisions.append({"url": value, "http_status": meta["http_status"], "source_id": meta["source_id"], "usable_games": len(rows)})
        if rows:
            official = rows
            break
    games = {}
    for offset in range(days):
        day = datetime.fromtimestamp(now, timezone.utc).date() + timedelta(days=offset)
        value = url(SPORT + "/scoreboard", dates=day.strftime("%Y%m%d"), limit=1000)
        meta, doc = session.json(value)
        decisions.append({"url": value, "http_status": meta["http_status"], "source_id": meta["source_id"]})
        if not isinstance(doc, dict):
            continue
        for event in doc.get("events", []):
            try:
                game = event_projection(event)
                if not game["scheduled"] or not game["time_valid"] or not game["counts_in_regular_season"] or timestamp(game["recorded_start_utc"]) <= now:
                    continue
                match = [g for g in official if g["home_code"] == game["home_code"] and g["away_code"] == game["away_code"]
                         and g["recorded_start_utc"] == game["recorded_start_utc"]]
                # When the NBA feed is usable, a conflict is not silently overridden.
                if official and len(match) != 1:
                    decisions.append({"game_id": game["game_id"], "reason": "NBA_ESPN_schedule_not_corroborated"})
                    continue
                game.update(schedule_source_ids=[meta["source_id"]], schedule_provider="NBA_corroborated_ESPN" if match else "ESPN_fallback",
                            nba_game_id=match[0]["nba_game_id"] if match else None)
                games[game["game_id"]] = game
            except (KeyError, TypeError, ValueError):
                decisions.append({"reason": "unusable_schedule_event", "event_id": event.get("id")})
    return sorted(games.values(), key=lambda g: (g["recorded_start_utc"], g["game_id"])), decisions


def collect_history(session, game, now):
    history, audit, complete = {}, [], {}
    for side in ("home", "away"):
        meta, board = session.json(url(SPORT + "/teams/" + game[side + "_id"] + "/schedule", season=game["season_year"], seasontype=2))
        rows = []
        try:
            if not board or str(board["team"]["id"]) != game[side + "_id"]:
                raise ValueError("team schedule missing or mismatched")
            rows = [event_projection(e) for e in board["events"] if e.get("season", {}).get("year") == game["season_year"]]
            target = [r for r in rows if r["game_id"] == game["game_id"]]
            if len(target) != 1 or any(target[0][f] != game[f] for f in ("home_id", "away_id", "recorded_start_utc")):
                raise ValueError("target not corroborated by team season schedule")
            complete[side] = True
        except (KeyError, TypeError, ValueError) as exc:
            complete[side] = False
            audit.append({"team_id": game[side + "_id"], "reason": str(exc), "source_id": meta["source_id"]})
        for row in rows if complete[side] else []:
            if row["season_type"] != 2 or row["game_id"] == game["game_id"] or timestamp(row["recorded_start_utc"]) >= now or row["excluded_fixture"]:
                continue
            if row["game_id"] in history:
                continue
            summary_meta, summary = session.json(url(SPORT + "/summary", event=row["game_id"]))
            fact = extract_history(row, summary, summary_meta["source_id"])
            if fact["available_by_utc"]:
                fact["available_by_utc"] = iso(max(timestamp(fact["available_by_utc"]), timestamp(summary_meta["retrieved_at_utc"])))
            history[row["game_id"]] = fact
            if fact["issue"]:
                audit.append({"game_id": row["game_id"], "source_id": summary_meta["source_id"], "reason": fact["issue"]})
    return {"history": list(history.values()), "complete": complete, "decisions": audit}


def statistical_sections(game, collected, cutoff, extended=True):
    sections, lineage = {}, {}
    for side in ("home", "away"):
        if collected["complete"].get(side):
            facts, refs = team_facts(game[side + "_id"], cutoff, collected["history"], game["game_id"], extended=extended)
        else:
            facts = {"omitted_features": [{"feature": feature, "reason": "prospective_season_schedule_unverified"}
                for feature in ["regular_season_record", "recent_regular_season", "rest_at_cutoff"] + (sorted(EXTENDED_FEATURES) if extended else [])]}
            refs = {}
        sections[side] = {"team_id": game[side + "_id"], "team_name": game[side + "_name"], "designation": side, **facts}
        lineage[side] = refs
    return sections, lineage


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = set()
    def handle_starttag(self, tag, attrs):
        value = dict(attrs).get("href", "")
        if tag == "a" and value.startswith(PREFIX) and allowed_source(value):
            self.urls.add(value)


def issue_from_url(value):
    text = value.rsplit("/", 1)[-1]
    stated = datetime.strptime(text, "Injury-Report_%Y-%m-%d_%I_%M%p.pdf")
    return stated.replace(tzinfo=ET).timestamp()


def collect_official(session, game, now, max_reports=8, use_team_catalog=False):
    if type(max_reports) is not int or not 0 <= max_reports <= 16:
        raise ValueError("Official report budget must be 0–16")
    year = int(game["season_year"]) - 1
    links, archive = set(), []
    # The preceding season's page can remain a rolling index; validate the PDF's
    # own issue/creation clocks and target matchup, never trust the page title.
    for start in (year, year - 1):
        value = f"https://official.nba.com/nba-injury-report-{start}-{str(start + 1)[-2:]}-season/"
        meta, body = session.get(value)
        archive.append(meta)
        if meta["http_status"] == 200 and not meta.get("truncated"):
            parser = Links()
            parser.feed(body.decode(errors="replace"))
            links.update(parser.urls)
    candidates = []
    for value in links:
        try:
            issue = issue_from_url(value)
            if now - 86400 <= issue <= now:
                candidates.append((issue, value))
        except ValueError:
            continue
    reports, decisions = {}, []
    names = {game[s + "_id"]: {game[s + "_name"]} for s in ("home", "away")}
    catalog = {}
    if use_team_catalog:
        meta, document = session.json(SPORT + "/teams")
        catalog = {"team_catalog_source_id": meta["source_id"]}
        try:
            all_teams = document["sports"][0]["leagues"][0]["teams"]
            mapped = {str(t["team"]["id"]): {t["team"]["displayName"]} for t in all_teams}
            if len(mapped) != 30 or any(not names[k].issubset(mapped.get(k, set())) for k in names):
                raise ValueError("Incomplete/mismatched NBA team catalog")
            names = mapped
        except (KeyError, TypeError, ValueError, IndexError):
            catalog["missing_reason"] = "official_team_mapping_catalog_unavailable"
            return {"reports": {}, "candidates": [], "archive": archive, **catalog}
    for labels in names.values():
        if "LA Clippers" in labels:
            labels.add("Los Angeles Clippers")
    for issue, value in sorted(candidates, reverse=True)[:max_reports]:
        meta, body = session.get(value)
        report = {"issue_utc": None, "creation_utc": None, "teams": [], "uncertainty_flags": [], "extractor": "unavailable"}
        try:
            if meta["http_status"] == 200 and body.startswith(b"%PDF") and not meta.get("truncated"):
                report = parse_pdf(body, issue, names)
        except Exception as exc:
            report["uncertainty_flags"].append("parse_failed:" + type(exc).__name__)
        # A live capture proves availability by retrieval; it does not prove first
        # publication. Require source issue/creation clocks to precede that bound.
        captured = timestamp(meta["retrieved_at_utc"])
        ok = bool(report["issue_utc"] and report["creation_utc"] and
                  timestamp(report["issue_utc"]) <= timestamp(report["creation_utc"]) <= captured)
        reports[meta["source_id"]] = {**report, **{k: meta[k] for k in ("source_id", "url", "body_sha256", "retrieved_at_utc")}}
        decisions.append({"source_id": meta["source_id"], "report_issue_utc": report["issue_utc"],
            "published_at_utc": iso(captured), "publication_supported": ok,
            "rejection_reason": None if ok else "unavailable_or_inconsistent_issue_creation_capture"})
        if ok:
            break
    return {"reports": reports, "candidates": decisions, "archive": archive, **catalog}


def official_at_snapshot(game, collected, cutoff):
    candidates = [c for c in collected["candidates"] if timestamp(c["published_at_utc"]) <= cutoff]
    section, lineage = official_section(game, {"reports": collected["reports"], "cutoff_candidates": {iso(cutoff): candidates}}, cutoff)
    section.update(collection_mode="prospective_official_capture", selection_scope="latest_eligible_among_captured_index_links_last_24h",
                   publication_verification="observed_public_capture_upper_bound" if section["report_source_id"] else "unavailable")
    lineage["policy"] = {"selection_scope": section["selection_scope"], "publication_bound": "actual PDF retrieval, not first publication"}
    if "team_catalog_source_id" in collected:
        lineage["team_mapping_source_id"] = collected["team_catalog_source_id"]
    if collected.get("missing_reason"):
        lineage["uncertainty_flags"].append(collected["missing_reason"])
        for side in ("home", "away"):
            section[side]["uncertainty_flags"].append(collected["missing_reason"])
    return section, lineage
