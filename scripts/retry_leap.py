#!/usr/bin/env python3
"""Explicitly authorized failed-request retry layer; frozen inference unchanged."""
import argparse
import json
import math
import os
import shutil
import time
from pathlib import Path

import leap_forecast as leap
from evidence_documents import canonical, digest
from forecast_split import ROOT, DEFAULT_DATA, DEFAULT_SPLIT, immutable_json

AUTHORIZATION = "Operator explicitly requested retrying failed development requests and merging successful replacements; one new attempt per failed request."
REGISTRY = ROOT / "captures/leap_failed_retry_registry"


def retry_plan(source, dataset=DEFAULT_DATA):
    source = Path(source)
    if json.loads((source/"run.json").read_text())["subset"] != "development":
        raise ValueError("Retries are restricted to development; reserved scope is forbidden")
    leap.verify_experiment(source, dataset)
    run, games, _ = leap.load_experiment(source)
    plan, specs = leap.plan_experiment(dataset, DEFAULT_SPLIT, run["config"], limit=len(games))
    original = {r["request_sha256"]: r for g in games for r in g["groups"]}
    failed = [s for s in specs if original[s["key"]]["status"] == "failed"]
    if any(not s["usable"] for s in failed):
        raise ValueError("Missing evidence cannot be retried as a model request")
    identity = {"kind": "explicit_failed_development_retry", "source_completion_sha256": digest((source/"completion.json").read_bytes()),
        "source_directory": str(source.resolve()), "source_cache_directory": run["cache_directory"],
        "split_sha256": run["split_sha256"], "config": run["config"], "authorization": AUTHORIZATION,
        "failed_requests": [{**leap.brief(s), "original_record_sha256": original[s["key"]]["record_sha256"]} for s in failed],
        "maximum_new_requests": len(failed), "reserved_upper_bound_usd": math.fsum(s["reserved_cost_usd"] for s in failed)}
    return identity, plan, specs, original, failed


def run_retries(source, output, allow_paid=False, max_calls=40, max_cost=1.20, dataset=DEFAULT_DATA,
        registry=REGISTRY, transport_factory=leap.CapturedHTTP, delay_seconds=1):
    identity, _, _, original, failed = retry_plan(source, dataset)
    if type(max_calls) is not int or max_calls < 0 or type(max_cost) not in (int,float) or not math.isfinite(max_cost) or max_cost < 0:
        raise ValueError("Finite nonnegative budgets required")
    if len(failed) > max_calls or identity["reserved_upper_bound_usd"] > max_cost + 1e-12:
        raise ValueError("Entire retry plan exceeds authorization; no calls made")
    output = Path(output)
    leap.protect_paths(output, identity["source_directory"], dataset)
    leap.protect_paths(output, identity["source_cache_directory"], dataset)
    if not allow_paid or not os.environ.get(identity["config"]["key_env"]):
        raise ValueError("Explicit retry/network/inference authorization and credential required")
    # A second output path cannot silently create a third attempt of the same
    # original failed run. Original request/cache identities never change.
    immutable_json(Path(registry)/identity["source_completion_sha256"]/"authorization.json",
        {"authorization": AUTHORIZATION, "output_directory": str(output.resolve()),
         "source_completion_sha256": identity["source_completion_sha256"]})
    output.mkdir(parents=True, exist_ok=True)
    manifest = {**identity, "max_paid_calls": max_calls, "max_estimated_cost_usd": max_cost}
    immutable_json(output/"retry_run.json", manifest)
    if (output/"completion.json").exists():
        return verify_retry(source, output, dataset)
    lock = output/".running"
    with lock.open("xb") as f: f.write(b"Active or interrupted retry; investigate before resuming.\n")
    try:
        attempted = []
        for spec in failed:
            # Reserve before invoking the original one-attempt cache machinery.
            immutable_json(output/"reservations"/(spec["key"]+".json"),
                {"request_sha256": spec["key"], "cost_usd": spec["reserved_cost_usd"],
                 "original_record_sha256": original[spec["key"]]["record_sha256"], "attempt_ordinal": 2})
            result = leap.cached_group(spec, identity["config"], output/"attempt_cache", True, transport_factory)
            attempted.append(result)
            if result["status"] != "success":
                break  # No repeated attempts or continued spending after failure.
            if delay_seconds:
                time.sleep(delay_seconds)
        complete = {"attempted": len(attempted), "successful": sum(r["status"]=="success" for r in attempted),
            "failed": sum(r["status"]!="success" for r in attempted), "not_attempted_after_stop": len(failed)-len(attempted),
            "reserved_cost_usd": math.fsum(r["reserved_cost_usd"] for r in attempted),
            "estimated_response_cost_usd": math.fsum(r["estimated_cost_usd"] for r in attempted),
            "reported_usage": {k: sum((r.get("usage") or {}).get(k,0) for r in attempted) for k in ("input_tokens","output_tokens")},
            "latency_seconds": math.fsum(r.get("latency_seconds") or 0 for r in attempted),
            "selected_request_sha256": [r["request_sha256"] for r in attempted if r["status"]=="success"],
            "files": {str(p.relative_to(output)): digest(p.read_bytes()) for p in sorted(output.rglob("*")) if p.is_file() and p.name!=".running"}}
        immutable_json(output/"completion.json", complete)
        return verify_retry(source, output, dataset)
    finally:
        lock.unlink()


def verify_retry(source, output, dataset=DEFAULT_DATA):
    output = Path(output)
    identity, _, _, original, failed = retry_plan(source, dataset)
    saved = json.loads((output/"retry_run.json").read_text())
    if any(saved[k] != v for k,v in identity.items()):
        raise ValueError("Original retry inputs changed")
    complete = json.loads((output/"completion.json").read_text())
    for name, sha in complete["files"].items():
        path = (output/name).resolve()
        if output.resolve() not in path.parents or digest(path.read_bytes()) != sha:
            raise ValueError("Retry capture hash mismatch")
    records = []
    for spec in failed[:complete["attempted"]]:
        record = leap.load_cached(spec, output/"attempt_cache")
        if record["status"]=="success":
            import gzip
            response = json.loads(gzip.decompress((output/"attempt_cache"/spec["key"]/record["raw_response"]["body_file"]).read_bytes()))
            parsed = leap.validate_response(response,spec,identity["config"])
            if any(record[k]!=v for k,v in parsed.items()): raise ValueError("Retry LR does not reproduce")
        records.append(record)
    if ([r["request_sha256"] for r in records if r["status"]=="success"] != complete["selected_request_sha256"]
            or complete["successful"] != sum(r["status"]=="success" for r in records)
            or complete["failed"] != sum(r["status"]!="success" for r in records)
            or complete["not_attempted_after_stop"] != len(failed)-len(records)
            or complete["attempted"] > saved["max_paid_calls"]
            or complete["reserved_cost_usd"] > saved["max_estimated_cost_usd"]+1e-12):
        raise ValueError("Retry counters/budget do not reconcile")
    checks={"reserved_cost_usd":math.fsum(r["reserved_cost_usd"] for r in records),
        "estimated_response_cost_usd":math.fsum(r["estimated_cost_usd"] for r in records),
        "latency_seconds":math.fsum(r.get("latency_seconds") or 0 for r in records),
        "reported_usage":{k:sum((r.get("usage") or {}).get(k,0) for r in records) for k in ("input_tokens","output_tokens")}}
    if any(complete[k]!=v for k,v in checks.items()): raise ValueError("Retry usage/cost/latency does not reconcile")
    return complete


def merge_successes(source, retry, output, cache, dataset=DEFAULT_DATA):
    identity, plan, specs, original, _ = retry_plan(source, dataset)
    complete = verify_retry(source,retry,dataset)
    output, cache, retry = Path(output), Path(cache), Path(retry)
    for root in (identity["source_directory"], identity["source_cache_directory"], retry):
        leap.protect_paths(output,root,dataset); leap.protect_paths(cache,root,dataset)
    leap.protect_paths(output,cache,dataset)
    selected=set(complete["selected_request_sha256"])
    lineage=[]
    for s in specs:
        root = retry/"attempt_cache" if s["key"] in selected else Path(identity["source_cache_directory"])
        chosen=leap.load_cached(s,root)
        if s["key"] in selected and (original[s["key"]]["status"]!="failed" or chosen["status"]!="success"):
            raise ValueError("Only a successful authorized retry may replace a failed original")
        target=cache/s["key"]
        if not target.exists(): shutil.copytree(root/s["key"], target)
        if leap.load_cached(s,cache)!=chosen: raise ValueError("Merged cache differs from selected observation")
        lineage.append({"request_sha256":s["key"],"game_id":s["game_id"],"group":s["group"],
            "selection":"successful_authorized_retry" if s["key"] in selected else "original_observation",
            "original_record_sha256":original[s["key"]]["record_sha256"],"selected_record_sha256":chosen["record_sha256"]})
    immutable_json(output/"merge_lineage.json",{"original_completion_sha256":identity["source_completion_sha256"],
        "retry_completion_sha256":digest((retry/"completion.json").read_bytes()),"observations":lineage})
    immutable_json(output/"run.json",{**plan,"cache_directory":str(cache.resolve()),
        "max_paid_calls":0,"max_estimated_cost_usd":0})
    if (output/"completion.json").exists():
        leap.verify_experiment(output,dataset)
        return leap.load_experiment(output)[2]
    games=[]
    for g in plan["games"]:
        records=[leap.load_cached(s,cache) for s in specs if s["game_id"]==g["game_id"]]
        record=leap.game_record(g["game_id"],g["evidence_sha256"],records)
        immutable_json(output/"forecasts"/(g["game_id"]+".json"),record);games.append(record)
    result={**leap.counters(games),"paid_call_reservations":0,"reserved_cost_usd":0,
        "reused_observations":sum(r["status"]=="success" for g in games for r in g["groups"]),
        "files":{str(p.relative_to(output)):digest(p.read_bytes()) for p in sorted(output.rglob("*")) if p.is_file()}}
    immutable_json(output/"completion.json",result)
    leap.verify_experiment(output,dataset)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source",type=Path,required=True)
    p.add_argument("--output",type=Path)
    p.add_argument("--plan",action="store_true")
    p.add_argument("--verify",type=Path)
    p.add_argument("--merge",type=Path,help="Merge a sealed authorized retry batch offline")
    p.add_argument("--merged-cache",type=Path)
    for flag in ("live","allow-network","allow-inference","authorize-failed-retries"):
        p.add_argument("--"+flag,action="store_true")
    p.add_argument("--max-paid-calls",type=int,default=40)
    p.add_argument("--max-estimated-cost-usd",type=float,default=1.20)
    a=p.parse_args()
    live=a.live and a.allow_network and a.allow_inference and a.authorize_failed_retries
    if a.verify:
        if any((a.live,a.allow_network,a.allow_inference,a.authorize_failed_retries)):p.error("Verification is offline")
        r=verify_retry(a.source,a.verify)
    elif a.merge:
        if not a.output or not a.merged_cache or any((a.live,a.allow_network,a.allow_inference,a.authorize_failed_retries)):p.error("Merge requires separate output/cache and is offline")
        r=merge_successes(a.source,a.merge,a.output,a.merged_cache)
    elif a.plan or not live:
        r=retry_plan(a.source)[0]
    else:
        if not a.output:p.error("Live retries require output and all explicit opt-ins")
        r=run_retries(a.source,a.output,True,a.max_paid_calls,a.max_estimated_cost_usd)
    print(json.dumps({k:v for k,v in r.items() if k not in ("files","failed_requests")},indent=2))


if __name__=="__main__":main()
