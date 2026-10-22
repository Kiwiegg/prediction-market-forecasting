#!/usr/bin/env python3
"""One bounded synthetic-only experiment. Default is a zero-network cost plan."""
import argparse
import gzip
import json
import math
import os
import time
from pathlib import Path

from direct_forecast import signed_record,verify_raw
from evidence_documents import canonical,digest
from forecast_split import immutable_json
from investigate_kalshi import iso
from research_providers import CapturedHTTP,ProviderError
from synthetic_elicitation import ROOT,REGISTRY_SHA,make_specs,strict_json,parse_assessment

DEFAULT_CACHE=ROOT/"captures/leap_nba_v2_phase1_cache"


def record_valid(r):
    if r.get("record_sha256")!=digest(canonical({k:v for k,v in r.items() if k!="record_sha256"})):raise ValueError("Synthetic record hash mismatch")
    if r["schema_valid"]:
        parsed=parse_assessment(r["method"],r["assessment"])
        if any(r[k]!=v for k,v in parsed.items()):raise ValueError("Assessment/mapping changed")
    elif r["likelihood_ratio"] is not None:raise ValueError("Failed observation was imputed")
    return r


def validate_envelope(response,spec,config):
    u=response.get("usage")
    if (not isinstance(u,dict) or any(type(u.get(k)) is not int or u[k]<0 for k in ("input_tokens","output_tokens"))
            or u["input_tokens"]>spec["input_token_bound"] or u["output_tokens"]>128
            or u.get("cache_creation_input_tokens",0) or u.get("cache_read_input_tokens",0)
            or not isinstance(u.get("server_tool_use",{}),dict) or any(u.get("server_tool_use",{}).values())):
        raise ValueError("Invalid/unexpected usage or tool/cache billing")
    b=response.get("content")
    if (response.get("model")!=config["model"] or response.get("stop_reason")!="end_turn" or response.get("role")!="assistant"
            or not isinstance(b,list) or len(b)!=1 or not isinstance(b[0],dict) or set(b[0]) - {"type","text","citations"}
            or b[0].get("type")!="text" or not isinstance(b[0].get("text"),str) or b[0].get("citations")):
        raise ValueError("Invalid model/stop/content; tools and citations forbidden")
    return b[0]["text"]


def empty_record(spec,config,status):
    return {"schema_version":1,"method":spec["method"],"request_sha256":spec["key"],
        "provider":config["provider"],"requested_model":config["model"],"returned_model":None,
        "generation_settings":config["generation"],"prompt_sha256":spec["prompt_sha256"],
        "input_text_sha256":spec["input_text_sha256"],"evidence_sha256":spec["evidence_sha256"],
        "status":status,"strict_json_object_valid":False,"schema_valid":False,"assessment":None,
        "likelihood_ratio":None,"direction":None,"unsupported_field_count":0,
        "raw_response":None,"usage":None,"estimated_cost_usd":0,"estimated_cost_kind":"not_requested",
        "reserved_cost_usd":spec["reserved_cost_usd"],"request_started_at_utc":None,"response_retrieved_at_utc":None,
        "latency_seconds":None,"error":None}


def parse_into_record(r,response,spec,config):
    text=validate_envelope(response,spec,config)
    value=strict_json(text);r["strict_json_object_valid"]=True
    expected={"likelihood_ratio","evidence_sufficiency"} if spec["method"]=="numeric" else {"favored_side","strength","evidence_sufficiency"}
    r["unsupported_field_count"]=len(set(value)-expected)
    parsed=parse_assessment(spec["method"],value)
    r.update(**parsed,schema_valid=True)
    return r


def read_cache(spec,cache):
    folder=Path(cache)/spec["key"]
    r=record_valid(json.loads((folder/"response.json").read_text()))
    for k,sk in (("request_sha256","key"),("input_text_sha256","input_text_sha256"),("evidence_sha256","evidence_sha256"),("prompt_sha256","prompt_sha256"),("method","method")):
        if r[k]!=spec[sk]:raise ValueError("Synthetic cache identity mismatch")
    verify_raw(r,folder)
    if r["raw_response"] and (folder/"raw"/(spec["key"]+".request.json")).read_bytes()!=canonical(spec["wire"])+b"\n":raise ValueError("Wire request changed")
    return r


def cached_request(spec,config,cache,allow_paid=False,transport_factory=CapturedHTTP):
    folder=Path(cache)/spec["key"];final=folder/"response.json"
    if final.exists():return read_cache(spec,cache)
    folder.mkdir(parents=True,exist_ok=True)
    if (folder/"attempt.json").exists():raise ValueError("Uncertain prior request: automatic resend forbidden")
    if config["provider"]!="mock" and (not allow_paid or not os.environ.get(config["key_env"])):raise ValueError("Paid synthetic requests require explicit opt-ins and credential")
    with (folder/"attempt.json").open("xb") as f:f.write(canonical({"request_sha256":spec["key"],"claimed_at_utc":iso(time.time())})+b"\n")
    r=empty_record(spec,config,"provider_error")
    r.update(estimated_cost_usd=spec["reserved_cost_usd"],estimated_cost_kind="reserved_upper_bound_usage_unavailable")
    transport=transport_factory(folder/"raw",allow_network=allow_paid)
    try:
        if config["provider"]=="mock":
            # Intentionally simple mock, not an empirical LLM or fixture oracle.
            e=json.loads(spec["wire"]["payload"]["messages"][0]["content"])
            informative=any(e[s].get("regular_season_record",{}).get("games_completed",0)>0 for s in ("Team X","Team Y"))
            assessment=({"likelihood_ratio":1,"evidence_sufficiency":"limited" if informative else "insufficient"} if spec["method"]=="numeric" else
                {"favored_side":"neither","strength":"neutral","evidence_sufficiency":"limited" if informative else "insufficient"})
            response={"model":config["model"],"role":"assistant","stop_reason":"end_turn","usage":{"input_tokens":0,"output_tokens":0},
                "content":[{"type":"text","text":json.dumps(assessment)}]}
            immutable_json(folder/"mock_response.json",response)
        else:
            w=spec["wire"]
            response=transport.request("anthropic","POST",w["url"],w["payload"],
                {"x-api-key":os.environ[config["key_env"]],"anthropic-version":"2023-06-01","Content-Type":"application/json"},128*16+8192)
        r.update(returned_model=response.get("model"))
        u=response.get("usage")
        if isinstance(u,dict) and all(type(u.get(k)) is int and u[k]>=0 for k in ("input_tokens","output_tokens")):
            r.update(usage={k:u[k] for k in ("input_tokens","output_tokens")},
                estimated_cost_usd=(u["input_tokens"]*config["prices"]["input_usd_per_million"]+u["output_tokens"]*config["prices"]["output_usd_per_million"])/1e6,
                estimated_cost_kind="mock_no_provider_calls" if config["provider"]=="mock" else "reported_tokens_at_configured_rates")
        r["status"]="invalid_response"
        try:parse_into_record(r,response,spec,config)
        except (ValueError,TypeError,KeyError) as exc:r["error"]={"type":type(exc).__name__,"message":str(exc)[:200]}
    except (ValueError,ProviderError,OSError,TypeError,KeyError) as exc:
        r["error"]={"type":type(exc).__name__,"message":str(exc) if isinstance(exc,ValueError) else "Provider/transport failure; inspect private capture"}
    if transport.calls:
        m=transport.calls[-1]
        r.update(request_started_at_utc=m["started_at_utc"],response_retrieved_at_utc=m["retrieved_at_utc"],latency_seconds=m["latency_seconds"],
            raw_response={"body_file":"raw/"+m["source_id"]+".body.gz","body_sha256":m["body_sha256"],"http_status":m["http_status"],"truncated":m["truncated"]})
    r["record_created_at_utc"]=iso(time.time())
    return immutable_json(final,signed_record(r))


def execute(output,cache=DEFAULT_CACHE,mock=False,allow_paid=False,max_calls=120,max_cost=1.0,transport_factory=CapturedHTTP,authorization_path=None):
    cases,config,assets,specs=make_specs(mock)
    if type(max_calls) is not int or not 0<=max_calls<=120 or type(max_cost) not in (int,float) or not math.isfinite(max_cost) or not 0<=max_cost<=1:
        raise ValueError("Hard maximum 120 requests / $1; finite nonnegative budgets required")
    output,cache=Path(output),Path(cache)
    for p in (output,cache):
        resolved=p.resolve()
        if resolved==ROOT or resolved in ROOT.parents or (ROOT in resolved.parents and (ROOT/"captures") not in resolved.parents):
            raise ValueError("Repository outputs must be in ignored captures, outside frozen assets/data")
    if output.resolve()==cache.resolve() or output.resolve() in cache.resolve().parents or cache.resolve() in output.resolve().parents:raise ValueError("Separate run/cache directories required")
    unique={s["key"]:s for s in specs}
    fresh=[]
    for s in unique.values():
        f=cache/s["key"]
        if (f/"response.json").exists():read_cache(s,cache)
        elif (f/"attempt.json").exists():raise ValueError("Uncertain original attempt; no automatic retry")
        else:fresh.append(s)
    bound=math.fsum(s["reserved_cost_usd"] for s in fresh)
    if not mock and (len(fresh)>max_calls or bound>max_cost+1e-12):raise ValueError("Whole fixed plan exceeds budget; no cases dropped, no calls made")
    if not mock and (not allow_paid or not os.environ.get(config["key_env"])):raise ValueError("All paid opt-ins and credential required")
    plan={"schema_version":1,"experiment":"leap_nba_v2_phase1","provider":config["provider"],"config":config,"frozen_assets":assets,
        "cache_directory":str(cache.resolve()),"max_paid_calls":max_calls,"max_estimated_cost_usd":max_cost,
        "slots":[{k:v for k,v in s.items() if k!="wire"} for s in specs],"entire_uncached_reservation_usd":math.fsum(s["reserved_cost_usd"] for s in unique.values())}
    if not mock:
        immutable_json(authorization_path or ROOT/"captures/leap_nba_v2_phase1_live_authorization.json",{"output_directory":str(output.resolve()),"frozen_registry_sha256":REGISTRY_SHA})
    immutable_json(output/"run.json",plan)
    if (output/"completion.json").exists():return verify(output)
    lock=output/".running"
    with lock.open("xb") as f:f.write(b"Active/interrupted experiment; never automatically retry.\n")
    stopped=False;records=[]
    try:
        for index,s in enumerate(specs):
            final=cache/s["key"]/"response.json"
            if final.exists():r=read_cache(s,cache)
            elif stopped:r=signed_record(empty_record(s,config,"not_attempted_after_access_denial"))
            else:
                if not mock:immutable_json(output/"reservations"/(s["key"]+".json"),{"request_sha256":s["key"],"cost_usd":s["reserved_cost_usd"]})
                r=cached_request(s,config,cache,allow_paid,transport_factory)
            if r["raw_response"] and r["raw_response"]["http_status"]==403:stopped=True
            slot={"case_id":s["case_id"],"method":s["method"],"record":r}
            immutable_json(output/"slots"/(str(index).zfill(3)+".json"),slot);records.append(slot)
        observed={r["record"]["request_sha256"]:r["record"] for r in records if not r["record"]["status"].startswith("not_attempted")}
        reservations=[json.loads(p.read_text()) for p in (output/"reservations").glob("*.json")]
        complete={"planned_slots":60,"unique_planned_requests":len(unique),"paid_request_reservations":len(reservations),
            "reserved_cost_usd":math.fsum(r["cost_usd"] for r in reservations),"estimated_cost_usd":math.fsum(r["estimated_cost_usd"] for r in observed.values()),
            "usage":{k:sum((r.get("usage") or {}).get(k,0) for r in observed.values()) for k in ("input_tokens","output_tokens")},
            "latency_seconds":math.fsum(r.get("latency_seconds") or 0 for r in observed.values()),
            "slot_status_counts":{s:sum(r["record"]["status"]==s for r in records) for s in sorted({r["record"]["status"] for r in records})},
            "stopped_on_access_denial":stopped,"completed_at_utc":iso(time.time()),
            "files":{str(p.relative_to(output)):digest(p.read_bytes()) for p in sorted(output.rglob("*")) if p.is_file() and p.name!=".running"}}
        immutable_json(output/"completion.json",complete)
        return verify(output)
    finally:lock.unlink()


def verify(output):
    output=Path(output);run=json.loads((output/"run.json").read_text());complete=json.loads((output/"completion.json").read_text())
    _,config,assets,specs=make_specs(run["provider"]=="mock")
    if run["config"]!=config or run["frozen_assets"]!=assets or run["slots"]!=[{k:v for k,v in s.items() if k!="wire"} for s in specs]:raise ValueError("Frozen synthetic plan changed")
    required={"run.json"}|{"slots/"+str(i).zfill(3)+".json" for i in range(60)}
    if not required<=set(complete["files"]):raise ValueError("Incomplete experiment seal")
    for name,sha in complete["files"].items():
        p=(output/name).resolve()
        if output.resolve() not in p.parents or digest(p.read_bytes())!=sha:raise ValueError("Synthetic run file hash mismatch")
    records=[]
    for i,s in enumerate(specs):
        slot=json.loads((output/"slots"/(str(i).zfill(3)+".json")).read_text());r=record_valid(slot["record"])
        records.append(r)
        if slot["case_id"]!=s["case_id"] or slot["method"]!=s["method"] or r["request_sha256"]!=s["key"]:raise ValueError("Slot identity mismatch")
        if r["status"].startswith("not_attempted"):continue
        if read_cache(s,run["cache_directory"])!=r:raise ValueError("Synthetic cached record differs")
        folder=Path(run["cache_directory"])/s["key"]
        if r["raw_response"] and r["raw_response"]["http_status"]==200:
            try:
                response=json.loads(gzip.decompress((folder/r["raw_response"]["body_file"]).read_bytes()))
            except (ValueError,UnicodeError):
                if r["status"]!="provider_error":raise ValueError("Malformed provider failure classification changed")
                continue
            if not isinstance(response,dict):
                if r["status"]!="provider_error":raise ValueError("Nonobject provider failure classification changed")
                continue
        elif run["provider"]=="mock":response=json.loads((folder/"mock_response.json").read_text())
        else:continue
        check=empty_record(s,config,"invalid_response")
        try:parse_into_record(check,response,s,config)
        except (ValueError,TypeError,KeyError):pass
        if any(check[k]!=r[k] for k in ("assessment","likelihood_ratio","direction","status","strict_json_object_valid","schema_valid","unsupported_field_count")):
            raise ValueError("Raw response does not reproduce")
    observed={r["request_sha256"]:r for r in records if not r["status"].startswith("not_attempted")}
    reservations=[json.loads(p.read_text()) for p in (output/"reservations").glob("*.json")]
    expected={"planned_slots":60,"unique_planned_requests":len({s["key"] for s in specs}),
        "paid_request_reservations":len(reservations),"reserved_cost_usd":math.fsum(r["cost_usd"] for r in reservations),
        "estimated_cost_usd":math.fsum(r["estimated_cost_usd"] for r in observed.values()),
        "usage":{k:sum((r.get("usage") or {}).get(k,0) for r in observed.values()) for k in ("input_tokens","output_tokens")},
        "latency_seconds":math.fsum(r.get("latency_seconds") or 0 for r in observed.values()),
        "slot_status_counts":{s:sum(r["status"]==s for r in records) for s in sorted({r["status"] for r in records})},
        "stopped_on_access_denial":any(r.get("raw_response") and r["raw_response"]["http_status"]==403 for r in records)}
    if any(complete[k]!=v for k,v in expected.items()):raise ValueError("Completion accounting does not reconcile")
    bykey={s["key"]:s for s in specs}
    if any(r["request_sha256"] not in bykey or r["cost_usd"]!=bykey[r["request_sha256"]]["reserved_cost_usd"] for r in reservations):raise ValueError("Reservation changed")
    if len(reservations)>run["max_paid_calls"] or expected["reserved_cost_usd"]>run["max_estimated_cost_usd"]+1e-12:raise ValueError("Budget exceeded")
    return complete


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for flag in ("plan","mock","live","allow-network","allow-inference"):p.add_argument("--"+flag,action="store_true")
    p.add_argument("--output",type=Path);p.add_argument("--cache",type=Path,default=DEFAULT_CACHE);p.add_argument("--verify",type=Path)
    a=p.parse_args()
    if a.verify:
        if any((a.mock,a.live,a.allow_network,a.allow_inference)):p.error("Verification is offline")
        r=verify(a.verify)
    elif a.plan or not(a.mock or a.live):
        _,cfg,_,ss=make_specs(a.mock);unique={s["key"]:s for s in ss}
        r={"case_method_slots":len(ss),"unique_requests":len(unique),"entire_plan_reserved_cost_usd":math.fsum(s["reserved_cost_usd"] for s in unique.values()),
            "max_requests":120,"max_estimated_cost_usd":1,"credential_present":bool(os.environ.get(cfg["key_env"])),"network_calls":0}
    else:
        if not a.output or a.mock and any((a.live,a.allow_network,a.allow_inference)) or a.live and not(a.allow_network and a.allow_inference):p.error("Specify output and coherent explicit opt-ins")
        r=execute(a.output,a.cache,a.mock,a.live and a.allow_network and a.allow_inference)
    print(json.dumps({k:v for k,v in r.items() if k!="files"},indent=2))


if __name__=="__main__":main()
