#!/usr/bin/env python3
"""One-game prospective evidence -> frozen Direct/v1/v2 orchestration.

No evaluation/market imports. Default is a no-cost configuration dry run.
"""
import argparse
import copy
import gzip
import json
import math
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

import collect_prospective as collection
import direct_forecast as direct
import leap_forecast as v1
import leap_v2_forecast as v2
import leap_v2_evidence as v2_evidence
from evidence_documents import DocumentStore, canonical, digest
from forecast_split import ROOT, immutable_json
from investigate_kalshi import iso, timestamp
from prospective_research import Budget, allowed_page, planned_queries, research
from prospective_sources import (SourceSession, allowed_source, collect_history, collect_official,
    discover, official_at_snapshot, statistical_sections)
from research_providers import BraveAnthropicProvider, CapturedHTTP, ProviderError
from run_v2_development import response_category
from shared_evidence import load_game_snapshot

BASE = ROOT / "captures/prospective_phase1"
STOP = BASE / "access_denial.json"
CONFIG = ROOT / "examples/prospective_study.json"
PROTOCOL = ROOT / "experiments/prospective_phase1_protocol.md"
REGISTRY = ROOT / "experiments/prospective_phase1_assets.json"
CACHES = {"direct": ROOT / "captures/forecast_cache", "v1": v1.DEFAULT_CACHE, "v2": v2.DEFAULT_CACHE}
MODULES = {"direct": direct, "v1": v1, "v2": v2}
ORDER = ("direct", "v2", "v1")


class Halt(BaseException):
    """Escapes research's recoverable-source exception handlers."""


def aware(value):
    if not isinstance(value, str): raise ValueError("Timestamp must be an explicit timezone-aware string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None: raise ValueError("Explicit timezone required")
    return parsed.timestamp()


def timing(game, now):
    target = aware(game["recorded_start_utc"]) - 86400
    delta = now - target
    return {"target_cutoff_utc": iso(target), "actual_utc": iso(now), "deviation_seconds": round(delta, 6),
        "exact_t24h": delta == 0, "within_tolerance": abs(delta) <= 300,
        "status": "exact" if delta == 0 else "early_within_tolerance" if -300 <= delta < 0 else
        "late_within_tolerance" if 0 < delta <= 300 else "early_outside_tolerance" if delta < 0 else "late_outside_tolerance"}


def game_guard(game, now, window=True):
    if (not game.get("scheduled") or not game.get("time_valid") or not game.get("counts_in_regular_season")
            or game.get("excluded_fixture") or timestamp(game["recorded_start_utc"]) <= now):
        raise ValueError("Only a currently scheduled upcoming regular-season game is allowed")
    if window and not timing(game, now)["within_tolerance"]:
        raise ValueError("Outside the fixed T−24h ±300-second collection window")


def select_game(games, now, gid=None, eligible_only=False):
    selected = []
    for g in games:
        if gid and g["game_id"] != gid: continue
        try: game_guard(g, now, eligible_only)
        except ValueError: continue
        selected.append(g)
    return min(selected, key=lambda g: (abs(timing(g, now)["deviation_seconds"]), g["game_id"])) if selected else None


def same_schedule(a, b):
    return all(a.get(k) == b.get(k) for k in ("game_id", "home_id", "away_id", "recorded_start_utc", "neutral_site", "nba_game_id"))


def check_assets():
    v2_evidence.frozen_assets(); v1.frozen_assets()
    assets = json.loads(REGISTRY.read_text())
    for name, sha in assets.items():
        if digest((ROOT / name).read_bytes()) != sha: raise ValueError("Precommitted prospective asset changed: " + name)
    return assets


class PilotBudget:
    """Append-only reservations for the entire collection+forecast operation."""
    def __init__(self, folder, clock=time.time, stop_path=STOP):
        self.folder, self.clock, self.stop_path = Path(folder), clock, Path(stop_path)
        self.reason = None

    def entries(self): return [json.loads(p.read_text()) for p in sorted((self.folder / "reservations").glob("*.json"))]

    def stop(self, reason, **details):
        self.reason = reason
        value = {"reason": reason, "at_utc": iso(self.clock()), **details}
        if reason == "access_denial": value["requires_new_operator_authorization"] = True
        immutable_json(self.folder / "stop.json", value)
        if reason == "access_denial": immutable_json(self.stop_path, value)

    def reserve(self, key, kind, amount, wire_sha256=None):
        if self.reason: raise Halt(self.reason)
        if type(amount) not in (int, float) or not math.isfinite(amount) or amount < 0: raise ValueError("Invalid reservation")
        entries = self.entries()
        if any(r["key"] == key for r in entries): raise Halt("Claimed request cannot be resent")
        limits = {"anthropic": 20, "brave": 2, "article": 4}
        if kind not in limits or sum(r["kind"] == kind for r in entries) >= limits[kind] or math.fsum(r["reserved_usd"] for r in entries) + amount > 1 + 1e-12:
            self.stop("budget_exhausted", next_kind=kind); raise Halt("Global pilot budget exhausted before request")
        entry = {"key": key, "kind": kind, "reserved_usd": amount, "reserved_at_utc": iso(self.clock()), "wire_sha256": wire_sha256}
        immutable_json(self.folder / "reservations" / (digest(key.encode()) + ".json"), entry)


class OneShotDocuments(DocumentStore):
    """Reuse document format/allowlist/hash replay, with one HTTP attempt only."""
    def __init__(self, folder, offline, allowed, budget=None, article=False, guard=lambda: None,
            clock=time.time, opener=None):
        super().__init__(folder, offline, allowed)
        self.budget, self.article, self.guard, self.clock = budget, article, guard, clock
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl): return None
        self.opener = opener or urllib.request.build_opener(NoRedirect)

    def _get(self, url):
        key = digest(url.encode()); meta_path = self.folder / (key + ".json")
        if self.offline or meta_path.exists(): return super()._get(url)
        self.guard()
        if self.article: self.budget.reserve("article:" + key, "article", 0)
        start = iso(self.clock())
        try:
            with self.opener.open(urllib.request.Request(url, headers={"User-Agent": "nba-prospective-study/1.0"}), timeout=30) as r:
                body, status, headers = r.read(5_000_001), r.status, dict(r.headers.items())
        except urllib.error.HTTPError as e: body, status, headers = e.read(5_000_001), e.code, dict(e.headers.items())
        except OSError as e: body, status, headers = type(e).__name__.encode(), 0, {}
        end = iso(self.clock())
        meta = {"source_id": key, "url": url, "http_status": status, "retrieved_at_utc": end,
            "attempts": [{"started_at_utc": start, "finished_at_utc": end, "http_status": status}],
            "headers": {k.lower(): v for k, v in headers.items()}, "body_sha256": digest(body),
            "body_size": len(body), "truncated": len(body) > 5_000_000}
        (self.folder / (key + ".body.gz")).write_bytes(gzip.compress(body, mtime=0)); immutable_json(meta_path, meta)
        if status in (401, 403, 407, 451):
            if self.budget: self.budget.stop("access_denial", http_status=status, url=url)
            raise Halt("Access denial; stop without fallback/retry")
        self.guard()
        return meta, body


class PilotHTTP(CapturedHTTP):
    def __init__(self, folder, allow_network, budget, guard, expected=None, opener=None):
        super().__init__(folder, allow_network, opener, budget.clock)
        self.budget, self.guard, self.expected = budget, guard, expected

    def request(self, provider, method, url, payload, headers, max_bytes):
        self.guard()
        wire = {"provider": provider, "method": method, "url": url, "payload": payload}; key = digest(canonical(wire))
        if (self.folder / (key + ".json")).exists(): raise Halt("No provider request retries in the prospective pilot")
        if self.expected:
            if key != self.expected["wire_sha256"]: raise Halt("Forecast request differs from frozen specification")
        else:
            kind = "brave" if provider == "brave" else "anthropic"
            cost = .01 if kind == "brave" else ((len(canonical(payload)) + 4096) * 3 + payload["max_tokens"] * 15) / 1e6
            self.budget.reserve("research:" + key, kind, cost, key)
        try: result = super().request(provider, method, url, payload, headers, max_bytes)
        except ProviderError:
            if self.calls and self.calls[-1]["http_status"] in (401, 403, 407, 451):
                self.budget.stop("access_denial", http_status=self.calls[-1]["http_status"], provider=provider)
            raise
        error = result.get("error")
        if isinstance(error, dict) and (error.get("type") in ("forbidden", "permission_error", "authentication_error", "unauthorized")
                or any(s in str(error.get("message", "")).casefold() for s in ("access denied", "request not allowed", "permission denied", "unauthorized"))):
            self.budget.stop("access_denial", http_status=200, provider=provider)
            raise ProviderError("Provider access denial")
        return result


class StudySession(SourceSession):
    def __init__(self, folder, budget, guard=lambda: None, opener=None):
        super().__init__(folder, False, 190, OneShotDocuments(folder, False, allowed_source, budget, guard=guard, clock=budget.clock, opener=opener))
        self.target_id = None

    def get(self, url):
        if self.target_id and url.endswith("/summary?event=" + self.target_id): raise Halt("Target-game outcome endpoint is forbidden during collection")
        return super().get(url)

    def json(self, value):
        meta, doc = super().json(value)
        if not isinstance(doc, dict): return meta, doc
        doc = copy.deepcopy(doc)
        def dated(event, key):
            try: aware(event[key]); return True
            except (ValueError, TypeError, KeyError, AttributeError): return False
        if "events" in doc:
            doc["events"] = [e for e in doc["events"] if dated(e, "date")]
            if self.target_id and getattr(self, "registry_game", None) and "/schedule?" in value:
                from prospective_sources import event_projection
                target = [e for e in doc["events"] if str(e.get("id")) == self.target_id]
                if len(target) != 1: return meta, None
                projected = event_projection(target[0]); expected = self.registry_game
                if not projected["scheduled"] or not projected["counts_in_regular_season"] or any(
                        projected[k] != expected[k] for k in ("home_id", "away_id", "recorded_start_utc", "neutral_site")):
                    return meta, None
        for day in doc.get("leagueSchedule", {}).get("gameDates", []):
            day["games"] = [g for g in day.get("games", []) if dated(g, "gameDateTimeUTC")]
        if "/summary?" in value:
            fields = [(doc.get("article", {}), "published"), (doc.get("article", {}), "lastModified"),
                (doc.get("meta", {}), "lastUpdatedAt")]
            fields += [(p, "wallclock") for p in doc.get("plays", []) if str(p.get("type", {}).get("id")) == "402"]
            if any(not dated(o, k) for o, k in fields): return meta, None
        return meta, doc


def strict_packet(game, history, injuries, news, started, snapshot, created, public_sources):
    cap = min(snapshot, timestamp(game["recorded_start_utc"]) - 86400)
    filtered = copy.deepcopy(history); rejected = []
    for fact in filtered["history"]:
        if fact["available_by_utc"] and timestamp(fact["available_by_utc"]) > cap:
            rejected.append({"game_id": fact["game_id"], "reason": "source_available_after_designated_cutoff"})
            fact["available_by_utc"] = None
    # A late, newly retrieved season schedule is not an as-of-cutoff version.
    for meta in public_sources:
        if "/schedule?" in meta["url"] and timestamp(meta["retrieved_at_utc"]) > cap:
            for side in ("home", "away"):
                if "/teams/" + game[side + "_id"] + "/" in meta["url"]: filtered["complete"][side] = False
    packet, lineage = collection.assemble(game, filtered, injuries, news, started, snapshot, created, extended=True, tolerance=300)
    official, injury_audit = official_at_snapshot(game, injuries, cap)
    packet["injury_news"]["official_injury"] = official; lineage["injuries"] = injury_audit
    # Frozen v2 permits this conservative qualifier. It describes unversioned
    # timestamped statistical payloads, not when collection occurred. The actual
    # prospective mode and capture clocks remain explicit in run and timing.
    packet["reconstruction_status"] = "timestamped_history_unversioned_payloads"
    lineage.update(source_information_cutoff_utc=iso(cap), source_cutoff_rejections=rejected)
    for f in news["findings"]:
        if any(timestamp(f[k]) > cap for k in ("published_at_utc", "retrieved_at_utc")):
            raise ValueError("News beyond the designated source cutoff")
    complete = all(filtered["complete"].get(s) and "regular_season_record" in packet[s] for s in ("home", "away"))
    lineage["evidence_complete"] = complete
    return packet, lineage


def packet_eligibility(packet, run, lineage):
    t = packet["snapshot_timing"]; game = run["game"]
    within = all(timing(game, timestamp(t[k]))["within_tolerance"] for k in
        ("collection_started_at_utc", "actual_snapshot_utc", "packet_created_at_utc"))
    return {"exact_capture": t["strict_t24h_eligible"], "within_tolerance": within,
        "evidence_complete": bool(lineage.get("evidence_complete")),
        "eligible": within and bool(lineage.get("evidence_complete")) and run.get("mode") == "prospective_live",
        "mock": run.get("mode") == "offline_mock", "actual_capture_utc": t["actual_snapshot_utc"],
        "target_cutoff_utc": t["target_cutoff_utc"], "source_information_cutoff_utc": lineage["source_information_cutoff_utc"]}


def specs_for_bundle(folder, mock=False):
    check_assets(); bundle = collection.verify_bundle(folder); game = json.loads((Path(folder) / "run.json").read_text())["game"]
    packet = direct.load_evidence(folder, game["game_id"])
    if packet["evidence_snapshot_sha256"] != bundle["packet_sha256"]: raise ValueError("Snapshot differs from bundle")
    cfg = {"direct": json.loads(direct.DEFAULT_CONFIG.read_text()), "v1": json.loads(v1.DEFAULT_CONFIG.read_text()), "v2": v2_evidence.config()}
    if mock:
        for c in cfg.values(): c["provider"] = "mock"
    specs = {"direct": [direct.request_spec(packet, cfg["direct"])],
        "v1": [v1.group_spec(g, cfg["v1"]) for g in v1.build_groups(packet)],
        "v2": [v2_evidence.group_spec(g, cfg["v2"]) for g in v2_evidence.build_groups(packet)]}
    return packet, cfg, specs


def forecast_bundle(folder, output, budget, mock=False, caches=None, clock=time.time, transport_factory=None, seal_only=False):
    folder, output = Path(folder), Path(output)
    packet, cfg, specs = specs_for_bundle(folder, mock)
    run = json.loads((folder / "run.json").read_text()); lineage = json.loads((folder / "lineage.json").read_text())
    eligibility = packet_eligibility(packet, run, lineage)
    if not eligibility["eligible"] and not (mock and eligibility["mock"] and eligibility["evidence_complete"] and eligibility["within_tolerance"]): raise ValueError("Frozen evidence is off-time, incomplete or not prospective")
    caches = caches or CACHES
    for n, c in caches.items(): v1.protect_paths(output, c, folder)
    identity = {"schema_version": 1, "mode": "offline_mock" if mock else "prospective_live", "game": run["game"],
        "packet_sha256": packet["evidence_snapshot_sha256"], "eligibility": eligibility, "configs": cfg,
        "specs": {n: [{k: v for k, v in s.items() if k != "wire"} for s in ss] for n, ss in specs.items()},
        "evidence_bundle_sha256": digest((folder / "bundle_manifest.json").read_bytes()), "assets": check_assets(),
        "cache_directories": {n: str(Path(c).resolve()) for n, c in caches.items()}}
    identity["inference_started_at_utc"] = (json.loads((output / "run.json").read_text())["inference_started_at_utc"]
        if (output / "run.json").exists() else iso(clock()))
    immutable_json(output / "run.json", identity)
    if (output / "completion.json").exists(): return verify_forecasts(folder, output)["completion"]
    if seal_only: budget.reason = "interrupted_offline_seal"
    records = {}; reason = "completed"; started = timestamp(identity["inference_started_at_utc"])
    for n in ORDER:
        observations = []
        for spec in specs[n]:
            if clock() >= timestamp(packet["recorded_tipoff_utc"]): budget.reason = "tipoff_reached"
            final = Path(caches[n]) / spec["key"] / ("forecast.json" if n == "direct" else "group.json")
            marker = Path(caches[n]) / spec["key"] / "attempt.json"
            if marker.exists() and not final.exists():
                if not seal_only: raise ValueError("Uncertain cached attempt cannot be retried")
                from heldout_forecast import blank
                observations.append(blank(n, spec, cfg[n], budget.reason, True, marker)); continue
            if budget.reason and spec.get("usable", True) and not final.exists():
                from heldout_forecast import blank
                r = blank(n, spec, cfg[n], budget.reason)
            else:
                def factory(path, allow_network=False, spec=spec):
                    return PilotHTTP(path, allow_network, budget, lambda: None,
                        {"wire_sha256": digest(canonical(spec["wire"]))})
                try:
                    if not mock and spec.get("usable", True) and not final.exists():
                        budget.reserve(n + ":" + spec["key"], "anthropic", spec["reserved_cost_usd"], digest(canonical(spec["wire"])))
                    if n == "direct": r = direct.cached_forecast(spec, cfg[n], caches[n], not mock, transport_factory or factory)
                    else: r = MODULES[n].cached_group(spec, cfg[n], caches[n], not mock, transport_factory or factory)
                except (Halt, Exception, KeyboardInterrupt) as exc:
                    budget.reason = budget.reason or ("interrupted" if isinstance(exc, KeyboardInterrupt) else "execution_failed")
                    from heldout_forecast import blank
                    if final.exists(): r = direct.cached_forecast(spec, cfg[n], caches[n]) if n == "direct" else MODULES[n].load_cached(spec, caches[n])
                    else: r = blank(n, spec, cfg[n], budget.reason, marker.exists(), marker)
                if r.get("raw_response") and response_category(dict(r, key=r["request_sha256"]), caches[n]) == "access_denial":
                    if not budget.reason: budget.stop("access_denial", http_status=r["raw_response"]["http_status"])
            observations.append(r)
        records[n] = observations[0] if n == "direct" else v1.game_record(packet["game_id"], packet["evidence_snapshot_sha256"], observations) if n == "v1" else v2.game_record({"game_id": packet["game_id"], "evidence_sha256": packet["evidence_snapshot_sha256"]}, observations)
        immutable_json(output / (n + ".json"), records[n])
    sealed = clock(); reason = budget.reason or reason
    complete = {"started_at_utc": iso(started), "sealed_at_utc": iso(sealed), "before_tipoff": sealed < timestamp(packet["recorded_tipoff_utc"]),
        "stop_reason": reason, "successful_methods": [n for n, r in records.items() if r["status"] == "success"],
        "files": {p.name: digest(p.read_bytes()) for p in output.glob("*.json")}}
    immutable_json(output / "completion.json", complete)
    return complete


def verify_forecasts(folder, output):
    folder, output = Path(folder), Path(output)
    run = json.loads((output / "run.json").read_text()); done = json.loads((output / "completion.json").read_text())
    for name, sha in done["files"].items():
        if name not in ("run.json", "direct.json", "v1.json", "v2.json") or digest((output / name).read_bytes()) != sha: raise ValueError("Immutable forecast changed")
    if set(done["files"]) != {"run.json", "direct.json", "v1.json", "v2.json"}: raise ValueError("Incomplete forecast seal")
    packet, cfg, specs = specs_for_bundle(folder, run["mode"] == "offline_mock")
    if cfg != run["configs"] or packet["evidence_snapshot_sha256"] != run["packet_sha256"] or run["assets"] != check_assets(): raise ValueError("Frozen model/packet assets differ")
    if run["evidence_bundle_sha256"] != digest((folder / "bundle_manifest.json").read_bytes()): raise ValueError("Evidence bundle differs")
    source_run = json.loads((folder / "run.json").read_text()); lineage = json.loads((folder / "lineage.json").read_text())
    if run["eligibility"] != packet_eligibility(packet, source_run, lineage): raise ValueError("Eligibility changed")
    clocks = source_run["clocks"]
    rebuilt, _ = strict_packet(source_run["game"], lineage["source_history"], lineage["official_collection"],
        packet["injury_news"]["news"], clocks["started"], clocks["snapshot"], clocks["created"], lineage["public_sources"])
    if digest(canonical(rebuilt)) != packet["evidence_snapshot_sha256"]: raise ValueError("Offline evidence reconstruction differs")
    if run["mode"] != "offline_mock" and (folder / "schedule_raw").is_dir():
        discovery = json.loads((folder / "discovery.json").read_text())
        games, _ = discover(SourceSession(folder / "schedule_raw", True), discovery["started_at"], 3)
        matches = [g for g in games if g["game_id"] == source_run["game"]["game_id"]]
        if len(matches) != 1 or not same_schedule(matches[0], source_run["game"]): raise ValueError("Registered schedule does not replay")
    records = {}
    for n in ORDER:
        r = json.loads((output / (n + ".json")).read_text()); records[n] = r
        obs = [r] if n == "direct" else r["groups"]
        if len(obs) != len(specs[n]): raise ValueError("Missing group")
        for o, s in zip(obs, specs[n]):
            MODULES[n].verify_record(o)
            if o["request_sha256"] != s["key"] or o["evidence_sha256"] != packet["evidence_snapshot_sha256"]: raise ValueError("Consumer evidence identity differs")
            if n != "direct" and any(o[k] != v for k, v in MODULES[n].brief(s).items()): raise ValueError("Group projection changed")
            if run["mode"] != "offline_mock" and o.get("request_started_at_utc"):
                if not timestamp(packet["snapshot_timing"]["packet_created_at_utc"]) <= timestamp(o["request_started_at_utc"]) <= timestamp(o["response_retrieved_at_utc"]) <= timestamp(done["sealed_at_utc"]):
                    raise ValueError("Forecast request lies outside frozen-packet/pregame seal clocks")
            cache = Path(run["cache_directories"][n]); final = cache / s["key"] / ("forecast.json" if n == "direct" else "group.json")
            if not o["status"].startswith("not_attempted"):
                if o.get("uncertain_attempt"):
                    if final.exists() or digest((cache / s["key"] / "attempt.json").read_bytes()) != o["attempt_marker_sha256"]: raise ValueError("Uncertain claim changed")
                else:
                    if not final.exists(): raise ValueError("Original immutable cache required for private replay")
                    saved = direct.cached_forecast(s, cfg[n], cache) if n == "direct" else MODULES[n].load_cached(s, cache)
                    if saved != o: raise ValueError("Cache observation changed")
        expected = r if n == "direct" else v1.game_record(packet["game_id"], packet["evidence_snapshot_sha256"], obs) if n == "v1" else v2.game_record({"game_id": packet["game_id"], "evidence_sha256": packet["evidence_snapshot_sha256"]}, obs)
        if r != expected: raise ValueError("Aggregation differs")
    if done["before_tipoff"] != (timestamp(done["sealed_at_utc"]) < timestamp(packet["recorded_tipoff_utc"])): raise ValueError("Incorrect pregame seal status")
    if done["successful_methods"] != [n for n in ORDER if records[n]["status"] == "success"]: raise ValueError("Completion counters differ")
    if timestamp(done["started_at_utc"]) > timestamp(done["sealed_at_utc"]): raise ValueError("Reversed inference clocks")
    return {"run": run, "records": records, "completion": done, "packet_sha256": packet["evidence_snapshot_sha256"]}


def collect_game(folder, config, game, discovery, session, budget, clock=time.time, provider=None):
    started = clock(); game_guard(game, started); session.target_id = game["game_id"]; session.registry_game = game
    target = timestamp(game["recorded_start_utc"]) - 86400
    history = collect_history(session, game, clock())
    injuries = collect_official(session, game, clock(), config["max_injury_reports"], use_team_catalog=True)
    documents = OneShotDocuments(Path(folder) / "news_raw", False, lambda u: allowed_page(u, dated_articles=True),
        budget, article=True, guard=lambda: game_guard(game, clock()), clock=clock)
    begin = clock(); game_guard(game, begin)
    _, preview = strict_packet(game, history, injuries, collection.no_research()["news"], started, begin, begin, session.records)
    if begin > target or not preview["evidence_complete"]:
        news = collection.no_research()
        news["news"]["missing_reason"] = "research_not_run_after_cutoff_or_incomplete_statistics"
    else:
        provider = provider or BraveAnthropicProvider(config, Path(folder) / "provider_captures", True, True,
            PilotHTTP(Path(folder) / "provider_captures", True, budget, lambda: game_guard(game, clock())))
        news = research(game, begin, provider, documents.get, Budget(**config["budget"]), config["prices"], now=begin,
            use_model=True, live_window=True, clock=lambda: min(target, clock()), diagnostics=True, dated_articles=True, format_recovery=True)
    if budget.reason: raise Halt(budget.reason)
    calls = provider.http.calls if provider else []
    failed_research = any(r["http_status"] != 200 for r in calls) or any("error_type" in d for d in news["audit"].get("decisions", []))
    if failed_research:
        news["news"] = {"state": "collection_failed", "findings": [], "missing_reason": "research_provider_or_extraction_error"}
    snapshot = clock(); game_guard(game, snapshot)
    packet, lineage = strict_packet(game, history, injuries, news["news"], started, snapshot, clock(), session.records)
    lineage["research_collection_failed"] = failed_research
    lineage["evidence_complete"] = lineage["evidence_complete"] and not failed_research
    lineage.update(public_sources=session.records, historical_game_facts=history["history"], source_history=history,
        official_collection=injuries, news={**news["audit"],
        "provider_requests": calls, "actual_provider_usage": provider.usage if provider else []})
    run = {"game": game, "mode": "prospective_live", "settings": {"config": config},
        "clocks": {"started": started, "snapshot": snapshot, "created": timestamp(packet["snapshot_timing"]["packet_created_at_utc"])},
        "source_information_cutoff_utc": lineage["source_information_cutoff_utc"]}
    return collection.save_completed(Path(folder), packet, lineage, run, discovery)


def dry_plan(config, game=None, now=None):
    now = time.time() if now is None else now
    return {"dry_run": True, "network_calls": 0, "paid_calls": 0, "selected_game": game,
        "timing": timing(game, now) if game else None, "planned_queries": planned_queries(game, Budget(**config["budget"]), dated_articles=True) if game else [],
        "global_limits": {"anthropic": 20, "brave": 2, "article": 4, "conservative_reserved_usd": 1},
        "source_policy": "Source information/retrieval cap=min(actual snapshot,T−24h); no retrospective source backfill",
        "expected_outputs": ["evidence/", "forecasts/", "reservations/", "completion.json"],
        "live_access_blocked": STOP.exists()}


def run_live(output, config, gid=None, clock=time.time):
    if STOP.exists(): raise ValueError("Prior access denial: live work requires new operator authorization; do not remove the journal to retry")
    check_assets(); output = Path(output)
    for name in [str(REGISTRY.relative_to(ROOT)), *check_assets()]:
        if subprocess.check_output(["git", "show", "HEAD:" + name], cwd=ROOT) != (ROOT / name).read_bytes():
            raise ValueError("Commit the frozen prospective protocol/implementation before live inference")
    if output.resolve() != (BASE / "pilot").resolve(): raise ValueError("Phase1 has exactly one fixed live pilot output")
    output.mkdir(parents=True, exist_ok=False); budget = PilotBudget(output, clock)
    try:
        session = StudySession(output / "discovery_raw", budget)
        start = clock(); games, decisions = discover(session, start, 3)
        discovery = {"started_at": start, "captured_at_utc": iso(clock()), "games": games, "decisions": decisions}
        immutable_json(output / "discovery.json", discovery)
        game = select_game(games, clock(), gid, eligible_only=True)
        if game is None:
            immutable_json(output / "no_window.json", dry_plan(config, select_game(games, clock(), gid), clock())); return {"status": "no_eligible_window", "paid_calls": 0}
        for env in ("BRAVE_SEARCH_API_KEY", "ANTHROPIC_API_KEY"):
            if not os.environ.get(env): raise ValueError("Required provider credential is unavailable")
        immutable_json(BASE / "pilot_authorization.json", {"game_id": game["game_id"], "output": str(output.resolve()), "protocol_sha256": digest(PROTOCOL.read_bytes())})
        guard = lambda: game_guard(game, clock())
        sources = StudySession(output / "evidence/raw", budget, guard)
        shutil.copytree(output / "discovery_raw", output / "evidence/schedule_raw")
        packet = collect_game(output / "evidence", config, game, discovery, sources, budget, clock)
        done = forecast_bundle(output / "evidence", output / "forecasts", budget, clock=clock)
        immutable_json(output / "completion.json", {"status": "sealed", "packet_sha256": packet["evidence_snapshot_sha256"], "forecast_completion_sha256": digest((output / "forecasts/completion.json").read_bytes()), "completed_at_utc": iso(clock()),
            "files": {str(p.relative_to(output)): digest(p.read_bytes()) for p in output.rglob("*") if p.is_file() and p.parent != output}})
        return done
    except (Halt, Exception, KeyboardInterrupt) as e:
        immutable_json(output / "failure.json", {"error_type": type(e).__name__, "reason": str(e), "at_utc": iso(clock()), "stop_reason": budget.reason})
        return {"status": "failed", "reason": str(e), "paid_requests_reserved": len([r for r in budget.entries() if r["kind"] != "article"])}


def offline_mock(output):
    """Artificial one-game fixture; never replay a real/historical game as live."""
    output = Path(output)
    if (output / "forecasts/completion.json").exists(): return verify_forecasts(output / "evidence", output / "forecasts")
    now = timestamp("2030-01-01T00:00:00Z")
    game = {"game_id": "offline-prospective-fixture", "recorded_start_utc": iso(now + 86400), "season_year": 2030,
        "season_type": 2, "counts_in_regular_season": True, "excluded_fixture": False, "neutral_site": False,
        "game_date": "2030-01-01", "time_valid": True, "scheduled": True,
        "home_id": "1", "away_id": "2", "home_name": "Fixture Home", "away_name": "Fixture Away",
        "home_code": "HOM", "away_code": "AWY", "nba_game_id": "002-fixture", "schedule_provider": "offline_fixture"}
    fact = {"game_id": "offline-past-fixture", "recorded_start_utc": iso(now - 10000), "home_id": "1", "away_id": "2",
        "counts_in_regular_season": True, "excluded_fixture": False, "source_id": "fixture-summary",
        "end_utc": iso(now - 3600), "available_by_utc": iso(now - 3000), "recap_published_utc": iso(now - 3500),
        "recap_modified_utc": iso(now - 3200), "event_updated_utc": iso(now - 3000), "home_points": 110,
        "away_points": 100, "home_won": True, "end_game_score_matches_header": True, "point_in_time_verified": False, "issue": None}
    history = {"history": [fact], "complete": {"home": True, "away": True}, "decisions": []}
    injuries = {"reports": {}, "candidates": [], "archive": []}; news = collection.no_research()
    packet, lineage = strict_packet(game, history, injuries, news["news"], now - 2, now, now + 1, [])
    lineage.update(public_sources=[], historical_game_facts=[fact], source_history=history, official_collection=injuries, news=news["audit"])
    run = {"game": game, "mode": "offline_mock", "settings": {"config": json.loads(CONFIG.read_text())},
        "clocks": {"started": now - 2, "snapshot": now, "created": now + 1}}
    collection.save_completed(output / "evidence", packet, lineage, run, {"fixture": True})
    budget = PilotBudget(output, clock=lambda: now + 2, stop_path=output / "unused_stop.json")
    forecast_bundle(output / "evidence", output / "forecasts", budget, mock=True,
        caches={n: output / "cache" / n for n in ORDER}, clock=lambda: now + 2)
    return verify_forecasts(output / "evidence", output / "forecasts")


def public_audit(capture, output):
    capture, output = Path(capture), Path(output)
    verified = verify_forecasts(capture / "evidence", capture / "forecasts")
    packet = direct.load_evidence(capture / "evidence", verified["run"]["game"]["game_id"])
    payload = {"packet": packet, "forecast_run": verified["run"], "forecasts": verified["records"],
        "completion": {k: v for k, v in verified["completion"].items() if k != "files"},
        "evidence_lineage": json.loads((capture / "evidence/lineage.json").read_text()),
        "raw_provider_responses_included": False, "original_forecast_completion_sha256": digest((capture / "forecasts/completion.json").read_bytes()),
        "reservations": [json.loads(p.read_text()) for p in sorted((capture / "reservations").glob("*.json"))]}
    payload["forecast_run"] = {k: v for k, v in payload["forecast_run"].items() if k != "cache_directories"}
    allowed_meta = {"source_id", "url", "http_status", "retrieved_at_utc", "body_sha256", "truncated", "started_at_utc", "latency_seconds"}
    line = payload["evidence_lineage"]
    line["public_sources"] = [{k: v for k, v in m.items() if k in allowed_meta} for m in line["public_sources"]]
    line["news"]["provider_requests"] = [{k: v for k, v in m.items() if k in allowed_meta} for m in line["news"].get("provider_requests", [])]
    if "agent_candidates" in line["news"]:
        line["news"]["agent_candidates_sha256"] = digest(canonical(line["news"].pop("agent_candidates")))
    def clean(value):
        if isinstance(value, dict): return {k: clean(v) for k, v in value.items() if k not in {"headers", "payload"}}
        return [clean(v) for v in value] if isinstance(value, list) else value
    payload["evidence_lineage"] = clean(line)
    immutable_json(output / "audit.json", payload)
    immutable_json(output / "public_manifest.json", {"audit.json": digest((output / "audit.json").read_bytes())})
    return payload


def replay_public(folder):
    folder = Path(folder); manifest = json.loads((folder / "public_manifest.json").read_text())
    if set(manifest) != {"audit.json"} or digest((folder / "audit.json").read_bytes()) != manifest["audit.json"]: raise ValueError("Public audit hash mismatch")
    a = json.loads((folder / "audit.json").read_text()); p = a["packet"]
    from shared_evidence import validate_packet
    validate_packet(p)
    if a["raw_provider_responses_included"] is not False or digest(canonical({k: v for k, v in p.items() if k != "evidence_snapshot_sha256"})) != p["evidence_snapshot_sha256"]: raise ValueError("Unsafe or changed packet")
    run = a["forecast_run"]
    if run["assets"] != check_assets() or run["packet_sha256"] != p["evidence_snapshot_sha256"]: raise ValueError("Frozen assets/parent differ")
    specs = {"direct": [direct.request_spec(p, run["configs"]["direct"])],
        "v1": [v1.group_spec(g, run["configs"]["v1"]) for g in v1.build_groups(p)],
        "v2": [v2_evidence.group_spec(g, run["configs"]["v2"]) for g in v2_evidence.build_groups(p)]}
    for n in ORDER:
        r = a["forecasts"][n]; obs = [r] if n == "direct" else r["groups"]
        if len(obs) != len(specs[n]): raise ValueError("Incomplete group list")
        for o, s in zip(obs, specs[n]):
            MODULES[n].verify_record(o)
            if o["request_sha256"] != s["key"] or o["evidence_sha256"] != p["evidence_snapshot_sha256"]: raise ValueError("Different evidence or request")
            if n != "direct" and any(o[k] != v for k, v in MODULES[n].brief(s).items()): raise ValueError("Group projection differs")
        expected = r if n == "direct" else v1.game_record(p["game_id"], p["evidence_snapshot_sha256"], obs) if n == "v1" else v2.game_record({"game_id": p["game_id"], "evidence_sha256": p["evidence_snapshot_sha256"]}, obs)
        if r != expected: raise ValueError("Forecast aggregation differs")
    return a


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true"); p.add_argument("--schedule-capture", type=Path); p.add_argument("--game-id")
    p.add_argument("--mock", action="store_true"); p.add_argument("--output", type=Path)
    p.add_argument("--discover", action="store_true")
    p.add_argument("--export-audit", type=Path)
    p.add_argument("--seal-partial", type=Path)
    p.add_argument("--live-pilot", action="store_true"); p.add_argument("--allow-network", action="store_true")
    p.add_argument("--allow-search", action="store_true"); p.add_argument("--allow-inference", action="store_true")
    p.add_argument("--replay", type=Path); a = p.parse_args(); config = json.loads(CONFIG.read_text()); collection.check_config(config)
    if a.seal_partial:
        if any((a.live_pilot, a.allow_network, a.allow_search, a.allow_inference, a.mock, a.discover)): p.error("Partial sealing is strictly offline; stop the active process first")
        root = a.seal_partial; old = json.loads((root / "forecasts/run.json").read_text())
        result = forecast_bundle(root / "evidence", root / "forecasts", PilotBudget(root),
            mock=old["mode"] == "offline_mock", caches={n: Path(v) for n, v in old["cache_directories"].items()}, seal_only=True)
        print(json.dumps(result, indent=2)); return
    if a.replay:
        if any((a.live_pilot, a.allow_network, a.allow_search, a.allow_inference)): p.error("Replay is offline")
        if (a.replay / "public_manifest.json").exists():
            result = replay_public(a.replay); print(json.dumps({"verified": True, "mode": result["forecast_run"]["mode"], "packet_sha256": result["packet"]["evidence_snapshot_sha256"]})); return
        result = verify_forecasts(a.replay / "evidence", a.replay / "forecasts")
        print(json.dumps({"verified": True, "packet_sha256": result["packet_sha256"], "completion": result["completion"]}, indent=2)); return
    if a.mock or a.export_audit:
        if any((a.live_pilot, a.allow_network, a.allow_search, a.allow_inference)): p.error("Mock/audit export is offline only")
        if a.mock:
            result = offline_mock(a.output or BASE / "mock"); print(json.dumps({"mode": "offline_mock", "packet_sha256": result["packet_sha256"], "successful_methods": result["completion"]["successful_methods"], "paid_calls": 0})); return
        if not a.output: p.error("--export-audit requires a separate --output")
        result = public_audit(a.export_audit, a.output); print(json.dumps({"exported": True, "mode": result["forecast_run"]["mode"]})); return
    if a.discover:
        if not a.allow_network or any((a.allow_search, a.allow_inference, a.live_pilot, a.dry_run)): p.error("Discovery requires public network only")
        if STOP.exists(): raise ValueError("Access denial blocks further live discovery; fresh authorization required")
        output = a.output or BASE / "discovery"; output.mkdir(parents=True, exist_ok=False)
        budget = PilotBudget(output); session = StudySession(output / "raw", budget)
        start = time.time()
        try:
            games, decisions = discover(session, start, 3)
            immutable_json(output / "discovery.json", {"started_at": start, "captured_at_utc": iso(time.time()), "games": games, "decisions": decisions})
            result = {**dry_plan(config, select_game(games, time.time(), a.game_id)), "public_requests": session.used}
        except (Halt, Exception) as e:
            immutable_json(output / "failure.json", {"error_type": type(e).__name__, "reason": str(e), "at_utc": iso(time.time())})
            result = {"status": "discovery_failed", "reason": str(e), "paid_calls": 0}
    elif a.live_pilot:
        if a.dry_run or not all((a.allow_network, a.allow_search, a.allow_inference)): p.error("Live pilot requires all explicit paid/network opt-ins")
        result = run_live(BASE / "pilot", config, a.game_id)
    else:
        if any((a.allow_network, a.allow_search, a.allow_inference)): p.error("Dry run cannot enable network or paid calls")
        game = None; failure = None
        if a.schedule_capture:
            if (a.schedule_capture / "failure.json").exists(): failure = json.loads((a.schedule_capture / "failure.json").read_text())
            else:
                d = json.loads((a.schedule_capture / "discovery.json").read_text()); ss = SourceSession(a.schedule_capture / "raw", True)
                games, _ = discover(ss, d["started_at"], 3); game = select_game(games, time.time(), a.game_id)
        result = {**dry_plan(config, game), "discovery_failure": failure}
    print(json.dumps(result, indent=2))


if __name__ == "__main__": main()
