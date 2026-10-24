#!/usr/bin/env python3
"""Persist the existing one-game launchd definitions across user login/reboot.

Copies only hash-verified, already registered plists. No game discovery, paid
calls, altered job identity or new timer. Requires normal user OS permissions.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

import scheduled_prospective as pilot
from evidence_documents import digest
from forecast_split import immutable_json
from investigate_kalshi import iso

NOTE = pilot.ROOT / "experiments/prospective_scheduled_pilot_login_v1.md"


def persist(job, installation, destination):
    destination = Path(destination); destination.mkdir(parents=True, exist_ok=True)
    copies = []
    for task in installation["tasks"]:
        phase = task["phase"]; source = pilot.BASE / (phase + ".plist")
        body = source.read_bytes()
        if digest(body) != task["plist_sha256"] or task["label"] != job["labels"][phase]:
            raise ValueError("Immutable timer definition differs")
        target = destination / (task["label"] + ".plist")
        if target.exists():
            if target.read_bytes() != body: raise ValueError("Refuse to replace an existing different LaunchAgent")
        else:
            with target.open("xb") as f: f.write(body)
            target.chmod(0o644)
        copies.append({"phase": phase, "label": task["label"], "plist_sha256": digest(body), "path": str(target)})
    return copies


def main():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument("--install", action="store_true")
    a = p.parse_args()
    if not a.install: print(json.dumps({"status": "plan_only", "action": "Persist verified plists to ~/Library/LaunchAgents; no network or paid calls"})); return
    pilot.assets(True); job = pilot.load_job(); pilot.check_stops(job)
    if sys.platform != "darwin": raise ValueError("macOS launchd deployment only")
    for path in (Path(__file__).resolve(), NOTE):
        if subprocess.check_output(["git", "show", "HEAD:" + str(path.relative_to(pilot.ROOT))], cwd=pilot.ROOT) != path.read_bytes():
            raise ValueError("Commit login persistence deployment before installation")
    installation = json.loads((pilot.BASE / "installation.json").read_text())
    if installation["status"] != "scheduled_pending": raise ValueError("Both original timers/startup probes must be verified")
    if pilot.phase_due(job, "evidence", pilot.time.time()) != "pending": raise ValueError("Do not change deployment after execution is due")
    copies = persist(job, installation, Path.home() / "Library/LaunchAgents")
    record = {"status": "login_persistence_installed_pending", "job_id": job["job_id"], "at_utc": iso(pilot.time.time()),
        "files": copies, "network_calls": 0, "paid_calls": 0}
    if not (pilot.BASE / "login_persistence.json").exists(): immutable_json(pilot.BASE / "login_persistence.json", record)
    print(json.dumps(record, indent=2))


if __name__ == "__main__": main()
