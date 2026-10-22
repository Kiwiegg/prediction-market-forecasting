import copy
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import Mock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import synthetic_elicitation as s
import run_synthetic_elicitation as runner
import evaluate_synthetic_elicitation as evaluator
from evidence_documents import canonical,digest
from research_providers import CapturedHTTP


class Response:
    status=200
    def __init__(self,value):self.body=canonical(value)
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def read(self,n):return self.body[:n]


class SyntheticTests(unittest.TestCase):
    def test_frozen_generator_semantics_blinding_and_wire_isolation(self):
        cases,config,assets,specs=s.make_specs()
        self.assertEqual((len(cases["cases"]),len(specs),len({r["key"] for r in specs})),(30,60,54))
        self.assertLess(sum(r["reserved_cost_usd"] for r in {r["key"]:r for r in specs}.values()),1)
        self.assertEqual(len([c for c in cases["cases"] if c["expected"]["dominance"]]),15)
        byid={c["case_id"]:c for c in cases["cases"]}
        for n in range(1,11):
            b,w,f=(byid[f"f{n:02d}_{v}"] for v in ("base","swap","format"))
            self.assertEqual(b["evidence"]["Team X"],w["evidence"]["Team Y"])
            self.assertEqual(b["evidence"],f["evidence"])
            self.assertNotEqual(b["input_text"],f["input_text"])
        for i in range(0,60,2):
            a,b=specs[i:i+2]
            self.assertEqual(a["wire"]["payload"]["messages"],b["wire"]["payload"]["messages"])
            self.assertNotIn("tools",a["wire"]["payload"])
            self.assertEqual(set(json.loads(a["wire"]["payload"]["messages"][0]["content"])),{"Team X","Team Y","source_verification"})
            self.assertEqual(a["method"],"numeric" if i//2%2==0 else "qualitative")
        packet={"game_id":"opaque-artificial-id","home":copy.deepcopy(byid["f01_base"]["evidence"]["Team X"]),
            "away":copy.deepcopy(byid["f01_base"]["evidence"]["Team Y"]),"point_in_time_verified":False,
            "reconstruction_status":"timestamped_history_unversioned_payloads","outcome":1,"market_price":.9,"tipoff":"secret-date"}
        for side in ("home","away"):
            packet[side].update(team_name="DO NOT SEND",team_id="123",home_away_splits={"wins":30},rest_days=3,injuries=["SECRET"])
        projected,audit=s.blind_packet(packet)
        for forbidden in ("DO NOT SEND","123","home_away","rest_days","injuries","outcome","market_price","secret-date","opaque-artificial-id"):
            self.assertNotIn(forbidden,canonical(projected).decode())
        changed=copy.deepcopy(packet);changed.update(outcome=0,market_price=.1)
        self.assertEqual(s.blind_packet(changed),(projected,audit))
        changed["home"],changed["away"]=changed["away"],changed["home"]
        swapped,_=s.blind_packet(changed)
        self.assertEqual(swapped["Team X"],projected["Team Y"])
        assignments={s.blind_packet({**packet,"game_id":str(n)})[1]["X_source_side"] for n in range(20)}
        self.assertEqual(assignments,{"home","away"})

    def test_missingness_source_qualifiers_and_per_game_ids(self):
        cases,_,_=s.load_phase();c=copy.deepcopy(cases["cases"][-1]["evidence"])
        packet={"game_id":"fictional","home":c["Team X"],"away":c["Team Y"],"point_in_time_verified":False}
        e,_=s.blind_packet(packet)
        self.assertNotIn("regular_season_scoring",e["Team X"])
        self.assertEqual(e["Team X"]["omitted_features"],packet["home"]["omitted_features"])
        self.assertFalse(e["source_verification"]["point_in_time_verified"])
        packet["reconstruction_status"]="Boston secret result"
        with self.assertRaises(ValueError):s.blind_packet(packet)
        side={"regular_season_record":{"wins":1,"losses":1,"games_completed":2},"regular_season_scoring":{"games_completed":2,"total_point_differential":0,"average_point_differential":0,
            "per_game":[{"game_id":"SECRET-ID-1","point_differential":5},{"game_id":"SECRET-ID-2","point_differential":-5}]}}
        e,_=s.blind_packet({"game_id":"fictional","home":side,"away":side})
        self.assertNotIn("SECRET",str(e));self.assertEqual(e["Team X"]["regular_season_scoring"]["point_differentials"],[5,-5])

    def test_mapping_schema_strictness_and_abstention(self):
        for strength,mag in (("slight",1.25),("moderate",1.75),("strong",2.5),("very_strong",4)):
            for side,lr in (("X",mag),("Y",1/mag)):
                v=s.parse_assessment("qualitative",{"favored_side":side,"strength":strength,"evidence_sufficiency":"limited"})
                self.assertEqual(v["likelihood_ratio"],lr)
        for method,v in (("numeric",{"likelihood_ratio":1,"evidence_sufficiency":"insufficient"}),
            ("qualitative",{"favored_side":"neither","strength":"neutral","evidence_sufficiency":"insufficient"})):
            p=s.parse_assessment(method,v);self.assertIsNone(p["likelihood_ratio"]);self.assertIsNone(p["direction"])
        for value in (0,-1,True,float("inf"),float("nan"),.049,20.01,"1",None):
            with self.assertRaises(ValueError):s.parse_assessment("numeric",{"likelihood_ratio":value,"evidence_sufficiency":"adequate"})
        for value in (.05,1,20):self.assertEqual(s.parse_assessment("numeric",{"likelihood_ratio":value,"evidence_sufficiency":"adequate"})["likelihood_ratio"],value)
        for side,strength,suff in (("X","neutral","adequate"),("neither","strong","adequate"),("X","slight","insufficient"),("Y","slight","bad")):
            with self.assertRaises(ValueError):s.parse_assessment("qualitative",{"favored_side":side,"strength":strength,"evidence_sufficiency":suff})
        for text in ('{"a":1,"a":2}','[]','{"likelihood_ratio":NaN}','```json\n{}\n```'):
            with self.assertRaises(ValueError):s.strict_json(text)
        with self.assertRaises(ValueError):s.parse_assessment("numeric",{"likelihood_ratio":1,"evidence_sufficiency":"insufficient","explanation":"invented"})

    def test_mock_immutable_cache_replay_and_zero_data_network_reads(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);output=root/"run";cache=root/"cache"
            original_open=Path.open
            def guarded(path,*args,**kwargs):
                if s.ROOT/"data" in path.resolve().parents:raise AssertionError("Phase 1 accessed historical data")
                return original_open(path,*args,**kwargs)
            with patch.object(Path,"open",guarded),patch("urllib.request.OpenerDirector.open",side_effect=AssertionError("Offline")):
                result=runner.execute(output,cache,mock=True)
                before={p:digest(p.read_bytes()) for parent in (output,cache) for p in parent.rglob("*") if p.is_file()}
                self.assertEqual(runner.execute(output,cache,mock=True),result)
                summary=evaluator.export_run(output,root/"public")
                self.assertEqual(evaluator.replay(root/"public"),summary)
                self.assertEqual(summary["numeric"]["criteria"]["dominance"]["status"],"fail")
                self.assertEqual(summary["qualitative"]["criteria"]["uninformative_abstention"]["status"],"pass")
                self.assertFalse(summary["recommend_separately_authorized_pilot"])
                self.assertEqual(before,{p:digest(p.read_bytes()) for p in before})
            self.assertEqual(len(list(cache.glob("*/response.json"))),54)
            response=next(cache.glob("*/response.json"));response.write_text("{}")
            with self.assertRaises((ValueError,KeyError)):runner.verify(output)

    def test_preflight_budget_uncertain_requests_and_output_protection(self):
        _,_,_,specs=s.make_specs()
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{"ANTHROPIC_API_KEY":"fixture"}),patch("urllib.request.OpenerDirector.open") as network:
            root=Path(tmp)
            for calls,cost in ((53,1),(120,.01),(121,1),(120,float("nan"))):
                with self.assertRaises(ValueError):runner.execute(root/"run",root/"cache",allow_paid=True,max_calls=calls,max_cost=cost)
            folder=root/"cache"/specs[0]["key"];folder.mkdir(parents=True);(folder/"attempt.json").write_text("{}")
            with self.assertRaises(ValueError):runner.execute(root/"run",root/"cache",allow_paid=True)
            with self.assertRaises(ValueError):runner.execute(s.ROOT/"data/bad",root/"mockcache",mock=True)
            network.assert_not_called()

    def test_first_access_denial_stops_without_retry_and_partial_metrics_are_incomplete(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{"ANTHROPIC_API_KEY":"fixture-not-saved"}):
            root=Path(tmp);opener=Mock()
            opener.open.side_effect=urllib.error.HTTPError("https://api.anthropic.com/v1/messages",403,"Forbidden",{},io.BytesIO(b'{"error":{"type":"forbidden","message":"Request not allowed"}}'))
            factory=lambda folder,allow_network:CapturedHTTP(folder,allow_network,opener=opener)
            # Redirect only the private authorization registry into the test sandbox.
            kwargs={"allow_paid":True,"transport_factory":factory,"authorization_path":root/"registry.json"}
            result=runner.execute(root/"run",root/"cache",**kwargs)
            self.assertEqual(result["paid_request_reservations"],1)
            self.assertTrue(result["stopped_on_access_denial"])
            self.assertEqual(opener.open.call_count,1)
            runner.execute(root/"run",root/"cache",**kwargs)
            self.assertEqual(opener.open.call_count,1)
            with self.assertRaises(ValueError):runner.execute(root/"another",root/"cache",**kwargs)
            summary=evaluator.export_run(root/"run",root/"public")
            self.assertEqual(summary["numeric"]["criteria"]["dominance"]["status"],"incomplete")
            self.assertFalse(summary["recommend_separately_authorized_pilot"])
            for p in root.rglob("*"):
                if p.is_file():self.assertNotIn(b"fixture-not-saved",p.read_bytes())

    def test_envelope_malformed_usage_and_provider_failure_are_terminal(self):
        _,cfg,_,specs=s.make_specs();spec=specs[0]
        valid={"model":cfg["model"],"role":"assistant","stop_reason":"end_turn","usage":{"input_tokens":100,"output_tokens":20},"content":[{"type":"text","text":'{"likelihood_ratio":1.5,"evidence_sufficiency":"adequate"}'}]}
        for mutate in (lambda r:r["usage"].update(input_tokens=True),lambda r:r.update(stop_reason="max_tokens"),lambda r:r.update(model="other"),lambda r:r["usage"].update(server_tool_use={"web_search_requests":1})):
            bad=copy.deepcopy(valid);mutate(bad)
            with self.assertRaises(ValueError):runner.validate_envelope(bad,spec,cfg)
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{"ANTHROPIC_API_KEY":"fixture"}):
            opener=Mock();bad=copy.deepcopy(valid);bad["content"][0]["text"]="bad JSON"
            opener.open.return_value=Response(bad);factory=lambda folder,allow_network:CapturedHTTP(folder,allow_network,opener=opener)
            record=runner.cached_request(spec,cfg,tmp,True,factory)
            self.assertEqual(record["status"],"invalid_response");self.assertIsNone(record["likelihood_ratio"])
            self.assertEqual(runner.cached_request(spec,cfg,tmp,True,factory),record);self.assertEqual(opener.open.call_count,1)

    def test_prespecified_metrics_swap_reciprocity_formatting_and_thresholds(self):
        cases,_,_,specs=s.make_specs(mock=True);byid={c["case_id"]:c for c in cases["cases"]};observations=[]
        for spec in specs:
            c=byid[spec["case_id"]];side=c["expected"]["favored_side"] or "X";abstain=c["expected"]["must_abstain"]
            if abstain:side="neither"
            lr=1 if side=="neither" else 1.75 if side=="X" else 1/1.75
            value={"likelihood_ratio":lr,"evidence_sufficiency":"insufficient" if abstain else "adequate"} if spec["method"]=="numeric" else {
                "favored_side":side,"strength":"neutral" if side=="neither" else "moderate","evidence_sufficiency":"insufficient" if abstain else "adequate"}
            # Only fixture arithmetic: conflicting/missing families choose a consistent reverse, not numeric ground truth.
            if c["variant"]=="swap" and c["expected"]["favored_side"] is None and not abstain:
                value.update({"likelihood_ratio":1/1.75} if spec["method"]=="numeric" else {"favored_side":"Y"})
            observations.append({"case_id":c["case_id"],"method":spec["method"],"provider":"mock","http_status":None,"request_sha256":spec["key"],
                "schema_valid":True,"strict_json_object_valid":True,"unsupported_field_count":0,**s.parse_assessment(spec["method"],value)})
        m=evaluator.metrics(observations)
        self.assertTrue(m["recommend_separately_authorized_pilot"])
        for method in s.METHODS:
            self.assertEqual(m[method]["criteria"]["dominance"]["successes"],15)
            self.assertEqual(m[method]["exact_reciprocal_pairs"],8)
            self.assertEqual(m[method]["format_exact_pairs"],10)
        self.assertEqual(evaluator.criterion(14,15,15,.9)["status"],"pass")
        self.assertEqual(evaluator.criterion(13,15,15,.9)["status"],"fail")
        self.assertEqual(evaluator.criterion(7,8,8,.9)["status"],"fail")
        missing=next(r for r in observations if r["method"]=="qualitative" and r["case_id"]=="f01_base")
        missing.update(schema_valid=False,strict_json_object_valid=False,status="not_attempted_after_access_denial",likelihood_ratio=None,direction=None,provider="anthropic")
        m=evaluator.metrics(observations)
        self.assertEqual(m["qualitative"]["criteria"]["dominance"]["status"],"incomplete")
        self.assertFalse(m["recommend_separately_authorized_pilot"])


if __name__=="__main__":unittest.main()
