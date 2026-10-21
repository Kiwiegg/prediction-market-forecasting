import copy
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"scripts"))
from analyze_development import (PLAN_PATH, diagnostics, distribution, paired_bootstrap, quantile,
    reconstruct, replay, resource_summary, strength_diagnostic)
from compare_forecasts import compare_rows, METHODS
from direct_forecast import load_evidence
from forecast_split import DEFAULT_DATA, ROOT
from evidence_documents import canonical, digest
from leap_evidence import GROUPS
from leap_forecast import PILOT, game_record

PLAN = json.loads(PLAN_PATH.read_text())
PACKET = load_evidence(DEFAULT_DATA, PILOT[0])


def diagnostic_packet(home_win=.4, away_win=.7, home_pd=-3, away_pd=5):
    p = copy.deepcopy(PACKET)
    for side, pct, pd in (("home", home_win, home_pd), ("away", away_win, away_pd)):
        p[side]["regular_season_record"] = {"wins": round(100*pct), "losses": 100-round(100*pct), "games_completed": 100}
        p[side]["regular_season_scoring"] = {"average_point_differential": pd}
    return p


def quote(gid, cutoff):
    return {"game_id": gid, "home_yes_outcome": "1", "home_mapping_verified": "True", "market_status": "finalized",
        "market_open_at_cutoff": "True", "cutoff_utc": cutoff, "preferred_midpoint_price": ".6",
        "preferred_quote_bid": ".59", "preferred_quote_ask": ".61", "preferred_quote_candle_end_utc": cutoff,
        "preferred_quote_candle_end_lag_seconds": "0"}


class DevelopmentAnalysisTests(unittest.TestCase):
    def test_quantiles_population_spread_and_empty_samples(self):
        self.assertEqual(quantile([0, 10], .25), 2.5)
        self.assertEqual(quantile([3], .99), 3)
        self.assertIsNone(quantile([], .5))
        self.assertIsNone(distribution([])["mean"])
        self.assertEqual(distribution([0, 2])["population_stddev"], 1)
        with self.assertRaises(ValueError): quantile([float("nan")], .5)

    def test_bootstrap_uses_paired_game_resamples_and_fixed_seed(self):
        rows = [{"game_id": str(i), "paired_eligible": True, "outcome": y, "direct": .5,
            "leap_raw": .6, "leap_conservative": .55, "kalshi": .5} for i, y in enumerate((0, 1))]
        first = paired_bootstrap(rows)
        self.assertEqual(first, paired_bootstrap(rows))
        self.assertEqual(first["seed"], 20261021)
        self.assertEqual(first["replicates"], 10000)
        self.assertAlmostEqual(first["comparisons"]["leap_raw_minus_direct"]["mean_brier_difference"], .01)
        self.assertAlmostEqual(first["comparisons"]["leap_raw_minus_direct"]["lower_95"], -.09)
        self.assertAlmostEqual(first["comparisons"]["leap_raw_minus_direct"]["upper_95"], .11)
        self.assertEqual(first["comparisons"]["direct_minus_kalshi"]["lower_95"], 0)
        self.assertEqual(first["comparisons"]["direct_minus_kalshi"]["upper_95"], 0)
        self.assertIsNone(paired_bootstrap([])["comparisons"]["direct_minus_kalshi"]["lower_95"])
        one = paired_bootstrap(rows[:1], replicates=20)
        self.assertEqual(one["comparisons"]["leap_raw_minus_direct"]["lower_95"], one["comparisons"]["leap_raw_minus_direct"]["upper_95"])
        with self.assertRaises(ValueError): paired_bootstrap(rows+rows[:1])
        with self.assertRaises(ValueError): paired_bootstrap([{**rows[0], "paired_eligible": False}])

    def test_directionality_strict_dominance_is_outcome_independent(self):
        p = diagnostic_packet()
        original = copy.deepcopy(p)
        d = strength_diagnostic(p, 2)
        self.assertEqual(d["weaker_team"], "home"); self.assertTrue(d["favors_weaker_team"])
        self.assertFalse(strength_diagnostic(p, .5)["favors_weaker_team"])
        self.assertFalse(strength_diagnostic(p, 1)["favors_weaker_team"])
        self.assertEqual(strength_diagnostic(diagnostic_packet(.8,.2,4,-3), .5)["weaker_team"], "away")
        self.assertTrue(strength_diagnostic(diagnostic_packet(.8,.2,4,-3), .5)["favors_weaker_team"])
        for other in (diagnostic_packet(.5,.5,-3,4), diagnostic_packet(.4,.7,5,-3)):
            self.assertEqual(strength_diagnostic(other, 2)["unassessable_reason"], "ties_or_discordant_indicators")
        self.assertIsNone(strength_diagnostic(p, None)["favors_weaker_team"])
        self.assertEqual(p, original)

    def test_directionality_missing_zero_games_and_nonfinite(self):
        for change in ("missing", "zero", "nonfinite"):
            p = diagnostic_packet()
            if change == "missing": del p["home"]["regular_season_scoring"]
            elif change == "zero": p["home"]["regular_season_record"]["games_completed"] = 0
            else: p["home"]["regular_season_scoring"]["average_point_differential"] = float("nan")
            self.assertEqual(strength_diagnostic(p, 2)["unassessable_reason"], "missing_or_zero_game_statistics")

    def test_group_missingness_separate_from_failure_and_same_paired_strata(self):
        packets, records, direct, leap, labels, cutoffs = {}, {}, [], [], {}, {}
        for i, gid in enumerate(("a", "b", "c")):
            p = diagnostic_packet(); p["game_id"] = gid; packets[gid] = p
            groups = [{"game_id": gid, "group": g, "status": "success", "usable": True,
                "likelihood_ratio": 1.5 if j == 0 else 1, "evidence_sufficiency": "adequate" if i%2 == 0 else "limited",
                "missing_reason": None, "error": None} for j,g in enumerate(GROUPS)]
            groups[3].update(status="skipped_missing", usable=False, missing_reason="not_collected")
            if i == 1: groups[2].update(status="skipped_missing", usable=False, missing_reason="unavailable")
            if i == 2: groups[2].update(status="failed", likelihood_ratio=None, error={"message": "fixture failure"})
            records[gid] = groups
            direct.append({"game_id": gid, "evidence_sha256": gid, "status": "success", "home_win_probability": .6})
            leap.append(game_record(gid, gid, groups)); cutoffs[gid] = p["cutoff_utc"]
            labels[gid] = quote(gid, p["cutoff_utc"])
        rows, _ = compare_rows(direct, leap, labels, cutoffs)
        result = diagnostics(rows, packets, records, PLAN)
        self.assertEqual(result["paired_n"], 2)
        self.assertEqual(result["injury_strata"]["usable"]["n"], 1)
        self.assertEqual(result["injury_strata"]["unavailable"]["n"], 1)
        self.assertEqual(result["groups"][GROUPS[2]]["source_missingness"], {"unavailable": 1})
        self.assertEqual(result["groups"][GROUPS[2]]["model_failure_reasons"], {"fixture failure": 1})
        self.assertEqual(result["groups"][GROUPS[3]]["likelihood_ratios_success_only"]["n"], 0)
        self.assertEqual(result["groups"][GROUPS[3]]["directions_success_only"]["neutral_lr_eq_1"], 0)
        for group in GROUPS:
            for variant in ("leap_raw", "leap_conservative"):
                self.assertEqual(result["groups"][group]["contributions"][variant]["leave_one_out_scores"]["n"], 2)
        self.assertEqual(result["groups"][GROUPS[3]]["contributions"]["leap_raw"]["omission_minus_full_scores"]["brier_score"], 0)

    def test_resource_accounting_separates_reused_and_additional(self):
        records = [{"request_sha256": key, "raw_response_sha256": "raw", "status": "success", "usage": {"input_tokens": 10,"output_tokens": 2},
            "estimated_cost_usd": .1, "latency_seconds": 1} for key in ("pilot","new")]
        records.append({"request_sha256": "missing", "raw_response_sha256": None, "status": "skipped_missing", "usage": None,
            "estimated_cost_usd": 0, "latency_seconds": None})
        r = resource_summary(records, {"new"})
        self.assertEqual(r["all_saved"]["estimated_cost_usd"], .2)
        self.assertEqual(r["additional"]["usage"]["input_tokens"], 10)
        self.assertEqual(r["reused"]["captured_requests"], 1)

    def test_reconstruction_rejects_non_development_scope_before_loading_packets(self):
        with patch("analyze_development.direct.load_evidence", side_effect=AssertionError("Packet should not be opened")):
            with self.assertRaises(ValueError): reconstruct({"direct": [{"game_id":"unapproved"}], "leap": []})

    def test_completed_development_public_replay_is_offline_and_reconciles_coverage(self):
        self.assertNotIn(b"\r", (ROOT/"reports/development_50/results.csv").read_bytes())
        with patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("No network in public replay")):
            result = replay(ROOT/"reports/development_50")
        self.assertEqual(result["games"], 50)
        self.assertEqual(result["paired_games"], 34)
        self.assertEqual({s["n"] for s in result["paired_scores"].values()}, {34})
        self.assertFalse(result["private_raw_reparse"])

    def test_report_tampering_and_inconsistent_resource_totals_rejected(self):
        import shutil
        source = ROOT/"reports/development_50"
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)/"derived"; shutil.copytree(source, target)
            resource = target/"reproduction.json"; saved = json.loads(resource.read_text())
            saved["resources"]["direct"]["additional"]["estimated_cost_usd"] += 1
            resource.write_bytes(canonical(saved)+b"\n")
            with self.assertRaises(ValueError): replay(target)
            manifest = json.loads((target/"manifest.json").read_text())
            manifest["files"]["reproduction.json"] = digest(resource.read_bytes())
            (target/"manifest.json").write_bytes(canonical(manifest)+b"\n")
            with self.assertRaisesRegex(ValueError, "reconcile"): replay(target)


if __name__ == "__main__": unittest.main()
