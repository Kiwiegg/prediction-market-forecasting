"""Blinded, synthetic-only Phase 1 evidence and response contracts. No data reads."""
import copy
import importlib.util
import json
import math
from pathlib import Path

from evidence_documents import canonical,digest

ROOT=Path(__file__).resolve().parents[1]
ASSETS=ROOT/"experiments/leap_nba_v2_phase1"
REGISTRY_SHA="e6087d3663076f02da358ab0268b8236b6bb3c8b28c8444ec3fd5df15aee5b88"
BLIND_SEED="leap-nba-v2-phase1-blinding-2026-10-22"
METHODS=("numeric","qualitative")
FEATURES=("regular_season_record","recent_regular_season","regular_season_scoring")
REASONS={"incomplete_timestamped_history","no_completed_games","unverified_final_scores"}


def load_phase():
    path=ASSETS/"frozen_assets.json"
    if digest(path.read_bytes())!=REGISTRY_SHA:raise ValueError("Phase 1 registry changed")
    assets=json.loads(path.read_text())
    for name,sha in assets.items():
        p=(ROOT/name).resolve()
        if ROOT not in p.parents or digest(p.read_bytes())!=sha:raise ValueError("Frozen Phase 1 asset changed: "+name)
    module_spec=importlib.util.spec_from_file_location("frozen_synthetic_generator",ASSETS/"generate_cases.py")
    module=importlib.util.module_from_spec(module_spec);module_spec.loader.exec_module(module)
    cases=json.loads((ASSETS/"cases.json").read_text())
    if cases!=module.generate():raise ValueError("Cases do not reproduce from frozen generator")
    for c in cases["cases"]:
        validate_evidence(c["evidence"])
        if json.loads(c["input_text"])!=c["evidence"] or digest(c["input_text"].encode())!=c["input_text_sha256"]:
            raise ValueError("Case input serialization mismatch")
    return cases,json.loads((ASSETS/"config.json").read_text()),assets


def validate_team(team):
    if not isinstance(team,dict) or set(team)-set(FEATURES)-{"omitted_features"}:raise ValueError("Unapproved blinded team fields")
    for key in ("regular_season_record","recent_regular_season"):
        if key not in team:continue
        r=team[key];nkey="games_completed" if key=="regular_season_record" else "window_games"
        expected={nkey,"wins","losses"}|({"results_oldest_to_newest"} if key=="recent_regular_season" else set())
        if (not isinstance(r,dict) or set(r)!=expected or any(type(r[k]) is not int or r[k]<0 for k in (nkey,"wins","losses"))
                or r["wins"]+r["losses"]!=r[nkey]):raise ValueError("Invalid record/counts")
        if key=="recent_regular_season":
            seq=r["results_oldest_to_newest"]
            if not isinstance(seq,str) or set(seq)-{"W","L"} or len(seq)!=r[nkey] or seq.count("W")!=r["wins"]:raise ValueError("Invalid recent form")
            season=team.get("regular_season_record")
            if season and (r["wins"]>season["wins"] or r["losses"]>season["losses"]):raise ValueError("Recent form exceeds season counts")
    if "regular_season_scoring" in team:
        r=team["regular_season_scoring"];required={"games_completed","total_point_differential","average_point_differential"}
        if (not isinstance(r,dict) or not required<=set(r) or set(r)-required-{"point_differentials"}
                or type(r["games_completed"]) is not int or r["games_completed"]<=0
                or type(r["total_point_differential"]) is not int
                or type(r["average_point_differential"]) not in (int,float) or not math.isfinite(r["average_point_differential"])
                or round(r["total_point_differential"]/r["games_completed"],6)!=r["average_point_differential"]):raise ValueError("Invalid scoring summary")
        if "regular_season_record" in team and r["games_completed"]!=team["regular_season_record"]["games_completed"]:raise ValueError("Scoring sample differs")
        if "point_differentials" in r:
            values=r["point_differentials"]
            if (not isinstance(values,list) or any(type(v) is not int or v==0 for v in values)
                    or len(values)!=r["games_completed"] or sum(values)!=r["total_point_differential"]):raise ValueError("Invalid per-game margins")
    for o in team.get("omitted_features",[]):
        if set(o)!={"feature","reason"} or o["feature"] not in FEATURES or o["reason"] not in REASONS:raise ValueError("Unapproved omission metadata")
        if o["feature"] in team:raise ValueError("Feature simultaneously present and omitted")
    return team


def validate_evidence(evidence):
    if not isinstance(evidence,dict) or set(evidence)!={"Team X","Team Y","source_verification"}:raise ValueError("Unapproved evidence root")
    for s in ("Team X","Team Y"):validate_team(evidence[s])
    v=evidence["source_verification"]
    if not isinstance(v,dict) or set(v)-{"reconstruction_status","point_in_time_verified"}:raise ValueError("Unapproved source qualifiers")
    if "point_in_time_verified" in v and type(v["point_in_time_verified"]) is not bool:raise ValueError("Invalid verification flag")
    if "reconstruction_status" in v and v["reconstruction_status"] not in ("synthetic_fixture","timestamped_history_unversioned_payloads"):
        raise ValueError("Unknown qualifier could leak identity; retain separately for audit")
    return evidence


def blind_packet(packet,seed=BLIND_SEED):
    """In-memory future-facing projection; Phase 1 runner never loads real packets."""
    gid=packet.get("game_id")
    if not isinstance(gid,str) or not gid:raise ValueError("Opaque assignment identifier required outside model context")
    assignment=digest((seed+"|"+gid).encode())
    sides=("home","away") if int(assignment,16)%2==0 else ("away","home")
    content={"source_verification":{k:copy.deepcopy(packet[k]) for k in ("reconstruction_status","point_in_time_verified") if k in packet}}
    for label,side in zip(("Team X","Team Y"),sides):
        src=packet[side];out={}
        for field in FEATURES:
            if field not in src:continue
            if field=="regular_season_scoring":
                r=src[field];out[field]={k:copy.deepcopy(r[k]) for k in ("games_completed","total_point_differential","average_point_differential")}
                if "per_game" in r:out[field]["point_differentials"]=[v["point_differential"] for v in r["per_game"]]
            else:out[field]=copy.deepcopy(src[field])
        out["omitted_features"]=[copy.deepcopy(o) for o in src.get("omitted_features",[]) if o["feature"] in FEATURES]
        content[label]=out
    validate_evidence(content)
    return content,{"assignment_sha256":assignment,"X_source_side":sides[0],"Y_source_side":sides[1]}


def strict_json(text):
    def pairs(items):
        if len(dict(items))!=len(items):raise ValueError("Duplicate JSON keys")
        return dict(items)
    def bad(_):raise ValueError("Nonstandard JSON constant")
    value=json.loads(text,object_pairs_hook=pairs,parse_constant=bad)
    if not isinstance(value,dict):raise ValueError("Object required")
    return value


def parse_assessment(method,value):
    expected={"likelihood_ratio","evidence_sufficiency"} if method=="numeric" else {"favored_side","strength","evidence_sufficiency"}
    if method not in METHODS or set(value)!=expected:raise ValueError("Unapproved response fields")
    suff=value["evidence_sufficiency"]
    if suff not in ("adequate","limited","insufficient"):raise ValueError("Invalid sufficiency")
    if method=="numeric":
        lr=value["likelihood_ratio"]
        if type(lr) not in (int,float) or not math.isfinite(lr) or not .05<=lr<=20:raise ValueError("Invalid numeric LR")
        if suff=="insufficient" and lr!=1:raise ValueError("Insufficient numeric response must use placeholder 1")
    else:
        side,strength=value["favored_side"],value["strength"]
        mapping=json.loads((ASSETS/"mapping.json").read_text())
        if side not in ("X","Y","neither") or not isinstance(strength,str) or strength not in mapping:raise ValueError("Invalid qualitative labels")
        if (side=="neither")!=(strength=="neutral"):raise ValueError("Incoherent direction/strength")
        if suff=="insufficient" and side!="neither":raise ValueError("Insufficiency cannot be confident/directional")
        lr=mapping[strength] if side!="Y" else 1/mapping[strength]
    if suff=="insufficient":return {"assessment":value,"likelihood_ratio":None,"direction":None,"status":"insufficient"}
    direction="neither" if abs(math.log(lr))<=1e-9 else "X" if lr>1 else "Y"
    return {"assessment":value,"likelihood_ratio":float(lr),"direction":direction,"status":"ok"}


def make_specs(mock=False):
    cases,config,assets=load_phase()
    config=copy.deepcopy(config)
    if mock:config["provider"]="mock"
    byid={c["case_id"]:c for c in cases["cases"]};specs=[]
    for index,cid in enumerate(cases["run_order"]):
        c=byid[cid]
        for method in METHODS if index%2==0 else tuple(reversed(METHODS)):
            prompt=(ROOT/f"prompts/leap_nba_v2_phase1_{method}_v1.txt").read_bytes()
            schema=json.loads((ASSETS/(method+"_schema.json")).read_text())
            payload={"model":config["model"],"system":prompt.decode(),"messages":[{"role":"user","content":c["input_text"]}],
                **config["generation"],"output_config":{"format":{"type":"json_schema","schema":schema}}}
            wire={"provider":config["provider"],"method":"POST","url":"https://api.anthropic.com/v1/messages","payload":payload}
            bound=len(canonical(payload))+config["input_overhead_token_bound"]
            cost=(bound*config["prices"]["input_usd_per_million"]+128*config["prices"]["output_usd_per_million"])/1e6
            specs.append({"case_id":cid,"method":method,"key":digest(canonical(wire)),"wire":wire,
                "input_token_bound":bound,"reserved_cost_usd":cost if not mock else 0,
                "input_text_sha256":c["input_text_sha256"],"evidence_sha256":digest(canonical(c["evidence"])),"prompt_sha256":digest(prompt)})
    return cases,config,assets,specs
