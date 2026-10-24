#!/usr/bin/env python3
"""One-game launchd planning, strict evidence freeze and native forecasting.

No market/evaluation imports. Default plan is offline; enrollment and OS install
are explicit operations. Native frozen forecasters and schemas are unchanged.
"""
import argparse
import contextlib
import copy
import fcntl
import json
import os
import plistlib
import shlex
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import prospective_discovery as discovery
import prospective_study as study
from evidence_documents import canonical, digest
from forecast_split import ROOT, immutable_json
from investigate_kalshi import iso, timestamp
from prospective_sources import SourceSession

BASE = ROOT / "captures/prospective_scheduled_pilot"
CONFIG = ROOT / "examples/prospective_scheduled_pilot_v1.json"
PROTOCOL = ROOT / "experiments/prospective_scheduled_pilot_v1.md"
REGISTRY = ROOT / "experiments/prospective_scheduled_pilot_v1_assets.json"
STOP = BASE / "access_denial.json"


def assets(committed=False):
    discovery.check_assets()
    values = json.loads(REGISTRY.read_text())
    for name, sha in values.items():
        body = (ROOT / name).read_bytes()
        if digest(body) != sha: raise ValueError("Scheduled pilot asset changed: " + name)
        if committed and subprocess.check_output(["git", "show", "HEAD:" + name], cwd=ROOT) != body:
            raise ValueError("Commit scheduled pilot assets before network/installation")
    if committed and subprocess.check_output(["git", "show", "HEAD:" + str(REGISTRY.relative_to(ROOT))], cwd=ROOT) != REGISTRY.read_bytes():
        raise ValueError("Commit scheduled pilot asset registry")
    return values


@contextlib.contextmanager
def lock(folder, name):
    folder = Path(folder); folder.mkdir(parents=True, exist_ok=True)
    with (folder / (name + ".lock")).open("a") as f:
        try: fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise ValueError("Another process owns this phase")
        try: yield
        finally: fcntl.flock(f, fcntl.LOCK_UN)


def check_stops(job=None):
    if job:
        for name, sha in job["parent_journals"].items():
            p = ROOT / name
            if not p.is_file() or digest(p.read_bytes()) != sha: raise study.Halt("Bound parent journal missing or changed")
    for p in (study.STOP, discovery.STOP, STOP):
        if not p.exists(): continue
        value = json.loads(p.read_text())
        if p == study.STOP and value.get("reason") == "access_denial" and value.get("http_status") == 403 and value.get("url") == discovery.NBA_SCHEDULES[0]:
            if job and job["parent_journals"].get(str(p.relative_to(ROOT))) != digest(p.read_bytes()):
                raise study.Halt("Original schedule denial journal changed")
            continue
        raise study.Halt("Access-denial journal blocks this job: " + p.name)


class JobBudget(study.PilotBudget):
    def reserve(self, *a, **kw):
        check_stops()
        return super().reserve(*a, **kw)

    def stop(self, reason, **details):
        if reason == "access_denial":
            self.reason = reason
            if not self.stop_path.exists():
                immutable_json(self.stop_path, {"reason": reason, "at_utc": iso(self.clock()),
                    "requires_new_operator_authorization": True, **details})
            if not (self.folder / "stop.json").exists():
                immutable_json(self.folder / "stop.json", json.loads(self.stop_path.read_text()))
            return
        for p in (self.stop_path, self.folder / "stop.json"):
            if p.exists(): self.reason = json.loads(p.read_text())["reason"]; return
        return super().stop(reason, **details)


class TargetMixin:
    def json(self, value):
        meta, doc = super().json(value)
        if "/scoreboard?" in value and isinstance(doc, dict):
            doc = copy.deepcopy(doc)
            doc["events"] = [e for e in doc.get("events", []) if str(e.get("id")) == self.registered_id]
        return meta, doc


class TargetSession(TargetMixin, discovery.ScheduleSession): pass
class OfflineTarget(TargetMixin, SourceSession): pass


def revalidate(job, folder, budget, clock=time.time):
    game = job["game"]; guard = lambda: check_stops(job)
    session = TargetSession(Path(folder) / "raw", budget, guard)
    session.registered_id = game["game_id"]
    start = clock(); games, decisions = discovery.discover_verified(session, start, 2)
    record = {"started_at": start, "captured_at_utc": iso(clock()), "days": 2, "game_id_filter": game["game_id"], "games": games, "decisions": decisions}
    immutable_json(Path(folder) / "discovery.json", record)
    if len(games) != 1 or discovery.differences(game, games[0]): raise ValueError("Schedule changed, canceled, missing or conflicting; never move cutoff")
    if game.get("nba_game_id") and games[0].get("nba_game_id") and game["nba_game_id"] != games[0]["nba_game_id"]:
        raise ValueError("NBA identity changed")
    return record


def choose_future(games, now, config):
    usable = []
    for g in games:
        try: study.game_guard(g, now, window=False)
        except ValueError: continue
        target = study.aware(g["recorded_start_utc"]) - 86400
        if target + config["capture_offset_seconds"] >= now + config["minimum_preparation_seconds"]: usable.append(g)
    return min(usable, key=lambda g: (study.aware(g["recorded_start_utc"]), g["game_id"])) if usable else None


def plan_for(game, now, config):
    target = study.aware(game["recorded_start_utc"]) - 86400
    return {"game": game, "target_cutoff_utc": iso(target), "window_start_utc": iso(target - 300),
        "window_end_utc": iso(target + 300), "evidence_launch_utc": iso(target + config["capture_offset_seconds"]),
        "market_launch_utc": iso(target + config["market_launch_offset_seconds"]),
        "market_request_utc": iso(target + config["market_request_offset_seconds"]),
        "source_retrieval_deadline_utc": iso(target), "planned_at_utc": iso(now),
        "capture_exactness": "actual clocks determine eligibility; operational tolerance is not exact cutoff",
        "paid_news": "not_collected_before_valid_frozen_capture", "limits": {k: config[k] for k in
            ("max_anthropic_requests", "max_brave_queries", "max_articles", "max_reserved_usd")}}


def prepare(allow_inference=False, clock=time.time):
    frozen = assets(True); check_stops(); config = json.loads(CONFIG.read_text())
    enrollment = BASE / "enrollment"; enrollment.mkdir(parents=True, exist_ok=False)
    budget = JobBudget(enrollment, clock, STOP)
    try:
        start = clock(); session = discovery.ScheduleSession(enrollment / "raw", budget, lambda: check_stops())
        games, decisions = discovery.discover_verified(session, start, 3)
        immutable_json(enrollment / "discovery.json", {"started_at": start, "days": 3, "games": games, "decisions": decisions, "captured_at_utc": iso(clock())})
        game = choose_future(games, clock(), config)
        if not game:
            immutable_json(enrollment / "no_game.json", {"status": "no_safely_schedulable_game", "at_utc": iso(clock())}); return None
        plan = plan_for(game, clock(), config)
        identity = digest(canonical({"game_id": game["game_id"], "tipoff": game["recorded_start_utc"], "assets": frozen}))
        parent = {str(p.relative_to(ROOT)): digest(p.read_bytes()) for p in (study.STOP, discovery.STOP) if p.exists()}
        job = {"job_id": identity, "mode": "prospective_live", "game": game, "plan": plan, "assets": frozen,
            "config": config, "parent_journals": parent, "allow_inference": allow_inference,
            "authorization": "one scheduled game; maximum20 Anthropic/$1; no paid retries",
            "enrollment_manifest_sha256": digest(canonical({str(p.relative_to(enrollment)): digest(p.read_bytes()) for p in enrollment.rglob('*') if p.is_file()})),
            "labels": {p: "org.nba.prospective." + identity[:20] + "." + p for p in ("evidence", "market")}}
        immutable_json(BASE / "job.json", job)
        immutable_json(BASE / "job_manifest.json", {"job.json": digest((BASE / "job.json").read_bytes())})
        return job
    except (Exception, study.Halt, KeyboardInterrupt) as e:
        immutable_json(enrollment / "failure.json", {"reason": str(e), "error_type": type(e).__name__, "at_utc": iso(clock())})
        raise


def load_job():
    manifest = json.loads((BASE / "job_manifest.json").read_text())
    if manifest != {"job.json": digest((BASE / "job.json").read_bytes())}: raise ValueError("Immutable job changed")
    job = json.loads((BASE / "job.json").read_text())
    if job["assets"] != assets(): raise ValueError("Job assets differ")
    return job


def phase_due(job, phase, now):
    target = study.aware(job["plan"]["target_cutoff_utc"])
    due = study.aware(job["plan"][phase + "_launch_utc"])
    if now < due: return "pending"
    if now > target: return "missed_source_cutoff"
    if not study.timing(job["game"], now)["within_tolerance"]: return "missed_capture_window"
    return "due"


def freeze_evidence(job, budget, clock=time.time):
    game = job["game"]; folder = BASE / "evidence"; started = clock()
    def guard():
        check_stops(job); study.game_guard(game, clock())
        if clock() > study.aware(job["plan"]["target_cutoff_utc"]): raise study.Halt("Source cutoff passed; no late evidence")
    guard(); sources = study.StudySession(folder / "raw", budget, guard)
    sources.target_id = game["game_id"]; sources.registry_game = game
    history = study.collect_history(sources, game, clock())
    injuries = study.collect_official(sources, game, clock(), 8, use_team_catalog=True)
    news = study.collection.no_research()
    news["news"]["missing_reason"] = "scheduled_pilot_paid_news_not_collected_before_frozen_capture"
    guard(); snapshot = clock(); created = clock()
    packet, lineage = study.strict_packet(game, history, injuries, news["news"], started, snapshot, created, sources.records)
    lineage.update(public_sources=sources.records, historical_game_facts=history["history"], source_history=history,
        official_collection=injuries, news=news["audit"], research_collection_failed=False)
    run = {"game": game, "mode": "prospective_live", "settings": {"config": json.loads(study.CONFIG.read_text()),
        "allow_search": False, "allow_model": False, "job_id": job["job_id"]},
        "clocks": {"started": started, "snapshot": snapshot, "created": created}, "source_information_cutoff_utc": lineage["source_information_cutoff_utc"]}
    study.collection.save_completed(folder, packet, lineage, run, json.loads((BASE / "revalidation/discovery.json").read_text()))
    return valid_capture(job)


def valid_capture(job):
    bundle = study.collection.verify_bundle(BASE / "evidence")
    run = json.loads((BASE / "evidence/run.json").read_text()); line = json.loads((BASE / "evidence/lineage.json").read_text())
    packet = study.direct.load_evidence(BASE / "evidence", job["game"]["game_id"])
    if not study.same_schedule(run["game"], job["game"]) or packet["evidence_snapshot_sha256"] != bundle["packet_sha256"]:
        raise ValueError("Registered/frozen game changed")
    if not study.packet_eligibility(packet, run, line)["eligible"]: raise ValueError("Evidence incomplete or off-time; no inference")
    return packet


def load_credentials():
    path = ROOT / ".env"
    if path.is_file():
        for line in path.read_text().splitlines():
            line = line.strip().removeprefix("export ")
            if not line or line.startswith("#") or "=" not in line: continue
            key, value = line.split("=", 1)
            if key.strip() == "ANTHROPIC_API_KEY" and not os.environ.get(key.strip()):
                try: parts = shlex.split(value, comments=True)
                except ValueError: raise ValueError("Invalid trusted credential-file syntax") from None
                if parts: os.environ[key.strip()] = parts[0]
    if not os.environ.get("ANTHROPIC_API_KEY"): raise ValueError("Anthropic credential unavailable; frozen evidence preserved")


def forecast(job, budget, clock=time.time):
    packet = valid_capture(job); check_stops(job)
    if clock() >= study.aware(job["game"]["recorded_start_utc"]): raise ValueError("Tipoff reached; no inference")
    if not job["allow_inference"]: raise ValueError("Paid inference was not authorized in this job")
    marker = BASE / "inference_claim.json"
    if marker.exists():
        if (BASE / "forecasts/completion.json").exists(): return study.verify_forecasts(BASE / "evidence", BASE / "forecasts")["completion"]
        # Never resend or continue paid calls after a process lost its lease.
        if (BASE / "forecasts/run.json").exists():
            return study.forecast_bundle(BASE / "evidence", BASE / "forecasts", budget, clock=clock, seal_only=True)
        return {"stop_reason": "uncertain_inference_claim_not_retried", "successful_methods": []}
    load_credentials()
    immutable_json(marker, {"job_id": job["job_id"], "packet_sha256": packet["evidence_snapshot_sha256"], "at_utc": iso(clock())})
    class ForecastHTTP(study.PilotHTTP):
        def request(self, provider, method, url, payload, headers, max_bytes):
            check_stops(job)
            if provider != "anthropic" or url != "https://api.anthropic.com/v1/messages": raise study.Halt("Inference cannot retrieve independent evidence")
            if clock() >= study.aware(job["game"]["recorded_start_utc"]): raise study.Halt("Tipoff reached")
            self.expected = {"wire_sha256": digest(canonical({"provider": provider, "method": method, "url": url, "payload": payload}))}
            return super().request(provider, method, url, payload, headers, max_bytes)
    def factory(folder, allow_network=False): return ForecastHTTP(folder, allow_network, budget, lambda: check_stops(job))
    return study.forecast_bundle(BASE / "evidence", BASE / "forecasts", budget, clock=clock, transport_factory=factory)


def retire(job, phase):
    if sys.platform == "darwin" and (BASE / "installation.json").exists():
        # Final audit is already durable. Removing only our label can terminate
        # the calling job, so do not put required writes after this request.
        subprocess.Popen(["/bin/launchctl", "bootout", "gui/" + str(os.getuid()) + "/" + job["labels"][phase]],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def worker_start(phase):
    job = load_job(); path = BASE / (phase + "_startup.json")
    if not path.exists(): immutable_json(path, {"job_id": job["job_id"], "phase": phase,
        "at_utc": iso(time.time()), "pid": os.getpid(), "assets_verified": True})


def run_evidence(clock=time.time):
    job = load_job(); result_path = BASE / "evidence_result.json"
    with lock(BASE, "evidence"):
        if result_path.exists(): retire(job, "evidence"); return json.loads(result_path.read_text())
        due = phase_due(job, "evidence", clock())
        captured = (BASE / "evidence/bundle_manifest.json").exists()
        if due == "pending" and not captured: return {"status": "pending", "paid_calls": 0}
        budget = JobBudget(BASE, clock, STOP)
        try:
            check_stops(job)
            if not captured:
                if (BASE / "capture_claim.json").exists(): raise ValueError("Interrupted capture claim; do not repeat retrieval")
                if due != "due": raise ValueError(due)
                immutable_json(BASE / "capture_claim.json", {"job_id": job["job_id"], "at_utc": iso(clock())})
                revalidate(job, BASE / "revalidation", budget, clock)
                if phase_due(job, "evidence", clock()) != "due": raise ValueError("Revalidation missed source cutoff")
                freeze_evidence(job, budget, clock)
            packet = valid_capture(job)
            done = forecast(job, budget, clock)
            status = "sealed_complete" if done.get("before_tipoff") and set(done.get("successful_methods", [])) == set(study.ORDER) else "sealed_partial"
            if not done.get("before_tipoff", True): status = "sealed_ineligible_after_tipoff"
            result = {"status": status, "job_id": job["job_id"], "packet_sha256": packet["evidence_snapshot_sha256"], "forecast_completion": done, "at_utc": iso(clock())}
        except (Exception, study.Halt, KeyboardInterrupt) as e:
            result = {"status": "failed_or_missed", "job_id": job["job_id"], "reason": str(e), "error_type": type(e).__name__, "at_utc": iso(clock())}
        immutable_json(result_path, result); retire(job, "evidence"); return result


def launch_spec(job, phase, executable=None):
    when = study.aware(job["plan"][phase + "_launch_utc"]); local = datetime.fromtimestamp(when).astimezone()
    script = ROOT / "scripts" / ("scheduled_prospective.py" if phase == "evidence" else "scheduled_market.py")
    args = [str(executable or ROOT / ".venv/bin/python"), str(script), "--run", "--allow-network"]
    if phase == "evidence": args.append("--allow-inference")
    return {"Label": job["labels"][phase], "ProgramArguments": args, "WorkingDirectory": str(ROOT),
        "StartCalendarInterval": {"Month": local.month, "Day": local.day, "Hour": local.hour, "Minute": local.minute},
        "RunAtLoad": True, "KeepAlive": False, "StandardOutPath": str(BASE / (phase + ".stdout.log")),
        "StandardErrorPath": str(BASE / (phase + ".stderr.log"))}


def install():
    assets(True); job = load_job(); check_stops(job)
    if sys.platform != "darwin": raise ValueError("This deployment uses macOS launchd; no custom background service")
    if phase_due(job, "evidence", time.time()) != "pending": raise ValueError("Too late to install safely")
    records = []
    for phase in ("evidence", "market"):
        spec = launch_spec(job, phase); path = BASE / (phase + ".plist"); body = plistlib.dumps(spec, sort_keys=True)
        if path.exists():
            if path.read_bytes() != body: raise ValueError("Existing timer differs")
        else:
            with path.open("xb") as f: f.write(body)
        domain = "gui/" + str(os.getuid()); label = job["labels"][phase]
        existing = subprocess.run(["/bin/launchctl", "print", domain + "/" + label], capture_output=True, text=True, timeout=15)
        rc = 0
        if existing.returncode:
            registered = subprocess.run(["/bin/launchctl", "bootstrap", domain, str(path)], capture_output=True, text=True, timeout=15)
            rc = registered.returncode
        checked = subprocess.run(["/bin/launchctl", "print", domain + "/" + label], capture_output=True, text=True, timeout=15)
        deadline = time.monotonic() + 5
        while checked.returncode == 0 and not (BASE / (phase + "_startup.json")).exists() and time.monotonic() < deadline:
            time.sleep(.1)
        records.append({"phase": phase, "label": label, "bootstrap_returncode": rc, "loaded": checked.returncode == 0,
            "worker_startup_verified": (BASE / (phase + "_startup.json")).exists(),
            "plist_sha256": digest(body), "host_local_launch": datetime.fromtimestamp(study.aware(job["plan"][phase + "_launch_utc"])).astimezone().isoformat()})
    value = {"status": "scheduled_pending" if all(r["loaded"] and r["worker_startup_verified"] for r in records) else "installation_incomplete", "at_utc": iso(time.time()), "tasks": records}
    if not (BASE / "installation.json").exists(): immutable_json(BASE / "installation.json", value)
    return value


def replay():
    job = load_job()
    for folder, targeted in ((BASE / "enrollment", False), (BASE / "revalidation", True)):
        if not (folder / "discovery.json").exists(): continue
        saved = json.loads((folder / "discovery.json").read_text())
        s = OfflineTarget(folder / "raw", True) if targeted else SourceSession(folder / "raw", True)
        if targeted: s.registered_id = job["game"]["game_id"]
        games, decisions = discovery.discover_verified(s, saved["started_at"], saved["days"])
        if games != saved["games"] or decisions != saved["decisions"]: raise ValueError("Schedule extraction does not replay")
    if (BASE / "evidence/bundle_manifest.json").exists(): valid_capture(job)
    if (BASE / "forecasts/completion.json").exists(): study.verify_forecasts(BASE / "evidence", BASE / "forecasts")
    return {"verified": True, "job_id": job["job_id"], "forecasts_sealed": (BASE / "forecasts/completion.json").exists(), "network_calls": 0}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--prepare", action="store_true"); p.add_argument("--install", action="store_true")
    p.add_argument("--run", action="store_true"); p.add_argument("--replay", action="store_true")
    p.add_argument("--allow-network", action="store_true"); p.add_argument("--allow-inference", action="store_true")
    a = p.parse_args()
    if sum((a.prepare, a.install, a.run, a.replay)) > 1: p.error("Choose one operation")
    if a.prepare:
        if not a.allow_network: p.error("Enrollment needs explicit public network permission")
        job = prepare(a.allow_inference); result = job["plan"] if job else {"status": "no_safely_schedulable_game"}
    elif a.run:
        if not (a.allow_network and a.allow_inference): p.error("Scheduled worker requires explicit network/inference flags")
        assets(True); worker_start("evidence"); result = run_evidence()
    else:
        if a.allow_network or a.allow_inference: p.error("Plan/install/replay makes no source/model requests")
        if a.install: result = install()
        elif a.replay: result = replay()
        elif (BASE / "job.json").exists(): result = {"status": "saved_job", "plan": load_job()["plan"], "installation": json.loads((BASE / "installation.json").read_text()) if (BASE / "installation.json").exists() else None, "network_calls": 0, "paid_calls": 0}
        else:
            source = discovery.ATTEMPT / "discovery.json"
            saved = json.loads(source.read_text()) if source.exists() else {"games": []}
            config = json.loads(CONFIG.read_text()); game = choose_future(saved["games"], time.time(), config)
            result = {"status": "tentative_saved_schedule_only", "plan": plan_for(game, time.time(), config) if game else None, "fresh_discovery_required": True, "network_calls": 0, "paid_calls": 0}
    print(json.dumps(result, indent=2))


if __name__ == "__main__": main()
