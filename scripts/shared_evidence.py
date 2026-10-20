"""One model-facing packet contract and hash verification for every consumer."""

import json
from math import isfinite
from pathlib import Path

from evidence_documents import canonical, digest
from investigate_kalshi import timestamp

SNAPSHOT_KEY = "evidence_snapshot_sha256"


def validate_packet(packet):
    allowed = {"schema_version", "game_id", "recorded_tipoff_utc", "cutoff_utc", "neutral_site",
        "reconstruction_status", "point_in_time_verified", "schedule_asof_cutoff_verified", "home", "away",
        "injury_news", SNAPSHOT_KEY, "snapshot_timing"}
    if set(packet) - allowed or allowed - {SNAPSHOT_KEY, "snapshot_timing"} - set(packet):
        raise ValueError("Unapproved model-facing packet fields")
    cutoff = timestamp(packet["cutoff_utc"])
    if cutoff >= timestamp(packet["recorded_tipoff_utc"]):
        raise ValueError("Evidence cutoff must precede tipoff")
    if "snapshot_timing" in packet:
        timing = packet["snapshot_timing"]
        required = {"target_cutoff_utc", "collection_started_at_utc", "actual_snapshot_utc",
                "packet_created_at_utc", "deviation_seconds", "status", "strict_t24h_eligible"}
        optional = {"timing_tolerance_seconds", "within_timing_tolerance"}
        if not required <= set(timing) or set(timing) - required not in (set(), optional):
            raise ValueError("Unapproved timing fields")
        target = timestamp(packet["recorded_tipoff_utc"]) - 86400
        deviation = round(cutoff - target, 6)
        if (timestamp(timing["target_cutoff_utc"]) != target or timestamp(timing["actual_snapshot_utc"]) != cutoff
                or not timestamp(timing["collection_started_at_utc"]) <= cutoff <= timestamp(timing["packet_created_at_utc"])
                or timing["deviation_seconds"] != deviation
                or timing["status"] != ("late" if deviation > 0 else "early" if deviation < 0 else "at_target")
                or timing["strict_t24h_eligible"] != (deviation == 0)):
            raise ValueError("Inconsistent or backdated snapshot timing")
        if optional <= set(timing):
            tolerance = timing["timing_tolerance_seconds"]
            if (type(tolerance) not in (int, float) or not isfinite(tolerance) or tolerance < 0
                    or timing["within_timing_tolerance"] != (abs(deviation) <= tolerance)):
                raise ValueError("Invalid practical timing tolerance")
    team_keys = {"team_id", "team_name", "designation", "regular_season_record", "recent_regular_season",
                 "rest_at_cutoff", "omitted_features", "regular_season_scoring", "regular_season_home_away"}
    for side in ("home", "away"):
        if set(packet[side]) - team_keys or packet[side]["designation"] != side:
            raise ValueError("Unapproved team packet fields")
        for feature, keys in {
                "regular_season_record": {"games_completed", "wins", "losses"},
                "recent_regular_season": {"window_games", "wins", "losses", "results_oldest_to_newest"},
                "rest_at_cutoff": {"hours_since_last_completed_game", "full_24h_days_since_last_completed_game"}}.items():
            if feature in packet[side] and set(packet[side][feature]) != keys:
                raise ValueError("Unapproved statistical feature fields")
        team = packet[side]
        if "regular_season_home_away" in team:
            splits = team["regular_season_home_away"]
            if set(splits) != {"home", "away"}:
                raise ValueError("Invalid split record schema")
            for record in splits.values():
                if (set(record) != {"games_completed", "wins", "losses"}
                        or any(type(v) is not int or v < 0 for v in record.values())
                        or record["wins"] + record["losses"] != record["games_completed"]):
                    raise ValueError("Invalid split record")
            if "regular_season_record" in team and any(sum(s[k] for s in splits.values()) != team["regular_season_record"][k] for k in ("games_completed", "wins", "losses")):
                raise ValueError("Split records do not reconcile")
        if "regular_season_scoring" in team:
            score = team["regular_season_scoring"]
            if set(score) != {"games_completed", "per_game", "total_point_differential", "average_point_differential"}:
                raise ValueError("Invalid scoring schema")
            rows = score["per_game"]
            if (not isinstance(rows, list) or not rows or any(set(r) != {"game_id", "point_differential"}
                    or not isinstance(r["game_id"], str) or r["game_id"] == packet["game_id"]
                    or type(r["point_differential"]) is not int or r["point_differential"] == 0 for r in rows)
                    or len({r["game_id"] for r in rows}) != len(rows)):
                raise ValueError("Invalid per-game margins or target leakage")
            total = sum(r["point_differential"] for r in rows)
            if (type(score["games_completed"]) is not int or type(score["total_point_differential"]) is not int
                    or type(score["average_point_differential"]) not in (int, float) or not isfinite(score["average_point_differential"])
                    or score["games_completed"] != len(rows) or score["total_point_differential"] != total
                    or "regular_season_record" in team and score["games_completed"] != team["regular_season_record"]["games_completed"]
                    or score["average_point_differential"] != round(total / len(rows), 6)):
                raise ValueError("Scoring aggregates do not reconcile")
        for omission in packet[side].get("omitted_features", []):
            if set(omission) != {"feature", "reason"}:
                raise ValueError("Unapproved feature omission fields")
    section = packet["injury_news"]
    if set(section) != {"official_injury", "news"}:
        raise ValueError("Unapproved injury/news schema")
    official = section["official_injury"]
    if set(official) != {"collection_mode", "publication_verification", "report_source_id", "report_url",
            "report_issue_utc", "published_at_utc", "independent_historical_public_capture_verified",
            "latest_report_globally_verified", "selection_scope", "home", "away"}:
        raise ValueError("Unapproved official evidence fields")
    for field in ("report_issue_utc", "published_at_utc"):
        if official.get(field) and timestamp(official[field]) > cutoff:
            raise ValueError("Post-cutoff official injury evidence")
    valid_statuses = {"Out", "Doubtful", "Questionable", "Probable", "Available", "ambiguous"}
    for side in ("home", "away"):
        team = official[side]
        if set(team) != {"team_id", "state", "players", "uncertainty_flags"}:
            raise ValueError("Unapproved injury team fields")
        if team["team_id"] != packet[side]["team_id"] or team["state"] not in (
                "reported", "not_yet_submitted", "unavailable", "ambiguous"):
            raise ValueError("Invalid injury team mapping/state")
        for player in team["players"]:
            if set(player) != {"player", "status", "status_raw", "reason", "page", "uncertainty_flags", "source_ref"}:
                raise ValueError("Unapproved injury player fields")
            if (player["status"] not in valid_statuses or not official["report_source_id"]
                    or not player.get("source_ref", "").startswith(official["report_source_id"] + ":page:")):
                raise ValueError("Unsupported player status/reference")
    news = section["news"]
    if set(news) != {"state", "findings", "missing_reason"}:
        raise ValueError("Unapproved news fields")
    for finding in news["findings"]:
        if set(finding) != {"category", "team", "player", "claim", "source_url", "published_at_utc",
                "retrieved_at_utc", "source_references", "uncertainty_flags"}:
            raise ValueError("Unapproved news finding fields")
        if timestamp(finding["published_at_utc"]) > cutoff or not finding.get("source_references"):
            raise ValueError("Unsupported or post-cutoff news finding")
        if finding["category"] not in ("injury_update", "lineup_availability", "roster_transaction", "team_development") or finding["team"] not in {packet[s]["team_name"] for s in ("home", "away")}:
            raise ValueError("Unapproved news category/team")
        for ref in finding["source_references"]:
            if set(ref) != {"source_ref", "source_id", "url", "published_at_utc", "retrieved_at_utc", "supporting_excerpt", "supported_claim", "authority"}:
                raise ValueError("Unapproved source reference fields")
            if timestamp(ref["published_at_utc"]) > cutoff or ref["supported_claim"] not in ref["supporting_excerpt"]:
                raise ValueError("News reference does not substantiate claim at cutoff")
            if "snapshot_timing" in packet and timestamp(ref["retrieved_at_utc"]) > cutoff:
                raise ValueError("News retrieved after actual snapshot")
        if "snapshot_timing" in packet and timestamp(finding["retrieved_at_utc"]) > cutoff:
            raise ValueError("News retrieved after actual snapshot")
        if not any(finding["claim"] == r["supported_claim"] for r in finding["source_references"]):
            raise ValueError("Primary news claim has no supporting reference")
    return packet


def freeze_packet(packet, capture_dir):
    payload = {k: v for k, v in packet.items() if k != SNAPSHOT_KEY}
    validate_packet(payload)
    key = digest(canonical(payload))
    frozen = dict(payload, **{SNAPSHOT_KEY: key})
    target = Path(capture_dir) / (key + ".json")
    target.parent.mkdir(parents=True, exist_ok=True)
    data = canonical(frozen) + b"\n"
    if target.exists():
        if target.read_bytes() != data:
            raise ValueError("Immutable evidence capture changed")
    else:
        target.write_bytes(data)
    return frozen


def load_frozen_packet(path, expected_sha256=None):
    """Consumer-neutral loader: direct LLM and future methods get identical bytes."""
    packet = json.loads(Path(path).read_text())
    key = packet.get(SNAPSHOT_KEY)
    payload = {k: v for k, v in packet.items() if k != SNAPSHOT_KEY}
    if key != digest(canonical(payload)) or expected_sha256 and key != expected_sha256:
        raise ValueError("Evidence snapshot hash mismatch")
    return validate_packet(packet)


def load_game_snapshot(dataset_dir, game_id):
    """Single manifest binding, shared by all future forecasting consumers."""
    root = Path(dataset_dir)
    manifest = json.loads((root / "evidence_snapshot_manifest.json").read_text())
    matches = [g for g in manifest["games"] if g["game_id"] == game_id]
    if len(matches) != 1:
        raise ValueError("Snapshot game is missing or ambiguous")
    entry = matches[0]
    target = (root / entry["capture_file"]).resolve()
    if root.resolve() not in target.parents:
        raise ValueError("Snapshot path escapes evidence directory")
    return load_frozen_packet(target, entry["sha256"])
