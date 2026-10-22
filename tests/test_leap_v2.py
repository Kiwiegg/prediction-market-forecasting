import copy
import io
import json
import math
import os
import shutil
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import Mock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import leap_v2_evidence as evidence
import leap_v2_forecast as runner
import compare_leap_v2 as compare
from direct_forecast import load_evidence,signed_record
from evidence_documents import canonical,digest
from forecast_split import DEFAULT_DATA,DEFAULT_SPLIT
from leap_evidence import GROUPS
from test_leap_forecast import Response,factory,finding,rehash


def reply(side="neither",strength="neutral",sufficiency="adequate",**changes):
    return {"role":"assistant","model":"claude-haiku-4-5-20251001","stop_reason":"end_turn", "usage":{"input_tokens":100,"output_tokens":30},
        "content":[{"type":"text","text":json.dumps({"favored_side":side,"strength":strength,"evidence_sufficiency":sufficiency})}],**changes}


class ProjectionTests(unittest.TestCase):
    def setUp(self):self.packet=load_evidence(DEFAULT_DATA,evidence.PILOT[0])

    def test_group_isolation_blinding_and_no_mutation(self):
        before=canonical(self.packet);groups=evidence.build_groups(self.packet)
        self.assertEqual(groups,evidence.build_groups(copy.deepcopy(self.packet)));self.assertEqual(before,canonical(self.packet))
        a,b,c,d=[g["content"] for g in groups]
        self.assertEqual(set(a),{"Team X","Team Y","source_verification"})
        text=canonical(a).decode()
        for token in (self.packet["game_id"],"home","away","neutral_site","rest_at_cutoff","official_injury","regular_season_home_away",self.packet["cutoff_utc"]):self.assertNotIn(token,text)
        for side in ("home","away"):
            self.assertNotIn(self.packet[side]["team_name"],text)
            self.assertEqual(b["evidence"][side].get("regular_season_home_away"),self.packet[side].get("regular_season_home_away"))
            self.assertNotIn("regular_season_record",b["evidence"][side]);self.assertNotIn("regular_season_scoring",b["evidence"][side])
        for g in (a,b,d):self.assertNotIn("official_injury",canonical(g).decode())
        p=copy.deepcopy(self.packet);p["home"]["rest_at_cutoff"]["hours_since_last_completed_game"]+=1
        changed=evidence.build_groups(rehash(p))
        self.assertNotEqual(groups[1]["content"],changed[1]["content"])
        for i in (0,2,3):self.assertEqual(groups[i]["content"],changed[i]["content"])
        p=copy.deepcopy(self.packet)
        for venue,delta in (("home",1),("away",-1)):
            p["home"]["regular_season_home_away"][venue]["wins"]+=delta
            p["home"]["regular_season_home_away"][venue]["losses"]-=delta
        moved=evidence.build_groups(rehash(p))
        self.assertEqual(groups[0]["content"],moved[0]["content"]);self.assertNotEqual(groups[1]["content"],moved[1]["content"])

    def test_orientation_inversion_schema_coherence_and_mapping(self):
        group=evidence.build_groups(self.packet)[0];orientation=group["orientation"]
        self.assertEqual(group,evidence.build_groups(self.packet)[0])
        for strength,magnitude in (("slight",1.25),("moderate",1.75),("strong",2.5),("very_strong",4)):
            for side in ("X","Y"):
                obj={"favored_side":side,"strength":strength,"evidence_sufficiency":"limited"}
                home={"X_source_side":"home","Y_source_side":"away"};away={"X_source_side":"away","Y_source_side":"home"}
                a=evidence.assessment(GROUPS[0],obj,home);b=evidence.assessment(GROUPS[0],obj,away)
                self.assertAlmostEqual(a["likelihood_ratio"]*b["likelihood_ratio"],1)
                self.assertEqual(a["favored_side_home"],"home" if side=="X" else "away")
                self.assertEqual(b["favored_side_home"],"away" if side=="X" else "home")
        for side,strength,suff in (("home","neutral","adequate"),("neither","strong","adequate"),("home","strong","insufficient"),("X","slight","adequate"),("away","strong","unknown")):
            with self.assertRaises(ValueError):evidence.assessment(GROUPS[1],{"favored_side":side,"strength":strength,"evidence_sufficiency":suff})
        with self.assertRaises(ValueError):evidence.assessment(GROUPS[0],{"favored_side":"home","strength":"slight","evidence_sufficiency":"adequate"},orientation)
        for text in ('{"a":1,"a":2}','[]','{"x":NaN}','```json\n{}\n```'):
            with self.assertRaises(ValueError):evidence.strict_json(text)
        abstention=evidence.assessment(GROUPS[1],{"favored_side":"neither","strength":"neutral","evidence_sufficiency":"insufficient"})
        self.assertIsNone(abstention["likelihood_ratio"]);self.assertIsNone(abstention["favored_side_home"])
        self.assertEqual(abstention["status"],"insufficient")
        self.assertEqual(evidence.assessment(GROUPS[1],{"favored_side":"neither","strength":"neutral","evidence_sufficiency":"limited"})["likelihood_ratio"],1)

    def test_missing_reports_news_and_zero_games(self):
        groups=evidence.build_groups(self.packet)
        self.assertEqual(groups[2]["content"]["evidence"]["official_injury"]["away"]["state"],"not_yet_submitted")
        self.assertTrue(groups[2]["usable"]);self.assertFalse(groups[3]["usable"])
        self.assertIn("not_collected_historical",groups[3]["missing_reason"])
        for state in ("unavailable","not_yet_submitted","ambiguous"):
            p=copy.deepcopy(self.packet)
            for side in ("home","away"):p["injury_news"]["official_injury"][side].update(state=state,players=[])
            g=evidence.build_groups(rehash(p))[2]
            self.assertFalse(g["usable"]);self.assertIn(state,g["missing_reason"])
        for absent in (False,True):
            p=copy.deepcopy(self.packet)
            for side in ("home","away"):
                for key in ("regular_season_record","recent_regular_season","regular_season_scoring","regular_season_home_away"):p[side].pop(key,None)
                p[side]["omitted_features"]=[]
                if not absent:p[side]["regular_season_record"]={"games_completed":0,"wins":0,"losses":0}
            groups=evidence.build_groups(rehash(p))
            self.assertFalse(groups[0]["usable"]);self.assertEqual(groups[0]["missing_reason"],"statistical_source_unavailable" if absent else "no_completed_games")
            self.assertTrue(groups[1]["usable"])

    def test_news_partition_deduplication_and_leakage_rejection(self):
        p=copy.deepcopy(self.packet);a=finding("injury_update","Player is out.","article:1");b=finding("team_development","Coach resigned.","article:2")
        p["injury_news"]["news"].update(state="collected",missing_reason=None,findings=[a,a,b,{**a,"category":"roster_transaction"}])
        groups=evidence.build_groups(rehash(p))
        self.assertEqual([f["claim"] for f in groups[2]["content"]["evidence"]["news"]["findings"]],[a["claim"]])
        self.assertEqual([f["claim"] for f in groups[3]["content"]["evidence"]["findings"]],[b["claim"]])
        self.assertTrue(groups[3]["usable"])
        for key in ("outcome","market_price","evaluation","audit"):
            p=copy.deepcopy(self.packet);p[key]="forbidden"
            with self.assertRaises(ValueError):evidence.build_groups(rehash(p))
        p=copy.deepcopy(self.packet);p["injury_news"]["official_injury"]["published_at_utc"]="2099-01-01T00:00:00Z"
        with self.assertRaises(ValueError):evidence.build_groups(rehash(p))
        p=copy.deepcopy(self.packet);p["neutral_site"]=not p["neutral_site"]
        with self.assertRaises(ValueError):evidence.build_groups(p)


class RunnerTests(unittest.TestCase):
    def setUp(self):self.plan,self.specs=evidence.plan_experiment(mock=True)

    def test_plan_identity_fixed_selection_and_authorization_before_loading(self):
        self.assertEqual([g["game_id"] for g in self.plan["games"]],evidence.PILOT)
        self.assertEqual(sum(s["usable"] for s in self.specs),13)
        native,specs=evidence.plan_experiment()
        self.assertLess(sum(s["reserved_cost_usd"] for s in specs),1)
        self.assertNotEqual(self.specs[0]["key"],specs[0]["key"])
        for spec in specs:
            if spec["group"]==GROUPS[0]:
                content=spec["wire"]["payload"]["messages"][0]["content"]
                self.assertNotIn(spec["game_id"],content);self.assertNotIn(spec["evidence_sha256"],content);self.assertNotIn("orientation",content)
        with patch("leap_v2_evidence.load_evidence",side_effect=AssertionError("No unauthorized packet reads")):
            for scope in ("evaluation","full-development"):
                with self.assertRaises(ValueError):evidence.plan_experiment(scope=scope)

    def test_aggregation_variants_loo_stability_and_failed_required_group(self):
        records=[]
        for spec in self.specs[:4]:
            r=runner.base_record(spec,self.plan["config"],"success")
            r.update(status="success",likelihood_ratio=4,evidence_sufficiency="adequate")
            records.append(r)
        result=evidence.aggregate(records)
        self.assertAlmostEqual(result["variants"]["leap_v2_raw"]["home_win_probability"],256/257)
        self.assertAlmostEqual(result["variants"]["leap_v2_conservative"]["home_win_probability"],16/17)
        self.assertAlmostEqual(result["variants"]["leap_v2_raw"]["leave_one_group_out"][GROUPS[0]]["home_win_probability"],64/65)
        for r in records:r["likelihood_ratio"]=.25
        self.assertAlmostEqual(evidence.aggregate(records)["variants"]["leap_v2_raw"]["home_win_probability"],1/257)
        records[0].update(status="insufficient",likelihood_ratio=None)
        result=evidence.aggregate(records)
        self.assertEqual(result["status"],"failed");self.assertIsNone(result["variants"]["leap_v2_raw"]["home_win_probability"])

    def test_mock_cache_immutability_and_replay_no_evaluation_reads(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);original_open=Path.open
            def guarded(p,*args,**kwargs):
                if p.name=="evaluation.csv":raise AssertionError("Outcome/market read during inference")
                return original_open(p,*args,**kwargs)
            with patch.object(Path,"open",guarded),patch("urllib.request.OpenerDirector.open",side_effect=AssertionError("Offline")):
                result=runner.run_experiment(self.plan,self.specs,root/"run",root/"cache")
                before={p:digest(p.read_bytes()) for parent in (root/"run",root/"cache") for p in parent.rglob("*") if p.is_file()}
                self.assertEqual(runner.run_experiment(self.plan,self.specs,root/"run",root/"cache"),result)
                self.assertEqual(runner.verify_experiment(root/"run"),result)
                self.assertEqual(before,{p:digest(p.read_bytes()) for p in before})
            self.assertEqual((result["successful_forecasts"],result["paid_call_reservations"]),(5,0))
            self.assertEqual(result["group_status_counts"],{"success":13,"skipped_missing":7})
            self.assertEqual(len(list((root/"cache").glob("*/attempt.json"))),13)
            with self.assertRaises(ValueError):runner.protect_paths(root/"run",evidence.ROOT/"captures/leap_nba_v1_cache")
            with self.assertRaises(ValueError):runner.protect_paths(evidence.ROOT/"data/other",root/"cache")
            p=next((root/"cache").glob("*/group.json"));p.write_text("{}")
            with self.assertRaises((ValueError,KeyError)):runner.verify_experiment(root/"run")

    def test_budget_and_uncertain_attempt_block_before_network(self):
        plan,specs=evidence.plan_experiment()
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{"ANTHROPIC_API_KEY":"fixture"}),patch("urllib.request.OpenerDirector.open") as network:
            root=Path(tmp)
            for calls,cost in ((12,1),(20,.01),(21,1),(20,1.01),(True,1),(20,float("nan"))):
                with self.assertRaises(ValueError):runner.run_experiment(plan,specs,root/"run",root/"cache",calls,cost,True)
            folder=root/"cache"/specs[0]["key"];folder.mkdir(parents=True);(folder/"attempt.json").write_text("{}")
            with self.assertRaises(ValueError):runner.run_experiment(plan,specs,root/"run",root/"cache",allow_paid=True)
            network.assert_not_called()

    def native_run(self,root,opener):
        plan,specs=evidence.plan_experiment()
        return runner.run_experiment(plan,specs,root/"run",root/"cache",allow_paid=True,transport_factory=factory(opener),authorization_path=root/"authorization.json")

    def test_first_403_stops_and_no_alternate_output_retry(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{"ANTHROPIC_API_KEY":"fixture-never-export"}):
            root=Path(tmp);opener=Mock();opener.open.side_effect=urllib.error.HTTPError("https://api.anthropic.com/v1/messages",403,"Forbidden",{},io.BytesIO(b'{"error":{"message":"Request not allowed"}}'))
            result=self.native_run(root,opener)
            self.assertEqual(opener.open.call_count,1);self.assertEqual(result["paid_call_reservations"],1)
            self.assertEqual(result["group_status_counts"],{"failed":1,"not_attempted_access_denial":12,"skipped_missing":7})
            self.assertTrue(result["stopped_on_access_denial"]);self.assertEqual(result["successful_forecasts"],0)
            self.assertEqual(self.native_run(root,opener),result);self.assertEqual(opener.open.call_count,1)
            plan,specs=evidence.plan_experiment()
            with self.assertRaises(ValueError):runner.run_experiment(plan,specs,root/"another",root/"cache",allow_paid=True,transport_factory=factory(opener),authorization_path=root/"authorization.json")
            for p in root.rglob("*"):
                if p.is_file():self.assertNotIn(b"fixture-never-export",p.read_bytes())

    def test_insufficient_is_abstention_not_neutral_and_shared_observations(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{"ANTHROPIC_API_KEY":"fixture"}):
            root=Path(tmp);opener=Mock();opener.open.side_effect=[Response(reply(sufficiency="insufficient"))]+[Response(reply()) for _ in range(12)]
            result=self.native_run(root,opener);self.assertEqual(opener.open.call_count,13)
            self.assertEqual((result["successful_forecasts"],result["group_status_counts"]["insufficient"]),(4,1))
            run,games,_=runner.load_experiment(root/"run")
            self.assertIsNone(games[0]["groups"][0]["likelihood_ratio"])
            for key in evidence.VARIANTS:self.assertIsNone(games[0]["variants"][key]["home_win_probability"])
            self.assertEqual(runner.verify_experiment(root/"run"),result)
            summary=compare.export_run(root/"run",root/"public")
            self.assertEqual(summary["coverage"]["paired_games"],4)
            self.assertEqual({s["n"] for s in summary["paired"]["scores"].values()},{4})
            self.assertEqual(len(summary["exclusions"]),1)
            self.assertEqual(compare.replay(root/"public"),summary)

    def test_provider_and_malformed_failures_are_terminal_without_retry(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{"ANTHROPIC_API_KEY":"fixture"}):
            root=Path(tmp);opener=Mock()
            bad=reply();bad["content"][0]["text"]='{"favored_side":"neither","strength":"strong","evidence_sufficiency":"adequate"}'
            opener.open.side_effect=[urllib.error.URLError("fixture offline failure"),Response(bad)]+[Response(reply()) for _ in range(11)]
            result=self.native_run(root,opener)
            self.assertEqual(opener.open.call_count,13);self.assertEqual(result["group_status_counts"]["failed"],2)
            self.assertEqual(result["successful_forecasts"],4)
            self.assertEqual(self.native_run(root,opener),result);self.assertEqual(opener.open.call_count,13)


class ComparisonTests(unittest.TestCase):
    def test_saved_paid_pilot_public_replay_without_private_captures(self):
        original_open=Path.open
        def guarded(p,*args,**kwargs):
            if evidence.ROOT/"captures" in p.resolve().parents or p.name==".env":raise AssertionError("Public replay opened private captures/credential")
            return original_open(p,*args,**kwargs)
        with patch.object(Path,"open",guarded),patch("urllib.request.OpenerDirector.open",side_effect=AssertionError("Replay is offline")):
            summary=compare.replay(evidence.ROOT/"reports/leap_nba_v2_pilot")
        self.assertEqual(summary["coverage"]["paired_games"],5)
        self.assertEqual({s["n"] for s in summary["paired"]["scores"].values()},{5})
        self.assertEqual(summary["resources"]["new_direct_or_v1_calls"],0)
        self.assertEqual(summary["resources"]["v2_saved_observations"]["reported_usage"],{"input_tokens":14286,"output_tokens":286})

    def test_paired_evaluation_missing_coverage_and_empty_intersection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);plan,specs=evidence.plan_experiment(mock=True);runner.run_experiment(plan,specs,root/"run",root/"cache")
            _,games,_=runner.load_experiment(root/"run");baseline=json.loads((compare.BASELINE/"per_game.json").read_text())
            rows,summary=compare.compare_rows(games,baseline)
            self.assertEqual(summary["coverage"]["paired_games"],5)
            self.assertEqual(summary["paired"]["scores"]["leap_v2_raw"]["brier_score"],.25)
            baseline[0]["kalshi"]=None
            rows,summary=compare.compare_rows(games,baseline)
            self.assertEqual({s["n"] for s in summary["paired"]["scores"].values()},{4})
            for g in games:
                for v in g["variants"].values():v["home_win_probability"]=None
            rows,summary=compare.compare_rows(games,baseline)
            self.assertEqual(summary["coverage"]["paired_games"],0)
            self.assertTrue(all(s["brier_score"] is None for s in summary["paired"]["scores"].values()))
            self.assertTrue(all(not r["paired_score_differences"] for r in rows))
            baseline[0]["evidence_sha256"]="bad"
            with self.assertRaises(ValueError):compare.compare_rows(games,baseline)

    def test_public_replay_and_preservation(self):
        split_sha=digest(DEFAULT_SPLIT.read_bytes());pilot=json.loads((evidence.ASSETS/"pilot.json").read_text())
        before={gid:canonical(load_evidence(DEFAULT_DATA,gid)) for gid in evidence.PILOT}
        with tempfile.TemporaryDirectory() as tmp,patch("urllib.request.OpenerDirector.open",side_effect=AssertionError("Offline")):
            root=Path(tmp);plan,specs=evidence.plan_experiment(mock=True);runner.run_experiment(plan,specs,root/"run",root/"cache")
            with self.assertRaises(ValueError):compare.export_run(root/"run",root/"public")
            summary=compare.export_run(root/"run",root/"public",allow_mock=True)
            self.assertEqual(compare.replay(root/"public"),summary)
            path=root/"public/diagnostics.json";path.write_text("{}")
            with self.assertRaises(ValueError):compare.replay(root/"public")
        self.assertEqual(digest(DEFAULT_SPLIT.read_bytes()),split_sha)
        self.assertEqual(before,{gid:canonical(load_evidence(DEFAULT_DATA,gid)) for gid in evidence.PILOT})
        self.assertEqual(pilot["split_file_sha256"],split_sha)


if __name__=="__main__":unittest.main()
