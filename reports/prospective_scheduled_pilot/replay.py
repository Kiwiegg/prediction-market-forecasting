"""Offline public plan/timer replay. Does not authenticate future execution."""
import json
import sys
from datetime import datetime
from pathlib import Path
import plistlib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import scheduled_prospective as pilot
from evidence_documents import canonical, digest

folder = Path(__file__).resolve().parent
manifest = json.loads((folder / "manifest.json").read_text())
for name, sha in manifest.items():
    path = (folder / name).resolve()
    if folder not in path.parents or digest(path.read_bytes()) != sha: raise ValueError("Changed public report")
job = json.loads((folder / "job.json").read_text())
assert json.loads((folder / "job_manifest.json").read_text()) == {"job.json": digest((folder / "job.json").read_bytes())}
assert job["assets"] == pilot.assets()
assert job["job_id"] == digest(canonical({"game_id": job["game"]["game_id"], "tipoff": job["game"]["recorded_start_utc"], "assets": job["assets"]}))
assert pilot.plan_for(job["game"], pilot.study.aware(job["plan"]["planned_at_utc"]), job["config"]) == job["plan"]
installation = json.loads((folder / "installation.json").read_text())
for task in installation["tasks"]:
    phase = task["phase"]; body = (folder / (phase + ".plist")).read_bytes()
    assert digest(body) == task["plist_sha256"]
    spec = plistlib.loads(body); local = datetime.fromisoformat(task["host_local_launch"])
    assert spec["Label"] == job["labels"][phase]
    assert spec["StartCalendarInterval"] == {"Month": local.month, "Day": local.day, "Hour": local.hour, "Minute": local.minute}
    assert local.timestamp() == pilot.study.aware(job["plan"][phase + "_launch_utc"])
    assert spec["RunAtLoad"] and not spec["KeepAlive"] and "EnvironmentVariables" not in spec
    assert "--allow-inference" in spec["ProgramArguments"] if phase == "evidence" else "--allow-inference" not in spec["ProgramArguments"]
print(json.dumps({"verified": True, "job_id": job["job_id"], "scope": "sanitized fixed plan, timer hashes and frozen assets", "network_calls": 0, "paid_calls": 0, "forecasts_verified": False}))
