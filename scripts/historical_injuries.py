"""Deterministic official-only historical injury evidence; no search/model tools."""

import argparse
import io
import json
import re
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from evidence_documents import DocumentStore
from investigate_kalshi import iso, timestamp, write_csv

ARCHIVE = "https://official.nba.com/nba-injury-report-2025-26-season/"
PREFIX = "https://ak-static.cms.nba.com/referee/injury/"
ET = ZoneInfo("America/New_York")
EXTRACTOR = "pypdf-6.21.1-coordinate-columns-v1"
STATUSES = {"Out", "Doubtful", "Questionable", "Probable", "Available"}
HISTORY_POLICY = {"approved_archive": ARCHIVE, "approved_pdf_prefix": PREFIX,
    "candidate_interval_minutes": 15, "lookback_hours": 4,
    "max_candidates_per_cutoff": 17, "latest_report_globally_verified": False,
    "publication_policy": "matching_issue_and_creation_clocks_plus_official_origin_last_modified",
    "independent_historical_public_capture_verified": False,
    "limitation": "Historical index unavailable; latest is only among the bounded approved candidates. "
                  "Origin object timestamps support prior existence, not an independently captured public posting."}


def approved_url(url):
    return url == ARCHIVE or bool(re.fullmatch(re.escape(PREFIX) + r"Injury-Report_\d{4}-\d{2}-\d{2}_\d{2}_\d{2}[AP]M\.pdf", url))


def normalized(text):
    return re.sub(r"[^a-z0-9]", "", text.lower())


def report_url(issue):
    local = datetime.fromtimestamp(issue, ET)
    return PREFIX + local.strftime("Injury-Report_%Y-%m-%d_%I_%M%p.pdf")


def candidate_issues(cutoff):
    # This is a documented probe grid, not an assertion that every report exists.
    local = datetime.fromtimestamp(cutoff, ET)
    latest = local.replace(minute=local.minute // 15 * 15, second=0, microsecond=0)
    for i in range(HISTORY_POLICY["max_candidates_per_cutoff"]):
        yield latest.timestamp() - i * 900


def pdf_lines(body):
    from pypdf import PdfReader, mult
    reader = PdfReader(io.BytesIO(body))
    pages = []
    for page in reader.pages:
        fragments = []
        def visit(text, cm, tm, font, size):
            text = " ".join(text.split())
            if text:
                matrix = mult(tm, cm)
                fragments.append((matrix[4], matrix[5], text))
        page.extract_text(visitor_text=visit)
        groups = []
        for x, y, text in sorted(fragments, key=lambda v: (-v[1], v[0])):
            group = next((g for g in groups if abs(g[0] - y) < 1.2), None)
            if group is None:
                group = [y, []]
                groups.append(group)
            group[1].append((x, text))
        pages.append([(y, sorted(parts)) for y, parts in groups])
    creation = reader.metadata.creation_date if reader.metadata else None
    return pages, iso(creation.timestamp()) if creation and creation.tzinfo else None


def parse_pdf(body, expected_issue, team_names):
    """Column coordinates preserve team/game context and wrapped injury reasons."""
    pages, creation = pdf_lines(body)
    result = {"extractor": EXTRACTOR, "issue_utc": None, "creation_utc": creation,
              "teams": [], "uncertainty_flags": [], "unresolved_reason_fragments": []}
    if not pages:
        result["uncertainty_flags"].append("empty_pdf")
        return result
    header = next((" ".join(text for x, text in parts) for y, parts in pages[0]
                   if "Injury" in " ".join(t for x, t in parts) and "Report" in " ".join(t for x, t in parts)), "")
    match = re.search(r"(\d{2}/\d{2}/\d{2})\s+(\d{2}:\d{2})\s+([AP]M)", header)
    if not match:
        result["uncertainty_flags"].append("unrecognized_issue_header")
        return result
    stated = datetime.strptime(" ".join(match.groups()), "%m/%d/%y %I:%M %p")
    # Resolve any DST fold with the independently zoned creation timestamp.
    issues = {stated.replace(tzinfo=ET, fold=fold).timestamp() for fold in (0, 1)}
    valid = [t for t in issues if creation and 0 <= timestamp(creation) - t <= 1800]
    if len(valid) != 1 or abs(valid[0] - expected_issue) > 1:
        result["uncertainty_flags"].append("issue_creation_or_url_clock_mismatch")
        return result
    result["issue_utc"] = iso(valid[0])
    anchors = None
    for y, parts in pages[0]:
        words = {text: x for x, text in parts}
        if all(k in words for k in ("Matchup", "Team", "Player", "Current", "Reason")):
            anchors = [words[k] - 2 for k in ("Matchup", "Team", "Player", "Current", "Reason")]
            break
    if anchors is None:
        result["uncertainty_flags"].append("unrecognized_table_columns")
        return result
    names = {normalized(name): tid for tid, labels in team_names.items() for name in labels}
    current_date = current_match = current_team = None
    sections = {}
    last_player = None
    for page_number, lines in enumerate(pages, 1):
        preceding_page_player = last_player
        page_players, page_reasons = [], []
        for y, parts in lines:
            full = " ".join(t for x, t in parts)
            if "Injury" in full and "Report" in full or re.match(r"Page\s+\d+\s+of", full):
                continue
            if "Matchup" in full and "Player" in full:
                continue
            columns = [[], [], [], [], [], []]
            for x, text in parts:
                col = sum(x >= anchor for anchor in anchors)
                columns[col].append(text)
            date_time, matchup, team, player, status, reason = [" ".join(c) for c in columns]
            if reason and "NOT YET SUBMITTED" not in full.upper():
                page_reasons.append((y, reason))
            day = re.search(r"\d{2}/\d{2}/\d{4}", date_time)
            if day:
                current_date = datetime.strptime(day.group(), "%m/%d/%Y").date().isoformat()
            if re.fullmatch(r"[A-Z]{2,3}@[A-Z]{2,3}", matchup):
                current_match, current_team, last_player = matchup, None, None
            elif matchup:
                result["uncertainty_flags"].append(f"unparsed_matchup_page_{page_number}")
                current_team = None
            if team:
                current_team = names.get(normalized(team))
                last_player = None
                if current_team is None:
                    result["uncertainty_flags"].append("unrecognized_team:" + team)
            if current_team is None or current_date is None or current_match is None:
                continue
            key = (current_date, current_match, current_team)
            section = sections.setdefault(key, {"game_date": current_date, "matchup": current_match,
                "team_id": current_team, "state": "reported", "players": [], "uncertainty_flags": []})
            if "NOT YET SUBMITTED" in full.upper():
                section["state"] = "not_yet_submitted"
                last_player = None
            elif player:
                if "," not in player:
                    section["uncertainty_flags"].append("unparsed_player_row")
                    last_player = None
                    continue
                last_player = {"player": player, "status": status if status in STATUSES else "ambiguous",
                    "status_raw": status, "reason": None, "page": page_number,
                    "uncertainty_flags": [] if status in STATUSES else ["unrecognized_status"]}
                section["players"].append(last_player)
                page_players.append((y, last_player))
            elif status:
                section["uncertainty_flags"].append("unattached_status")
        # Multi-line reason cells are vertically centred relative to the player
        # baseline: a first reason line can precede that player's name. Assign by
        # nearest row geometry rather than attaching it to the previous player.
        for y, reason in page_reasons:
            if not page_players:
                result["uncertainty_flags"].append("unattached_reason")
                result["unresolved_reason_fragments"].append({"page": page_number, "text": reason})
                if preceding_page_player:
                    preceding_page_player["uncertainty_flags"].append("reason_incomplete_at_page_boundary")
                continue
            distances = [(abs(y - py), player) for py, player in page_players]
            closest = min(d for d, p in distances)
            owners = [p for d, p in distances if abs(d - closest) < .01]
            if len(owners) != 1 or closest > 20:
                result["uncertainty_flags"].append("ambiguous_reason_geometry")
                result["unresolved_reason_fragments"].append({"page": page_number, "text": reason})
                if preceding_page_player and y > max(py for py, p in page_players):
                    preceding_page_player["uncertainty_flags"].append("reason_incomplete_at_page_boundary")
                else:
                    for d, player in distances:
                        if abs(d - closest) < .01:
                            player["uncertainty_flags"].append("reason_extraction_ambiguous")
                continue
            owner = owners[0]
            owner["reason"] = " ".join(filter(None, (owner["reason"], reason)))
    result["teams"] = list(sections.values())
    return result


def publication_decision(meta, report, cutoff):
    """Official origin upload time is distinct from issue/creation/retrieval clocks."""
    if meta["http_status"] != 200 or meta.get("truncated"):
        return False, None, "document_unavailable"
    if not report.get("issue_utc") or not report.get("creation_utc"):
        return False, None, "issue_or_creation_clock_unresolved"
    try:
        modified = parsedate_to_datetime(meta["headers"]["last-modified"])
        if modified.tzinfo is None:
            raise ValueError("unbounded publication timezone")
        published = modified.timestamp()
    except (KeyError, TypeError, ValueError):
        return False, None, "official_publication_timestamp_unavailable"
    issue, created = timestamp(report["issue_utc"]), timestamp(report["creation_utc"])
    if not issue <= created <= published:
        return False, iso(published), "publication_clocks_conflict"
    if max(issue, created, published) > cutoff:
        return False, iso(published), "published_after_cutoff"
    return True, iso(published), None


def latest_eligible(reports, cutoff):
    eligible = [r for r in reports if r.get("publication_supported") and
                timestamp(r["published_at_utc"]) <= cutoff and timestamp(r["report_issue_utc"]) <= cutoff]
    return max(eligible, key=lambda r: (timestamp(r["report_issue_utc"]), timestamp(r["published_at_utc"])), default=None)


def collect_injuries(output, games, offline=True, workers=4):
    output = Path(output)
    store = DocumentStore(output / "injury_raw", offline, approved_url)
    archive_meta, _ = store.get(ARCHIVE)
    team_names = defaultdict(set)
    for game in games:
        for side in ("home", "away"):
            team_names[game[side + "_id"]].add(game[side + "_name"])
    # Official reports use both spellings across seasons.
    for tid, labels in team_names.items():
        if "LA Clippers" in labels:
            labels.add("Los Angeles Clippers")
    parsed, attempts = {}, {}
    cutoffs = sorted({int(timestamp(g["recorded_start_utc"]) - 86400) for g in games})
    def at_cutoff(cutoff):
        tried = []
        for issue in candidate_issues(cutoff):
            url = report_url(issue)
            meta, body = store.get(url)
            key = meta["source_id"]
            # Different games/cutoffs can share a source. Parsing is pure and cached
            # in the final normalized map; raw captures never change.
            report = {"extractor": EXTRACTOR, "issue_utc": None, "creation_utc": None,
                      "teams": [], "uncertainty_flags": []}
            if meta["http_status"] == 200 and body.startswith(b"%PDF"):
                try:
                    report = parse_pdf(body, issue, team_names)
                except Exception as exc:
                    report["uncertainty_flags"].append("pdf_extraction_failed:" + type(exc).__name__)
            ok, published, reason = publication_decision(meta, report, cutoff)
            parsed[key] = {"source_id": key, "url": url, "body_sha256": meta["body_sha256"],
                "retrieved_at_utc": meta["retrieved_at_utc"], "http_status": meta["http_status"],
                "origin_last_modified": meta["headers"].get("last-modified"), **report}
            tried.append({"source_id": key, "candidate_issue_utc": iso(issue),
                "report_issue_utc": report["issue_utc"], "published_at_utc": published,
                "publication_supported": ok, "rejection_reason": reason})
            if ok:
                break
        attempts[iso(cutoff)] = tried
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for i, _ in enumerate(pool.map(at_cutoff, cutoffs), 1):
            if i % 20 == 0:
                print(f"INJURY CUTOFFS {i}/{len(cutoffs)}", flush=True)
    bundle = {"policy": HISTORY_POLICY, "archive_source_id": archive_meta["source_id"],
              "archive_http_status": archive_meta["http_status"],
              "reports": dict(sorted(parsed.items())), "cutoff_candidates": dict(sorted(attempts.items()))}
    (output / "injury_extractions.json").write_text(json.dumps(bundle, sort_keys=True, indent=2) + "\n")
    return bundle


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="data/nba_2025_26")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    games = json.loads((Path(args.output) / "selection_manifest.json").read_text())["games"]
    collect_injuries(args.output, games, args.offline, args.workers)
