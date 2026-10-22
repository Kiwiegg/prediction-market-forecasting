#!/usr/bin/env python3
"""Immutable historical qualitative v2 runner; default is a no-cost five-game plan."""
import argparse
import gzip
import json
import math
import os
import time
from collections import Counter
from pathlib import Path

from direct_forecast import signed_record,verify_raw
from evidence_documents import canonical,digest
from forecast_split import ROOT,immutable_json
from investigate_kalshi import iso
from leap_v2_evidence import GROUPS,REGISTRY_SHA,aggregate,assessment,brief,config,plan_experiment,strict_json
from research_providers import CapturedHTTP,ProviderError
from run_synthetic_elicitation import validate_envelope

DEFAULT_CACHE=ROOT/"captures/leap_nba_v2_phase2_cache"


def base_record(spec,cfg,status):
    return {**brief(spec),"schema_version":1,"request_sha256":spec["key"],"status":status,"provider":cfg["provider"],
        "requested_model":cfg["model"],"returned_model":None,"generation_settings":cfg["generation"],
        "assessment":None,"schema_valid":False,"likelihood_ratio":None,"elicited_likelihood_ratio":None,
        "favored_side_home":None,"evidence_sufficiency":None,"error":None,"raw_response":None,"usage":None,
        "latency_seconds":None,"request_started_at_utc":None,"response_retrieved_at_utc":None,
        "estimated_cost_usd":0,"estimated_cost_kind":"not_requested"}


def verify_record(r):
    if r.get("record_sha256")!=digest(canonical({k:v for k,v in r.items() if k!="record_sha256"})):raise ValueError("V2 record hash mismatch")
    if r["status"] in ("success","insufficient"):
        parsed=assessment(r["group"],r["assessment"],r["orientation"])
        if not r["schema_valid"] or any(r[k]!=v for k,v in parsed.items()):raise ValueError("V2 qualitative mapping changed")
    elif r["status"]=="skipped_missing":
        if r["usable"] or not r["missing_reason"] or r["likelihood_ratio"]!=1 or r["assessment"] is not None:raise ValueError("Invalid source-missing skip")
    elif r["status"] not in ("failed","not_attempted_budget","not_attempted_access_denial") or r["likelihood_ratio"] is not None or not r["usable"]:
        raise ValueError("Invalid failure or imputed LR")
    return r


def load_cached(spec,cache):
    folder=Path(cache)/spec["key"];r=verify_record(json.loads((folder/"group.json").read_text()))
    if any(r[k]!=v for k,v in brief(spec).items()):raise ValueError("Cached group identity differs")
    verify_raw(r,folder)
    if r["raw_response"] and (folder/"raw"/(spec["wire_sha256"]+".request.json")).read_bytes()!=canonical(spec["wire"])+b"\n":raise ValueError("Cached wire changed")
    return r


def parse_response(response,spec,cfg):
    text=validate_envelope(response,spec,cfg)
    return assessment(spec["group"],strict_json(text),spec["orientation"])


def cached_group(spec,cfg,cache,allow_paid=False,transport_factory=CapturedHTTP):
    folder=Path(cache)/spec["key"];target=folder/"group.json"
    if target.exists():return load_cached(spec,cache)
    folder.mkdir(parents=True,exist_ok=True)
    if not spec["usable"]:
        r=base_record(spec,cfg,"skipped_missing");r.update(likelihood_ratio=1.0,evidence_sufficiency="not_applicable_missing")
        return immutable_json(target,signed_record(r))
    if (folder/"attempt.json").exists():raise ValueError("Uncertain prior attempt; automatic resend forbidden")
    if cfg["provider"]!="mock" and (not allow_paid or not os.environ.get(cfg["key_env"])):raise ValueError("Credential and paid opt-ins required")
    with (folder/"attempt.json").open("xb") as f:f.write(canonical({"request_sha256":spec["key"],"claimed_at_utc":iso(time.time())})+b"\n")
    r=base_record(spec,cfg,"failed");r.update(estimated_cost_usd=spec["reserved_cost_usd"],estimated_cost_kind="reserved_upper_bound_usage_unavailable")
    transport=transport_factory(folder/"raw",allow_network=allow_paid)
    try:
        if cfg["provider"]=="mock":
            response={"role":"assistant","model":cfg["model"],"stop_reason":"end_turn","usage":{"input_tokens":0,"output_tokens":0},
                "content":[{"type":"text","text":'{"favored_side":"neither","strength":"neutral","evidence_sufficiency":"limited"}'}]}
            immutable_json(folder/"mock_response.json",response)
        else:
            w=spec["wire"];response=transport.request("anthropic","POST",w["url"],w["payload"],
                {"x-api-key":os.environ[cfg["key_env"]],"anthropic-version":"2023-06-01","Content-Type":"application/json"},128*16+8192)
        r["returned_model"]=response.get("model");u=response.get("usage")
        if isinstance(u,dict) and all(type(u.get(k)) is int and u[k]>=0 for k in ("input_tokens","output_tokens")):
            r.update(usage={k:u[k] for k in ("input_tokens","output_tokens")},
                estimated_cost_usd=(u["input_tokens"]*cfg["prices"]["input_usd_per_million"]+u["output_tokens"]*cfg["prices"]["output_usd_per_million"])/1e6,
                estimated_cost_kind="mock_no_provider_calls" if cfg["provider"]=="mock" else "reported_tokens_at_configured_rates")
        r.update(**parse_response(response,spec,cfg),schema_valid=True)
    except (ProviderError,ValueError,TypeError,KeyError,OSError) as exc:
        r["error"]={"type":type(exc).__name__,"message":str(exc)[:240] if isinstance(exc,ValueError) else "Provider/response failure; inspect private capture"}
    if transport.calls:
        m=transport.calls[-1];r.update(request_started_at_utc=m["started_at_utc"],response_retrieved_at_utc=m["retrieved_at_utc"],latency_seconds=m["latency_seconds"],
            raw_response={"body_file":"raw/"+m["source_id"]+".body.gz","body_sha256":m["body_sha256"],"http_status":m["http_status"],"truncated":m["truncated"]})
    r["record_created_at_utc"]=iso(time.time())
    return immutable_json(target,signed_record(r))


def game_record(game,records):
    return signed_record({"game_id":game["game_id"],"evidence_sha256":game["evidence_sha256"],"groups":records,**aggregate(records)})


def counters(games):
    groups=[r for g in games for r in g["groups"]]
    unique={r["key"]:r for r in groups if r["usable"] and not r["status"].startswith("not_attempted")}
    return {"planned_games":len(games),"successful_forecasts":sum(g["status"]=="success" for g in games),
        "failed_forecasts":sum(g["status"]!="success" for g in games),"group_status_counts":dict(sorted(Counter(r["status"] for r in groups).items())),
        "reported_usage":{k:sum((r["usage"] or {}).get(k,0) for r in unique.values()) for k in ("input_tokens","output_tokens")},
        "estimated_response_cost_usd":math.fsum(r["estimated_cost_usd"] for r in unique.values()),
        "summed_observation_latency_seconds":math.fsum(r["latency_seconds"] or 0 for r in unique.values()),
        "usage_unavailable_attempts":sum(r["usage"] is None for r in unique.values()),
        "stopped_on_access_denial":any(r["raw_response"] and r["raw_response"]["http_status"]==403 for r in groups)}


def protect_paths(output,cache):
    output,cache=Path(output).resolve(),Path(cache).resolve()
    if output==cache or output in cache.parents or cache in output.parents:raise ValueError("Run/cache must be separate")
    for p in (output,cache):
        if p==ROOT or p in ROOT.parents:raise ValueError("Protected repository path")
        if ROOT in p.parents:
            relative=p.relative_to(ROOT).parts
            if len(relative)<2 or relative[0]!="captures" or not relative[1].startswith("leap_nba_v2_phase2"):raise ValueError("Only new Phase 2 captures may be written in repository")


def run_experiment(plan,specs,output,cache=DEFAULT_CACHE,max_paid_calls=20,max_cost=1,allow_paid=False,transport_factory=CapturedHTTP,authorization_path=None):
    full=plan["scope"]=="full-development";caps=(200,10) if full else (20,1)
    if type(max_paid_calls) is not int or not 0<=max_paid_calls<=caps[0] or type(max_cost) not in (int,float) or not math.isfinite(max_cost) or not 0<=max_cost<=caps[1]:raise ValueError("Explicit budgets exceed authorized scope")
    expected,rebuilt=plan_experiment(plan["config"]["provider"]=="mock",plan["scope"],plan["full_development_authorized"])
    if plan!=expected or specs!=rebuilt:raise ValueError("Plan differs from frozen evidence/settings")
    output,cache=Path(output),Path(cache);protect_paths(output,cache);cfg=plan["config"];mock=cfg["provider"]=="mock"
    fresh=[]
    for spec in specs:
        folder=cache/spec["key"]
        if (folder/"group.json").exists():load_cached(spec,cache)
        elif (folder/"attempt.json").exists():raise ValueError("Uncertain prior attempt; no automatic resend")
        elif spec["usable"]:fresh.append(spec)
    if not mock and (len(fresh)>max_paid_calls or math.fsum(s["reserved_cost_usd"] for s in fresh)>max_cost+1e-12):raise ValueError("Entire uncached plan exceeds budget; no calls made or groups omitted")
    if not mock and (not allow_paid or not os.environ.get(cfg["key_env"])):raise ValueError("All live opt-ins and credential required")
    if not mock:immutable_json(authorization_path or ROOT/f"captures/leap_nba_v2_phase2_authorization_{plan['scope']}.json",{"output_directory":str(output.resolve()),"frozen_registry_sha256":REGISTRY_SHA,"scope":plan["scope"]})
    immutable_json(output/"run.json",{**plan,"cache_directory":str(cache.resolve()),"max_paid_calls":max_paid_calls,"max_estimated_cost_usd":max_cost})
    if (output/"completion.json").exists():return verify_experiment(output)
    lock=output/".running"
    with lock.open("xb") as f:f.write(b"Active/interrupted experiment: no automatic retry.\n")
    stopped=False;budget_stopped=False;games=[];observed_cost=0
    try:
        for game in plan["games"]:
            records=[]
            for spec in (s for s in specs if s["game_id"]==game["game_id"]):
                cached=(cache/spec["key"]/"group.json").exists()
                if cached or not spec["usable"]:r=cached_group(spec,cfg,cache,allow_paid,transport_factory)
                elif stopped or budget_stopped:
                    r=base_record(spec,cfg,"not_attempted_access_denial" if stopped else "not_attempted_budget")
                    r["error"]={"type":"AccessDeniedStop" if stopped else "BudgetStop","message":"No request made after access denial or exhausted budget"};r=signed_record(r)
                else:
                    reservations=[json.loads(p.read_text()) for p in (output/"reservations").glob("*.json")]
                    if not mock and (len(reservations)>=max_paid_calls or max(observed_cost,math.fsum(v["cost_usd"] for v in reservations))+spec["reserved_cost_usd"]>max_cost+1e-12):
                        budget_stopped=True;r=base_record(spec,cfg,"not_attempted_budget");r["error"]={"type":"BudgetStop","message":"Stopped before request"};r=signed_record(r)
                    else:
                        if not mock:immutable_json(output/"reservations"/(spec["key"]+".json"),{"request_sha256":spec["key"],"cost_usd":spec["reserved_cost_usd"],"reserved_at_utc":iso(time.time())})
                        r=cached_group(spec,cfg,cache,allow_paid,transport_factory)
                        observed_cost+=r["estimated_cost_usd"]
                if r["raw_response"] and r["raw_response"]["http_status"]==403:stopped=True
                records.append(r)
            record=game_record(game,records);immutable_json(output/"forecasts"/(game["game_id"]+".json"),record);games.append(record)
        reservations=[json.loads(p.read_text()) for p in (output/"reservations").glob("*.json")]
        complete={**counters(games),"paid_call_reservations":len(reservations),"reserved_cost_usd":math.fsum(r["cost_usd"] for r in reservations),
            "reused_observations":sum(r["usable"] and r["key"] not in {v["request_sha256"] for v in reservations} and not r["status"].startswith("not_attempted") for g in games for r in g["groups"]) if not mock else 0,
            "completed_at_utc":iso(time.time()),"files":{str(p.relative_to(output)):digest(p.read_bytes()) for p in sorted(output.rglob("*")) if p.is_file() and p.name!=".running"}}
        immutable_json(output/"completion.json",complete)
        return verify_experiment(output)
    finally:lock.unlink()


def load_experiment(output):
    output=Path(output);run=json.loads((output/"run.json").read_text());complete=json.loads((output/"completion.json").read_text())
    if run["subset"]!="development":raise ValueError("Reserved subset unsupported")
    required={"run.json"}|{"forecasts/"+g["game_id"]+".json" for g in run["games"]}
    if not required<=set(complete["files"]):raise ValueError("Incomplete seal")
    for name,sha in complete["files"].items():
        p=(output/name).resolve()
        if output.resolve() not in p.parents or digest(p.read_bytes())!=sha:raise ValueError("V2 experiment hash mismatch")
    games=[]
    for planned in run["games"]:
        g=json.loads((output/"forecasts"/(planned["game_id"]+".json")).read_text())
        if len(g["groups"])!=4:raise ValueError("Four group observations required")
        for r,s in zip(g["groups"],planned["groups"]):
            verify_record(r)
            if any(r[k]!=v for k,v in s.items()):raise ValueError("Saved group differs from planned identity")
        if g!=game_record(planned,g["groups"]):raise ValueError("V2 aggregation does not reproduce")
        games.append(g)
    if any(complete[k]!=v for k,v in counters(games).items()):raise ValueError("V2 completion counters disagree")
    reservations=[json.loads(p.read_text()) for p in (output/"reservations").glob("*.json")];specs={s["key"]:s for g in run["games"] for s in g["groups"]}
    if (len(reservations)!=complete["paid_call_reservations"] or math.fsum(r["cost_usd"] for r in reservations)!=complete["reserved_cost_usd"]
            or len(reservations)>run["max_paid_calls"] or complete["reserved_cost_usd"]>run["max_estimated_cost_usd"]+1e-12
            or any(r["request_sha256"] not in specs or r["cost_usd"]!=specs[r["request_sha256"]]["reserved_cost_usd"] for r in reservations)):
        raise ValueError("V2 reservation accounting differs")
    reused=sum(r["usable"] and r["key"] not in {v["request_sha256"] for v in reservations} and not r["status"].startswith("not_attempted") for g in games for r in g["groups"]) if run["config"]["provider"]!="mock" else 0
    if complete["reused_observations"]!=reused:raise ValueError("V2 reuse accounting differs")
    return run,games,complete


def verify_experiment(output):
    run,games,complete=load_experiment(output)
    plan,specs=plan_experiment(run["config"]["provider"]=="mock",run["scope"],run["full_development_authorized"])
    if any(run[k]!=v for k,v in plan.items()):raise ValueError("Frozen v2 plan changed")
    cache=Path(run["cache_directory"])
    for spec,r in zip(specs,[r for g in games for r in g["groups"]]):
        if r["status"].startswith("not_attempted"):continue
        if load_cached(spec,cache)!=r:raise ValueError("Cached and sealed v2 records differ")
        folder=cache/spec["key"]
        if r["raw_response"]:
            if r["raw_response"]["http_status"]!=200 or r["raw_response"]["truncated"]:continue
            try:response=json.loads(gzip.decompress((folder/r["raw_response"]["body_file"]).read_bytes()))
            except (ValueError,UnicodeError):
                if r["status"]!="failed":raise ValueError("Malformed provider classification differs")
                continue
            if not isinstance(response,dict):
                if r["status"]!="failed":raise ValueError("Nonobject provider classification differs")
                continue
        elif run["config"]["provider"]=="mock" and r["usable"]:response=json.loads((folder/"mock_response.json").read_text())
        else:continue
        try:parsed=parse_response(response,spec,run["config"])
        except (ValueError,TypeError,KeyError):
            if r["status"]!="failed":raise ValueError("Invalid response classification differs")
            continue
        if not r["schema_valid"] or any(r[k]!=v for k,v in parsed.items()):raise ValueError("Raw v2 response does not reproduce")
    return complete


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for flag in ("plan","mock","live","allow-network","allow-inference","full-development","authorize-development"):p.add_argument("--"+flag,action="store_true")
    p.add_argument("--output",type=Path);p.add_argument("--cache",type=Path,default=DEFAULT_CACHE);p.add_argument("--verify",type=Path)
    p.add_argument("--max-paid-calls",type=int);p.add_argument("--max-estimated-cost-usd",type=float);a=p.parse_args()
    if a.verify:
        if any((a.mock,a.live,a.allow_network,a.allow_inference)):p.error("Verification is read-only")
        result=verify_experiment(a.verify)
    else:
        if a.mock and any((a.live,a.allow_network,a.allow_inference)):p.error("Mock cannot enable paid flags")
        if a.full_development and (not a.authorize_development or a.max_paid_calls is None or a.max_estimated_cost_usd is None):p.error("Future full development needs separate authorization and explicit budgets")
        plan,specs=plan_experiment(a.mock,"full-development" if a.full_development else "pilot",a.authorize_development)
        if a.plan or not (a.mock or a.live):
            fresh=[s for s in specs if s["usable"] and not (a.cache/s["key"]/"group.json").exists()]
            result={"game_ids":[g["game_id"] for g in plan["games"]],"scope":plan["scope"],"required_group_observations":sum(s["usable"] for s in specs),
                "missing_groups":[{"game_id":s["game_id"],"group":s["group"],"reason":s["missing_reason"]} for s in specs if not s["usable"]],
                "maximum_new_requests":len(fresh) if not a.mock else 0,"uncached_reservation_usd":math.fsum(s["reserved_cost_usd"] for s in fresh),
                "credential_present":bool(os.environ.get(plan["config"]["key_env"])),"network_calls":0}
        else:
            if not a.output or a.live and not(a.allow_network and a.allow_inference):p.error("Output and all live opt-ins required")
            result=run_experiment(plan,specs,a.output,a.cache,20 if a.max_paid_calls is None else a.max_paid_calls,1 if a.max_estimated_cost_usd is None else a.max_estimated_cost_usd,a.live and a.allow_network and a.allow_inference)
    print(json.dumps({k:v for k,v in result.items() if k!="files"},indent=2))


if __name__=="__main__":main()
