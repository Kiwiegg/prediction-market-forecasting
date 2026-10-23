#!/usr/bin/env python3
"""Execution-only guards for the frozen 50-game v2 development experiment."""
import argparse
import gzip
import json
import math
import os
import subprocess
import time
from pathlib import Path

import direct_forecast as direct
import leap_forecast as v1
import leap_v2_forecast as v2
from evidence_documents import canonical,digest
from forecast_split import ROOT,immutable_json
from investigate_kalshi import iso
from leap_v2_evidence import REGISTRY_SHA,aggregate,brief,plan_experiment
from research_providers import CapturedHTTP

PLAN_PATH=ROOT/"experiments/leap_nba_v2_development_50_analysis_plan.json"
BASE=ROOT/"captures/leap_nba_v2_phase2_development_50"
AUTH=ROOT/"captures/leap_nba_v2_phase2_authorization_full-development.json"


def analysis_plan():return json.loads(PLAN_PATH.read_text())


def cache_state(specs,cache):
    original=[];fresh=[]
    for s in specs:
        folder=Path(cache)/s["key"]
        if (folder/"group.json").exists():
            v2.load_cached(s,cache);original.append(s["key"])
        elif (folder/"attempt.json").exists():raise ValueError("Uncertain original attempt: no new paid requests permitted")
        elif s["usable"]:fresh.append(s)
    return original,fresh


def preflight():
    rules=analysis_plan();plan,specs=plan_experiment(scope="full-development",authorize_development=True)
    if plan["frozen_registry_sha256"]!=rules["forecast_registry_sha256"]:raise ValueError("Frozen v2 registry differs")
    for name,sha in plan["frozen_assets"].items():
        if digest(subprocess.check_output(["git","show","8520406:"+name],cwd=ROOT))!=sha:raise ValueError("Asset differs from pre-inference commit: "+name)
    for name in ("scripts/leap_v2_evidence.py","scripts/leap_v2_forecast.py"):
        if (ROOT/name).read_bytes()!=subprocess.check_output(["git","show","8520406:"+name],cwd=ROOT):raise ValueError("Original v2 code changed")
    old=rules["execution"]
    pilot=v2.verify_experiment(ROOT/old["pilot"])
    dr=direct.verify_experiment(ROOT/old["direct"]);lr=v1.verify_experiment(ROOT/old["v1"])
    if pilot["successful_forecasts"]!=5:raise ValueError("Original five pilot forecasts unavailable")
    original,fresh=cache_state(specs,v2.DEFAULT_CACHE)
    return {"schema_version":1,"git_commit":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
        "analysis_plan_sha256":digest(PLAN_PATH.read_bytes()),"frozen_registry_sha256":REGISTRY_SHA,
        "split_sha256":plan["split_sha256"],"game_ids":[g["game_id"] for g in plan["games"]],
        "parent_evidence_hashes":{g["game_id"]:g["evidence_sha256"] for g in plan["games"]},
        "original_cache_keys":original,"new_request_keys":[s["key"] for s in fresh],
        "planned_new_calls":len(fresh),"additional_reservation_usd":math.fsum(s["reserved_cost_usd"] for s in fresh),
        "original_pilot_calls":pilot["paid_call_reservations"],"existing_direct_complete":dr["successful_forecasts"],"existing_v1_complete":lr["successful_forecasts"],
        "prior_completion_hashes":{name:digest((ROOT/old[name]/"completion.json").read_bytes()) for name in ("pilot","direct","v1")},
        "baseline_manifest_sha256":digest((ROOT/old["baseline_public"]/"manifest.json").read_bytes()),
        "config":plan["config"],"max_new_requests":180,"max_additional_reserved_cost_usd":5,"network_calls":0}


def response_category(r,cache):
    raw=r.get("raw_response")
    if not raw:return "model_abstention" if r["status"]=="insufficient" else "invalid_response" if r["status"]=="failed" else r["status"]
    rules=analysis_plan()["execution"];status=raw["http_status"]
    if status in rules["stop_http_statuses"]:return "access_denial"
    raw_body=gzip.decompress((Path(cache)/r["key"]/raw["body_file"]).read_bytes())
    try:body=json.loads(raw_body)
    except (ValueError,UnicodeError):body={}
    # A provider/proxy error page is not model evidence. Do not inspect normal
    # JSON content blocks for denial phrases (they may quote untrusted text).
    page=raw_body.decode("utf-8",errors="replace").strip().casefold()
    if (status>=400 or page.startswith(("<html","<!doctype"))) and not isinstance(body.get("content") if isinstance(body,dict) else None,list):
        if any(m in page for m in rules["stop_error_messages"]):return "access_denial"
    error=body.get("error") if isinstance(body,dict) else None
    if isinstance(error,dict):
        kind=error.get("type");message=error.get("message")
        if kind in rules["stop_error_types"] or isinstance(message,str) and any(m in message.casefold() for m in rules["stop_error_messages"]):return "access_denial"
    if status==0:return "transport_failure"
    if status!=200:return "provider_http_failure"
    if raw["truncated"]:return "response_truncated"
    return "model_abstention" if r["status"]=="insufficient" else "invalid_response" if r["status"]=="failed" else "usable_response"


def blocked(spec,cfg,status,reason):
    r=v2.base_record(spec,cfg,status);r["error"]={"type":reason,"message":"No model request made; execution stopped"}
    return direct.signed_record(r)


def uncertain(spec,cfg,cache):
    marker=Path(cache)/spec["key"]/"attempt.json"
    r=v2.base_record(spec,cfg,"failed");r.update(uncertain_attempt=True,attempt_marker_sha256=digest(marker.read_bytes()),
        estimated_cost_usd=spec["reserved_cost_usd"],estimated_cost_kind="reserved_upper_bound_usage_unavailable",
        error={"type":"InterruptedUnknown","message":"Prior claimed attempt has no terminal response; never automatically resend"})
    return direct.signed_record(r)


def game_record(game,records):
    adapted=[{**r,"status":"failed"} if r["status"]=="not_attempted_interrupted" else r for r in records]
    return direct.signed_record({"game_id":game["game_id"],"evidence_sha256":game["evidence_sha256"],"groups":records,**aggregate(adapted)})


def seal(output,plan,specs,cache,reason):
    output=Path(output);cfg=plan["config"];games=[]
    # On process interruption, retain all terminal cache observations and mark
    # claimed unknown requests separately from requests never made.
    for game in plan["games"]:
        path=output/"forecasts"/(game["game_id"]+".json")
        if path.exists():games.append(json.loads(path.read_text()));continue
        records=[]
        for s in (s for s in specs if s["game_id"]==game["game_id"]):
            folder=Path(cache)/s["key"]
            if (folder/"group.json").exists():r=v2.load_cached(s,cache)
            elif (folder/"attempt.json").exists():r=uncertain(s,cfg,cache)
            elif not s["usable"]:r=v2.cached_group(s,cfg,cache)
            else:r=blocked(s,cfg,"not_attempted_interrupted",reason["category"])
            records.append(r)
        g=game_record(game,records);immutable_json(path,g);games.append(g)
    reservations=[json.loads(p.read_text()) for p in (output/"reservations").glob("*.json")]
    categories={r["key"]:response_category(r,cache) for g in games for r in g["groups"] if r.get("raw_response")}
    immutable_json(output/"execution.json",{"stop_reason":reason,"response_categories":categories})
    complete={**v2.counters(games),"paid_call_reservations":len(reservations),"reserved_cost_usd":math.fsum(r["cost_usd"] for r in reservations),
        "stopped_on_access_denial":reason["category"]=="access_denial","completed_at_utc":iso(time.time()),
        "files":{str(p.relative_to(output)):digest(p.read_bytes()) for p in sorted(output.rglob("*")) if p.is_file() and p.name!=".running"}}
    immutable_json(output/"completion.json",complete)
    return verify(output)[2]


def execute(plan,specs,output,cache,before,allow_paid=False,transport_factory=CapturedHTTP,authorization_path=AUTH,seal_interrupted=False):
    expected,rebuilt=plan_experiment(plan["config"]["provider"]=="mock",scope="full-development",authorize_development=True)
    if plan!=expected or specs!=rebuilt:raise ValueError("Plan differs from frozen full-development evidence")
    output,cache=Path(output),Path(cache);v2.protect_paths(output,cache);cfg=plan["config"];mock=cfg["provider"]=="mock"
    identity={**plan,"cache_directory":str(cache.resolve()),"max_paid_calls":180,"max_estimated_cost_usd":5,
        "development_execution":{"analysis_plan_sha256":digest(PLAN_PATH.read_bytes()),"preflight":before}}
    if seal_interrupted:
        if json.loads((output/"run.json").read_text())!=identity:raise ValueError("Interrupted manifest differs")
        if (output/"completion.json").exists():return verify(output)[2]
        return seal(output,plan,specs,cache,{"category":"interrupted","message":"Explicit offline sealing; no new requests"})
    if (output/"completion.json").exists():return verify(output)[2]
    original,fresh=cache_state(specs,cache)
    if before["original_cache_keys"]!=original or before["new_request_keys"]!=[s["key"] for s in fresh] or before["analysis_plan_sha256"]!=digest(PLAN_PATH.read_bytes()):raise ValueError("Cache/preflight changed before execution")
    if not mock and (len(fresh)>180 or math.fsum(s["reserved_cost_usd"] for s in fresh)>5):raise ValueError("Full remaining plan exceeds authorization; no requests made")
    if not mock and (not allow_paid or not os.environ.get(cfg["key_env"])):raise ValueError("Explicit network/inference opt-ins and credential required")
    if not mock:immutable_json(authorization_path,{"output_directory":str(output.resolve()),"frozen_registry_sha256":REGISTRY_SHA,"scope":"full-development"})
    immutable_json(output/"run.json",identity)
    lock=output/".running"
    with lock.open("xb") as f:f.write(b"Active/interrupted run. Use offline --seal-interrupted; never resend claims.\n")
    reason={"category":"completed","message":"All planned group slots processed"};stopped=False;spent=0
    try:
        for game in plan["games"]:
            records=[]
            for s in (s for s in specs if s["game_id"]==game["game_id"]):
                cached=(cache/s["key"]/"group.json").exists()
                if cached or not s["usable"]:r=v2.cached_group(s,cfg,cache,allow_paid,transport_factory)
                elif stopped:r=blocked(s,cfg,"not_attempted_access_denial" if reason["category"]=="access_denial" else "not_attempted_budget",reason["category"])
                else:
                    reservations=[json.loads(p.read_text()) for p in (output/"reservations").glob("*.json")]
                    if not mock and (len(reservations)>=180 or max(spent,math.fsum(v["cost_usd"] for v in reservations))+s["reserved_cost_usd"]>5+1e-12):
                        stopped=True;reason={"category":"budget","request_sha256":s["key"]};r=blocked(s,cfg,"not_attempted_budget","BudgetStop")
                    else:
                        if not mock:immutable_json(output/"reservations"/(s["key"]+".json"),{"request_sha256":s["key"],"cost_usd":s["reserved_cost_usd"],"reserved_at_utc":iso(time.time())})
                        r=v2.cached_group(s,cfg,cache,allow_paid,transport_factory);spent+=r["estimated_cost_usd"]
                if r.get("raw_response") and response_category(r,cache)=="access_denial":
                    stopped=True;reason={"category":"access_denial","request_sha256":s["key"],"http_status":r["raw_response"]["http_status"]}
                records.append(r)
            immutable_json(output/"forecasts"/(game["game_id"]+".json"),game_record(game,records))
    except KeyboardInterrupt:reason={"category":"interrupted","message":"Keyboard interruption; no request retried"}
    except Exception as exc:reason={"category":"execution_error","error_type":type(exc).__name__,"message":"Execution stopped; no request retried"}
    finally:
        result=seal(output,plan,specs,cache,reason)
        lock.unlink()
    return result


def verify(output):
    output=Path(output);run=json.loads((output/"run.json").read_text());complete=json.loads((output/"completion.json").read_text())
    if run["subset"]!="development" or run["scope"]!="full-development":raise ValueError("Development-only verification")
    plan,specs=plan_experiment(run["config"]["provider"]=="mock",scope="full-development",authorize_development=True)
    if any(run[k]!=v for k,v in plan.items()) or run["development_execution"]["analysis_plan_sha256"]!=digest(PLAN_PATH.read_bytes()):raise ValueError("Frozen plan changed")
    required={"run.json","execution.json"}|{"forecasts/"+g["game_id"]+".json" for g in plan["games"]}
    if not required<=set(complete["files"]):raise ValueError("Incomplete seal")
    for name,sha in complete["files"].items():
        p=(output/name).resolve()
        if output.resolve() not in p.parents or digest(p.read_bytes())!=sha:raise ValueError("Execution file hash differs")
    cache=Path(run["cache_directory"]);games=[]
    for planned in plan["games"]:
        g=json.loads((output/"forecasts"/(planned["game_id"]+".json")).read_text())
        validate_public_game(g,planned)
        for r,s in zip(g["groups"],[s for s in specs if s["game_id"]==g["game_id"]]):
            if r.get("uncertain_attempt"):
                if digest((cache/r["key"]/"attempt.json").read_bytes())!=r["attempt_marker_sha256"] or (cache/r["key"]/"group.json").exists():raise ValueError("Uncertain claim changed")
            elif not r["status"].startswith("not_attempted"):
                if v2.load_cached(s,cache)!=r:raise ValueError("Cached observation differs")
                if r.get("raw_response") and r["raw_response"]["http_status"]==200 and not r["raw_response"]["truncated"]:
                    try:
                        response=json.loads(gzip.decompress((cache/r["key"]/r["raw_response"]["body_file"]).read_bytes()))
                        if not isinstance(response,dict):raise ValueError("Nonobject provider capture")
                        parsed=v2.parse_response(response,s,run["config"])
                    except (ValueError,TypeError,KeyError,UnicodeError):
                        if r["status"]!="failed":raise ValueError("Raw response classification differs")
                    else:
                        if any(r[k]!=v for k,v in parsed.items()):raise ValueError("Raw response mapping differs")
                elif run["config"]["provider"]=="mock" and r["usable"]:
                    response=json.loads((cache/r["key"]/"mock_response.json").read_text())
                    parsed=v2.parse_response(response,s,run["config"])
                    if any(r[k]!=v for k,v in parsed.items()):raise ValueError("Mock response mapping differs")
        games.append(g)
    execution=json.loads((output/"execution.json").read_text());categories={r["key"]:response_category(r,cache) for g in games for r in g["groups"] if r.get("raw_response")}
    if execution["response_categories"]!=categories:raise ValueError("Provider classifications differ")
    expected=v2.counters(games);expected["stopped_on_access_denial"]=execution["stop_reason"]["category"]=="access_denial"
    if any(complete[k]!=v for k,v in expected.items()):raise ValueError("Execution counters disagree")
    reservations=[json.loads(p.read_text()) for p in (output/"reservations").glob("*.json")];bykey={s["key"]:s for s in specs}
    if (len(reservations)!=complete["paid_call_reservations"] or len(reservations)>180 or math.fsum(r["cost_usd"] for r in reservations)!=complete["reserved_cost_usd"] or complete["reserved_cost_usd"]>5
            or any(r["request_sha256"] not in bykey or bykey[r["request_sha256"]]["reserved_cost_usd"]!=r["cost_usd"] for r in reservations)):raise ValueError("Execution budget ledger differs")
    return run,games,complete,execution


def validate_public_game(g,planned):
    if len(g["groups"])!=4:raise ValueError("Four groups required")
    for r,s in zip(g["groups"],planned["groups"]):
        if any(r[k]!=v for k,v in s.items()):raise ValueError("Projection/request identity changed")
        if r["status"]=="not_attempted_interrupted":
            if r["likelihood_ratio"] is not None or r["record_sha256"]!=direct.signed_record({k:v for k,v in r.items() if k!="record_sha256"})["record_sha256"]:raise ValueError("Interrupted record changed")
        else:v2.verify_record(r)
    if game_record(planned,g["groups"])!=g:raise ValueError("Frozen aggregation differs")


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for f in ("plan","mock","live","allow-network","allow-inference","seal-interrupted"):p.add_argument("--"+f,action="store_true")
    p.add_argument("--preflight",type=Path,default=BASE/"preflight.json");p.add_argument("--save-preflight",action="store_true");p.add_argument("--verify",type=Path);a=p.parse_args()
    if a.plan and any((a.live,a.allow_network,a.allow_inference,a.mock,a.seal_interrupted)):p.error("Planning cannot enable inference or sealing")
    if a.seal_interrupted and any((a.live,a.allow_network,a.allow_inference,a.mock)):p.error("Interrupted sealing is offline only")
    if a.save_preflight and any((a.live,a.mock,a.seal_interrupted,a.verify)):p.error("Preflight saving is a separate offline step")
    if a.verify:
        if any((a.live,a.allow_network,a.allow_inference,a.mock)):p.error("Verification cannot enable network")
        result=verify(a.verify)[2]
    elif a.mock:
        if any((a.live,a.allow_network,a.allow_inference)):p.error("Mock cannot enable network")
        plan,specs=plan_experiment(True,scope="full-development",authorize_development=True);cache=BASE/"mock_cache"
        original,fresh=cache_state(specs,cache);before={"original_cache_keys":original,"new_request_keys":[s["key"] for s in fresh],"analysis_plan_sha256":digest(PLAN_PATH.read_bytes())}
        result=execute(plan,specs,BASE/"mock",cache,before)
    elif a.live or a.seal_interrupted:
        if a.live and not(a.allow_network and a.allow_inference):p.error("All three live opt-ins required")
        plan,specs=plan_experiment(scope="full-development",authorize_development=True);before=json.loads(a.preflight.read_text())
        if a.live and not a.seal_interrupted and not (BASE/"run/completion.json").exists():
            if preflight()!=before:raise ValueError("Saved preflight differs; do not bypass original attempts")
        result=execute(plan,specs,BASE/"run",v2.DEFAULT_CACHE,before,a.live,seal_interrupted=a.seal_interrupted)
    else:
        result=preflight()
        if a.save_preflight:immutable_json(a.preflight,result)
    print(json.dumps({k:v for k,v in result.items() if k not in ("files","original_cache_keys","new_request_keys","parent_evidence_hashes")},indent=2))


if __name__=="__main__":main()
