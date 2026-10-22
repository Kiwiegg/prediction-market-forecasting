#!/usr/bin/env python3
"""Evaluation-only seven-method pilot comparison and sanitized offline replay."""
import argparse
import json
import math
from collections import Counter
from itertools import combinations
from pathlib import Path

from analyze_development import distribution,strength_diagnostic
from compare_forecasts import replay_sanitized as verify_baseline
from evaluate_forecasts import EPSILON,brier,calibration,log_loss,scores
from evidence_documents import canonical,digest
from forecast_split import ROOT,DEFAULT_DATA,immutable_json
from leap_v2_evidence import GROUPS,PILOT,VARIANTS,brief,load_evidence,plan_experiment
from leap_v2_forecast import counters,game_record,load_experiment,verify_experiment,verify_record

BASELINE=ROOT/"reports/leap_nba_v1_pilot"
METHODS=("direct","leap_v1_raw","leap_v1_conservative","leap_v2_raw","leap_v2_conservative","kalshi","constant_50")


def compare_rows(games,baseline):
    if [g["game_id"] for g in games]!=[b["game_id"] for b in baseline] or len({g["game_id"] for g in games})!=len(games):raise ValueError("Identical ordered, unique games required")
    rows=[]
    for g,b in zip(games,baseline):
        if g["evidence_sha256"]!=b["evidence_sha256"]:raise ValueError("Methods have different parent evidence")
        r={"game_id":g["game_id"],"evidence_sha256":g["evidence_sha256"],"outcome":b["outcome"],"direct":b["direct"],
            "leap_v1_raw":b["leap_raw"],"leap_v1_conservative":b["leap_conservative"],
            **{v:g["variants"][v]["home_win_probability"] for v in VARIANTS},"kalshi":b["kalshi"],"constant_50":.5,
            "direct_status":b["direct_status"],"v1_status":b["leap_status"],"v2_status":g["status"],"v2_failed_groups":g["failed_groups"],
            "market_missing_reason":b["market_missing_reason"],"outcome_missing_reason":b["outcome_missing_reason"],
            "v2_groups":g["groups"],"v2_variants":g["variants"],"v2_group_log_likelihood_ratios":g["group_log_likelihood_ratios"],
            "v1_groups":b["groups"],"v1_variants":b["variants"],"v1_group_log_likelihood_ratios":b["group_log_likelihood_ratios"]}
        r["paired_eligible"]=r["outcome"] is not None and all(r[m] is not None for m in METHODS)
        r["scores"]={m:{"brier":brier(r[m],r["outcome"]),"log_loss":log_loss(r[m],r["outcome"])} if r[m] is not None and r["outcome"] is not None else None for m in METHODS}
        r["paired_score_differences"]={a+"_minus_"+c:{metric:r["scores"][a][metric]-r["scores"][c][metric] for metric in ("brier","log_loss")} for a,c in combinations(METHODS,2)} if r["paired_eligible"] else {}
        rows.append(r)
    paired=[r for r in rows if r["paired_eligible"]];ids=[r["game_id"] for r in paired];loo={}
    for variant in METHODS[1:5]:
        version="v1" if "v1" in variant else "v2";key=variant.replace("_v1","") if version=="v1" else variant
        loo[variant]={}
        for group in GROUPS:
            chosen=[{"outcome":r["outcome"],"p":r[version+"_variants"][key]["leave_one_group_out"][group]["home_win_probability"]} for r in paired]
            omitted=scores(chosen,"p");full=scores(paired,variant)
            loo[variant][group]={**omitted,"game_ids":ids,"omission_minus_full":{metric:omitted[metric]-full[metric] if paired else None for metric in ("brier_score","log_loss")}}
    summary={"interpretation":"Development-informed historical integration pilot; no independent test or comparative skill claim.",
        "log_loss":{"base":"natural","epsilon":EPSILON,"clipping_applies_only_to_log_loss":True},
        "market_rule":"Unchanged preferred valid two-sided YES midpoint; candle end <=cutoff and lag <=1200 seconds; actual quote-refresh age unknown.",
        "coverage":{"planned":len(rows),"paired_games":len(paired),"available_probabilities":{m:sum(r[m] is not None for r in rows) for m in METHODS},
            "v2_forecast_status_counts":dict(Counter(r["v2_status"] for r in rows)),"v2_group_status_counts":dict(Counter(g["status"] for r in rows for g in r["v2_groups"]))},
        "exclusions":[{k:r[k] for k in ("game_id","direct_status","v1_status","v2_status","v2_failed_groups","market_missing_reason","outcome_missing_reason")} for r in rows if not r["paired_eligible"]],
        "paired":{"game_ids":ids,"scores":{m:scores(paired,m) for m in METHODS},"calibration":{m:calibration(paired,m) for m in METHODS},
            "mean_score_differences":{a+"_minus_"+b:{metric:math.fsum(r["paired_score_differences"][a+"_minus_"+b][metric] for r in paired)/len(paired) if paired else None for metric in ("brier","log_loss")} for a,b in combinations(METHODS,2)}},
        "leave_one_group_out_same_intersection":loo}
    return rows,summary


def diagnostics(rows,packets):
    result={"strength_directionality":{},"groups":{},"strength_venue_reinforcement":{}}
    for version in ("v1","v2"):
        result["strength_directionality"][version]=[strength_diagnostic(packets[r["game_id"]],r[version+"_groups"][0]["likelihood_ratio"] if r[version+"_groups"][0]["status"]=="success" else None) for r in rows]
        result["groups"][version]={}
        for i,group in enumerate(GROUPS):
            observations=[r[version+"_groups"][i] for r in rows];success=[o for o in observations if o["status"]=="success"]
            result["groups"][version][group]={"planned":len(observations),"usable_before_inference":sum(o["missing_reason"] is None for o in observations),
                "status_counts":dict(Counter(o["status"] for o in observations)),"source_missing_reasons":dict(Counter(o["missing_reason"] for o in observations if o["missing_reason"])),
                "directions_success_only":{"home":sum(o["likelihood_ratio"]>1 for o in success),"away":sum(o["likelihood_ratio"]<1 for o in success),"neither":sum(o["likelihood_ratio"]==1 for o in success)},
                "likelihood_ratios_success_only":distribution(o["likelihood_ratio"] for o in success),"absolute_log_lr_success_only":distribution(abs(math.log(o["likelihood_ratio"])) for o in success),
                "sufficiency":dict(Counter(o["evidence_sufficiency"] for o in observations)),
                "qualitative_categories":dict(Counter(o["assessment"]["strength"] for o in observations if o.get("assessment"))),
                "usable_neutral_game_ids":[r["game_id"] for r in rows if r[version+"_groups"][i]["status"]=="success" and r[version+"_groups"][i]["likelihood_ratio"]==1]}
        eligible=[r for r in rows if all(r[version+"_groups"][i]["status"]=="success" for i in (0,1))]
        same=[r["game_id"] for r in eligible if r[version+"_group_log_likelihood_ratios"][GROUPS[0]]*r[version+"_group_log_likelihood_ratios"][GROUPS[1]]>0]
        result["strength_venue_reinforcement"][version]={"assessable_game_ids":[r["game_id"] for r in eligible],"same_nonzero_direction_game_ids":same,"same_nonzero_direction_count":len(same)}
    result["injury_report_states"]={r["game_id"]:{s:packets[r["game_id"]]["injury_news"]["official_injury"][s]["state"] for s in ("home","away")} for r in rows}
    result["news_collection_states"]={r["game_id"]:packets[r["game_id"]]["injury_news"]["news"]["state"] for r in rows}
    return result


def evaluate(games):
    if [g["game_id"] for g in games]!=PILOT:raise ValueError("Comparison is restricted to the five frozen development pilot games")
    # This existing replay validates finalized labels, home mapping, quote rules,
    # baseline cache identities/settings and parent hashes before reusing results.
    verify_baseline(BASELINE)
    baseline=json.loads((BASELINE/"per_game.json").read_text());rows,summary=compare_rows(games,baseline)
    baseline_summary=json.loads((BASELINE/"summary.json").read_text())
    summary["resources"]={"v2_saved_observations":counters(games),"saved_baselines":baseline_summary["resources"],"new_direct_or_v1_calls":0}
    packets={gid:load_evidence(DEFAULT_DATA,gid) for gid in PILOT}
    return rows,summary,diagnostics(rows,packets)


def export_run(run_path,output,allow_mock=False):
    run_path,output=Path(run_path),Path(output);verify_experiment(run_path);run,games,complete=load_experiment(run_path)
    if run["config"]["provider"]=="mock" and not allow_mock:raise ValueError("Mock comparison requires --allow-mock")
    resolved=output.resolve()
    for protected in (run_path.resolve(),Path(run["cache_directory"]).resolve(),DEFAULT_DATA.resolve(),BASELINE.resolve()):
        if resolved==protected or resolved in protected.parents or protected in resolved.parents:raise ValueError("Evaluation output must be separate")
    rows,summary,diag=evaluate(games)
    observations={"plan":{k:v for k,v in run.items() if k!="cache_directory"},"games":games,"completion":{k:v for k,v in complete.items() if k!="files"},
        "private_completion_sha256":digest((run_path/"completion.json").read_bytes()),"baseline_manifest_sha256":digest((BASELINE/"manifest.json").read_bytes()),
        "provider_raw_bodies_included":False}
    for name,value in (("observations.json",observations),("per_game.json",rows),("summary.json",summary),("diagnostics.json",diag)):immutable_json(output/name,value)
    immutable_json(output/"manifest.json",{name:digest((output/name).read_bytes()) for name in ("observations.json","per_game.json","summary.json","diagnostics.json")})
    replay(output)
    return summary


def replay(output):
    output=Path(output);manifest=json.loads((output/"manifest.json").read_text())
    if set(manifest)!={"observations.json","per_game.json","summary.json","diagnostics.json"}:raise ValueError("Public v2 manifest changed")
    for name,sha in manifest.items():
        if digest((output/name).read_bytes())!=sha:raise ValueError("Public v2 report hash mismatch")
    obs=json.loads((output/"observations.json").read_text());run=obs["plan"]
    if run["scope"]!="pilot" or run["subset"]!="development" or obs["provider_raw_bodies_included"] is not False:raise ValueError("Public v2 replay is pilot-only")
    plan,specs=plan_experiment(run["config"]["provider"]=="mock")
    if any(run[k]!=v for k,v in plan.items()) or obs["baseline_manifest_sha256"]!=digest((BASELINE/"manifest.json").read_bytes()):raise ValueError("Frozen plan/baseline changed")
    games=obs["games"]
    if [g["game_id"] for g in games]!=PILOT:raise ValueError("Public v2 sample changed")
    for g,planned in zip(games,plan["games"]):
        if len(g["groups"])!=4:raise ValueError("Missing group records")
        for r,s in zip(g["groups"],[s for s in specs if s["game_id"]==g["game_id"]]):
            verify_record(r)
            if any(r[k]!=v for k,v in brief(s).items()):raise ValueError("Public v2 projection/request identity changed")
        if game_record(planned,g["groups"])!=g:raise ValueError("Public v2 aggregation changed")
    if any(obs["completion"][k]!=v for k,v in counters(games).items()):raise ValueError("Public v2 accounting changed")
    rows,summary,diag=evaluate(games)
    if rows!=json.loads((output/"per_game.json").read_text()) or summary!=json.loads((output/"summary.json").read_text()) or diag!=json.loads((output/"diagnostics.json").read_text()):raise ValueError("Public v2 metrics do not reproduce")
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--run",type=Path);p.add_argument("--output",type=Path);p.add_argument("--replay",type=Path);p.add_argument("--allow-mock",action="store_true");a=p.parse_args()
    if a.replay:result=replay(a.replay)
    elif a.run and a.output:result=export_run(a.run,a.output,a.allow_mock)
    else:p.error("Use --run SEALED --output PUBLIC or --replay PUBLIC")
    print(json.dumps({"coverage":result["coverage"],"paired_scores":result["paired"]["scores"]},indent=2))


if __name__=="__main__":main()
