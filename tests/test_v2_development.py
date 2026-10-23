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
import analyze_v2_development as analysis
import run_v2_development as execution
import leap_v2_forecast as v2
from evidence_documents import canonical,digest
from forecast_split import ROOT,load_split
from leap_v2_evidence import plan_experiment
from test_leap_forecast import Response,factory


def before(plan,specs,cache):
    original,fresh=execution.cache_state(specs,cache)
    return {"original_cache_keys":original,"new_request_keys":[s["key"] for s in fresh],"analysis_plan_sha256":digest(execution.PLAN_PATH.read_bytes()),
        "baseline_manifest_sha256":digest((ROOT/"reports/development_50/merged/manifest.json").read_bytes()),
        "parent_evidence_hashes":{g["game_id"]:g["evidence_sha256"] for g in plan["games"]}}


def native_fixture(root):
    plan,specs=plan_experiment(scope="full-development",authorize_development=True);cache=root/"cache"
    for s in specs[:20]:shutil.copytree(v2.DEFAULT_CACHE/s["key"],cache/s["key"])
    return plan,specs,cache,before(plan,specs,cache)


class AnalysisTests(unittest.TestCase):
    def rows(self):
        rows=[]
        for i,(p,y) in enumerate(((.1,0),(.9,1),(.5,0))):
            r={"game_id":str(i),"outcome":y,"direct":p,"kalshi":p,"constant_50":.5,"outcome_missing_reason":None,"market_missing_reason":None,"v1_status":"success","v2_status":"success","v2_failed_groups":[]}
            r["scores"]={m:{"brier":analysis.brier(r[m],y),"log_loss":analysis.log_loss(r[m],y)} for m in ("direct","kalshi","constant_50")};rows.append(r)
        return rows

    def test_secondary_metrics_thresholds_and_identical_intersections(self):
        rows=self.rows();r=analysis.evaluated(rows,["direct","kalshi","constant_50"])
        self.assertEqual(r["n"],3);s=r["scores"]["direct"]
        self.assertAlmostEqual(s["brier_score"],.09);self.assertAlmostEqual(s["mean_home_probability"],.5)
        self.assertEqual(s["extreme_count"],2);self.assertEqual(s["classification_accuracy"],2/3)
        self.assertAlmostEqual(s["mean_confidence"],2.3/3)
        rows[1]["kalshi"]=None
        r=analysis.evaluated(rows,["direct","kalshi","constant_50"])
        self.assertEqual({s["n"] for s in r["scores"].values()},{2});self.assertEqual(r["exclusions"][0]["missing_methods"],["kalshi"])
        for row in rows:row["kalshi"]=None
        r=analysis.evaluated(rows,["direct","kalshi"])
        self.assertEqual(r["n"],0);self.assertIsNone(r["scores"]["direct"]["log_loss"])

    def test_paired_bootstrap_determinism_sign_and_empty_samples(self):
        rows=self.rows();pairs=[("direct","kalshi"),("direct","constant_50")]
        a=analysis.bootstrap(rows,pairs,20261023,1000)
        self.assertEqual(a,analysis.bootstrap(rows,pairs,20261023,1000))
        self.assertEqual(a["comparisons"]["direct_minus_kalshi"],{"mean_brier_difference":0,"lower_95":0,"upper_95":0})
        reverse=analysis.bootstrap(rows,[("constant_50","direct")],20261023,1000)
        self.assertAlmostEqual(a["comparisons"]["direct_minus_constant_50"]["lower_95"],-reverse["comparisons"]["constant_50_minus_direct"]["upper_95"])
        self.assertIsNone(analysis.bootstrap([],pairs,1,10)["comparisons"]["direct_minus_kalshi"]["lower_95"])
        rows[0]["kalshi"]=None
        with self.assertRaises(ValueError):analysis.bootstrap(rows,pairs,1,10)

    def test_directionality_injury_removal_and_dependence_diagnostics(self):
        rows=json.loads((ROOT/"reports/leap_nba_v2_pilot/per_game.json").read_text())
        from direct_forecast import load_evidence
        from forecast_split import DEFAULT_DATA
        packets={r["game_id"]:load_evidence(DEFAULT_DATA,r["game_id"]) for r in rows}
        cohorts={name:analysis.evaluated(rows,methods) for name,methods in execution.analysis_plan()["comparisons"].items() if isinstance(methods,list)}
        detail=analysis.group_diagnostics(rows,packets,cohorts)
        self.assertEqual((detail["common_strength_directionality"]["n"],detail["common_strength_directionality"]["v1_favors_weaker"],detail["common_strength_directionality"]["v2_favors_weaker"]),(4,2,0))
        self.assertEqual(detail["common_strength_venue"]["same_nonzero_direction_count"],{"v1":5,"v2":4})
        self.assertEqual(len(detail["one_sided_injury_reports"]),1)
        self.assertEqual(detail["injury_strata"]["A_v2_development"]["source_usable"]["n"],3)
        self.assertEqual(detail["injury_strata"]["A_v2_development"]["source_missing"]["n"],2)
        self.assertEqual(detail["groups"]["v2"]["C_player_availability"]["usable_qualitative_categories"],{"moderate":3})
        self.assertAlmostEqual(cohorts["A_v2_development"]["leave_one_group_out"]["leap_v2_raw"]["C_player_availability"]["brier_score"],.21279142897267173)
        self.assertEqual(detail["shrinkage"]["A_v2_development"]["closer_to_half"],5)
        self.assertEqual(detail["shrinkage"]["A_v2_development"]["conservative_minus_raw"]["classification_accuracy"],0)

    def test_full_mock_export_replay_and_no_reserved_packet_reads(self):
        development=set(load_split()["run_order"]["development"])
        import direct_forecast
        original_loader=direct_forecast.load_game_snapshot
        def guarded(dataset,gid):
            self.assertIn(gid,development)
            return original_loader(dataset,gid)
        with tempfile.TemporaryDirectory() as tmp,patch("direct_forecast.load_game_snapshot",side_effect=guarded),patch("urllib.request.OpenerDirector.open",side_effect=AssertionError("Offline")):
            root=Path(tmp);plan,specs=plan_experiment(True,scope="full-development",authorize_development=True);cache=root/"cache"
            pre=before(plan,specs,cache)
            result=execution.execute(plan,specs,root/"run",cache,pre)
            self.assertEqual((result["successful_forecasts"],result["paid_call_reservations"]),(50,0))
            saved={p:digest(p.read_bytes()) for folder in (root/"run",cache) for p in folder.rglob("*") if p.is_file()}
            self.assertEqual(execution.execute(plan,specs,root/"run",cache,pre),result)
            summary=analysis.export(root/"run",root/"public",True)
            self.assertEqual(summary["comparisons"]["A_v2_development"]["n"],50)
            self.assertEqual(summary["comparisons"]["B_seven_method"]["n"],40)
            self.assertEqual(analysis.replay(root/"public"),summary)
            detail=json.loads((root/"public/diagnostics.json").read_text())
            self.assertTrue(any("not_returned" in g["sufficiency"] for g in detail["groups"]["v1"].values()))
            self.assertEqual(saved,{p:digest(p.read_bytes()) for p in saved})
            self.assertNotIn(b'\r\n',(root/"public/results.csv").read_bytes())
            obs=json.loads((root/"public/observations.json").read_text());obs["reservations"]=[{"request_sha256":"bad","cost_usd":6}]
            with self.assertRaises(ValueError):analysis.execution_audit(obs)
            (root/"public/bootstrap.json").write_text("{}")
            with self.assertRaises(ValueError):analysis.replay(root/"public")


class ExecutionTests(unittest.TestCase):
    def denied(self,code=403,body=None):
        return urllib.error.HTTPError("https://api.anthropic.com/v1/messages",code,"Denied",{},io.BytesIO(canonical(body or {"error":{"type":"forbidden","message":"Request not allowed"}})))

    def test_first_401_403_and_provider_error_denials_stop_without_retries(self):
        for response in (self.denied(401),self.denied(403),Response({"error":{"type":"permission_error","message":"Denied"}})):
            with self.subTest(response=type(response).__name__),tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{"ANTHROPIC_API_KEY":"fixture-never-export"}):
                root=Path(tmp);plan,specs,cache,pre=native_fixture(root);opener=Mock()
                if isinstance(response,Exception):opener.open.side_effect=response
                else:opener.open.return_value=response
                original={p:digest(p.read_bytes()) for p in cache.rglob("*") if p.is_file()}
                result=execution.execute(plan,specs,root/"run",cache,pre,True,factory(opener),root/"authorization.json")
                self.assertEqual(opener.open.call_count,1);self.assertEqual(result["paid_call_reservations"],1)
                self.assertEqual(result["successful_forecasts"],5);self.assertTrue(result["stopped_on_access_denial"])
                self.assertEqual(result["group_status_counts"]["not_attempted_access_denial"],113)
                self.assertEqual(execution.execute(plan,specs,root/"run",cache,pre,True,factory(opener),root/"authorization.json"),result)
                self.assertEqual(opener.open.call_count,1);self.assertEqual(original,{p:digest(p.read_bytes()) for p in original})
                with self.assertRaises(ValueError):execution.execute(plan,specs,root/"second",cache,pre,True,factory(opener),root/"authorization.json")
                if isinstance(response,Exception) and response.code==403:
                    summary=analysis.export(root/"run",root/"public")
                    self.assertEqual(summary["comparisons"]["A_v2_development"]["n"],5)
                    self.assertEqual(summary["comparisons"]["B_seven_method"]["n"],5)
                    audit=json.loads((root/"public/execution_audit.json").read_text())
                    self.assertEqual((audit["new_claimed_attempts"],audit["unattempted_new_requests"]),(1,113))
                    self.assertGreater(audit["resources"]["additional"]["unknown_usage_reserve_usd"],0)
                    self.assertEqual(analysis.replay(root/"public"),summary)
                for p in (root/"run").rglob("*"):
                    if p.is_file():self.assertNotIn(b"fixture-never-export",p.read_bytes())

    def test_interruption_seals_uncertain_claim_and_forbids_resend(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{"ANTHROPIC_API_KEY":"fixture"}):
            root=Path(tmp);plan,specs,cache,pre=native_fixture(root);opener=Mock();opener.open.side_effect=KeyboardInterrupt()
            result=execution.execute(plan,specs,root/"run",cache,pre,True,factory(opener),root/"authorization.json")
            self.assertEqual(result["successful_forecasts"],5);self.assertEqual(opener.open.call_count,1)
            self.assertEqual(result["group_status_counts"]["not_attempted_interrupted"],113)
            self.assertEqual(execution.verify(root/"run")[3]["stop_reason"]["category"],"interrupted")
            with self.assertRaises(ValueError):execution.cache_state(specs,cache)
            execution.execute(plan,specs,root/"run",cache,pre,seal_interrupted=True)
            self.assertEqual(opener.open.call_count,1)
            summary=analysis.export(root/"run",root/"public")
            self.assertEqual(summary["comparisons"]["A_v2_development"]["n"],5)
            self.assertEqual(analysis.replay(root/"public"),summary)

    def test_uncertain_original_cache_blocks_all_new_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);plan,specs,cache,pre=native_fixture(root)
            s=next(s for s in specs if s["key"] in pre["new_request_keys"]);folder=cache/s["key"];folder.mkdir();(folder/"attempt.json").write_text("{}")
            with patch("urllib.request.OpenerDirector.open",side_effect=AssertionError("No retries")):
                with self.assertRaises(ValueError):execution.execute(plan,specs,root/"run",cache,pre,True)

    def test_html_denial_page_stops_but_model_text_is_not_a_provider_denial(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{"ANTHROPIC_API_KEY":"fixture"}):
            root=Path(tmp);plan,specs,cache,pre=native_fixture(root);opener=Mock()
            opener.open.side_effect=urllib.error.HTTPError("https://api.anthropic.com/v1/messages",502,"Proxy",{},io.BytesIO(b'<html><title>Access denied</title></html>'))
            result=execution.execute(plan,specs,root/"run",cache,pre,True,factory(opener),root/"authorization.json")
            self.assertEqual(opener.open.call_count,1);self.assertTrue(result["stopped_on_access_denial"])
            r=execution.verify(root/"run")[1][5]["groups"][0]
            folder=cache/r["key"];body={"content":[{"text":"access denied"}]}
            import gzip
            # Classification fixture only; never replace an immutable capture.
            fake=root/"fake"/r["key"]/"raw";fake.mkdir(parents=True)
            (fake/"body.gz").write_bytes(gzip.compress(canonical(body)))
            r=copy.deepcopy(r);r["raw_response"].update(http_status=200,body_file="raw/body.gz")
            self.assertEqual(execution.response_category(r,root/"fake"),"invalid_response")


if __name__=="__main__":unittest.main()
