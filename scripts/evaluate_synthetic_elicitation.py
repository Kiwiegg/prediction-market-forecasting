#!/usr/bin/env python3
"""Outcome-free synthetic diagnostics and sanitized, network-free public replay."""
import argparse
import json
import math
from collections import Counter
from pathlib import Path

from evidence_documents import canonical,digest
from forecast_split import immutable_json
from run_synthetic_elicitation import record_valid,verify
from synthetic_elicitation import REGISTRY_SHA,METHODS,load_phase,make_specs,parse_assessment


def distribution(values):
    values=sorted(values)
    return {"n":len(values),"min":values[0] if values else None,"median":(values[(len(values)-1)//2]+values[len(values)//2])/2 if values else None,
        "mean":math.fsum(values)/len(values) if values else None,"max":values[-1] if values else None}


def criterion(success,required,observed,threshold=1):
    return {"successes":success,"required_cases_or_pairs":required,"observed_cases_or_pairs":observed,
        "fraction_of_planned":success/required,"minimum_fraction":threshold,
        "status":"incomplete" if observed<required else "pass" if success/required>=threshold else "fail"}


def metrics(observations):
    cases,_,_=load_phase()
    bycase={c["case_id"]:c for c in cases["cases"]};result={}
    for method in METHODS:
        rows={r["case_id"]:r for r in observations if r["method"]==method}
        if set(rows)!=set(bycase):raise ValueError("All 30 planned slots required, including explicit missing records")
        returned=lambda r: r["http_status"]==200 or r["provider"]=="mock" and not r["status"].startswith("not_attempted")
        valid=lambda r:r["schema_valid"]
        usable=lambda r:valid(r) and r["status"]=="ok"
        abstains=lambda r:valid(r) and r["status"]=="insufficient"
        dominance=[c for c in bycase.values() if c["expected"]["dominance"]]
        identical=[c for c in bycase.values() if c["expected"]["identical_nonempty"]]
        unavailable=[c for c in bycase.values() if c["expected"]["must_abstain"]]
        criteria={
            "dominance":criterion(sum(usable(rows[c["case_id"]]) and rows[c["case_id"]]["direction"]==c["expected"]["favored_side"] for c in dominance),15,sum(returned(rows[c["case_id"]]) for c in dominance),.9),
            "identical_neutral":criterion(sum(usable(rows[c["case_id"]]) and rows[c["case_id"]]["direction"]=="neither" for c in identical),3,sum(returned(rows[c["case_id"]]) for c in identical)),
            "uninformative_abstention":criterion(sum(abstains(rows[c["case_id"]]) for c in unavailable),6,sum(returned(rows[c["case_id"]]) for c in unavailable))}
        swaps=[];formats=[];uninformative_swaps=[]
        reverse={"X":"Y","Y":"X","neither":"neither"}
        for n in range(1,11):
            base,swap,fmt=(rows[f"f{n:02d}_{v}"] for v in ("base","swap","format"))
            if n<=8:
                both=usable(base) and usable(swap)
                error=abs(math.log(base["likelihood_ratio"])+math.log(swap["likelihood_ratio"])) if both else None
                swaps.append({"family_id":f"f{n:02d}","both_returned":returned(base) and returned(swap),"both_usable":both,
                    "direction_consistent":bool(both and reverse[base["direction"]]==swap["direction"]),"reciprocal_log_error":error,
                    "exact_reciprocal":error is not None and error<=1e-9,"within_1_25_factor":error is not None and error<=math.log(1.25)+1e-12})
            else:uninformative_swaps.append({"family_id":f"f{n:02d}","both_abstain":abstains(base) and abstains(swap),"both_returned":returned(base) and returned(swap)})
            both=valid(base) and valid(fmt)
            diff=abs(math.log(base["likelihood_ratio"])-math.log(fmt["likelihood_ratio"])) if usable(base) and usable(fmt) else None
            formats.append({"family_id":f"f{n:02d}","both_returned":returned(base) and returned(fmt),"both_valid":both,
                "exact_assessment_equal":both and base["assessment"]==fmt["assessment"],
                "direction_sufficiency_equal":both and base["direction"]==fmt["direction"] and base["assessment"]["evidence_sufficiency"]==fmt["assessment"]["evidence_sufficiency"],
                "absolute_log_lr_difference":diff,"stable_magnitude_or_abstention":bool(abstains(base) and abstains(fmt) or diff is not None and diff<=math.log(1.25)+1e-12)})
        criteria["team_swap_direction"]=criterion(sum(p["direction_consistent"] for p in swaps),8,sum(p["both_returned"] for p in swaps),.9)
        unsupported=sum(r["unsupported_field_count"] for r in rows.values())
        confident=sum(usable(rows[c["case_id"]]) for c in unavailable)
        criteria["observable_unsupported_evidence"]={"unsupported_output_fields":unsupported,"usable_assessments_on_uninformative_cases":confident,
            "status":"incomplete" if not all(returned(r) for r in rows.values()) else "pass" if unsupported==0 and confident==0 else "fail"}
        nreturned=sum(returned(r) for r in rows.values());njson=sum(r["strict_json_object_valid"] for r in rows.values());nvalid=sum(valid(r) for r in rows.values())
        result[method]={"planned_slots":30,"unique_observed_requests":len({r["request_sha256"] for r in rows.values() if not r["status"].startswith("not_attempted")}),
            "returned_slots":nreturned,"strict_json_objects":njson,"schema_valid_slots":nvalid,
            "json_rate_planned":njson/30,"json_rate_returned":njson/nreturned if nreturned else None,
            "schema_rate_planned":nvalid/30,"schema_rate_returned":nvalid/nreturned if nreturned else None,
            "status_counts":dict(sorted(Counter(r["status"] for r in rows.values()).items())),"criteria":criteria,
            "swap_pairs":swaps,"reciprocity_log_error":distribution([p["reciprocal_log_error"] for p in swaps if p["both_usable"]]),
            "exact_reciprocal_pairs":sum(p["exact_reciprocal"] for p in swaps),"tolerant_reciprocal_pairs":sum(p["within_1_25_factor"] for p in swaps),
            "uninformative_swap_pairs":uninformative_swaps,"format_pairs":formats,
            "format_exact_pairs":sum(p["exact_assessment_equal"] for p in formats),"format_stable_pairs":sum(p["stable_magnitude_or_abstention"] for p in formats),
            "likelihood_ratios":distribution([r["likelihood_ratio"] for r in rows.values() if usable(r)]),
            "magnitude_categories":dict(sorted(Counter(r["assessment"].get("strength","numeric") for r in rows.values() if valid(r)).items())),
            "categories":{category:{"status_counts":dict(Counter(r["status"] for cid,r in rows.items() if bycase[cid]["category"]==category)),
                "directions":dict(Counter(r["direction"] or "abstention_or_failed" for cid,r in rows.items() if bycase[cid]["category"]==category))}
                for category in sorted({c["category"] for c in bycase.values()})}}
    result["paired_schema_valid_cases"]=sum(all(next(r for r in observations if r["case_id"]==cid and r["method"]==m)["schema_valid"] for m in METHODS) for cid in bycase)
    complete=all(result[m]["schema_valid_slots"]==30 for m in METHODS)
    result["recommend_separately_authorized_pilot"]=complete and all(c["status"]=="pass" for c in result["qualitative"]["criteria"].values())
    return result


PUBLIC_FIELDS=("method","provider","requested_model","returned_model","generation_settings","request_sha256","prompt_sha256","input_text_sha256","evidence_sha256", "status","strict_json_object_valid","schema_valid","assessment","likelihood_ratio","direction","unsupported_field_count","usage","estimated_cost_usd","estimated_cost_kind","reserved_cost_usd","request_started_at_utc","response_retrieved_at_utc","latency_seconds","error","record_sha256")


def export_run(run_path,output):
    run_path,output=Path(run_path),Path(output)
    seal=verify(run_path);run=json.loads((run_path/"run.json").read_text());observations=[]
    for p in sorted((run_path/"slots").glob("*.json")):
        slot=json.loads(p.read_text());r=record_valid(slot["record"])
        observations.append({"case_id":slot["case_id"],**{k:r[k] for k in PUBLIC_FIELDS},
            "http_status":r["raw_response"]["http_status"] if r["raw_response"] else None,
            "raw_response_sha256":r["raw_response"]["body_sha256"] if r["raw_response"] else None})
    summary=metrics(observations)
    metadata={"experiment":"leap_nba_v2_phase1","provider":run["provider"],"frozen_registry_sha256":REGISTRY_SHA,
        "config":run["config"],"private_completion_sha256":digest((run_path/"completion.json").read_bytes()),
        "accounting":{k:v for k,v in seal.items() if k!="files"},
        "limitations":["Synthetic diagnostics only; mapped ratios are heuristic, not calibrated LRs.","Restricted outputs cannot reveal unspoken unsupported reasoning.","Identical requests reuse cache; case slots are not independent observations."]}
    for name,value in (("observations.json",observations),("metrics.json",summary),("metadata.json",metadata)):immutable_json(output/name,value)
    immutable_json(output/"manifest.json",{name:digest((output/name).read_bytes()) for name in ("observations.json","metrics.json","metadata.json")})
    return replay(output)


def replay(output):
    output=Path(output);manifest=json.loads((output/"manifest.json").read_text())
    if set(manifest)!={"observations.json","metrics.json","metadata.json"}:raise ValueError("Public bundle files changed")
    for name,sha in manifest.items():
        if digest((output/name).read_bytes())!=sha:raise ValueError("Sanitized output hash mismatch")
    meta=json.loads((output/"metadata.json").read_text());obs=json.loads((output/"observations.json").read_text())
    _,config,_,specs=make_specs(meta["provider"]=="mock")
    if meta["frozen_registry_sha256"]!=REGISTRY_SHA or meta["config"]!=config or len(obs)!=len(specs):raise ValueError("Public run configuration changed")
    for r,s in zip(obs,specs):
        if any(r[k]!=s[v] for k,v in (("case_id","case_id"),("method","method"),("request_sha256","key"),("prompt_sha256","prompt_sha256"),("input_text_sha256","input_text_sha256"),("evidence_sha256","evidence_sha256"))):raise ValueError("Public observation identity mismatch")
        if r["schema_valid"]:
            parsed=parse_assessment(r["method"],r["assessment"])
            if any(r[k]!=v for k,v in parsed.items()):raise ValueError("Public response mapping mismatch")
        elif r["likelihood_ratio"] is not None or r["direction"] is not None:raise ValueError("Public failure was imputed")
    calculated=metrics(obs)
    if calculated!=json.loads((output/"metrics.json").read_text()):raise ValueError("Public metrics do not reproduce")
    unique={r["request_sha256"]:r for r in obs if not r["status"].startswith("not_attempted")}
    accounting=meta["accounting"]
    if accounting["estimated_cost_usd"]!=math.fsum(r["estimated_cost_usd"] for r in unique.values()) or accounting["usage"]!={k:sum((r["usage"] or {}).get(k,0) for r in unique.values()) for k in ("input_tokens","output_tokens")}:raise ValueError("Public accounting mismatch")
    return calculated


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--run",type=Path);p.add_argument("--output",type=Path);p.add_argument("--replay",type=Path);a=p.parse_args()
    if a.replay:r=replay(a.replay)
    elif a.run and a.output:r=export_run(a.run,a.output)
    else:p.error("Use --run CAPTURE --output SANITIZED, or --replay SANITIZED")
    print(json.dumps({m:{k:r[m][k] for k in ("returned_slots","schema_valid_slots","criteria")} for m in METHODS},indent=2))


if __name__=="__main__":main()
