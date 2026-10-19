"""Allowlisted pregame team facts. No market data is accepted by this module."""

from math import floor

from investigate_kalshi import iso, timestamp


def extract_history(game, response, source):
    """Require a timestamped End Game score and game-specific recap clocks."""
    row = {"game_id": game["game_id"], "recorded_start_utc": game["recorded_start_utc"],
           "home_id": game["home_id"], "away_id": game["away_id"],
           "counts_in_regular_season": game["counts_in_regular_season"],
           "excluded_fixture": game.get("excluded_fixture", False),
           "source_id": source, "end_utc": None, "available_by_utc": None,
           "recap_published_utc": None, "recap_modified_utc": None,
           "event_updated_utc": None, "home_points": None, "away_points": None,
           "home_won": None, "end_game_score_matches_header": None,
           "point_in_time_verified": False, "issue": None}
    if row["excluded_fixture"]:
        row["issue"] = "excluded_postponed_or_cancelled_fixture"
        return row
    if not response or str(response.get("header", {}).get("id")) != game["game_id"]:
        row["issue"] = "missing_or_mismatched_summary"
        return row
    end_plays = [p for p in response.get("plays", [])
                 if str(p.get("type", {}).get("id")) == "402" and p.get("wallclock")]
    if not end_plays:
        row["issue"] = "missing_timestamped_end_game"
        return row
    try:
        end = max(end_plays, key=lambda p: timestamp(p["wallclock"]))
        row["end_utc"] = iso(timestamp(end["wallclock"]))
    except (TypeError, ValueError):
        row["issue"] = "invalid_end_game_clock"
        return row
    competition = response["header"]["competitions"][0]
    teams = {t["homeAway"]: t for t in competition["competitors"]}
    final = competition.get("status", {}).get("type", {}).get("completed")
    if not final or any(str(teams[s]["id"]) != game[s + "_id"] for s in ("home", "away")):
        row["issue"] = "completion_or_team_mismatch"
        return row
    try:
        hp, ap = int(end["homeScore"]), int(end["awayScore"])
        if hp == ap or timestamp(row["end_utc"]) < timestamp(game["recorded_start_utc"]):
            raise ValueError("bad final score or clock")
        header_hp, header_ap = int(teams["home"]["score"]), int(teams["away"]["score"])
        if (hp > ap) != (header_hp > header_ap) or header_hp == header_ap:
            raise ValueError("End Game and header disagree on winner")
        row["end_game_score_matches_header"] = hp == header_hp and ap == header_ap
    except (KeyError, ValueError, TypeError):
        row["issue"] = "invalid_or_conflicting_end_game_score"
        return row
    article = response.get("article") or {}
    row["recap_published_utc"] = article.get("published")
    row["recap_modified_utc"] = article.get("lastModified")
    row["event_updated_utc"] = response.get("meta", {}).get("lastUpdatedAt")
    if (str(article.get("gameId")) != game["game_id"] or article.get("type") != "Recap"
            or not all(row[k] for k in ("recap_published_utc", "recap_modified_utc", "event_updated_utc"))):
        row["issue"] = "missing_game_specific_publication_clocks"
        return row
    try:
        clocks = [timestamp(row[k]) for k in ("end_utc", "recap_published_utc",
                  "recap_modified_utc", "event_updated_utc")]
    except (ValueError, TypeError):
        row["issue"] = "invalid_source_clock"
        return row
    # Only W/L is used as a feature. Corrections that preserve the winner do not
    # justify an exact points/margin feature; leave exact scores blank and flag it.
    row.update(home_won=hp > ap, available_by_utc=iso(max(clocks)))
    if row["end_game_score_matches_header"]:
        row.update(home_points=hp, away_points=ap)
    else:
        row["issue"] = "final_scores_differ_winner_agrees"
    return row


def team_facts(team_id, cutoff, history, target_id):
    # Candidate starts must precede the cutoff. The target is excluded explicitly.
    candidates = [h for h in history if not h.get("excluded_fixture") and h["game_id"] != target_id
                  and team_id in (h["home_id"], h["away_id"])
                  and timestamp(h["recorded_start_utc"]) < cutoff]
    eligible = [h for h in candidates if h["available_by_utc"]
                and timestamp(h["available_by_utc"]) <= cutoff]
    eligible.sort(key=lambda h: (timestamp(h["end_utc"]), h["game_id"]))
    # A known ongoing game has no final result at T. Unknown/corrected/publication-
    # delayed results can make a complete historical record unreconstructible.
    blockers = [h for h in candidates if h not in eligible
                and (h["end_utc"] is None or timestamp(h["end_utc"]) <= cutoff)]
    regular = [h for h in eligible if h["counts_in_regular_season"]]
    regular_blockers = [h for h in blockers if h["counts_in_regular_season"]]
    def won(h):
        return h["home_won"] == (h["home_id"] == team_id)
    facts, lineage, omitted = {}, {}, []
    if not regular_blockers:
        wins = sum(won(h) for h in regular)
        facts["regular_season_record"] = {"games_completed": len(regular), "wins": wins,
                                           "losses": len(regular) - wins}
        lineage["regular_season_record"] = [h["game_id"] for h in regular]
    else:
        omitted.append({"feature": "regular_season_record", "reason": "incomplete_timestamped_history"})
    recent = regular[-5:]
    recent_blocked = bool(regular_blockers)
    if recent and not recent_blocked:
        wins = sum(won(h) for h in recent)
        facts["recent_regular_season"] = {"window_games": len(recent), "wins": wins,
            "losses": len(recent) - wins,
            "results_oldest_to_newest": "".join("W" if won(h) else "L" for h in recent)}
        lineage["recent_regular_season"] = [h["game_id"] for h in recent]
    else:
        omitted.append({"feature": "recent_regular_season", "reason":
                        "incomplete_timestamped_history" if recent_blocked else "no_completed_games"})
    # Rest is measured AT the evidence cutoff. Do not assume games between T and
    # tipoff have already happened or invent an end time from a scheduled start.
    last = eligible[-1] if eligible else None
    rest_blocked = last is None or any(h not in eligible and
        timestamp(h["recorded_start_utc"]) >= timestamp(last["recorded_start_utc"])
        for h in candidates)
    if not rest_blocked:
        hours = (cutoff - timestamp(last["end_utc"])) / 3600
        facts["rest_at_cutoff"] = {"hours_since_last_completed_game": round(hours, 6),
                                   "full_24h_days_since_last_completed_game": floor(hours / 24)}
        lineage["rest_at_cutoff"] = [last["game_id"]]
    else:
        omitted.append({"feature": "rest_at_cutoff", "reason": "no_reliable_latest_completed_game"})
    used_ids = set(gid for ids in lineage.values() for gid in ids)
    facts["omitted_features"] = omitted
    audit = {"feature_game_ids": lineage,
             "blocker_game_ids": [h["game_id"] for h in blockers],
             "source_ids": sorted({h["source_id"] for h in eligible if h["game_id"] in used_ids})}
    return facts, audit


def make_packet(game, history):
    """Construct from schedule-only identities and allowlisted past team facts."""
    cutoff = timestamp(game["recorded_start_utc"]) - 86400
    packet = {"schema_version": 1, "game_id": game["game_id"],
              "recorded_tipoff_utc": game["recorded_start_utc"], "cutoff_utc": iso(cutoff),
              "neutral_site": game["neutral_site"],
              "reconstruction_status": "timestamped_history_unversioned_payloads",
              "point_in_time_verified": False,
              "schedule_asof_cutoff_verified": False}
    audit = {"game_id": game["game_id"], "cutoff_utc": iso(cutoff),
             "schedule_source_ids": game["schedule_source_ids"]}
    for side in ("home", "away"):
        facts, team_audit = team_facts(game[side + "_id"], cutoff, history, game["game_id"])
        packet[side] = {"team_id": game[side + "_id"], "team_name": game[side + "_name"],
                        "designation": side, **facts}
        audit[side] = team_audit
    return packet, audit
