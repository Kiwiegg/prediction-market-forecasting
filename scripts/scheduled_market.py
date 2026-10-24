#!/usr/bin/env python3
"""Independent one-game benchmark task; never loaded by evidence/forecast code."""
import argparse
import json
import time

import scheduled_prospective as pilot
import prospective_evaluate as evaluation
from evidence_documents import digest
from forecast_split import immutable_json
from investigate_kalshi import BASE as MARKET_BASE, iso
from prospective_sources import url


def run(clock=time.time, sleep=time.sleep):
    job = pilot.load_job(); base = pilot.BASE / "market"; result_path = base / "result.json"
    with pilot.lock(base, "market"):
        if result_path.exists(): pilot.retire(job, "market"); return json.loads(result_path.read_text())
        due = pilot.phase_due(job, "market", clock())
        if due == "pending": return {"status": "pending", "paid_calls": 0}
        budget = pilot.JobBudget(pilot.BASE, clock, pilot.STOP)
        try:
            pilot.check_stops(job)
            if (base / "claim.json").exists(): raise ValueError("Interrupted benchmark is missing; never retrieve a later price")
            if due != "due": raise ValueError(due)
            immutable_json(base / "claim.json", {"job_id": job["job_id"], "at_utc": iso(clock())})
            pilot.revalidate(job, base / "revalidation", budget, clock)
            game = job["game"]; target = pilot.study.aware(job["plan"]["target_cutoff_utc"])
            event = evaluation.event_ticker(game)
            milestone_url = url(MARKET_BASE + "/milestones", limit=100, related_event_ticker=event)
            quote_url = MARKET_BASE + "/markets/" + event + "-" + game["home_code"]
            def guard():
                pilot.check_stops(job)
                if clock() > target: raise pilot.study.Halt("Cutoff passed; benchmark stays missing")
            guard()
            store = pilot.study.OneShotDocuments(base / "raw", False, lambda u: u in (milestone_url, quote_url), budget, guard=guard, clock=clock)
            mm, mb = store.get(milestone_url)
            if mm["http_status"] != 200 or mm["truncated"]: raise ValueError("Milestone source unavailable")
            send_at = pilot.study.aware(job["plan"]["market_request_utc"])
            while clock() < send_at:
                sleep(min(1, send_at - clock()))
                guard()
            qm, qb = store.get(quote_url)
            if qm["http_status"] != 200 or qm["truncated"]: raise ValueError("Quote source unavailable")
            record = evaluation.quote_record(game, json.loads(qb).get("market", {}), json.loads(mb), pilot.study.aware(qm["retrieved_at_utc"]))
            immutable_json(base / "quote.json", record)
            immutable_json(base / "manifest.json", {str(p.relative_to(base)): digest(p.read_bytes()) for p in base.rglob('*') if p.is_file() and p.name != "market.lock"})
            result = {"status": "quote_captured" if record["eligible"] else "missing_quote", "eligible": record["eligible"],
                "missing_reason": record["missing_reason"], "retrieved_at_utc": record["retrieved_at_utc"], "job_id": job["job_id"]}
        except (Exception, pilot.study.Halt, KeyboardInterrupt) as e:
            result = {"status": "missing_quote", "eligible": False, "missing_reason": str(e), "error_type": type(e).__name__,
                "job_id": job["job_id"], "at_utc": iso(clock())}
        immutable_json(result_path, result); pilot.retire(job, "market"); return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", action="store_true"); p.add_argument("--allow-network", action="store_true"); p.add_argument("--replay", action="store_true")
    a = p.parse_args()
    if a.run:
        if not a.allow_network or a.replay: p.error("Independent market task needs explicit network permission")
        pilot.assets(True); pilot.worker_start("market"); result = run()
    elif a.replay:
        if a.allow_network: p.error("Replay is offline")
        result = evaluation.verify_source_capture(pilot.BASE / "market", "quote") if (pilot.BASE / "market/quote.json").exists() else {"status": "missing_or_pending", "network_calls": 0}
    else:
        if a.allow_network: p.error("Default is offline")
        result = {"status": "plan_only", "plan": pilot.load_job()["plan"], "network_calls": 0}
    print(json.dumps(result, indent=2))


if __name__ == "__main__": main()
