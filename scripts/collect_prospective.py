#!/usr/bin/env python3
"""One-game prospective evidence collection. Default is an offline, no-cost plan."""

import argparse
import json
import os
import re
import time
import urllib.parse
from dataclasses import asdict
from datetime import datetime, timezone
from math import isfinite
from pathlib import Path

from evidence_documents import DocumentStore, canonical, digest
from investigate_kalshi import iso, timestamp
from prospective_research import (Budget, Ledger, allowed_page, planned_queries, prospective_guard,
                                  prospective_packet, research)
from prospective_sources import (SourceSession, collect_history, collect_official, discover,
                                 official_at_snapshot, statistical_sections)
from research_providers import BraveAnthropicProvider
from shared_evidence import freeze_packet, load_game_snapshot


def write_json(path, value):
    data = canonical(value) + b"\n"
    if path.exists() and path.read_bytes() != data:
        raise ValueError("Capture output already exists with different contents: " + str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def choose_game(games, now, game_id=None):
    eligible = [g for g in games if g["scheduled"] and g["counts_in_regular_season"]
                and g["time_valid"] and timestamp(g["recorded_start_utc"]) > now]
    if game_id:
        eligible = [g for g in eligible if g["game_id"] == game_id]
    if not eligible:
        raise ValueError("No eligible upcoming regular-season game in the captured discovery window")
    return min(eligible, key=lambda g: (abs(timestamp(g["recorded_start_utc"]) - 86400 - now), g["game_id"]))


def check_config(config):
    if set(config) - {"search_provider", "llm_provider", "model", "model_endpoint", "search_key_env", "llm_key_env",
            "discovery_days", "max_public_requests", "max_injury_reports", "injury_team_catalog", "budget", "prices"}:
        raise ValueError("Unknown configuration fields; credentials must be environment variables")
    if config.get("search_provider") != "brave" or config.get("llm_provider") not in {"anthropic", "json_gateway"}:
        raise ValueError("Choose a supported search and extraction provider")
    if "model_endpoint" in config:
        endpoint = urllib.parse.urlsplit(config["model_endpoint"])
        if endpoint.scheme != "https" or not endpoint.hostname or endpoint.username or endpoint.password:
            raise ValueError("Model endpoint must be HTTPS and contain no credentials")
    for field in ("search_key_env", "llm_key_env"):
        if field in config and not re.fullmatch(r"[A-Z_][A-Z0-9_]*", config[field]):
            raise ValueError("Credential configuration must name an environment variable")
    budget = Budget(**config.get("budget", {}))
    Ledger(budget)
    prices = config["prices"]
    for key in ("query_usd", "page_usd", "input_usd_per_million", "output_usd_per_million"):
        if type(prices.get(key)) not in (int, float) or not isfinite(prices[key]) or prices[key] < 0:
            raise ValueError("Explicit finite nonnegative conservative cost estimates required")
    if (type(config.get("discovery_days", 3)) is not int or type(config.get("max_public_requests", 190)) is not int
            or not 1 <= config.get("discovery_days", 3) <= 7 or not 1 <= config.get("max_public_requests", 190) <= 220):
        raise ValueError("Invalid bounded public-source configuration")
    return budget


def plan(config, game=None, now=None):
    now = time.time() if now is None else now
    budget = check_config(config)
    return {"dry_run": True, "network_calls": 0, "inference_calls": 0, "selected_game": game,
        "target_cutoff_utc": iso(timestamp(game["recorded_start_utc"]) - 86400) if game else None,
        "planned_queries": planned_queries(game, budget) if game else [], "research_budget": asdict(budget),
        "max_public_requests": config.get("max_public_requests", 190),
        "credentials_present": {"search": bool(os.environ.get(config.get("search_key_env", "BRAVE_SEARCH_API_KEY"))),
                                "inference": bool(os.environ.get(config.get("llm_key_env", "ANTHROPIC_API_KEY")))},
        "expected_outputs": ["evidence_packet.json", "evidence_snapshot_manifest.json", "bundle_manifest.json",
                             "evidence_audit.md", "lineage.json", "raw/", "news_raw/", "provider_captures/"],
        "limitation": None if game else "Supply an existing --schedule-capture for offline game selection; discover separately with free network opt-in."}


def assemble(game, history, injuries, news, started, snapshot, created):
    prospective_guard(game, snapshot, snapshot, "prospective")
    packet = prospective_packet(game, snapshot, news)
    stats, stat_lineage = statistical_sections(game, history, snapshot)
    official, injury_lineage = official_at_snapshot(game, injuries, snapshot)
    packet.update(stats)
    packet["injury_news"]["official_injury"] = official
    target = timestamp(game["recorded_start_utc"]) - 86400
    delta = round(snapshot - target, 6)
    packet["snapshot_timing"] = {"target_cutoff_utc": iso(target), "collection_started_at_utc": iso(started),
        "actual_snapshot_utc": iso(snapshot), "packet_created_at_utc": iso(created), "deviation_seconds": delta,
        "status": "late" if delta > 0 else "early" if delta < 0 else "at_target", "strict_t24h_eligible": delta == 0}
    return packet, {"statistics": stat_lineage, "injuries": injury_lineage,
                    "statistical_missingness": history["decisions"]}


def no_research():
    return {"news": {"state": "not_collected", "findings": [], "missing_reason": "paid_search_not_enabled"},
            "audit": {"agent_candidates": [], "sources_and_validation": [], "finding_decisions": [],
                      "decisions": [{"reason": "paid_search_not_enabled"}]}}


def run_components(folder, config, session, game, started, allow_search=False, allow_model=False,
                   clock=time.time, replay_run=None, provider=None):
    """Run once; a replay uses original clocks and immutable captured responses."""
    replay = replay_run is not None
    settings = {"config": config, "allow_search": allow_search, "allow_model": allow_model}
    clocks = dict(replay_run["clocks"]) if replay else {"started": started}
    def mark(key):
        if not replay:
            clocks[key] = clock()
        return clocks[key]
    before_history = mark("history_started")
    prospective_guard(game, before_history, before_history, "prospective")
    if not game.get("scheduled") or not game.get("counts_in_regular_season"):
        raise ValueError("Only scheduled regular-season games are eligible")
    history = collect_history(session, game, before_history)
    injuries = collect_official(session, game, mark("injury_started"), config.get("max_injury_reports", 8),
                               use_team_catalog=config.get("injury_team_catalog", False))
    news_result = no_research()
    if allow_search:
        provider = provider or BraveAnthropicProvider(config, folder / "provider_captures",
                    allow_network=not replay, allow_model=allow_model, replay=replay)
        documents = DocumentStore(folder / "news_raw", replay, allowed_page)
        begin = mark("research_started")
        def validation_clock():
            return mark("research_validation")
        news_result = research(game, begin, provider, documents.get, check_config(config), config["prices"],
            now=begin, use_model=allow_model, live_window=True, clock=validation_clock)
        news_result["audit"]["provider_requests"] = provider.http.calls
        news_result["audit"]["actual_provider_usage"] = provider.usage
    snapshot, created = mark("snapshot"), mark("created")
    # A game that starts/completes during collection cannot be published as prospective.
    prospective_guard(game, snapshot, snapshot, "prospective")
    for meta in session.records:
        if timestamp(meta["retrieved_at_utc"]) > snapshot:
            raise ValueError("Public source retrieved after actual snapshot")
    for meta in news_result["audit"].get("sources_and_validation", []) + news_result["audit"].get("provider_requests", []):
        if timestamp(meta["retrieved_at_utc"]) > snapshot:
            raise ValueError("Research response retrieved after actual snapshot")
    packet, lineage = assemble(game, history, injuries, news_result["news"], started, snapshot, created)
    lineage["public_sources"] = session.records
    if history["history"]:
        lineage["historical_game_facts"] = history["history"]  # audit only, never model context
    lineage["news"] = news_result["audit"]
    run = {"game": game, "clocks": clocks, "settings": settings}
    return packet, lineage, run


def audit_text(packet, lineage):
    timing = packet["snapshot_timing"]
    lines = ["# Prospective evidence audit", "", f"Game: {packet['game_id']}; {packet['away']['team_name']} at {packet['home']['team_name']}.",
        f"Recorded tipoff: {packet['recorded_tipoff_utc']}. Target T−24h: {timing['target_cutoff_utc']}.",
        f"Actual snapshot: {timing['actual_snapshot_utc']}; packet created: {timing['packet_created_at_utc']}.",
        f"Timing: **{timing['status']}**, deviation {timing['deviation_seconds']} seconds; strict T−24h eligible: **{timing['strict_t24h_eligible']}**.",
        "", "## Structured statistics", ""]
    for side in ("home", "away"):
        team = packet[side]
        lines.append(f"* {team['team_name']}: " + json.dumps({k: v for k, v in team.items() if k not in {"team_id", "team_name", "designation"}}, sort_keys=True))
    official = packet["injury_news"]["official_injury"]
    lines += ["", "## Official injuries", "", f"Verification: {official['publication_verification']}; issue: {official['report_issue_utc']}; availability bound: {official['published_at_utc']}.",
              f"Source: {official['report_url'] or 'unavailable'}. Method: deterministic pypdf coordinates; no healthy-player inference."]
    for side in ("home", "away"):
        team = official[side]
        lines.append(f"* {side}: {team['state']}; flags: {team['uncertainty_flags']}")
        for player in team["players"]:
            lines.append(f"  * {player['player']}: {player['status']}; {player['reason']}; reference {player['source_ref']}; flags {player['uncertainty_flags']}")
    lines += ["", "## News findings", "", "Method: bounded model extraction followed by deterministic citation, timestamp, team and verbatim-support checks."]
    for finding in packet["injury_news"]["news"]["findings"]:
        lines.append(f"* [{finding['category']}] {finding['claim']} — {finding['source_url']} (published {finding['published_at_utc']}; retrieved {finding['retrieved_at_utc']}).")
        for ref in finding["source_references"]:
            lines.append(f"  * {ref['source_ref']}: {ref['supporting_excerpt']}")
    if not packet["injury_news"]["news"]["findings"]:
        lines.append("No validated findings; " + str(packet["injury_news"]["news"]["missing_reason"]) + ". This does not imply availability.")
    lines += ["", "## Rejections and limitations", ""]
    for meta in lineage["public_sources"]:
        if meta["http_status"] != 200 or meta.get("truncated"):
            lines.append(f"* Public source rejected: HTTP {meta['http_status']}; {meta['url']}; retrieved {meta['retrieved_at_utc']}; truncated={meta.get('truncated', False)}.")
    for group in (lineage["statistical_missingness"], lineage["injuries"]["candidate_decisions"],
                  lineage["news"].get("sources_and_validation", []), lineage["news"].get("finding_decisions", []),
                  lineage["news"].get("decisions", [])):
        for decision in group:
            if decision.get("reason") or decision.get("rejection_reason"):
                lines.append("* " + json.dumps(decision, sort_keys=True))
    lines += ["* Schedule source and all raw bodies/clocks/hashes are in lineage.json; raw documents are audit-only.",
              "* Source publication metadata is not independent first-publication/version proof. Global latest-report coverage is not certified.",
              "* Early/late snapshots do not qualify as exact T−24h captures. No probabilities or market prices are included.", ""]
    return "\n".join(lines)


def save_completed(folder, packet, lineage, run, discovery):
    frozen = freeze_packet(packet, folder / "evidence_captures")
    write_json(folder / "evidence_packet.json", frozen)
    write_json(folder / "lineage.json", lineage)
    write_json(folder / "run.json", run)
    write_json(folder / "discovery.json", discovery)
    write_json(folder / "evidence_snapshot_manifest.json", {"games": [{"game_id": frozen["game_id"],
        "cutoff_utc": frozen["cutoff_utc"], "sha256": frozen["evidence_snapshot_sha256"],
        "capture_file": "evidence_captures/" + frozen["evidence_snapshot_sha256"] + ".json"}]})
    (folder / "evidence_audit.md").write_text(audit_text(frozen, lineage))
    files = {str(p.relative_to(folder)): digest(p.read_bytes()) for p in sorted(folder.rglob("*"))
             if p.is_file() and p.name != "bundle_manifest.json"}
    write_json(folder / "bundle_manifest.json", {"files": files, "packet_sha256": frozen["evidence_snapshot_sha256"]})
    return frozen


def verify_bundle(folder):
    folder = Path(folder).resolve()
    manifest = json.loads((folder / "bundle_manifest.json").read_text())
    for name, expected in manifest["files"].items():
        path = (folder / name).resolve()
        if folder not in path.parents or digest(path.read_bytes()) != expected:
            raise ValueError("Frozen bundle hash mismatch: " + name)
    return manifest


def load_for_consumer(folder, method):
    if method not in {"direct_llm", "leap"}:
        raise ValueError("Unknown evidence consumer")
    manifest = verify_bundle(folder)
    run = json.loads((Path(folder) / "run.json").read_text())
    packet = load_game_snapshot(folder, run["game"]["game_id"])
    if packet["evidence_snapshot_sha256"] != manifest["packet_sha256"]:
        raise ValueError("Consumer snapshot differs from bundle")
    return packet


def replay(folder):
    folder = Path(folder)
    verify_bundle(folder)
    run = json.loads((folder / "run.json").read_text())
    settings, game = run["settings"], run["game"]
    session = SourceSession(folder / "raw", True, settings["config"].get("max_public_requests", 190))
    discovery = json.loads((folder / "discovery.json").read_text())
    games, _ = discover(session, discovery["started_at"], settings["config"].get("discovery_days", 3))
    if choose_game(games, discovery["started_at"], game["game_id"]) != game:
        raise ValueError("Schedule replay differs")
    packet, lineage, _ = run_components(folder, settings["config"], session, game, run["clocks"]["started"],
        settings["allow_search"], settings["allow_model"], replay_run=run)
    if digest(canonical(packet)) != load_for_consumer(folder, "direct_llm")["evidence_snapshot_sha256"]:
        raise ValueError("Offline packet reproduction differs")
    if canonical(lineage) != canonical(json.loads((folder / "lineage.json").read_text())):
        raise ValueError("Offline lineage reproduction differs")
    return load_for_consumer(folder, "leap")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="examples/prospective_config.example.json")
    parser.add_argument("--schedule-capture", help="Previously captured discovery directory for offline planning")
    parser.add_argument("--game-id", help="One eligible ESPN game ID; default closest T−24h target")
    parser.add_argument("--output", help="New capture directory; existing captures are never overwritten")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--discover", action="store_true", help="Free public schedule GETs only")
    parser.add_argument("--live", action="store_true", help="Collect one upcoming game")
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--allow-search", action="store_true", help="Opt into paid Brave search")
    parser.add_argument("--allow-inference", action="store_true", help="Separately opt into paid extraction")
    parser.add_argument("--replay", help="Offline verification/reproduction of a completed capture")
    args = parser.parse_args()
    if args.replay:
        if args.live or args.discover or args.allow_network or args.allow_search or args.allow_inference:
            parser.error("Replay cannot enable live providers")
        print(json.dumps({"reproduced_sha256": replay(args.replay)["evidence_snapshot_sha256"]}))
        return
    config = json.loads(Path(args.config).read_text())
    check_config(config)
    now = time.time()
    if args.dry_run or not (args.live or args.discover):
        game = None
        if args.schedule_capture:
            saved = json.loads((Path(args.schedule_capture) / "discovery.json").read_text())
            # Verify original source bodies instead of trusting a supplied game projection.
            session = SourceSession(Path(args.schedule_capture) / "raw", True)
            games, _ = discover(session, saved["started_at"], config.get("discovery_days", 3))
            game = choose_game(games, now, args.game_id)
        print(json.dumps(plan(config, game, now), indent=2))
        return
    if not args.allow_network or args.live and args.discover:
        parser.error("Choose one operation and explicitly enable public network GETs")
    if args.allow_inference and not args.allow_search:
        parser.error("Inference requires search opt-in and validated captured sources")
    if args.discover and (args.allow_search or args.allow_inference):
        parser.error("Discovery does not call paid providers")
    if args.allow_search and not os.environ.get(config.get("search_key_env", "BRAVE_SEARCH_API_KEY")):
        parser.error("Brave credential unavailable; no paid calls made")
    if args.allow_inference and not os.environ.get(config.get("llm_key_env", "ANTHROPIC_API_KEY")):
        parser.error("Anthropic credential unavailable; no inference calls made")
    out = Path(args.output or ("captures/prospective/" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")))
    out.mkdir(parents=True, exist_ok=False)
    session = SourceSession(out / "raw", False, config.get("max_public_requests", 190))
    try:
        games, decisions = discover(session, now, config.get("discovery_days", 3))
        discovery = {"started_at": now, "games": games, "decisions": decisions, "captured_at_utc": iso(time.time())}
        if args.discover:
            write_json(out / "discovery.json", discovery)
            print(json.dumps({"games": games, "capture_directory": str(out)}, indent=2))
            return
        game = choose_game(games, time.time(), args.game_id)
        packet, lineage, run = run_components(out, config, session, game, now, args.allow_search, args.allow_inference)
        frozen = save_completed(out, packet, lineage, run, discovery)
        assert load_for_consumer(out, "direct_llm") == load_for_consumer(out, "leap")
        print(json.dumps({"capture_directory": str(out), "sha256": frozen["evidence_snapshot_sha256"],
                          "timing": frozen["snapshot_timing"]}, indent=2))
    except Exception as exc:
        write_json(out / "failure.json", {"error_type": type(exc).__name__, "error": str(exc), "at_utc": iso(time.time())})
        raise


if __name__ == "__main__":
    main()
