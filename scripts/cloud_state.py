"""Single-host durable cloud state; no provider, evidence or evaluation imports."""
import contextlib
import fcntl
import json
import math
import os
import sqlite3
import tempfile
import time
import uuid
from pathlib import Path

from evidence_documents import canonical, digest
from investigate_kalshi import iso, timestamp


def durable_json(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    body = canonical(value) + b"\n"
    if path.exists():
        if path.read_bytes() != body: raise ValueError("Immutable artifact differs: " + path.name)
        return value
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".pending-")
    try:
        with os.fdopen(fd, "wb") as f: f.write(body); f.flush(); os.fsync(f.fileno())
        try: os.link(tmp, path)
        except FileExistsError:
            if path.read_bytes() != body: raise ValueError("Immutable artifact race")
        directory = os.open(path.parent, os.O_RDONLY)
        try: os.fsync(directory)
        finally: os.close(directory)
    finally: os.unlink(tmp)
    return value


@contextlib.contextmanager
def process_lock(path):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        try: fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise RuntimeError("Job already owned by a running process")
        try: yield
        finally: fcntl.flock(f, fcntl.LOCK_UN)


@contextlib.contextmanager
def paid_gate(path,deadline,clock):
    """Serialize paid sends so a denial pauses every later send, even cross-job."""
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a') as f:
        while True:
            try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);break
            except BlockingIOError:
                if clock()>deadline:raise ValueError('Paid queue missed processing deadline')
                time.sleep(.05)
        try:yield
        finally:fcntl.flock(f,fcntl.LOCK_UN)


class State:
    def __init__(self, root, config, clock=time.time, initialize=False):
        self.root, self.config, self.clock = Path(root), config, clock
        repo=Path(__file__).resolve().parents[1]
        for protected in (repo/'data',repo/'.git',repo/'captures/prospective_phase1',repo/'captures/prospective_discovery_v1',repo/'captures/prospective_scheduled_pilot'):
            if self.root.resolve()==protected.resolve() or protected.resolve() in self.root.resolve().parents:raise ValueError('Legacy/historical state path is protected')
        new_store=False
        if initialize:
            self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
            with process_lock(self.root / "init.lock"):
                if not (self.root / "volume.json").exists():
                    durable_json(self.root / "volume.json", {"store_uuid": str(uuid.uuid4())});new_store=True
        if not (self.root / "volume.json").is_file(): raise ValueError("Persistent volume sentinel missing; do not recreate lost paid state")
        if not new_store and not (self.root/'state.sqlite').is_file():raise ValueError('Paid-state database missing; initialization cannot erase request history')
        self.uuid = json.loads((self.root / "volume.json").read_text())["store_uuid"]
        self.config_sha = digest(canonical(config))
        registry=Path(__file__).resolve().parents[1]/'experiments/prospective_cloud_news_v1_assets.json'
        self.registry_sha=digest(registry.read_bytes())
        self.registry=json.loads(registry.read_text())
        with self.db() as c:
            exists=c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='store_identity'").fetchone()
            if exists:
                identity=c.execute('SELECT uuid FROM store_identity').fetchall()
                if len(identity)!=1 or identity[0][0]!=self.uuid:raise ValueError('Database/volume identity mismatch')
            elif not new_store:raise ValueError('Paid-state identity missing; do not recreate a lost ledger')
            else:
                c.execute('CREATE TABLE store_identity(uuid TEXT PRIMARY KEY)');c.execute('INSERT INTO store_identity VALUES(?)',(self.uuid,))
            c.executescript('''
              CREATE TABLE IF NOT EXISTS authorizations(id TEXT PRIMARY KEY, body TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, game TEXT NOT NULL, config_sha TEXT NOT NULL, auth TEXT NOT NULL, mode TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS stages(job TEXT, name TEXT, status TEXT, artifact_sha TEXT, PRIMARY KEY(job,name));
              CREATE TABLE IF NOT EXISTS requests(id TEXT PRIMARY KEY, job TEXT NOT NULL, kind TEXT NOT NULL, usd REAL NOT NULL, status TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS circuits(id TEXT PRIMARY KEY, body TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS heartbeat(lane TEXT PRIMARY KEY, at_utc TEXT NOT NULL);
            ''')

    @contextlib.contextmanager
    def db(self):
        c = sqlite3.connect(self.root / "state.sqlite", timeout=30)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL"); c.execute("PRAGMA synchronous=FULL")
        try: yield c; c.commit()
        except BaseException: c.rollback(); raise
        finally: c.close()

    def event(self, job, kind, **data):
        durable_json(self.root / "events" / (str(time.time_ns()) + "-" + uuid.uuid4().hex + ".json"),
            {"job": job, "kind": kind, "at_utc": iso(self.clock()), **data})

    def authorize(self, ids, max_games=1, max_usd=1.35, mock=False):
        if not ids or max_games < 1 or max_games > len(set(ids)) or not math.isfinite(max_usd) or max_usd <= 0:
            raise ValueError("Explicit bounded game IDs and positive budget required")
        if set(ids) & set(self.config["excluded_game_ids"]): raise ValueError("Legacy pilot is protected")
        body = {"store_uuid": self.uuid, "config_sha256": self.config_sha, "game_ids": sorted(set(ids)),
            "assets_sha256":self.registry_sha,"max_games": max_games, "max_usd": max_usd, "mode": "offline_mock" if mock else "live_explicit_opt_in"}
        durable_json(self.root/'protocols'/(self.registry_sha+'.json'),{'file_sha256':self.registry_sha,'assets':self.registry,'config':self.config})
        key = digest(canonical(body)); durable_json(self.root / "authorizations" / (key + ".json"), body)
        with self.db() as c: c.execute("INSERT OR IGNORE INTO authorizations VALUES(?,?)", (key, canonical(body).decode()))
        return key

    def authorization(self, key):
        with self.db() as c: row = c.execute("SELECT body FROM authorizations WHERE id=?", (key,)).fetchone()
        if row is None: raise ValueError("Explicit cloud activation authorization missing")
        body = json.loads(row[0])
        if digest(canonical(body))!=key:raise ValueError('Authorization hash mismatch')
        if body["store_uuid"] != self.uuid or body["config_sha256"] != self.config_sha or body['assets_sha256']!=self.registry_sha: raise ValueError("Authorization volume/protocol mismatch")
        if json.loads((self.root / "authorizations" / (key + ".json")).read_text()) != body: raise ValueError("Authorization audit changed")
        return body

    def enroll(self, game, auth):
        approval = self.authorization(auth)
        if game["game_id"] in self.config["excluded_game_ids"] or game["game_id"] not in approval["game_ids"]: raise ValueError("Game not explicitly authorized")
        key = digest(canonical({"protocol": self.config["protocol"], "config_sha": self.config_sha,
            "assets_sha":self.registry_sha,"game_id": game["game_id"], "tipoff": game["recorded_start_utc"]}))
        record={"job_id":key,"game":game,"config":self.config,"config_sha256":self.config_sha,
            "assets_sha256":self.registry_sha,"authorization":auth,"mode":approval['mode']}
        with self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            old = c.execute("SELECT * FROM jobs WHERE id=?", (key,)).fetchone()
            if old:
                if old["game"] != canonical(game).decode() or old["auth"] != auth: raise ValueError("Registered job differs")
                durable_json(self.job_dir(key)/'job.json',record)
                return key
            # A reschedule cannot create another job for an already enrolled ID.
            for r in c.execute("SELECT game FROM jobs"):
                if json.loads(r[0])["game_id"] == game["game_id"]: raise ValueError("Game already registered at another cutoff")
            if c.execute("SELECT count(*) FROM jobs WHERE auth=?", (auth,)).fetchone()[0] >= approval["max_games"]: raise ValueError("Enrollment cap reached")
            c.execute("INSERT INTO jobs VALUES(?,?,?,?,?)", (key, canonical(game).decode(), self.config_sha, auth, approval["mode"]))
        durable_json(self.job_dir(key) / "job.json", record)
        return key

    def job_dir(self, key): return self.root / "jobs" / key

    def job(self, key):
        with self.db() as c: row = c.execute("SELECT * FROM jobs WHERE id=?", (key,)).fetchone()
        if row is None or row["config_sha"] != self.config_sha: raise ValueError("Job configuration changed or absent")
        value = json.loads((self.job_dir(key) / "job.json").read_text())
        if value["game"] != json.loads(row["game"]) or value["authorization"] != row["auth"] or value["config"] != self.config or value['assets_sha256']!=self.registry_sha: raise ValueError("Immutable job changed")
        return value

    def jobs(self):
        with self.db() as c: return [r[0] for r in c.execute("SELECT id FROM jobs ORDER BY id")]

    def circuit(self, key, **data):
        body = {"id": key, "at_utc": iso(self.clock()), **data}
        with self.db() as c: c.execute("INSERT OR IGNORE INTO circuits VALUES(?,?)", (key, canonical(body).decode()))
        with self.db() as c: old = json.loads(c.execute("SELECT body FROM circuits WHERE id=?", (key,)).fetchone()[0])
        durable_json(self.root / "circuits" / (digest(key.encode()) + ".json"), old)

    def check_circuit(self, key):
        with self.db() as c: row = c.execute("SELECT body FROM circuits WHERE id=?", (key,)).fetchone()
        if row: raise ValueError("Access-denial circuit open: " + key)

    def reserve(self, key, job, kind, usd):
        if not math.isfinite(usd) or usd < 0: raise ValueError("Invalid cost reservation")
        registered = self.job(job); auth = self.authorization(registered["authorization"])
        caps = {"search": self.config["research"]["max_queries"], "article": self.config["research"]["max_pages"],
            "extraction": self.config["research"]["max_extraction_calls"], "forecast": self.config["budgets"]["forecast_calls"]}
        if kind not in caps: raise ValueError("Unknown reservation category")
        self.check_circuit("paid") if kind != "article" else None
        with self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            if c.execute("SELECT 1 FROM requests WHERE id=?", (key,)).fetchone(): raise ValueError("Request already claimed; automatic retry forbidden")
            rows = list(c.execute("SELECT * FROM requests WHERE job=?", (job,)))
            research = kind in ("search", "article", "extraction")
            subtotal = sum(r["usd"] for r in rows if (r["kind"] in ("search", "article", "extraction")) == research)
            limit = self.config["research"]["max_estimated_cost_usd"] if research else self.config["budgets"]["forecast_usd"]
            total = c.execute("SELECT coalesce(sum(r.usd),0) FROM requests r JOIN jobs j ON j.id=r.job WHERE j.auth=?", (registered["authorization"],)).fetchone()[0]
            if (sum(r["kind"] == kind for r in rows) >= caps[kind] or subtotal + usd > limit + 1e-12
                    or sum(r["usd"] for r in rows) + usd > self.config["budgets"]["per_game_usd"] + 1e-12 or total + usd > auth["max_usd"] + 1e-12):
                raise ValueError("Pre-call reservation budget exhausted")
            c.execute("INSERT INTO requests VALUES(?,?,?,?,?)", (key, job, kind, usd, "claimed"))
        durable_json(self.root / "requests" / (key + ".json"), {"key": key, "job": job, "kind": kind, "reserved_usd": usd, "at_utc": iso(self.clock())})

    def stage(self, job, name, operation):
        folder = self.job_dir(job) / name; target = folder / "result.json"
        with self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            old = c.execute("SELECT * FROM stages WHERE job=? AND name=?", (job, name)).fetchone()
            if old:
                if old["status"] == "done":
                    if digest(target.read_bytes())!=old['artifact_sha']:raise ValueError('Stage seal changed')
                    return self.artifact(job, name, check_db=False)
                if old["status"] == "claimed" and target.exists():
                    result = self.artifact(job, name, check_db=False)
                    c.execute("UPDATE stages SET status='done',artifact_sha=? WHERE job=? AND name=?", (digest(target.read_bytes()), job, name)); return result
                raise ValueError("Interrupted/failed stage is not retried: " + name)
            c.execute("INSERT INTO stages VALUES(?,?,?,NULL)", (job, name, "claimed"))
        self.event(job, "stage_started", stage=name)
        try:
            value = operation(folder)
            files = {str(p.relative_to(folder)): digest(p.read_bytes()) for p in folder.rglob('*') if p.is_file() and p.name not in ("result.json",)}
            for p in folder.rglob('*'):
                if p.is_file():
                    with p.open('rb') as f: os.fsync(f.fileno())
            durable_json(target, {"value": value, "files": files, "finished_at_utc": iso(self.clock())})
            with self.db() as c: c.execute("UPDATE stages SET status='done',artifact_sha=? WHERE job=? AND name=?", (digest(target.read_bytes()), job, name))
            return value
        except BaseException as exc:
            self.event(job, "stage_failed", stage=name, error_type=type(exc).__name__, reason=str(exc)[:300])
            with self.db() as c: c.execute("UPDATE stages SET status='failed' WHERE job=? AND name=?", (job, name))
            raise

    def artifact(self, job, name, check_db=True):
        folder = self.job_dir(job) / name; target = folder / "result.json"
        if check_db:
            with self.db() as c: row = c.execute("SELECT * FROM stages WHERE job=? AND name=?", (job, name)).fetchone()
            if row is not None and row['status']=='claimed' and target.exists():
                value=self.artifact(job,name,check_db=False)
                with self.db() as c:c.execute("UPDATE stages SET status='done',artifact_sha=? WHERE job=? AND name=?",(digest(target.read_bytes()),job,name))
                return value
            if row is None or row["status"] != "done" or digest(target.read_bytes()) != row["artifact_sha"]: raise ValueError("Stage absent/incomplete or changed: " + name)
        result = json.loads(target.read_text())
        for name, sha in result["files"].items():
            p = (folder / name).resolve()
            if folder.resolve() not in p.parents or digest(p.read_bytes()) != sha: raise ValueError("Captured stage artifact changed")
        return result["value"]

    def has(self, job, stage):
        with self.db() as c: return c.execute("SELECT status FROM stages WHERE job=? AND name=?", (job, stage)).fetchone() is not None

    def status(self):
        with self.db() as c:
            jobs=[]
            for row in c.execute('SELECT * FROM jobs'):
                game=json.loads(row['game']);target=timestamp(game['recorded_start_utc'])-86400
                jobs.append({'job_id':row['id'],'game_id':game['game_id'],'mode':row['mode'],'cohort':self.config['cohort'],
                    'target_utc':iso(target),'collection_start_utc':iso(target-self.config['evidence']['collection_lead_minutes']*60),
                    'freeze_deadline_utc':iso(target+self.config['evidence']['packet_freeze_grace_minutes']*60),
                    'forecast_deadline_utc':iso(target+self.config['forecast']['completion_grace_minutes']*60)})
            return {"store_uuid": self.uuid, "jobs": len(self.jobs()), "stages": [dict(r) for r in c.execute("SELECT * FROM stages")],
                "job_windows":jobs,
                "circuits": [dict(r) for r in c.execute("SELECT id FROM circuits")],
                "heartbeat": [dict(r) for r in c.execute("SELECT * FROM heartbeat")],
                "reservations": [dict(r) for r in c.execute("SELECT job,kind,count(*) AS calls,sum(usd) AS reserved_usd FROM requests GROUP BY job,kind")]}

    def heartbeat(self,lane):
        with self.db() as c:c.execute('INSERT OR REPLACE INTO heartbeat VALUES(?,?)',(lane,iso(self.clock())))
