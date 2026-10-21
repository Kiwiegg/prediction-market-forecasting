"""Frozen LEAP-NBA v1 group projection, strict LR parsing and aggregation."""
import copy
import json
import math
import re

from direct_forecast import checked_config as check_direct_config, load_evidence
from evidence_documents import canonical, digest
from forecast_split import ROOT
from shared_evidence import validate_packet

VERSION = "leap_nba_lr_v1"
FROZEN = {
    "prompts/leap_nba_lr_v1.txt": "0c13c8db732600770adf6177a5b4a627ce5459db7206e6fe1033a6f3975342be",
    "experiments/leap_nba_v1_groups.json": "4a3038a99579f99e7ae7ff73fb65aab3207e192059fd9ee42fa95548957f137a",
    "experiments/leap_nba_v1_response_schema.json": "e4d661710868c78e77b2c610b2ab27407354bb5b57c980f42bf0a8c2476ac53f",
    "experiments/leap_nba_v1_protocol.md": "a60a10263ff62cdd1ba3f023d5e97128e391489a5870bf750e20824b8bc61e76",
    "examples/leap_forecast_config.json": "eed9351a0fec7c2b387678682a00f46a0511ecff4259552ef876ca5f40f5d1f1",
}
GROUPS = ("A_team_strength", "B_schedule_venue", "C_player_availability", "D_additional_news")
VARIANTS = {"leap_raw": 1.0, "leap_conservative": .5}
LR_MIN, LR_MAX = .05, 20.0
STRENGTH_FIELDS = ("regular_season_record", "recent_regular_season", "regular_season_scoring", "regular_season_home_away")


def frozen_assets():
    for name, expected in FROZEN.items():
        if digest((ROOT / name).read_bytes()) != expected:
            raise ValueError("Frozen LEAP v1 asset changed: " + name)
    return FROZEN.copy()


def checked_config(config):
    if config.get("prompt_version") != VERSION:
        raise ValueError("Only frozen LEAP-NBA v1 is registered")
    check_direct_config(dict(config, prompt_version="direct_home_win_v1"))
    if config["generation"] != {"temperature": 0.0, "max_tokens": 128, "structured_json": True}:
        raise ValueError("LEAP v1 generation settings are fixed")
    return config


def normalize(text):
    return re.sub(r"\W+", " ", (text or "").casefold()).strip()


def deduplicate(findings, seen=None, source_seen=None):
    seen, source_seen = set(seen or ()), set(source_seen or ())
    kept, rejected = [], []
    for finding in sorted(findings, key=canonical):
        key = tuple(normalize(finding.get(k)) for k in ("team", "player", "claim"))
        refs = {(r["source_ref"], normalize(r["supported_claim"])) for r in finding["source_references"]}
        if key in seen or refs & source_seen:
            rejected.append({"claim": finding["claim"], "reason": "duplicate_claim_or_source_fact"})
            continue
        kept.append(copy.deepcopy(finding)); seen.add(key); source_seen.update(refs)
    return kept, rejected, seen, source_seen


def build_groups(packet):
    """Projection only: no evaluation/audit reads, new features or retrieval."""
    validate_packet(packet)
    parent_hash = packet.get("evidence_snapshot_sha256")
    if parent_hash != digest(canonical({k: v for k, v in packet.items() if k != "evidence_snapshot_sha256"})):
        raise ValueError("Parent frozen packet hash mismatch")
    common = {k: copy.deepcopy(packet[k]) for k in ("game_id", "recorded_tipoff_utc", "cutoff_utc",
        "reconstruction_status", "point_in_time_verified", "schedule_asof_cutoff_verified")}
    common["teams"] = {s: {k: packet[s][k] for k in ("team_id", "team_name", "designation")} for s in ("home", "away")}
    strength, schedule = {}, {"neutral_site": packet["neutral_site"]}
    completed = False
    has_strength = False
    for side in ("home", "away"):
        team = packet[side]
        strength[side] = {k: copy.deepcopy(team[k]) for k in STRENGTH_FIELDS if k in team}
        completed |= any(team.get(k, {}).get("games_completed", team.get(k, {}).get("window_games", 0)) > 0
                         for k in STRENGTH_FIELDS)
        completed |= any(r.get("games_completed", 0) > 0 for r in team.get("regular_season_home_away", {}).values())
        has_strength |= bool(strength[side])
        strength[side]["omitted_features"] = [copy.deepcopy(x) for x in team.get("omitted_features", [])
            if any(x["feature"].startswith(k) for k in STRENGTH_FIELDS)]
        schedule[side] = {"omitted_features": [copy.deepcopy(x) for x in team.get("omitted_features", [])
            if x["feature"].startswith("rest")]}
        if "rest_at_cutoff" in team:
            schedule[side]["rest_at_cutoff"] = copy.deepcopy(team["rest_at_cutoff"])
    section = packet["injury_news"]
    news = section["news"]
    injury_news, duplicates_c, seen, refs = deduplicate([f for f in news["findings"]
        if f["category"] in ("injury_update", "lineup_availability")])
    other_news, duplicates_d, _, _ = deduplicate([f for f in news["findings"]
        if f["category"] in ("roster_transaction", "team_development")], seen, refs)
    official = copy.deepcopy(section["official_injury"])
    official_usable = bool(official["published_at_utc"] and official["report_issue_utc"]
        and official["report_source_id"] and official["publication_verification"] != "unavailable"
        and any(p["status"] != "ambiguous" for s in ("home", "away") for p in official[s]["players"]))
    injury = {"official_injury": official, "news": {"state": news["state"], "findings": injury_news,
        "missing_reason": news["missing_reason"]}}
    additional = {"state": news["state"], "findings": other_news, "missing_reason": news["missing_reason"]}
    reasons = {
        GROUPS[0]: None if completed else "no_completed_games" if has_strength else "statistical_source_unavailable",
        GROUPS[1]: None,
        GROUPS[2]: None if official_usable or injury_news else "no_usable_player_status:" +
            ",".join(s + "=" + official[s]["state"] for s in ("home", "away")),
        GROUPS[3]: None if other_news else "no_usable_additional_news:" + news["state"] + ":" + str(news["missing_reason"]),
    }
    groups = []
    for name, evidence, duplicates in zip(GROUPS, (strength, schedule, injury, additional), ([], [], duplicates_c, duplicates_d)):
        content = {**copy.deepcopy(common), "group": name, "evidence": evidence}
        groups.append({"group": name, "usable": reasons[name] is None, "missing_reason": reasons[name],
            "content": content, "group_evidence_sha256": digest(canonical(content)),
            "evidence_sha256": parent_hash, "deduplication_decisions": duplicates})
    return groups


def likelihood_ratio(value):
    if type(value) not in (int, float) or not math.isfinite(value) or not LR_MIN <= value <= LR_MAX:
        raise ValueError("LR must be a finite JSON number within [0.05,20]; no clipping")
    return float(value)


def lr_object(value):
    if not isinstance(value, dict) or set(value) != {"likelihood_ratio", "evidence_sufficiency"}:
        raise ValueError("LR response must have exactly the two registered fields")
    ratio = likelihood_ratio(value["likelihood_ratio"])
    if value["evidence_sufficiency"] not in ("adequate", "limited", "insufficient"):
        raise ValueError("Unregistered evidence sufficiency")
    if value["evidence_sufficiency"] == "insufficient":
        raise ValueError("Model reports insufficient evidence; required group inference failed")
    return {"likelihood_ratio": ratio, "evidence_sufficiency": value["evidence_sufficiency"]}


def strict_lr_json(text):
    def pairs(items):
        if len(dict(items)) != len(items):
            raise ValueError("Duplicate JSON keys")
        return dict(items)
    def invalid(_):
        raise ValueError("Nonstandard JSON constant")
    return lr_object(json.loads(text, object_pairs_hook=pairs, parse_constant=invalid))


def sigmoid(z):
    if not math.isfinite(z):
        raise ValueError("Nonfinite log odds")
    return 1 / (1 + math.exp(-z)) if z >= 0 else math.exp(z) / (1 + math.exp(z))


def aggregate(records):
    if [r["group"] for r in records] != list(GROUPS):
        raise ValueError("Exactly four ordered, distinct groups required")
    logs, failed = {}, []
    for r in records:
        if r["status"] == "success":
            logs[r["group"]] = math.log(lr_object({k: r[k] for k in ("likelihood_ratio", "evidence_sufficiency")})["likelihood_ratio"])
        elif r["status"] == "skipped_missing" and r.get("missing_reason") and r["likelihood_ratio"] == 1:
            logs[r["group"]] = 0.0
        elif r["status"] in ("failed", "not_attempted_budget") and r["likelihood_ratio"] is None:
            logs[r["group"]] = None; failed.append(r["group"])
        else:
            raise ValueError("Invalid group failure/missingness semantics")
    complete = not failed
    total = math.fsum(logs.values()) if complete else None
    return {"status": "success" if complete else "failed", "failed_groups": failed, "prior_home_win_probability": .5,
        "group_log_likelihood_ratios": logs,
        "variants": {name: {"alpha": alpha, "log_odds": alpha * total if complete else None,
            "home_win_probability": sigmoid(alpha * total) if complete else None,
            "group_log_odds_contributions": {g: alpha * v if v is not None else None for g, v in logs.items()},
            "leave_one_group_out": {g: {"home_win_probability": sigmoid(alpha * (total - logs[g])) if complete else None,
                "full_minus_omission_probability": sigmoid(alpha * total) - sigmoid(alpha * (total - logs[g])) if complete else None}
                for g in GROUPS}} for name, alpha in VARIANTS.items()}}
