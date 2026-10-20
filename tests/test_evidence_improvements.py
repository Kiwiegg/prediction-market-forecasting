import copy
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from collect_prospective import assemble, main, new_capture_directory, save_completed, verify_bundle
from prospective_research import Budget, planned_queries, research
from research_diagnostics import summarize_research
from shared_evidence import validate_packet
from team_evidence import exact_score, team_facts
from test_dataset import DATA, history_row
from test_prospective_pipeline import CLAIM, CONFIG, PAGE, ROOT, T, event
from prospective_sources import event_projection
from evidence_documents import digest
from investigate_kalshi import iso, timestamp


def scored(gid="past", home=True, differential=10):
    row = history_row(gid=gid)
    row.update(home_points=100 + differential, away_points=100, end_game_score_matches_header=True,
               home_won=differential > 0)
    if not home:
        row.update(home_id="2", away_id="1")
    return row


class ExtendedStatisticsTests(unittest.TestCase):
    def test_margins_venue_sign_average_and_future_target_exclusion(self):
        cutoff = timestamp("2026-01-03T00:00:00Z")
        rows = [scored("one"), scored("two", home=False, differential=4)]
        facts, audit = team_facts("1", cutoff, rows, "target")
        self.assertEqual(facts["regular_season_scoring"]["per_game"], [
            {"game_id": "one", "point_differential": 10}, {"game_id": "two", "point_differential": -4}])
        self.assertEqual(facts["regular_season_scoring"]["average_point_differential"], 3)
        self.assertEqual(facts["regular_season_home_away"]["home"]["wins"], 1)
        self.assertEqual(facts["regular_season_home_away"]["away"]["losses"], 1)
        altered = rows + [scored("target"), dict(scored("future"), recorded_start_utc="2026-01-04T00:00:00Z"),
            dict(scored("ongoing"), end_utc="2026-01-04T00:00:00Z")]
        again, _ = team_facts("1", cutoff, altered, "target")
        for feature in ("regular_season_scoring", "regular_season_home_away"):
            self.assertEqual(facts[feature], again[feature])
            self.assertEqual(audit["feature_game_ids"][feature], ["one", "two"])

    def test_no_games_score_failures_and_timestamp_failures_are_distinct(self):
        cutoff = timestamp("2026-01-03T00:00:00Z")
        empty, _ = team_facts("1", cutoff, [], "target")
        self.assertEqual(empty["regular_season_home_away"]["home"]["games_completed"], 0)
        self.assertIn({"feature": "regular_season_scoring", "reason": "no_completed_games"}, empty["omitted_features"])
        for change in ({"home_points": None}, {"end_game_score_matches_header": False}, {"home_points": 110.5}, {"home_won": False}):
            facts, _ = team_facts("1", cutoff, [dict(scored(), **change)], "target")
            self.assertNotIn("regular_season_scoring", facts)
            self.assertIn({"feature": "regular_season_scoring", "reason": "unverified_final_scores"}, facts["omitted_features"])
        late = dict(scored(), available_by_utc="2026-01-03T00:00:01Z")
        facts, _ = team_facts("1", cutoff, [late], "target")
        self.assertNotIn("regular_season_home_away", facts)
        self.assertIn({"feature": "regular_season_scoring", "reason": "incomplete_timestamped_history"}, facts["omitted_features"])
        late_edit = dict(scored(), recap_modified_utc="2026-01-03T00:00:01Z")
        self.assertNotIn("regular_season_scoring", team_facts("1", cutoff, [late_edit], "target")[0])
        for bad in (True, -1, 100.5, "100.5", "-1"):
            with self.assertRaises(ValueError):
                exact_score(bad)

    def test_all_200_scoring_features_resolve_to_exact_timestamped_sources(self):
        history = {h["game_id"]: h for h in map(json.loads, (DATA / "game_history.jsonl").read_text().splitlines())}
        lineage = {a["game_id"]: a for a in map(json.loads, (DATA / "evidence_lineage.jsonl").read_text().splitlines())}
        packets = list(map(json.loads, (DATA / "evidence_packets.jsonl").read_text().splitlines()))
        for p in packets:
            validate_packet(p)
            for side in ("home", "away"):
                score = p[side].get("regular_season_scoring")
                if not score:
                    self.assertTrue(any(o["feature"] == "regular_season_scoring" for o in p[side]["omitted_features"]))
                    continue
                self.assertEqual([r["game_id"] for r in score["per_game"]], lineage[p["game_id"]][side]["feature_game_ids"]["regular_season_scoring"])
                for row in score["per_game"]:
                    h = history[row["game_id"]]
                    self.assertTrue(h["end_game_score_matches_header"])
                    self.assertNotEqual(h["game_id"], p["game_id"])
                    for clock in ("end_utc", "available_by_utc", "recap_published_utc", "recap_modified_utc", "event_updated_utc"):
                        self.assertLessEqual(timestamp(h[clock]), timestamp(p["cutoff_utc"]))
                    expected = (h["home_points"] - h["away_points"]) * (1 if h["home_id"] == p[side]["team_id"] else -1)
                    self.assertEqual(row["point_differential"], expected)
        example = next(p for p in packets if p["home"].get("regular_season_scoring"))
        for target_leak in (False, True):
            broken = copy.deepcopy(example)
            if target_leak:
                broken["home"]["regular_season_scoring"]["per_game"][0]["game_id"] = broken["game_id"]
            else:
                broken["home"]["regular_season_scoring"]["average_point_differential"] += 1
            with self.assertRaises(ValueError):
                validate_packet(broken)


class DiagnosticsAndTimingTests(unittest.TestCase):
    def test_report_counters_and_query_attribution(self):
        game = event_projection(event())
        bad = "https://www.nba.com/news/test-undated"
        excluded = "https://www.nba.com/game/test/boxscore"
        provider = Mock()
        provider.search.return_value = [{"url": u} for u in (PAGE, bad, excluded)]
        source_id = digest(PAGE.encode())
        claim = {"category": "injury_update", "team": "Atlanta Hawks", "player": "Example Player", "claim": CLAIM,
                 "source_ref": source_id + ":paragraph:1"}
        provider.extract.return_value = [claim, claim]
        def page(value):
            body = ('<article><p>' + CLAIM + '</p></article>').encode()
            if value == PAGE:
                body = ('<meta property="article:published_time" content="' + iso(T - 10) + '">').encode() + body
            return {"source_id": digest(value.encode()), "url": value, "http_status": 200,
                    "retrieved_at_utc": iso(T), "body_sha256": digest(body)}, body
        result = research(game, T, provider, page, Budget(max_queries=2), CONFIG["prices"], now=T, use_model=True, diagnostics=True)
        audit = result["audit"]
        audit["provider_requests"] = [{"method": method, "source_id": str(i), "url": "https://provider.invalid",
            "http_status": 200, "latency_seconds": .25} for i, method in enumerate(("GET", "GET", "POST"))]
        audit["actual_provider_usage"] = [{"usage": {"input_tokens": 20, "output_tokens": 10}}]
        summary = summarize_research(audit, result["news"]["findings"], CONFIG["prices"])
        self.assertEqual(summary["counters"], {"queries_attempted": 2, "queries_returned_results": 2,
            "results_discovered": 6, "unique_urls_discovered": 3, "pages_retrieved": 2,
            "pages_rejected": 1, "validated_findings": 1, "duplicate_claims": 1})
        for search in summary["searches"][:2]:
            self.assertEqual(search["validated_findings"], 1)
            self.assertEqual(search["pages_rejected"], 1)
        self.assertEqual(summary["reported_token_usage"]["input_tokens"], 20)
        self.assertEqual(len(summary["provider_latency_seconds"]["inference"]), 1)
        self.assertAlmostEqual(summary["estimated_cost_usd"]["reported_inference_usage"], .00021)
        self.assertIn("publication_time_unverifiable", summary["rejection_reasons"])
        self.assertIn("duplicate_underlying_fact", summary["rejection_reasons"])
        provider.search.side_effect = [[{"url": PAGE}], ValueError("provider failed")]
        failed = research(game, T, provider, page, Budget(max_queries=2), CONFIG["prices"], now=T, diagnostics=True)
        self.assertEqual(len(failed["audit"]["sources_and_validation"]), 1)
        self.assertEqual(failed["news"]["findings"], [])
        malformed = dict(audit, raw_search_results=[{"query": "bad", "results": None}], actual_provider_usage=[{"usage": None}])
        self.assertIsNone(summarize_research(malformed, [], CONFIG["prices"])["reported_token_usage"]["input_tokens"])

    def test_timing_tolerance_boundaries_never_relabel_late_snapshots(self):
        game = event_projection(event())
        target = timestamp(game["recorded_start_utc"]) - 86400
        history = {"history": [], "complete": {}, "decisions": []}
        injuries = {"reports": {}, "candidates": []}
        news = {"state": "not_collected", "findings": [], "missing_reason": "disabled"}
        for deviation, within in ((-300, True), (300, True), (300.000001, False), (0, True)):
            packet, _ = assemble(game, history, injuries, news, target - 1000, target + deviation, target + deviation + 1, tolerance=300)
            validate_packet(packet)
            timing = packet["snapshot_timing"]
            self.assertEqual(timing["within_timing_tolerance"], within)
            self.assertEqual(timing["strict_t24h_eligible"], deviation == 0)
            if deviation > 0:
                self.assertEqual(timing["status"], "late")
            timing["within_timing_tolerance"] = not within
            with self.assertRaises(ValueError):
                validate_packet(packet)

    def test_retry_cannot_change_any_successful_bundle_byte(self):
        source = ROOT / "reports/prospective_validation/one_game_public_capture_complete"
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "successful"
            shutil.copytree(source, folder)
            before = {str(p.relative_to(folder)): p.read_bytes() for p in folder.rglob("*") if p.is_file()}
            read = lambda name: json.loads((folder / name).read_text())
            packet = read("evidence_packet.json")
            save_completed(folder, packet, read("lineage.json"), read("run.json"), read("discovery.json"))
            packet["neutral_site"] = True
            with self.assertRaises(ValueError):
                save_completed(folder, packet, read("lineage.json"), read("run.json"), read("discovery.json"))
            with self.assertRaisesRegex(ValueError, "new --output"):
                new_capture_directory(folder)
            new_capture_directory(Path(tmp) / "retry")
            self.assertEqual(before, {str(p.relative_to(folder)): p.read_bytes() for p in folder.rglob("*") if p.is_file()})
            verify_bundle(folder)

    def test_live_test_requires_explicit_operator_flags(self):
        with patch.object(sys, "argv", ["collect_prospective.py", "--live-test"]), patch("sys.stderr"), patch("urllib.request.OpenerDirector.open") as network:
            with self.assertRaises(SystemExit):
                main()
            network.assert_not_called()


if __name__ == "__main__":
    unittest.main()
