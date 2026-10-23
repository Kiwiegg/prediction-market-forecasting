#!/usr/bin/env python3
"""Offline five-/seven-method development analysis; no inference or reserved scope."""
import argparse
import csv
import io
import json
import math
import random
from collections import Counter
from itertools import combinations
from pathlib import Path

import analyze_development as previous
import compare_leap_v2 as pilot
import leap_v2_forecast as v2
import run_v2_development as execution
from evaluate_forecasts import brier,calibration,log_loss,scores
from evidence_documents import canonical,digest
from forecast_split import ROOT,DEFAULT_DATA,immutable_json
from investigate_kalshi import timestamp
from leap_v2_evidence import GROUPS,plan_experiment


def evaluated(rows,methods):
    chosen=[r for r in rows if r["outcome"] is not None and all(r[m] is not None for m in methods)]
    ids=[r["game_id"] for r in chosen];n=len(chosen);stats={}
    for method in methods:
        ps=[r[method] for r in chosen]
        stats[method]={**scores(chosen,method),"mean_home_probability":math.fsum(ps)/n if n else None,
            "extreme_count":sum(p<=.1 or p>=.9 for p in ps),"extreme_fraction":sum(p<=.1 or p>=.9 for p in ps)/n if n else None,
            "classification_accuracy":sum((r[method]>=.5)==bool(r["outcome"]) for r in chosen)/n if n else None,
            "mean_distance_from_half":math.fsum(abs(p-.5) for p in ps)/n if n else None,
            "mean_confidence":math.fsum(max(p,1-p) for p in ps)/n if n else None}
    loo={}
    for method in methods:
        if not method.startswith("leap_"):continue
        version="v1" if "_v1_" in method else "v2";key=method.replace("_v1","") if version=="v1" else method
        loo[method]={}
        for group in GROUPS:
            omitted=[{"outcome":r["outcome"],"p":r[version+"_variants"][key]["leave_one_group_out"][group]["home_win_probability"]} for r in chosen]
            score=scores(omitted,"p")
            contributions=[r[version+"_variants"][key]["group_log_odds_contributions"][group] for r in chosen]
            loo[method][group]={**score,"game_ids":ids,"omission_minus_full":{k:score[k]-stats[method][k] if n else None for k in ("brier_score","log_loss")},
                "weighted_contribution":previous.distribution(contributions)}
    differences={a+"_minus_"+b:{metric:math.fsum(r["scores"][a][metric]-r["scores"][b][metric] for r in chosen)/n if n else None for metric in ("brier","log_loss")} for a,b in combinations(methods,2)}
    return {"n":n,"game_ids":ids,"scores":stats,"calibration":{m:calibration(chosen,m) for m in methods},"paired_mean_differences":differences,
        "exclusions":[{"game_id":r["game_id"],"missing_methods":[m for m in methods if r[m] is None],"outcome_missing_reason":r["outcome_missing_reason"],
            "market_missing_reason":r["market_missing_reason"],"v1_status":r["v1_status"],"v2_status":r["v2_status"],"v2_failed_groups":r["v2_failed_groups"]} for r in rows if r not in chosen],
        "leave_one_group_out":loo}


def bootstrap(rows,comparisons,seed,replicates):
    if type(seed) is not int or type(replicates) is not int or replicates<=0 or len({r["game_id"] for r in rows})!=len(rows):raise ValueError("Fixed seed, positive replicates and unique paired rows required")
    if any(r["outcome"] is None or any(r[m] is None for pair in comparisons for m in pair) for r in rows):raise ValueError("Bootstrap requires identical eligible rows")
    n=len(rows);values={a+"_minus_"+b:[brier(r[a],r["outcome"])-brier(r[b],r["outcome"]) for r in rows] for a,b in comparisons}
    draws={k:[] for k in values};rng=random.Random(seed)
    if n:
        for _ in range(replicates):
            indices=[rng.randrange(n) for _ in range(n)]
            for key,v in values.items():draws[key].append(math.fsum(v[i] for i in indices)/n)
    return {"n":n,"game_ids":[r["game_id"] for r in rows],"seed":seed,"replicates":replicates,"descriptive_only":True,
        "comparisons":{k:{"mean_brier_difference":math.fsum(v)/n if n else None,"lower_95":previous.quantile(draws[k],.025),"upper_95":previous.quantile(draws[k],.975)} for k,v in values.items()}}


def group_diagnostics(rows,packets,cohorts):
    detail=pilot.diagnostics(rows,packets)
    common=[(a,b) for a,b in zip(detail["strength_directionality"]["v1"],detail["strength_directionality"]["v2"]) if a["weaker_team"] is not None and a["lr_available"] and b["lr_available"]]
    detail["common_strength_directionality"]={"n":len(common),"game_ids":[a["game_id"] for a,b in common],
        "v1_favors_weaker":sum(a["favors_weaker_team"] for a,b in common),"v2_favors_weaker":sum(b["favors_weaker_team"] for a,b in common),
        "v1_home_favoring":sum(a["strength_lr"]>1 for a,b in common),"v2_home_favoring":sum(b["strength_lr"]>1 for a,b in common),
        "exclusions":[{"game_id":a["game_id"],"statistical_reason":a["unassessable_reason"],"v1_lr_available":a["lr_available"],"v2_lr_available":b["lr_available"]} for a,b in zip(detail["strength_directionality"]["v1"],detail["strength_directionality"]["v2"]) if not (a["weaker_team"] is not None and a["lr_available"] and b["lr_available"])]}
    for version in ("v1","v2"):
        for i,group in enumerate(GROUPS):
            obs=[r[version+"_groups"][i] for r in rows];valid=[r for r in obs if r["status"]=="success"]
            # Old incomplete v1 responses have no sufficiency label. Preserve
            # that state under a JSON-safe name, distinct from source skips.
            detail["groups"][version][group]["sufficiency"]={"not_returned" if k is None else k:v for k,v in detail["groups"][version][group]["sufficiency"].items()}
            detail["groups"][version][group].update(
                usable_qualitative_categories=dict(Counter(r["assessment"]["strength"] for r in valid if r.get("assessment"))),
                insufficient_responses=sum(r["status"]=="insufficient" for r in obs),
                log_lr_success_only=previous.distribution(math.log(r["likelihood_ratio"]) for r in valid))
    common_ab=[r for r in rows if all(r[v+"_groups"][i]["status"]=="success" for v in ("v1","v2") for i in (0,1))]
    detail["common_strength_venue"]={"n":len(common_ab),"game_ids":[r["game_id"] for r in common_ab],
        "same_nonzero_direction_count":{v:sum(r[v+"_group_log_likelihood_ratios"][GROUPS[0]]*r[v+"_group_log_likelihood_ratios"][GROUPS[1]]>0 for r in common_ab) for v in ("v1","v2")}}
    partial=[]
    for r in rows:
        states=detail["injury_report_states"][r["game_id"]]
        if any(s=="reported" for s in states.values()) and any(s!="reported" for s in states.values()):
            c=r["v2_groups"][2];partial.append({"game_id":r["game_id"],"states":states,"source_usable":c["usable"],"status":c["status"],"assessment":c["assessment"],"home_lr":c["likelihood_ratio"]})
    detail["one_sided_injury_reports"]=partial
    detail["injury_source_evidence"]={gid:{k:p["injury_news"]["official_injury"][k] for k in ("published_at_utc","report_issue_utc","publication_verification","independent_historical_public_capture_verified","latest_report_globally_verified")} for gid,p in packets.items()}
    detail["injury_strata"]={}
    detail["shrinkage"]={}
    for name,cohort in cohorts.items():
        selected=[r for r in rows if r["game_id"] in cohort["game_ids"]]
        methods=list(cohort["scores"])
        detail["injury_strata"][name]={}
        for label,predicate in (("source_usable",lambda r:r["v2_groups"][2]["usable"]),("source_missing",lambda r:not r["v2_groups"][2]["usable"]),
                ("adequate",lambda r:r["v2_groups"][2]["evidence_sufficiency"]=="adequate"),("limited",lambda r:r["v2_groups"][2]["evidence_sufficiency"]=="limited")):
            part=[r for r in selected if predicate(r)]
            detail["injury_strata"][name][label]={"n":len(part),"game_ids":[r["game_id"] for r in part],"scores":{m:scores(part,m) for m in methods}}
        raw,cons=cohort["scores"]["leap_v2_raw"],cohort["scores"]["leap_v2_conservative"]
        detail["shrinkage"][name]={"n":len(selected),"game_ids":cohort["game_ids"],
            "conservative_minus_raw":{k:cons[k]-raw[k] if selected else None for k in ("brier_score","log_loss","mean_distance_from_half","mean_confidence","mean_home_probability","classification_accuracy","extreme_fraction")},
            "closer_to_half":sum(abs(r["leap_v2_conservative"]-.5)<abs(r["leap_v2_raw"]-.5)-1e-12 for r in selected),
            "unchanged_distance":sum(abs(abs(r["leap_v2_conservative"]-.5)-abs(r["leap_v2_raw"]-.5))<=1e-12 for r in selected)}
    return detail


def execution_audit(obs):
    before=obs["run"]["development_execution"]["preflight"];fresh=set(before["new_request_keys"]);original=set(before["original_cache_keys"])
    mock=obs["run"]["config"]["provider"]=="mock"
    if fresh & original:raise ValueError("Original/new request sets overlap")
    groups=[r for g in obs["games"] for r in g["groups"]];bykey={r["key"]:r for r in groups}
    ledger=obs["reservations"];claims=obs["claims"]
    if any(r["request_sha256"] not in fresh or r["request_sha256"] not in bykey or type(r["cost_usd"]) not in (int,float) or not math.isfinite(r["cost_usd"]) or r["cost_usd"]!=bykey[r["request_sha256"]]["reserved_cost_usd"] for r in ledger):raise ValueError("Unknown or changed reservation")
    if len({r["request_sha256"] for r in ledger})!=len(ledger) or len(ledger)>180 or math.fsum(r["cost_usd"] for r in ledger)>5+1e-12:raise ValueError("Execution budget exceeded or duplicated reservation")
    reserved={r["request_sha256"]:r for r in ledger}
    for key,claim in claims.items():
        if key not in fresh or claim["request_sha256"]!=key or key not in reserved:raise ValueError("Attempt lacks original reservation/identity")
        r=bykey[key]
        if reserved[key]["cost_usd"]!=r["reserved_cost_usd"]:raise ValueError("Reservation changed")
        if timestamp(reserved[key]["reserved_at_utc"])>timestamp(claim["claimed_at_utc"]):raise ValueError("Cost reservation was not made before claim")
        if r["request_started_at_utc"] and timestamp(claim["claimed_at_utc"])>timestamp(r["request_started_at_utc"]):raise ValueError("Claim after provider request")
    audit=[]
    for r in groups:
        key=r["key"];raw=r.get("raw_response");origin="offline_mock" if mock and r["usable"] else "original_cache" if key in original else "additional" if key in claims else "source_missing" if not r["usable"] else "unattempted"
        if raw and key in fresh and key not in claims:raise ValueError("New captured request lacks claim")
        audit.append({"game_id":r["game_id"],"group":r["group"],"request_sha256":key,"origin":origin,"status":r["status"],
            "http_status":raw["http_status"] if raw else None,"response_category":obs["execution"]["response_categories"].get(key,"uncertain_attempt" if r.get("uncertain_attempt") else r["status"]),
            "raw_response_sha256":raw["body_sha256"] if raw else None,"error_type":(r["error"] or {}).get("type"),
            "usage":r["usage"],"estimated_cost_usd":r["estimated_cost_usd"],"estimated_cost_kind":r["estimated_cost_kind"],"latency_seconds":r["latency_seconds"]})
    resources={}
    for name,keys in (("additional",set(claims)),("reused",set() if mock else original)):
        selected=[r for r in groups if r["key"] in keys and r["usable"]]
        resources[name]={"claimed_or_reused_requests":len(selected),"captured_requests":sum(bool(r["raw_response"]) for r in selected),
            "usable_estimates":sum(r["status"]=="success" for r in selected),"valid_structured_responses":sum(r["schema_valid"] for r in selected),
            "abstentions":sum(r["status"]=="insufficient" for r in selected),"failed_requests":sum(r["status"]=="failed" for r in selected),
            "http_status_counts":dict(Counter(str(r["raw_response"]["http_status"]) if r["raw_response"] else "uncertain" for r in selected)),
            "usage":{k:sum((r["usage"] or {}).get(k,0) for r in selected) for k in ("input_tokens","output_tokens")},
            "reported_token_cost_usd":math.fsum(r["estimated_cost_usd"] for r in selected if r["usage"] is not None),
            "unknown_usage_reserve_usd":math.fsum(r["estimated_cost_usd"] for r in selected if r["usage"] is None),
            "summed_latency_seconds":math.fsum(r["latency_seconds"] or 0 for r in selected),"missing_latency_count":sum(r["latency_seconds"] is None for r in selected),
            "first_request_at_utc":min((r["request_started_at_utc"] for r in selected if r["request_started_at_utc"]),default=None),
            "last_response_at_utc":max((r["response_retrieved_at_utc"] for r in selected if r["response_retrieved_at_utc"]),default=None)}
    ordered=[r["key"] for r in groups];denials=[r["request_sha256"] for r in audit if r["response_category"]=="access_denial"]
    if denials:
        first=min(ordered.index(k) for k in denials)
        if any(ordered.index(k)>first for k in claims):raise ValueError("New paid request after first access denial")
        if obs["execution"]["stop_reason"]["category"]!="access_denial":raise ValueError("Access denial was not recorded as stopping reason")
    return {"planned_new_requests":0 if mock else len(fresh),"new_claimed_attempts":len(claims),"unattempted_new_requests":0 if mock else len(fresh-set(claims)),
        "unattempted_request_sha256":[] if mock else sorted(fresh-set(claims)),"new_reservations":len(ledger),"additional_reserved_cost_usd":math.fsum(r["cost_usd"] for r in ledger),
        "stop_reason":obs["execution"]["stop_reason"],"resources":resources,"per_group":audit}


def reconstruct(obs):
    rules=execution.analysis_plan();run=obs["run"]
    if run["scope"]!="full-development" or run["subset"]!="development" or run["development_execution"]["analysis_plan_sha256"]!=digest(execution.PLAN_PATH.read_bytes()):raise ValueError("Only frozen development execution supported")
    plan,specs=plan_experiment(run["config"]["provider"]=="mock",scope="full-development",authorize_development=True)
    if any(run[k]!=v for k,v in plan.items()) or [g["game_id"] for g in obs["games"]]!=[g["game_id"] for g in plan["games"]]:raise ValueError("Full development manifest differs")
    for g,planned in zip(obs["games"],plan["games"]):execution.validate_public_game(g,planned)
    if run["config"]["provider"]!="mock":
        original=json.loads((ROOT/"reports/leap_nba_v2_pilot/observations.json").read_text())["games"]
        if obs["games"][:5]!=original:raise ValueError("Original pilot forecasts were altered or re-elicited")
    baseline=ROOT/rules["execution"]["baseline_public"]
    if digest((baseline/"manifest.json").read_bytes())!=obs["baseline_manifest_sha256"]:raise ValueError("Baseline source changed")
    before=run["development_execution"]["preflight"]
    if run["config"]["provider"]!="mock" and (before["baseline_manifest_sha256"]!=obs["baseline_manifest_sha256"] or before["parent_evidence_hashes"]!={g["game_id"]:g["evidence_sha256"] for g in plan["games"]}):raise ValueError("Preflight baseline/parent bindings changed")
    previous.replay(baseline)
    baseline_obs=json.loads((baseline/"observations.json").read_text());base_rows,_,packets,_=previous.reconstruct(baseline_obs)
    rows,_=pilot.compare_rows(obs["games"],base_rows)
    cohorts={name:evaluated(rows,methods) for name,methods in rules["comparisons"].items() if isinstance(methods,list)}
    for r in rows:
        r["paired_comparisons"]={name:r["game_id"] in c["game_ids"] for name,c in cohorts.items()}
        r["all_pairwise_score_differences"]={a+"_minus_"+b:{metric:r["scores"][a][metric]-r["scores"][b][metric] for metric in ("brier","log_loss")} for a,b in combinations(pilot.METHODS,2) if r["scores"][a] is not None and r["scores"][b] is not None}
    bs=rules["bootstrap"]
    boots={name:bootstrap([r for r in rows if r["game_id"] in cohorts[name]["game_ids"]],bs[key],bs["seed"],bs["replicates"]) for name,key in (("A_v2_development","A_pairs"),("B_seven_method","B_pairs"))}
    audit=execution_audit(obs)
    summary={"planned_games":50,"coverage":{m:sum(r[m] is not None for r in rows) for m in pilot.METHODS},"comparisons":cohorts,
        "v2_group_status_counts":dict(Counter(g["status"] for r in rows for g in r["v2_groups"])),"resources":audit["resources"],
        "baseline_selected_observation_resources":json.loads((baseline/"reproduction.json").read_text())["resources"],
        "interpretation":"Development-informed historical diagnostics, possible memory and game dependence; no independent predictive-skill claim."}
    return {"per_game.json":rows,"summary.json":summary,"bootstrap.json":boots,"diagnostics.json":group_diagnostics(rows,packets,cohorts),"execution_audit.json":audit},packets


def results_csv(rows,packets):
    fields=["game_id","home","away","cutoff_utc","outcome","paired_A","paired_B",*pilot.METHODS,"v1_status","v2_status","v2_failed_groups"]
    fields += [m+"_"+metric for m in pilot.METHODS for metric in ("brier","log_loss")]
    fields += [group+"_"+field for group in GROUPS for field in ("status","lr","category","sufficiency","missing_reason")]
    stream=io.StringIO(newline="");writer=csv.DictWriter(stream,fieldnames=fields,lineterminator="\n");writer.writeheader()
    for r in rows:
        p=packets[r["game_id"]];row={k:r[k] for k in fields if k in r}
        row.update(home=p["home"]["team_name"],away=p["away"]["team_name"],cutoff_utc=p["cutoff_utc"],paired_A=r["paired_comparisons"]["A_v2_development"],paired_B=r["paired_comparisons"]["B_seven_method"],v2_failed_groups="|".join(r["v2_failed_groups"]))
        for m in pilot.METHODS:
            for metric in ("brier","log_loss"):row[m+"_"+metric]=(r["scores"][m] or {}).get(metric)
        for g in r["v2_groups"]:
            for label,value in (("status",g["status"]),("lr",g["likelihood_ratio"]),("category",(g["assessment"] or {}).get("strength")),("sufficiency",g["evidence_sufficiency"]),("missing_reason",g["missing_reason"])):row[g["group"]+"_"+label]=value
        writer.writerow(row)
    return stream.getvalue()


def export(run_path,output,allow_mock=False):
    run_path,output=Path(run_path),Path(output);run,games,complete,stop=execution.verify(run_path)
    if run["config"]["provider"]=="mock" and not allow_mock:raise ValueError("Mock outputs require explicit --allow-mock")
    for protected in (run_path,Path(run["cache_directory"]),DEFAULT_DATA,ROOT/"reports/development_50"):
        if output.resolve()==protected.resolve() or output.resolve() in protected.resolve().parents or protected.resolve() in output.resolve().parents:raise ValueError("Separate analysis output required")
    cache=Path(run["cache_directory"]);fresh=run["development_execution"]["preflight"]["new_request_keys"]
    obs={"run":{k:v for k,v in run.items() if k!="cache_directory"},"games":games,"completion":{k:v for k,v in complete.items() if k!="files"},"execution":stop,
        "reservations":[json.loads(p.read_text()) for p in sorted((run_path/"reservations").glob("*.json"))],
        "claims":{key:json.loads((cache/key/"attempt.json").read_text()) for key in fresh if run["config"]["provider"]!="mock" and (cache/key/"attempt.json").exists()},
        "private_completion_sha256":digest((run_path/"completion.json").read_bytes()),
        "baseline_manifest_sha256":digest((ROOT/execution.analysis_plan()["execution"]["baseline_public"]/"manifest.json").read_bytes()),"provider_raw_bodies_included":False}
    artifacts,packets=reconstruct(obs)
    for name,value in {"observations.json":obs,"analysis_plan.json":execution.analysis_plan(),**artifacts}.items():immutable_json(output/name,value)
    previous.immutable_text(output/"results.csv",results_csv(artifacts["per_game.json"],packets))
    names=["observations.json","analysis_plan.json",*artifacts,"results.csv"]
    immutable_json(output/"manifest.json",{name:digest((output/name).read_bytes()) for name in sorted(names)})
    return artifacts["summary.json"]


def replay(output):
    output=Path(output);manifest=json.loads((output/"manifest.json").read_text())
    required={"observations.json","analysis_plan.json","per_game.json","summary.json","bootstrap.json","diagnostics.json","execution_audit.json","results.csv"}
    if set(manifest)!=required:raise ValueError("Public development file set differs")
    for name,sha in manifest.items():
        if digest((output/name).read_bytes())!=sha:raise ValueError("Public development file hash differs")
    if json.loads((output/"analysis_plan.json").read_text())!=execution.analysis_plan():raise ValueError("Diagnostic plan changed")
    obs=json.loads((output/"observations.json").read_text())
    if obs["provider_raw_bodies_included"] is not False:raise ValueError("Unsafe public artifact")
    artifacts,packets=reconstruct(obs)
    if any(value!=json.loads((output/name).read_text()) for name,value in artifacts.items()) or results_csv(artifacts["per_game.json"],packets).encode()!=(output/"results.csv").read_bytes():raise ValueError("Public diagnostics/scores do not reproduce")
    return artifacts["summary.json"]


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--run",type=Path);p.add_argument("--output",type=Path);p.add_argument("--replay",type=Path);p.add_argument("--allow-mock",action="store_true");a=p.parse_args()
    if a.replay:summary=replay(a.replay)
    elif a.run and a.output:summary=export(a.run,a.output,a.allow_mock)
    else:p.error("Use --run SEALED --output PUBLIC or --replay PUBLIC")
    print(json.dumps({"coverage":summary["coverage"],"comparisons":{name:{"n":c["n"],"scores":c["scores"]} for name,c in summary["comparisons"].items()}},indent=2))


if __name__=="__main__":main()
