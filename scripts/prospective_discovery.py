#!/usr/bin/env python3
"""Schedule amendment v1: one authorized discovery, then an eligible pilot only.

No change to the original protocol/assets, packet schema or forecasters. Default
is offline. Only the preferred NBA schedule's HTTP403 permits a denied-source
fallback; ESPN and all other access denials still stop the entire attempt.
"""
import argparse
import json
import os
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import prospective_study as study
from evidence_documents import DocumentStore, canonical, digest
from forecast_split import ROOT, immutable_json
from investigate_kalshi import iso, timestamp
from prospective_sources import NBA_SCHEDULES, SPORT, SourceSession, allowed_source, event_projection, nba_projection, url

BASE = ROOT / "captures/prospective_discovery_v1"
ATTEMPT = BASE / "attempt"
STOP = BASE / "access_denial.json"
AMENDMENT = ROOT / "experiments/prospective_schedule_amendment_v1.md"
REGISTRY = ROOT / "experiments/prospective_schedule_amendment_v1_assets.json"
FIELDS = ("game_id", "home_id", "away_id", "home_code", "away_code", "season_year",
          "season_type", "recorded_start_utc", "neutral_site", "time_valid", "scheduled", "counts_in_regular_season")


class ScheduleDocuments(study.OneShotDocuments):
    def _get(self, value):
        if value != NBA_SCHEDULES[0]:
            return super()._get(value)
        # Keep the exact original one-shot transport and immutable body format.
        # Withhold the *new* denial journal only for this one allowlisted URL.
        optional = study.OneShotDocuments(self.folder, self.offline, self.allowed_url,
            guard=self.guard, clock=self.clock, opener=self.opener)
        try:
            return optional._get(value)
        except study.Halt:
            meta, body = DocumentStore._get(self, value)  # verifies saved body hash
            if meta["http_status"] == 403:
                return meta, body
            self.budget.stop("access_denial", http_status=meta["http_status"], url=value)
            raise


class ScheduleSession(study.StudySession):
    def __init__(self, folder, budget, guard=lambda: None, opener=None):
        super().__init__(folder, budget, guard, opener)
        self.store = ScheduleDocuments(folder, False, self.store.allowed_url, budget,
            guard=guard, clock=budget.clock, opener=opener)


def project(event):
    study.aware(event["date"])
    comp = event["competitions"][0]
    if "date" in comp and study.aware(comp["date"]) != study.aware(event["date"]):
        raise ValueError("Conflicting event/competition tipoff")
    if "id" in comp and str(comp["id"]) != str(event["id"]):
        raise ValueError("Conflicting event/competition identity")
    row = event_projection(event)
    if not row["game_id"].isdigit() or type(row["season_year"]) is not int:
        raise ValueError("Missing numeric fixture identity/season")
    if row["home_id"] == row["away_id"]:
        raise ValueError("Distinct home/away teams required")
    return row


def differences(reference, candidate):
    return {k: {"reference": reference.get(k), "candidate": candidate.get(k)}
            for k in FIELDS if reference.get(k) != candidate.get(k)}


def discover_verified(session, now, days=3):
    """NBA-preferred mapping via ESPN; both ESPN team schedules must agree.

    Uses schedule projections exclusively. Raw feeds remain audit-only. Does
    not request target summaries, history, news, prices, or any model provider.
    """
    if type(days) is not int or not 1 <= days <= 7:
        raise ValueError("Discovery is bounded to 1–7 UTC dates")
    meta, doc = session.json(NBA_SCHEDULES[0])
    official = nba_projection(doc) if isinstance(doc, dict) else []
    official = [g for g in official if _explicit_nba_time(doc, g)]
    decisions = [{"stage": "preferred_NBA", "url": meta["url"], "source_id": meta["source_id"],
        "http_status": meta["http_status"], "usable_games": len(official),
        "fallback_permitted": not bool(official), "reason": None if official else "NBA_schedule_unavailable_or_unusable"}]
    nba_meta = meta
    candidates = {}
    for offset in range(days):
        day = datetime.fromtimestamp(now, timezone.utc).date() + timedelta(days=offset)
        value = url(SPORT + "/scoreboard", dates=day.strftime("%Y%m%d"), limit=1000)
        meta, doc = session.json(value)
        decisions.append({"stage": "ESPN_scoreboard", "url": value, "source_id": meta["source_id"],
            "http_status": meta["http_status"], "usable_document": isinstance(doc, dict)})
        for event in doc.get("events", []) if isinstance(doc, dict) else []:
            try:
                game = project(event)
                study.game_guard(game, now, window=False)
            except (KeyError, TypeError, ValueError, IndexError) as e:
                decisions.append({"stage": "candidate", "game_id": event.get("id"), "reason": "not_eligible_scheduled_regular_fixture", "detail": str(e)})
                continue
            match = [g for g in official if all(g[k] == game[k] for k in ("home_code", "away_code", "recorded_start_utc"))]
            if official and len(match) != 1:
                decisions.append({"stage": "candidate", "game_id": game["game_id"], "reason": "NBA_ESPN_schedule_conflict",
                    "ESPN_schedule": game, "NBA_same_teams": [g for g in official if all(g[k] == game[k] for k in ("home_code", "away_code"))]})
                continue
            old = candidates.get(game["game_id"])
            if old and differences(old[0], game):
                decisions.append({"stage": "candidate", "game_id": game["game_id"], "reason": "conflicting_scoreboards", "discrepancies": differences(old[0], game)})
                candidates[game["game_id"]] = (old[0], old[1], old[2], True)
            elif old is None:
                candidates[game["game_id"]] = (game, meta, match, False)
    games = []; team_cache = {}
    for game, board_meta, match, conflict in candidates.values():
        if conflict: continue
        providers = {k: [{"provider": "ESPN_scoreboard", "source_id": board_meta["source_id"]}] for k in FIELDS}
        valid = True; ids = [board_meta["source_id"]]
        for side in ("home", "away"):
            value = url(SPORT + "/teams/" + game[side + "_id"] + "/schedule", season=game["season_year"], seasontype=2)
            if value not in team_cache: team_cache[value] = session.json(value)
            meta, doc = team_cache[value]
            reason = None; delta = {}; row = None
            try:
                if not isinstance(doc, dict) or str(doc["team"]["id"]) != game[side + "_id"]:
                    raise ValueError("team_schedule_unavailable_or_wrong_team")
                matches = [e for e in doc["events"] if str(e.get("id")) == game["game_id"]]
                if len(matches) != 1: raise ValueError("target_missing_or_duplicated_in_team_schedule")
                row = project(matches[0]); study.game_guard(row, now, window=False)
                delta = differences(game, row)
                if delta: raise ValueError("conflicting_team_schedule")
            except (KeyError, TypeError, ValueError, IndexError) as e:
                valid = False; reason = str(e)
            decisions.append({"stage": "team_corroboration", "game_id": game["game_id"], "side": side,
                "url": value, "source_id": meta["source_id"], "http_status": meta["http_status"],
                "accepted": reason is None, "reason": reason, "discrepancies": delta})
            if reason is None:
                ids.append(meta["source_id"])
                for field in FIELDS: providers[field].append({"provider": "ESPN_" + side + "_schedule", "source_id": meta["source_id"]})
        if not valid: continue
        if match:
            ids.append(nba_meta["source_id"])
            for field in ("home_code", "away_code", "recorded_start_utc"):
                providers[field].insert(0, {"provider": "NBA", "source_id": nba_meta["source_id"]})
        game.update(nba_game_id=match[0]["nba_game_id"] if match else None,
            schedule_provider="NBA_corroborated_ESPN" if match else "ESPN_fallback",
            schedule_source_ids=ids)
        # Extra provenance stays in discovery audit, never the evidence schema.
        decisions.append({"stage": "accepted", "game_id": game["game_id"], "field_sources": providers,
            "display_names_source": {"provider": "ESPN_scoreboard", "source_id": board_meta["source_id"]},
            "game_date_derivation": "recorded_start_utc converted to America/New_York",
            "nba_game_id_source": {"provider": "NBA", "source_id": nba_meta["source_id"]} if match else None,
            "target_cutoff_utc": study.timing(game, now)["target_cutoff_utc"],
            "cutoff_derivation": "recorded_start_utc minus 86400 elapsed seconds"})
        games.append(game)
    return sorted(games, key=lambda g: (g["recorded_start_utc"], g["game_id"])), decisions


def _explicit_nba_time(doc, row):
    for day in doc.get("leagueSchedule", {}).get("gameDates", []):
        for game in day.get("games", []):
            if game.get("gameId") == row["nba_game_id"]:
                try: study.aware(game["gameDateTimeUTC"]); return True
                except (ValueError, TypeError): return False
    return False


def check_assets(committed=False):
    study.check_assets()
    assets = json.loads(REGISTRY.read_text())
    for name, sha in assets.items():
        body = (ROOT / name).read_bytes()
        if digest(body) != sha: raise ValueError("Operational amendment asset changed: " + name)
        if committed and subprocess.check_output(["git", "show", "HEAD:" + name], cwd=ROOT) != body:
            raise ValueError("Commit operational amendment before live discovery")
    if committed and subprocess.check_output(["git", "show", "HEAD:" + str(REGISTRY.relative_to(ROOT))], cwd=ROOT) != REGISTRY.read_bytes():
        raise ValueError("Commit operational registry first")
    return assets


def replay(folder):
    folder = Path(folder)
    authorization = json.loads((folder / "authorization.json").read_text())
    if authorization["assets"] != check_assets(): raise ValueError("Operational assets changed")
    if (folder / "failure.json").exists() and not (folder / "discovery.json").exists():
        failure = json.loads((folder / "failure.json").read_text())
        store = DocumentStore(folder / "discovery_raw", True, allowed_source)
        records = []
        for p in sorted((folder / "discovery_raw").glob("*.json")):
            meta = json.loads(p.read_text()); meta, _ = store.get(meta["url"])
            if len(meta["attempts"]) != 1: raise ValueError("Automatic source retry detected")
            records.append(meta)
        if failure["stop_reason"] == "access_denial" and not any(m["http_status"] in (401, 403, 407, 451)
                and not (m["url"] == NBA_SCHEDULES[0] and m["http_status"] == 403) for m in records):
            raise ValueError("No captured unauthorized denial supports the stop")
        return {"verified": True, "partial_failure": True, "source_records": len(records), "paid_calls": 0}
    saved = json.loads((folder / "discovery.json").read_text())
    if saved["assets"] != check_assets(): raise ValueError("Operational assets changed")
    session = SourceSession(folder / "discovery_raw", True)
    games, decisions = discover_verified(session, saved["started_at"], saved["days"])
    if games != saved["games"] or decisions != saved["decisions"]: raise ValueError("Schedule replay differs")
    if (folder / "forecasts/completion.json").exists(): study.verify_forecasts(folder / "evidence", folder / "forecasts")
    return {"verified": True, "games": len(games), "paid_calls": 0}


def export_audit(folder, output):
    folder, output = Path(folder), Path(output)
    replay(folder)
    sources = []
    for p in sorted((folder / "discovery_raw").glob("*.json")):
        meta = json.loads(p.read_text())
        sources.append({k: v for k, v in meta.items() if k != "headers"})
    audit = {"schema": "schedule_amendment_v1_audit", "private_raw_responses_included": False,
        "sources": sources, "original_stop_superseded_only_for_schedule_discovery": True}
    for name in ("authorization", "discovery", "plan", "completion", "failure"):
        if (folder / (name + ".json")).exists():
            value = json.loads((folder / (name + ".json")).read_text())
            if name == "failure": value.pop("source_records", None)
            audit[name] = value
    immutable_json(output / "audit.json", audit)
    immutable_json(output / "manifest.json", {"audit.json": digest((output / "audit.json").read_bytes())})
    return verify_audit(output)


def verify_audit(folder):
    folder = Path(folder); manifest = json.loads((folder / "manifest.json").read_text())
    if set(manifest) != {"audit.json"} or digest((folder / "audit.json").read_bytes()) != manifest["audit.json"]:
        raise ValueError("Public audit hash mismatch")
    audit = json.loads((folder / "audit.json").read_text())
    if audit["authorization"]["assets"] != check_assets() or audit["private_raw_responses_included"] is not False:
        raise ValueError("Operational assets/unsafe audit differ")
    ids = {m["source_id"] for m in audit["sources"]}
    for meta in audit["sources"]:
        if not allowed_source(meta["url"]) or len(meta["attempts"]) != 1 or "headers" in meta:
            raise ValueError("Unsafe source metadata or automatic retry")
    for d in audit.get("discovery", {}).get("decisions", []):
        if d.get("source_id") and d["source_id"] not in ids: raise ValueError("Unknown source reference")
        if d["stage"] == "accepted":
            for field in FIELDS:
                refs = d["field_sources"][field]
                if any(r["source_id"] not in ids for r in refs) or not all(
                        any(r["provider"] == "ESPN_" + side + "_schedule" for r in refs) for side in ("home", "away")):
                    raise ValueError("Both-team field corroboration missing")
    return {"verified": True, "scope": "sanitized hashes and source references; private documents needed for extraction replay",
        "source_records": len(ids), "verified_games": len(audit.get("discovery", {}).get("games", []))}


def run_attempt(output=ATTEMPT, allow_paid=False, clock=time.time, opener=None, require_committed=True):
    assets = check_assets(require_committed); output = Path(output)
    if require_committed and output.resolve() != ATTEMPT.resolve(): raise ValueError("One fixed newly authorized discovery attempt only")
    if STOP.exists(): raise ValueError("New access-denial journal blocks further live requests")
    original = json.loads(study.STOP.read_text())
    if original.get("reason") != "access_denial" or original.get("http_status") != 403 or original.get("url") != NBA_SCHEDULES[0]:
        raise ValueError("Amendment only supersedes the original NBA schedule 403")
    output.mkdir(parents=True, exist_ok=False)
    immutable_json(output / "authorization.json", {"amendment_sha256": digest(AMENDMENT.read_bytes()),
        "original_stop_sha256": digest(study.STOP.read_bytes()), "original_stop_path": os.path.relpath(study.STOP, ROOT),
        "operator_authorization": "one discovery attempt; original Phase1 paid caps only after eligible fixture",
        "allow_paid_if_eligible": allow_paid, "created_at_utc": iso(clock()), "assets": assets})
    budget = study.PilotBudget(output, clock, STOP)
    session = ScheduleSession(output / "discovery_raw", budget, opener=opener)
    start = clock()
    try:
        games, decisions = discover_verified(session, start)
        completed = clock()
        discovery = {"started_at": start, "captured_at_utc": iso(completed), "days": 3,
            "games": games, "decisions": decisions, "assets": assets}
        immutable_json(output / "discovery.json", discovery)
        eligible = study.select_game(games, completed, eligible_only=True)
        nearest = study.select_game(games, completed)
        immutable_json(output / "plan.json", {**study.dry_plan(json.loads(study.CONFIG.read_text()), eligible or nearest, completed),
            "live_access_blocked": False, "original_denial_preserved": True,
            "amendment": str(AMENDMENT.relative_to(ROOT)), "eligible_game_confirmed": eligible is not None})
        status = "discovery_validated_no_window" if not eligible else "eligible_collection_not_enabled"
        if eligible and allow_paid:
            for env in ("BRAVE_SEARCH_API_KEY", "ANTHROPIC_API_KEY"):
                if not os.environ.get(env): raise ValueError("Required provider credential is unavailable: " + env)
            # Discovery-specific exception ends here. Source/inference transports
            # remain the original strict first-denial-stop implementations.
            sources = study.StudySession(output / "evidence/raw", budget, lambda: study.game_guard(eligible, clock()), opener=opener)
            packet = study.collect_game(output / "evidence", json.loads(study.CONFIG.read_text()), eligible, discovery, sources, budget, clock)
            forecasts = study.forecast_bundle(output / "evidence", output / "forecasts", budget, clock=clock)
            status = "forecasts_sealed"
            immutable_json(output / "forecast_link.json", {"packet_sha256": packet["evidence_snapshot_sha256"], "completion": forecasts})
        result = {"status": status if games else "discovery_no_verified_games", "verified_games": len(games),
            "selected_game": eligible or nearest, "eligible_game_confirmed": eligible is not None,
            "completed_at_utc": iso(clock()), "public_requests": session.used,
            "paid_requests_reserved": sum(e["kind"] in ("anthropic", "brave") for e in budget.entries()),
            "reserved_usd": sum(e["reserved_usd"] for e in budget.entries())}
        immutable_json(output / "completion.json", result)
        return result
    except (study.Halt, Exception, KeyboardInterrupt) as e:
        failure = {"status": "failed", "error_type": type(e).__name__, "reason": str(e), "at_utc": iso(clock()),
            "stop_reason": budget.reason, "public_requests": session.used,
            "paid_requests_reserved": sum(e["kind"] in ("anthropic", "brave") for e in budget.entries()),
            "reserved_usd": sum(e["reserved_usd"] for e in budget.entries()), "source_records": session.records}
        immutable_json(output / "failure.json", failure)
        return failure


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--live-attempt", action="store_true"); p.add_argument("--allow-network", action="store_true")
    p.add_argument("--allow-search", action="store_true"); p.add_argument("--allow-inference", action="store_true")
    p.add_argument("--replay", type=Path)
    p.add_argument("--export-audit", type=Path); p.add_argument("--output", type=Path)
    p.add_argument("--verify-audit", type=Path)
    a = p.parse_args()
    if a.export_audit or a.verify_audit:
        if any((a.live_attempt, a.allow_network, a.allow_search, a.allow_inference, a.replay)): p.error("Audit commands are offline")
        if a.export_audit:
            if not a.output: p.error("Audit export requires a separate output directory")
            result = export_audit(a.export_audit, a.output)
        else: result = verify_audit(a.verify_audit)
    elif a.replay:
        if any((a.live_attempt, a.allow_network, a.allow_search, a.allow_inference)): p.error("Replay is offline")
        result = replay(a.replay)
    elif a.live_attempt:
        if not a.allow_network: p.error("Live discovery requires explicit network authorization")
        if a.allow_search != a.allow_inference: p.error("Both paid opt-ins are required to collect/forecast an eligible game")
        result = run_attempt(allow_paid=a.allow_search and a.allow_inference)
    else:
        if any((a.allow_network, a.allow_search, a.allow_inference)): p.error("Default dry run makes no network requests")
        result = {"dry_run": True, "network_calls": 0, "paid_calls": 0, "amendment": str(AMENDMENT.relative_to(ROOT)),
            "plan": "NBA primary once; ESPN daily scoreboards and both team schedules; collect/infer only within original window",
            "original_stop_present": study.STOP.exists(), "new_stop_present": STOP.exists(), "attempt_exists": ATTEMPT.exists(),
            "limits": {"anthropic": 20, "brave": 2, "articles": 4, "reserved_usd": 1}}
    print(json.dumps(result, indent=2))


if __name__ == "__main__": main()
