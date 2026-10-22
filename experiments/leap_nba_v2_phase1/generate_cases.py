"""Deterministic synthetic cases; no repository data, labels or source retrieval."""
import copy
import hashlib
import json
from pathlib import Path

SEED = "leap-nba-v2-phase1-synthetic-2026-10-22"


def team(wins=None, losses=None, pd=None, recent=None, missing_reason="unverified_final_scores"):
    result = {"omitted_features": []}
    if wins is not None:
        result["regular_season_record"] = {"games_completed": wins+losses, "wins": wins, "losses": losses}
    else:
        result["omitted_features"].append({"feature":"regular_season_record","reason":"incomplete_timestamped_history"})
    if recent:
        result["recent_regular_season"] = {"window_games":len(recent),"wins":recent.count("W"),"losses":recent.count("L"),"results_oldest_to_newest":recent}
    else:
        result["omitted_features"].append({"feature":"recent_regular_season","reason":"no_completed_games" if wins==0 and losses==0 else "incomplete_timestamped_history"})
    if pd is not None:
        n=wins+losses
        result["regular_season_scoring"] = {"games_completed":n,"total_point_differential":round(n*pd),"average_point_differential":pd}
    else:
        result["omitted_features"].append({"feature":"regular_season_scoring","reason":missing_reason})
    return result


def reverse_keys(value):
    if isinstance(value,dict):return {k:reverse_keys(v) for k,v in reversed(list(value.items()))}
    if isinstance(value,list):return [reverse_keys(v) for v in value]
    return value


def generate():
    families = [
        ("clear_x",team(30,10,7,"WWWWL"),team(14,26,-5,"LLLWL"),"X",True,False),
        ("modest_x",team(24,16,2.8,"WWWLL"),team(20,20,.6,"WWLLL"),"X",True,False),
        ("clear_y",team(12,28,-6,"LLLLW"),team(28,12,5,"LWWWW"),"Y",True,False),
        ("identical_nonempty",team(20,20,0,"WWLLL"),team(20,20,0,"WWLLL"),"neither",False,False),
        ("conflicting_indicators",team(30,10,1,"WWLLL"),team(22,18,6,"LWWWW"),None,False,False),
        ("missing_scoring",team(25,15,None,"WWWWL"),team(17,23,None,"WWLLL"),None,False,False),
        ("small_sample",team(2,0,6,"WW"),team(0,2,-6,"LL"),"X",True,False),
        ("extreme_consistent",team(36,4,12,"WWWWW"),team(4,36,-12,"LLLLL"),"X",True,False),
        ("all_features_unavailable",team(),team(),None,False,True),
        ("zero_completed_games",team(0,0,None,None,"no_completed_games"),team(0,0,None,None,"no_completed_games"),None,False,True),
    ]
    cases=[]
    for i,(category,x,y,side,dominance,abstain) in enumerate(families,1):
        base={"Team X":x,"Team Y":y,"source_verification":{"reconstruction_status":"synthetic_fixture","point_in_time_verified":False}}
        for variant in ("base","swap","format"):
            content=copy.deepcopy(base)
            expected=side
            if variant=="swap":
                content["Team X"],content["Team Y"]=content["Team Y"],content["Team X"]
                expected={"X":"Y","Y":"X","neither":"neither",None:None}[side]
            text=json.dumps(reverse_keys(content),indent=2,ensure_ascii=False) if variant=="format" else json.dumps(content,sort_keys=True,separators=(",",":"),ensure_ascii=False)
            cases.append({"case_id":f"f{i:02d}_{variant}","family_id":f"f{i:02d}","category":category,"variant":variant,
                "evidence":content,"input_text":text,"input_text_sha256":hashlib.sha256(text.encode()).hexdigest(),
                "expected":{"favored_side":expected,"dominance":dominance,"must_abstain":abstain,"identical_nonempty":category=="identical_nonempty"}})
    order=sorted([c["case_id"] for c in cases],key=lambda c:hashlib.sha256((SEED+"|run-order|"+c).encode()).hexdigest())
    return {"schema_version":1,"seed":SEED,"case_count":30,"family_count":10,"cases":cases,"run_order":order}


if __name__=="__main__":
    path=Path(__file__).with_name("cases.json")
    data=(json.dumps(generate(),sort_keys=True,separators=(",",":"))+"\n").encode()
    if path.exists() and path.read_bytes()!=data:raise SystemExit("Frozen cases differ; refusing overwrite")
    if not path.exists():
        with path.open("xb") as f:f.write(data)
    print(path.name+": 30 cases, 10 families; deterministic match")
