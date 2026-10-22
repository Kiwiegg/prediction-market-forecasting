"""Frozen historical v2 projections and mapped qualitative assessments."""
import copy
import json
import math

from direct_forecast import load_evidence
from evidence_documents import canonical,digest
from forecast_split import ROOT,DEFAULT_DATA,DEFAULT_SPLIT,load_split
from leap_evidence import GROUPS,aggregate as aggregate_v1,build_groups as groups_v1
from synthetic_elicitation import blind_packet,load_phase,parse_assessment,strict_json

ASSETS=ROOT/"experiments/leap_nba_v2_phase2"
REGISTRY_SHA="76bcb80ec46b452d33610ac10eb9dee1606c18b3723cfa9c25780b5c9f1ff114"
PILOT=["401810544","401810485","401810279","401836746","401809808"]
VARIANTS={"leap_v2_raw":1.0,"leap_v2_conservative":.5}


def frozen_assets():
    if digest((ASSETS/"frozen_assets.json").read_bytes())!=REGISTRY_SHA:raise ValueError("Frozen v2 registry changed")
    registry=json.loads((ASSETS/"frozen_assets.json").read_text())
    for name,sha in registry.items():
        p=(ROOT/name).resolve()
        if ROOT not in p.parents or digest(p.read_bytes())!=sha:raise ValueError("Frozen v2 asset changed: "+name)
    load_phase()  # Validate all reused Phase 1 prompt/mapping/projection dependencies.
    if json.loads((ASSETS/"mapping.json").read_text())!=json.loads((ROOT/"experiments/leap_nba_v2_phase1/mapping.json").read_text()):raise ValueError("Phase 1 mapping mismatch")
    return registry


def config(mock=False):
    result=json.loads((ASSETS/"config.json").read_text())
    if mock:result["provider"]="mock"
    return result


def build_groups(packet):
    # v1 verifies the parent/schema and retains the validated C/D partition and deduplication.
    old=groups_v1(packet);blinded,orientation=blind_packet(packet)
    completed=any(blinded[s].get(k,{}).get("games_completed",blinded[s].get(k,{}).get("window_games",0))>0
        for s in ("Team X","Team Y") for k in ("regular_season_record","recent_regular_season","regular_season_scoring"))
    has_stats=any(k in blinded[s] for s in ("Team X","Team Y") for k in ("regular_season_record","recent_regular_season","regular_season_scoring"))
    old[0].update(content=blinded,usable=completed,missing_reason=None if completed else "no_completed_games" if has_stats else "statistical_source_unavailable")
    for side in ("home","away"):
        target=old[1]["content"]["evidence"][side]
        if "regular_season_home_away" in packet[side]:target["regular_season_home_away"]=copy.deepcopy(packet[side]["regular_season_home_away"])
        target["omitted_features"].extend(copy.deepcopy(o) for o in packet[side].get("omitted_features",[]) if o["feature"].startswith("regular_season_home_away"))
    result=[]
    for g in old:
        result.append({**g,"game_id":packet["game_id"],"orientation":orientation if g["group"]==GROUPS[0] else None,
            "group_evidence_sha256":digest(canonical(g["content"]))})
    return result


def assessment(group,value,orientation=None):
    if not isinstance(value,dict) or set(value)!={"favored_side","strength","evidence_sufficiency"}:raise ValueError("Exactly three qualitative fields required")
    normalized=copy.deepcopy(value)
    if group==GROUPS[0]:
        if not isinstance(orientation,dict) or {orientation.get("X_source_side"),orientation.get("Y_source_side")}!={"home","away"}:raise ValueError("Invalid blinded orientation")
    elif group in GROUPS:
        if value["favored_side"] not in ("home","away","neither"):raise ValueError("Unapproved home/away label")
        normalized["favored_side"]={"home":"X","away":"Y","neither":"neither"}[value["favored_side"]]
    else:raise ValueError("Unknown v2 group")
    parsed=parse_assessment("qualitative",normalized)
    lr=parsed["likelihood_ratio"]
    if lr is not None and group==GROUPS[0] and orientation["X_source_side"]=="away":lr=1/lr
    if lr is not None and (not math.isfinite(lr) or not .25<=lr<=4):raise ValueError("Invalid mapped home LR")
    side=None if lr is None else "neither" if lr==1 else "home" if lr>1 else "away"
    return {"assessment":copy.deepcopy(value),"evidence_sufficiency":value["evidence_sufficiency"],
        "elicited_likelihood_ratio":parsed["likelihood_ratio"],"likelihood_ratio":lr,"favored_side_home":side,
        "status":"insufficient" if lr is None else "success"}


def aggregate(records):
    adapted=[]
    for r in records:
        status=r["status"]
        if status in ("insufficient","not_attempted_access_denial","not_attempted_budget"):status="failed"
        adapted.append({**r,"status":status})
    result=aggregate_v1(adapted)
    result["variants"]={name:result["variants"][old] for name,old in zip(VARIANTS,("leap_raw","leap_conservative"))}
    return result


def brief(spec):return {k:v for k,v in spec.items() if k!="wire"}


def group_spec(group,cfg):
    name=group["group"];letter=name[0]
    prompt=(ROOT/f"prompts/leap_nba_v2_{letter}_v1.txt").read_bytes()
    schema=json.loads((ASSETS/("xy_schema.json" if letter=="A" else "home_away_schema.json")).read_text())
    payload={"model":cfg["model"],"system":prompt.decode(),"messages":[{"role":"user","content":canonical(group["content"]).decode()}],
        **cfg["generation"],"output_config":{"format":{"type":"json_schema","schema":schema}}}
    wire={"provider":cfg["provider"],"method":"POST","url":"https://api.anthropic.com/v1/messages","payload":payload}
    identity={k:copy.deepcopy(group[k]) for k in ("game_id","group","evidence_sha256","group_evidence_sha256","orientation","usable","missing_reason","deduplication_decisions")}
    bound=len(canonical(payload))+cfg["input_overhead_token_bound"]
    price=(bound*cfg["prices"]["input_usd_per_million"]+128*cfg["prices"]["output_usd_per_million"])/1e6
    return {**identity,"wire":wire,"wire_sha256":digest(canonical(wire)),"key":digest(canonical({"identity":identity,"wire":wire,"frozen_registry_sha256":REGISTRY_SHA})),
        "prompt_sha256":digest(prompt),"input_token_bound":bound,"reserved_cost_usd":price if group["usable"] and cfg["provider"]!="mock" else 0}


def plan_experiment(mock=False,scope="pilot",authorize_development=False,dataset=DEFAULT_DATA,split_path=DEFAULT_SPLIT):
    if scope not in ("pilot","full-development") or scope=="full-development" and not authorize_development:raise ValueError("Full development requires separate explicit authorization; reserved evaluation is unsupported")
    assets=frozen_assets();split=load_split(split_path,dataset);pilot=json.loads((ASSETS/"pilot.json").read_text())
    if split["run_order"]["development"][:5]!=PILOT or pilot["game_ids"]!=PILOT or digest(canonical(split))!=pilot["split_canonical_sha256"] or digest(split_path.read_bytes())!=pilot["split_file_sha256"]:raise ValueError("Frozen split/pilot changed")
    cfg=config(mock);games=[];specs=[]
    expected={g["game_id"]:g["evidence_sha256"] for g in pilot["games"]}
    for gid in PILOT if scope=="pilot" else split["run_order"]["development"]:
        packet=load_evidence(dataset,gid)
        if gid in expected and packet["evidence_snapshot_sha256"]!=expected[gid]:raise ValueError("Frozen pilot parent changed")
        groups=[group_spec(g,cfg) for g in build_groups(packet)];specs.extend(groups)
        games.append({"game_id":gid,"evidence_sha256":packet["evidence_snapshot_sha256"],"groups":[brief(g) for g in groups]})
    return {"schema_version":1,"method":"leap_nba_v2_mock" if mock else "leap_nba_v2","subset":"development","scope":scope,
        "full_development_authorized":authorize_development,"split_sha256":digest(canonical(split)),"config":cfg,"frozen_assets":assets,
        "frozen_registry_sha256":REGISTRY_SHA,"historical_interpretation":"development_informed_exploratory_integration_pilot","games":games},specs
