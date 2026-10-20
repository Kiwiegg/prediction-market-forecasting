"""Historical injury enrichment, audit lineage and coverage. No live search path."""

import json
from collections import Counter
from pathlib import Path

from historical_injuries import HISTORY_POLICY, latest_eligible
from investigate_kalshi import iso, timestamp, write_csv
from shared_evidence import freeze_packet


def official_section(game, bundle, cutoff=None):
    cutoff = timestamp(game["recorded_start_utc"]) - 86400 if cutoff is None else cutoff
    candidates = bundle["cutoff_candidates"].get(iso(cutoff), [])
    chosen = latest_eligible(candidates, cutoff)
    official = {"collection_mode": "historical_approved_official_only",
        "publication_verification": "unavailable", "report_source_id": None, "report_url": None,
        "report_issue_utc": None, "published_at_utc": None,
        "independent_historical_public_capture_verified": False,
        "latest_report_globally_verified": False, "selection_scope": "four_hour_quarter_hour_candidate_grid"}
    report = bundle["reports"][chosen["source_id"]] if chosen else None
    if chosen:
        official.update(publication_verification="official_origin_object_timestamp",
            report_source_id=chosen["source_id"], report_url=report["url"],
            report_issue_utc=chosen["report_issue_utc"], published_at_utc=chosen["published_at_utc"])
    audit = {"game_id": game["game_id"], "cutoff_utc": iso(cutoff), "policy": HISTORY_POLICY,
        "candidate_decisions": candidates, "selected_source_id": chosen["source_id"] if chosen else None,
        "extraction_method": report["extractor"] if report else None,
        "extraction_model": None, "extraction_prompt": None, "extraction_response": None,
        "source_retrieved_at_utc": report["retrieved_at_utc"] if report else None,
        "source_sha256": report["body_sha256"] if report else None,
        "uncertainty_flags": report["uncertainty_flags"] if report else ["no_eligible_report_retrieved_in_bounded_scope"]}
    matchup = game["away_code"] + "@" + game["home_code"]
    for side in ("home", "away"):
        team_id = game[side + "_id"]
        matches = [t for t in report["teams"] if t["team_id"] == team_id
                   and t["matchup"] == matchup and t["game_date"] == game["game_date"]] if report else []
        team = {"team_id": team_id, "state": "unavailable", "players": [], "uncertainty_flags": []}
        if len(matches) == 1:
            source = matches[0]
            team.update(state=source["state"], uncertainty_flags=list(source["uncertainty_flags"]))
            if source["uncertainty_flags"] or source["state"] == "not_yet_submitted" and source["players"]:
                team["state"] = "ambiguous"
                team["uncertainty_flags"].append("team_rows_ambiguous")
            team["players"] = [{**player, "source_ref": report["source_id"] + ":page:" + str(player["page"])}
                               for player in source["players"]]
        else:
            team["uncertainty_flags"] = ["no_eligible_report_retrieved_in_bounded_scope" if not report
                                         else "target_team_game_absent" if not matches else "multiple_team_game_sections"]
        official[side] = team
    return official, audit


def enrich_packets(output, games, packets, bundle):
    output = Path(output)
    enriched, lineage, coverage = [], [], []
    for game, packet in zip(games, packets):
        official, audit = official_section(game, bundle)
        packet = {**packet, "injury_news": {"official_injury": official,
            "news": {"state": "not_collected_historical", "findings": [],
                     "missing_reason": "live_search_disabled_for_historical_games"}}}
        frozen = freeze_packet(packet, output / "evidence_captures")
        enriched.append(frozen)
        lineage.append(audit)
        coverage.append({"game_id": game["game_id"], "game_date": game["game_date"], "month": game["month"],
            "origin_timestamp_supported_report": official["report_source_id"] is not None,
            "independently_verified_historical_publication": False,
            "latest_report_globally_verified": False,
            "home_state": official["home"]["state"], "away_state": official["away"]["state"],
            "home_uncertainty": ";".join(official["home"]["uncertainty_flags"]),
            "away_uncertainty": ";".join(official["away"]["uncertainty_flags"]),
            "home_players": len(official["home"]["players"]), "away_players": len(official["away"]["players"]),
            "uncertain_player_records": sum(bool(p["uncertainty_flags"]) for side in ("home", "away") for p in official[side]["players"]),
            "snapshot_sha256": frozen["evidence_snapshot_sha256"]})
    write_csv(output / "injury_coverage.csv", coverage)
    (output / "injury_lineage.jsonl").write_text("".join(json.dumps(a, sort_keys=True) + "\n" for a in lineage))
    (output / "evidence_snapshot_manifest.json").write_text(json.dumps({
        "consumer_contract": "Both direct-LLM and future LEAP-inspired consumers must load the same game/cutoff hash using shared_evidence.load_frozen_packet.",
        "games": [{"game_id": p["game_id"], "cutoff_utc": p["cutoff_utc"],
                   "sha256": p["evidence_snapshot_sha256"],
                   "capture_file": "evidence_captures/" + p["evidence_snapshot_sha256"] + ".json"} for p in enriched]}, indent=2, sort_keys=True) + "\n")
    monthly = []
    for month in sorted({r["month"] for r in coverage}):
        part = [r for r in coverage if r["month"] == month]
        states = Counter(r[side + "_state"] for r in part for side in ("home", "away"))
        monthly.append({"month": month, "games": len(part),
            "origin_timestamp_supported_reports": sum(r["origin_timestamp_supported_report"] for r in part),
            "independently_verified_publication": 0, "globally_verified_latest": 0,
            "player_status_records": sum(r["home_players"] + r["away_players"] for r in part),
            "uncertain_player_records": sum(r["uncertain_player_records"] for r in part),
            **{state + "_team_games": states[state] for state in ("reported", "not_yet_submitted", "unavailable", "ambiguous")}})
    write_csv(output / "injury_coverage_by_month.csv", monthly)
    summary = {"games": len(coverage), "origin_timestamp_supported_reports": sum(r["origin_timestamp_supported_report"] for r in coverage),
        "independently_verified_publication": 0, "globally_verified_latest": 0,
        "player_status_records": sum(r["home_players"] + r["away_players"] for r in coverage),
        "uncertain_player_records": sum(r["uncertain_player_records"] for r in coverage),
        "archive_http_status": bundle["archive_http_status"], "policy": HISTORY_POLICY,
        "team_game_states": dict(Counter(r[side + "_state"] for r in coverage for side in ("home", "away"))),
        "candidate_rejection_reasons": dict(Counter(c["rejection_reason"] for a in lineage
            for c in a["candidate_decisions"] if c["rejection_reason"])),
        "report_http_statuses": dict(Counter(r["http_status"] for r in bundle["reports"].values()))}
    (output / "injury_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    lines = ["# Official injury evidence coverage", "",
        f"Games: {len(coverage)}. Official-origin-timestamp-supported pre-cutoff reports: {summary['origin_timestamp_supported_reports']}. "
        f"Player/status records: {summary['player_status_records']}. Independently archived publication verification: **0**. "
        "Globally verified latest report selection: **0**.", "",
        "Origin support requires matching PDF issue/creation clocks and an official object Last-Modified timestamp at or before the cutoff. "
        "This substantiates the issuer's object-version timestamp, not independently proven public visibility at that time. "
        "No report lacking that support contributes player statuses. Retrieval time never substitutes for publication time.", "",
        "| Month | Games | Origin-supported report | Player/status rows | Reported team-games | Not submitted | Unavailable | Ambiguous |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for m in monthly:
        lines.append("| " + " | ".join(str(m[k]) for k in ("month", "games", "origin_timestamp_supported_reports", "player_status_records",
            "reported_team_games", "not_yet_submitted_team_games", "unavailable_team_games", "ambiguous_team_games")) + " |")
    lines += ["", "## Limits", "",
        "* The season page currently lists a rolling day's links; direct collection returned HTTP " + str(bundle["archive_http_status"]) + ". "
        "The HTML request and each PDF attempt are retained, including 403/404 responses.",
        "* Approved official PDF URLs are probed at 15-minute issue intervals, newest first, at most 17 candidates/four hours per distinct cutoff. "
        "Missing or forbidden URLs do not prove absence. A complete historical publication index was not recovered; report selection is latest only "
        "among this explicit bounded candidate set, never asserted globally complete.",
        "* Raw captures also retain the initial longer-window investigation, including failed requests. Those extra exploratory captures do not expand the four-hour selection rule.",
        "* A report issued at the cutoff but uploaded seconds later is rejected. No target-game final pregame report is backfilled.",
        "* Target date, matchup and exact team mapping are required. Absent target sections are unavailable, not healthy. "
        "NOT YET SUBMITTED is distinct from reported, and ambiguous rows stay explicit. No inference is made for unlisted players.",
        f"* Extraction is deterministic, uses pypdf 6.21.1 coordinates, and records page references and warnings. {summary['uncertain_player_records']} player rows have uncertainty flags, including incomplete page-boundary reasons. Unassigned fragments remain in the extraction audit; they are not guessed. No inference model or paid research was run.",
        "* Historical collection has no live search/provider path. The entire dataset remains retrospectively reconstructed, not point-in-time verified.", ""]
    (output / "injury_coverage_report.md").write_text("\n".join(lines))
    return enriched
