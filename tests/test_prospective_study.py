import copy
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import prospective_study as study
import prospective_evaluate as evaluation
from evidence_documents import canonical, digest
from investigate_kalshi import iso, timestamp
from prospective_research import Budget, research
from prospective_sources import NBA_SCHEDULES, SPORT, SourceSession, event_projection, url
from research_providers import CapturedHTTP
from test_leap_forecast import Response
import test_prospective_pipeline as fixtures


def seed(root):
    study.offline_mock(root / "mock")
    original = root / "mock/evidence"
    packet = study.direct.load_evidence(original, "offline-prospective-fixture")
    lineage = json.loads((original / "lineage.json").read_text())
    run = json.loads((original / "run.json").read_text())
    return packet, lineage, run


def live_fixture(root):
    p, line, r = seed(root); r["mode"] = "prospective_live"
    study.collection.save_completed(root / "evidence", {k: v for k, v in p.items() if k != "evidence_snapshot_sha256"}, line, r, {"fixture": True})
    return p, line, r


class ProspectiveStudyTests(unittest.TestCase):
    def test_timing_timezone_dst_and_reschedule(self):
        game = event_projection(fixtures.event(start="2026-11-02T00:00:00Z"))
        t = timestamp(game["recorded_start_utc"]) - 86400
        for delta, expected in ((0, "exact"), (-300, "early_within_tolerance"), (300, "late_within_tolerance"),
                (-300.001, "early_outside_tolerance"), (300.001, "late_outside_tolerance")):
            self.assertEqual(study.timing(game, t + delta)["status"], expected)
        self.assertEqual(study.timing(game, t)["target_cutoff_utc"], "2026-11-01T00:00:00Z")
        g = dict(game, recorded_start_utc="2026-11-01T19:00:00-05:00")
        self.assertEqual(study.timing(g, t)["target_cutoff_utc"], "2026-11-01T00:00:00Z")
        with self.assertRaises(ValueError): study.timing(dict(game, recorded_start_utc="2026-11-02T00:00:00"), t)
        self.assertFalse(study.same_schedule(game, dict(game, recorded_start_utc=iso(t + 86460))))
        self.assertIsNone(study.select_game([dict(game, scheduled=False)], t, eligible_only=True))
        self.assertIsNone(study.select_game([game], t + 301, eligible_only=True))
        self.assertEqual(study.select_game([game], t, eligible_only=True), game)

    def test_mock_all_methods_same_packet_immutable_and_public_replay(self):
        original = Path.open
        def guarded(p, *a, **kw):
            if p.name == "evaluation.csv" or "heldout_150" in p.parts or p.name == ".env": raise AssertionError("Evaluation/credential leakage")
            return original(p, *a, **kw)
        with tempfile.TemporaryDirectory() as tmp, patch.object(Path, "open", guarded), \
                patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("No network")):
            root = Path(tmp); a = study.offline_mock(root)
            self.assertEqual(set(a["completion"]["successful_methods"]), set(study.ORDER))
            self.assertEqual({r["evidence_sha256"] for r in a["records"].values()}, {a["packet_sha256"]})
            self.assertTrue(a["completion"]["before_tipoff"])
            self.assertFalse(a["run"]["eligibility"]["eligible"])
            saved = {p: digest(p.read_bytes()) for p in root.rglob("*") if p.is_file()}
            self.assertEqual(study.offline_mock(root), a)
            self.assertEqual(saved, {p: digest(p.read_bytes()) for p in saved})
            public = root / "public"; study.public_audit(root, public)
            self.assertEqual(study.replay_public(public)["packet"]["evidence_snapshot_sha256"], a["packet_sha256"])
            self.assertNotIn("cache_directories", json.loads((public / "audit.json").read_text())["forecast_run"])
            self.assertEqual(a["records"]["v2"]["groups"][2]["status"], "skipped_missing")
            self.assertEqual(a["records"]["v1"]["variants"]["leap_raw"]["home_win_probability"], .5)
            (public / "audit.json").write_text("{}")
            with self.assertRaises(ValueError): study.replay_public(public)

    def test_source_cap_omissions_zero_games_and_off_time_block_inference(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); packet, line, run = seed(root); game = run["game"]; t = timestamp(packet["cutoff_utc"])
            history = copy.deepcopy(line["source_history"]); history["history"][0]["available_by_utc"] = iso(t + 1)
            p, l = study.strict_packet(game, history, line["official_collection"], packet["injury_news"]["news"], t, t + 2, t + 3, [])
            self.assertNotIn("regular_season_record", p["home"]); self.assertFalse(l["evidence_complete"])
            self.assertEqual(l["source_information_cutoff_utc"], iso(t))
            zero = dict(history, history=[])
            zp, zl = study.strict_packet(game, zero, line["official_collection"], packet["injury_news"]["news"], t - 2, t, t + 1, [])
            self.assertEqual(zp["home"]["regular_season_record"]["games_completed"], 0); self.assertTrue(zl["evidence_complete"])
            p, l = study.strict_packet(game, line["source_history"], line["official_collection"], packet["injury_news"]["news"], t - 2, t + 301, t + 302, [])
            l.update(public_sources=[], source_history=line["source_history"], official_collection=line["official_collection"], news=line["news"])
            r = dict(run, mode="prospective_live", clocks={"started": t-2, "snapshot": t+301, "created": t+302})
            study.collection.save_completed(root / "late", p, l, r, {})
            budget = study.PilotBudget(root / "run", clock=lambda: t + 303, stop_path=root / "stop.json")
            with self.assertRaises(ValueError): study.forecast_bundle(root / "late", root / "forecasts", budget, clock=lambda: t + 303)
            self.assertEqual(budget.entries(), [])

    def test_budget_includes_research_forecasts_and_article_attempts(self):
        with tempfile.TemporaryDirectory() as tmp:
            b = study.PilotBudget(tmp, clock=lambda: 1, stop_path=Path(tmp) / "deny.json")
            b.reserve("search1", "brave", .01); b.reserve("extract", "anthropic", .35)
            b.reserve("direct", "anthropic", .63)
            with self.assertRaises(study.Halt): b.reserve("v2", "anthropic", .02)
            self.assertEqual(len(b.entries()), 3)
        for kind, cap in (("anthropic", 20), ("brave", 2), ("article", 4)):
            with tempfile.TemporaryDirectory() as tmp:
                b = study.PilotBudget(tmp, stop_path=Path(tmp) / "stop.json")
                for i in range(cap): b.reserve(str(i), kind, 0)
                with self.assertRaises(study.Halt): b.reserve("over", kind, 0)

    def test_public_403_one_attempt_no_fallback_or_paid_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); b = study.PilotBudget(root, stop_path=root / "deny.json")
            opener = Mock(); opener.open.side_effect = urllib.error.HTTPError(NBA_SCHEDULES[0], 403, "Forbidden", {}, io.BytesIO(b"Forbidden"))
            session = study.StudySession(root / "raw", b, opener=opener)
            with self.assertRaises(study.Halt): study.discover(session, fixtures.T, 3)
            self.assertEqual(opener.open.call_count, 1); self.assertEqual(b.entries(), [])
            self.assertTrue((root / "deny.json").exists())
            self.assertEqual(json.loads(next((root / "raw").glob("*.json")).read_text())["http_status"], 403)

    def test_forecast_first_403_seals_partial_no_retries(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"ANTHROPIC_API_KEY": "fixture-secret"}):
            root = Path(tmp); p, _, r = live_fixture(root); now = timestamp(p["cutoff_utc"]) + 2
            b = study.PilotBudget(root, clock=lambda: now, stop_path=root / "stop.json"); caches = {n: root / "cache" / n for n in study.ORDER}
            opener = Mock(); opener.open.side_effect = [Response({"role": "assistant", "model": "claude-haiku-4-5-20251001", "stop_reason": "end_turn",
                "usage": {"input_tokens": 100, "output_tokens": 15}, "content": [{"type": "text", "text": '{"home_win_probability":0.6}'}]}),
                urllib.error.HTTPError("https://api.anthropic.com/v1/messages", 403, "Forbidden", {}, io.BytesIO(b'{"error":{"type":"permission_error"}}'))]
            factory = lambda folder, allow_network=False: CapturedHTTP(folder, allow_network, opener, clock=lambda: now)
            done = study.forecast_bundle(root / "evidence", root / "forecasts", b, caches=caches, clock=lambda: now, transport_factory=factory)
            self.assertEqual(opener.open.call_count, 2); self.assertEqual(done["stop_reason"], "access_denial")
            self.assertEqual(done["successful_methods"], ["direct"])
            v = study.verify_forecasts(root / "evidence", root / "forecasts")
            self.assertIsNone(v["records"]["v2"]["variants"]["leap_v2_raw"]["home_win_probability"])
            self.assertEqual(v["records"]["v2"]["groups"][2]["status"], "skipped_missing")
            self.assertEqual(study.forecast_bundle(root / "evidence", root / "forecasts", b, caches=caches, clock=lambda: now), done)
            self.assertEqual(opener.open.call_count, 2)

    def test_uncertain_interrupted_request_is_never_resent(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"ANTHROPIC_API_KEY": "fixture"}):
            root = Path(tmp); p, _, _ = live_fixture(root); now = timestamp(p["cutoff_utc"]) + 2
            budget = study.PilotBudget(root, clock=lambda: now, stop_path=root / "stop.json"); opener = Mock(); opener.open.side_effect = KeyboardInterrupt()
            caches = {n: root / "cache" / n for n in study.ORDER}
            factory = lambda f, allow_network=False: CapturedHTTP(f, allow_network, opener, clock=lambda: now)
            done = study.forecast_bundle(root / "evidence", root / "forecasts", budget, caches=caches, clock=lambda: now, transport_factory=factory)
            self.assertEqual(done["stop_reason"], "interrupted"); self.assertEqual(opener.open.call_count, 1)
            v = study.verify_forecasts(root / "evidence", root / "forecasts")
            self.assertTrue(v["records"]["direct"]["uncertain_attempt"])
            self.assertGreater(v["records"]["direct"]["estimated_cost_usd"], 0)

    def test_existing_collection_to_all_frozen_methods_with_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); folder = root / "evidence"; original_event = fixtures.event
            def event(*a, **kw):
                if not a and not kw: return original_event(start=iso(fixtures.T + 86520))
                return original_event(*a, **kw)
            with patch.object(fixtures, "event", event): fixtures.fixture(folder)
            game = event_projection(event()); session = SourceSession(folder / "raw", True)
            class Provider:
                http = type("HTTP", (), {"calls": []})(); usage = []
                def search(self, query, cutoff): return [{"url": fixtures.PAGE}]
                def extract(self, context, max_output_tokens):
                    self.context = context
                    ref = context["sources"][0]["snippets"][0]["source_ref"]
                    return [{"category": "injury_update", "team": "Atlanta Hawks", "player": "Example Player", "claim": fixtures.CLAIM, "source_ref": ref}]
            provider = Provider(); cfg = json.loads(study.CONFIG.read_text()); b = study.PilotBudget(root, clock=lambda: fixtures.T + 20, stop_path=root / "stop.json")
            with patch("prospective_sources.parse_pdf", side_effect=fixtures.parsed_fixture), patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("Offline fixture")):
                packet = study.collect_game(folder, cfg, game, {}, session, b, clock=lambda: fixtures.T + 20, provider=provider)
            self.assertEqual(packet["injury_news"]["official_injury"]["away"]["state"], "not_yet_submitted")
            self.assertEqual(len(packet["injury_news"]["news"]["findings"]), 1, json.dumps(json.loads((folder/"lineage.json").read_text())["news"]))
            self.assertNotIn("Kalshi", json.dumps(provider.context)); self.assertNotIn("110-100", json.dumps(provider.context))
            done = study.forecast_bundle(folder, root / "forecasts", b, mock=True, caches={n: root / "cache" / n for n in study.ORDER}, clock=lambda: fixtures.T + 21)
            self.assertEqual(set(done["successful_methods"]), set(study.ORDER))
            self.assertEqual(study.verify_forecasts(folder, root / "forecasts")["packet_sha256"], packet["evidence_snapshot_sha256"])
            # An extraction error must not silently become valid missing news.
            failed_folder=root/"failed_collection"
            with patch.object(fixtures,"event",event):fixtures.fixture(failed_folder)
            class BadProvider(Provider):
                def extract(self,context,max_output_tokens):raise ValueError("Malformed extraction fixture")
            with patch("prospective_sources.parse_pdf",side_effect=fixtures.parsed_fixture),patch("urllib.request.OpenerDirector.open",side_effect=AssertionError("Offline")):
                bad=study.collect_game(failed_folder,cfg,game,{},SourceSession(failed_folder/"raw",True),b,
                    clock=lambda:fixtures.T+20,provider=BadProvider())
            self.assertEqual(bad["injury_news"]["news"]["state"],"collection_failed")
            with self.assertRaises(ValueError):study.forecast_bundle(failed_folder,root/"no_forecasts",b,clock=lambda:fixtures.T+21)

    def test_future_and_late_news_never_reach_extraction(self):
        g = event_projection(fixtures.event(start=iso(fixtures.T + 86400)))
        provider = Mock(); provider.search.return_value = [{"url": fixtures.PAGE}]
        meta = {"source_id": "fixture", "http_status": 200, "retrieved_at_utc": iso(fixtures.T + 1), "truncated": False}
        body = ('<meta property="article:published_time" content="'+iso(fixtures.T+1)+'"><article><p>'+fixtures.CLAIM+'</p></article>').encode()
        result = research(g, fixtures.T, provider, lambda u:(meta,body), Budget(max_queries=1,max_pages=1,max_tokens=100000,max_estimated_cost_usd=.35),
            {"query_usd":.01,"page_usd":0,"input_usd_per_million":3,"output_usd_per_million":15}, now=fixtures.T,
            live_window=True, clock=lambda: fixtures.T, dated_articles=True)
        provider.extract.assert_not_called(); self.assertEqual(result["news"]["findings"], [])

    def test_outcome_gate_reschedules_and_quote_missingness(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);p,_,r=seed(root);g=r["game"];tip=timestamp(g["recorded_start_utc"])
            with patch.object(evaluation,"verify_source_capture",side_effect=AssertionError("No outcome before tipoff")):
                with self.assertRaises(ValueError): evaluation.score(root/"mock",root/"outcome",now=tip-1)
            summary={"header":{"id":g["game_id"],"competitions":[{"date":g["recorded_start_utc"],"status":{"type":{"completed":False}}}]}}
            with self.assertRaises(ValueError): evaluation.final_record(g,summary,tip-1)
            with self.assertRaises(ValueError): evaluation.final_record(g,summary,tip+100)
            summary["header"]["competitions"][0]["date"]=iso(tip+60)
            self.assertEqual(evaluation.final_record(g,summary,tip+100)["reason"],"rescheduled_or_schedule_unverified")
            summary["header"]["competitions"][0]["status"]["type"]["name"]="STATUS_POSTPONED"
            self.assertEqual(evaluation.final_record(g,summary,tip+100)["reason"],"postponed_or_canceled")
            event=evaluation.event_ticker(g);target=tip-86400
            ms={"milestones":[{"type":"basketball_game","related_event_tickers":[event],"start_date":g["recorded_start_utc"],"details":{"home_team_id":"fixture-home"}}]}
            market={"ticker":event+"-HOM","event_ticker":event,"custom_strike":{"basketball_team":"fixture-home"},"status":"active", "open_time":iso(target-5000),"close_time":iso(tip),"yes_bid_dollars":"0.5","yes_ask_dollars":"0.6"}
            self.assertTrue(evaluation.quote_record(g,market,ms,target-300)["eligible"])
            self.assertFalse(evaluation.quote_record(g,market,ms,target+.001)["eligible"])
            self.assertAlmostEqual(evaluation.quote_record(g,market,ms,target)["midpoint"],.55)
            self.assertFalse(evaluation.quote_record(g,dict(market,yes_bid_dollars="0.8"),ms,target)["eligible"])
            self.assertFalse(evaluation.quote_record(g,dict(market,ticker="WRONG"),ms,target)["eligible"])

    def test_final_scoring_keeps_primary_when_v1_and_market_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);v=study.offline_mock(root);g=v["run"]["game"];tip=timestamp(g["recorded_start_utc"])
            summary={"header":{"id":g["game_id"],"competitions":[{"date":g["recorded_start_utc"],"neutralSite":False,
                "status":{"type":{"completed":True,"name":"STATUS_FINAL"}}, "competitors":[
                    {"id":"1","homeAway":"home","score":"110"},{"id":"2","homeAway":"away","score":"100"}]}]},
                "plays":[{"type":{"id":"402"},"wallclock":iso(tip+7200),"homeScore":110,"awayScore":100}],
                "article":{"gameId":g["game_id"],"type":"Recap","published":iso(tip+7210),"lastModified":iso(tip+7220)},
                "meta":{"lastUpdatedAt":iso(tip+7230)}}
            final=evaluation.final_record(g,summary,tip+7300);self.assertEqual(final["outcome"],1)
            ambiguous=copy.deepcopy(summary);ambiguous["article"]["published"]="2030-01-02T02:00:00"
            with self.assertRaises(ValueError):evaluation.final_record(g,ambiguous,tip+7300)
            fake=copy.deepcopy(v);fake["run"]["mode"]="prospective_live";fake["run"]["eligibility"]["eligible"]=True
            for variant in fake["records"]["v1"]["variants"].values():variant["home_win_probability"]=None
            with patch.object(study,"verify_forecasts",return_value=fake),patch.object(evaluation,"verify_source_capture",return_value=final):
                result=evaluation.score(root,root/"result",now=tip+7400)
            self.assertTrue(result["primary_eligible"]);self.assertFalse(result["seven_method_paired_eligible"])
            self.assertEqual(result["primary_v2_minus_direct"]["brier"],0)
            self.assertIsNone(result["probabilities"]["kalshi"])

    def test_timezone_ambiguous_schedule_filtered_and_target_summary_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);b=study.PilotBudget(root,stop_path=root/"deny.json")
            session=study.StudySession(root/"raw",b)
            naive=fixtures.event(start="2026-10-21T00:00:00")
            fixtures.capture(root/"raw",url(SPORT+"/scoreboard",dates="20261021",limit=1000),{"events":[naive]})
            _,doc=session.json(url(SPORT+"/scoreboard",dates="20261021",limit=1000))
            self.assertEqual(doc["events"],[])
            session.target_id="900"
            with self.assertRaises(study.Halt):session.json(url(SPORT+"/summary",event="900"))


if __name__ == "__main__": unittest.main()
