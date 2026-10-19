"""Quote selection, coverage sensitivity, blinding and saved-data reconciliation."""

import csv
import hashlib
import json
import sys
import unittest
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path
from statistics import median

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_dataset import quote_fields, select_quote
from investigate_kalshi import timestamp

DATA = Path(__file__).resolve().parents[1] / "data/nba_2025_26"


def candle(end, bid=".4", ask=".6"):
    return {"end_period_ts": end, "yes_bid": {"close": bid}, "yes_ask": {"close": ask}}


class QuoteSelectionTests(unittest.TestCase):
    def test_future_candles_rejected_and_post_cutoff_data_cannot_change_proxy(self):
        observations = [candle(940), candle(700, ".3", ".5")]
        expected = quote_fields(observations, 1000, True, True)
        self.assertEqual(expected["preferred_quote_candle_end_lag_seconds"], 60)
        self.assertEqual(expected, quote_fields(observations + [candle(1001, ".8", ".9"),
            candle(1200), candle(1000.000001)], 1000, True, True))
        self.assertIsNone(select_quote([candle(1001)], 1000)[0])

    def test_latest_valid_quote_selected_and_order_independent(self):
        observations = [candle(700), candle(999, ".8", ".7"), candle(940, ".6", ".7"), candle(1001)]
        selected, reason = select_quote(observations, 1000)
        self.assertIsNone(reason)
        self.assertEqual(selected["end_period_ts"], 940)
        self.assertEqual(selected["midpoint"], Decimal(".65"))
        self.assertEqual(select_quote(observations[::-1], 1000), (selected, reason))

    def test_missing_invalid_crossed_and_sentinel_quotes(self):
        for bid, ask in ((None, ".6"), (".4", None), ("bad", ".6"), (".7", ".6"),
                         ("0", ".6"), (".4", "1"), ("-.1", ".6"), (".4", "1.1"),
                         ("NaN", ".6"), (".4", "Infinity")):
            with self.subTest(bid=bid, ask=ask):
                selected, reason = select_quote([candle(1000, bid, ask)], 1000)
                self.assertIsNone(selected)
                self.assertEqual(reason, "no_valid_two_sided_quote_within_lag_limit")
        for invalid in ({"end_period_ts": 1000}, {"end_period_ts": 1000, "yes_bid": "bad"},
                        candle(None), candle(float("nan")), candle(True)):
            self.assertIsNone(select_quote([invalid], 1000)[0])
        self.assertIsNotNone(select_quote([candle(1000, ".5", ".5")], 1000)[0])
        self.assertEqual(select_quote([], 1000), (None, "no_candle_at_or_before_cutoff"))

    def test_ties_identical_quotes_agree_conflicting_quotes_stay_ambiguous(self):
        same = [candle(940, ".4", ".6"), candle(940, "0.4000", "0.6000"), candle(700)]
        self.assertEqual(select_quote(same, 1000), select_quote(same[::-1], 1000))
        self.assertEqual(select_quote(same, 1000)[0]["end_period_ts"], 940)
        conflict = same + [candle(940, ".5", ".7")]
        self.assertEqual(select_quote(conflict, 1000), (None, "ambiguous_latest_valid_candle"))
        self.assertEqual(select_quote(conflict[::-1], 1000), select_quote(conflict, 1000))

    def test_lag_boundaries_are_inclusive_and_sets_nested(self):
        for limit in (60, 300, 900, 1200):
            with self.subTest(limit=limit):
                self.assertIsNotNone(select_quote([candle(2000 - limit)], 2000, limit)[0])
                self.assertIsNone(select_quote([candle(2000 - limit - .000001)], 2000, limit)[0])
        for lag in (0, 1, 60, 61, 300, 301, 900, 901, 1200, 1201):
            flags = [select_quote([candle(2000 - lag)], 2000, limit)[0] is not None for limit in (60, 300, 900, 1200)]
            self.assertLessEqual(flags[0], flags[1])
            self.assertLessEqual(flags[1], flags[2])
            self.assertLessEqual(flags[2], flags[3])
        with self.assertRaises(ValueError):
            select_quote([], 1000, -1)

    def test_earlier_diagnostic_and_actual_age_are_separate(self):
        fields = quote_fields([candle(1000, ".5", ".6"), candle(940, ".4", ".5")], 1000, True, True)
        self.assertEqual(fields["preferred_midpoint_price"], Decimal(".55"))
        self.assertEqual(fields["earlier_midpoint_price"], Decimal(".45"))
        self.assertEqual(fields["preferred_quote_candle_end_lag_seconds"], 0)
        self.assertIsNone(fields["preferred_quote_actual_age_seconds"])
        self.assertEqual(quote_fields([candle(1000)], 1000, False, True)["preferred_quote_missing_reason"],
                         "market_not_open_at_cutoff")
        self.assertIsNone(quote_fields([candle(1000)], 1000, True, False)["preferred_midpoint_price"])


class SavedQuoteDatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with (DATA / "evaluation.csv").open() as f:
            cls.rows = list(csv.DictReader(f))
        cls.candles = defaultdict(list)
        with (DATA / "candle_observations.csv").open() as f:
            for c in csv.DictReader(f):
                cls.candles[c["game_id"]].append(c)

    def test_price_only_update_preserves_selection_and_blinded_evidence(self):
        # Frozen before this price-only change; do not change features or sampling.
        expected = {
            "selection_manifest.json": "fe8171c1ef7ed831c1ca1492f37bc6120d3b822b2f690fd7221a2c8d27ad1d92",
            "evidence_packets.jsonl": "fee2f469b1ac21095df3abd1ef95f22f22cab4d253f99f72e2286ecd7b59d7f3",
            "evidence_lineage.jsonl": "af4cd1458882b7f79f7a1cc89c00f4fb2cc7af724b86b3968eeb1ac0736c5520",
        }
        for name, digest in expected.items():
            self.assertEqual(hashlib.sha256((DATA / name).read_bytes()).hexdigest(), digest)

    def test_all_200_quotes_against_independent_exported_observations(self):
        self.assertEqual(len(self.rows), 200)
        sets = {1: set(), 5: set(), 15: set(), 20: set()}
        for row in self.rows:
            cutoff = timestamp(row["cutoff_utc"])
            valid = []
            for c in self.candles[row["game_id"]]:
                if not c["yes_bid_close"] or not c["yes_ask_close"]:
                    continue
                bid, ask = Decimal(c["yes_bid_close"]), Decimal(c["yes_ask_close"])
                end = timestamp(c["end_period_utc"])
                if 0 < bid <= ask < 1 and 0 <= cutoff - end <= 1200:
                    valid.append((end, bid, ask))
            for minutes in (1, 5, 15, 20):
                expected = any(cutoff - end <= minutes * 60 for end, bid, ask in valid)
                self.assertEqual(row[f"quote_available_{minutes}m"], str(expected))
                if expected:
                    sets[minutes].add(row["game_id"])
            for prefix, candidates in (("preferred", valid), ("earlier", [v for v in valid if v[0] < cutoff])):
                if candidates:
                    end = max(v[0] for v in candidates)
                    quotes = {(bid, ask) for t, bid, ask in candidates if t == end}
                    self.assertEqual(len(quotes), 1)
                    bid, ask = quotes.pop()
                    self.assertEqual(timestamp(row[prefix + "_quote_candle_end_utc"]), end)
                    self.assertEqual(float(row[prefix + "_quote_candle_end_lag_seconds"]), cutoff - end)
                    self.assertEqual(Decimal(row[prefix + "_quote_bid"]), bid)
                    self.assertEqual(Decimal(row[prefix + "_quote_ask"]), ask)
                    self.assertEqual(Decimal(row[prefix + "_quote_spread"]), ask - bid)
                    self.assertEqual(Decimal(row[prefix + "_midpoint_price"]), (bid + ask) / 2)
                    self.assertEqual(row[prefix + "_quote_missing_reason"], "")
                else:
                    self.assertEqual(row[prefix + "_midpoint_price"], "")
                    self.assertTrue(row[prefix + "_quote_missing_reason"])
            self.assertEqual(row["preferred_quote_actual_age_seconds"], "")
            fresh = bool(row["last_trade_price"]) and float(row["last_trade_age_seconds"]) <= 900
            self.assertEqual(row["fresh_last_trade_available"], str(fresh))
            if row["midpoint_price"]:
                self.assertEqual(row["midpoint_price"], row["preferred_midpoint_price"])
        self.assertLessEqual(sets[1], sets[5])
        self.assertLessEqual(sets[5], sets[15])
        self.assertLessEqual(sets[15], sets[20])

    def test_coverage_and_comparisons_reconcile_with_all_records(self):
        summary = json.loads((DATA / "summary.json").read_text())
        with (DATA / "coverage.csv").open() as f:
            coverage = list(csv.DictReader(f))
        for group in coverage:
            part = [r for r in self.rows if r["game_date" if group["group_type"] == "date" else "month"] == group["group"]]
            for minutes in (1, 5, 15, 20):
                self.assertEqual(int(group[f"quote_coverage_{minutes}m"]),
                                 sum(r[f"quote_available_{minutes}m"] == "True" for r in part))
            self.assertEqual(int(group["preferred_midpoints"]), sum(bool(r["preferred_midpoint_price"]) for r in part))
            self.assertEqual(int(group["missing_preferred_midpoint"]), sum(not r["preferred_midpoint_price"] for r in part))
            self.assertEqual(int(group["fresh_last_trades"]), sum(r["fresh_last_trade_available"] == "True" for r in part))
            self.assertEqual(json.loads(group["preferred_quote_missing_reasons"]), dict(Counter(
                r["preferred_quote_missing_reason"] for r in part if not r["preferred_midpoint_price"])))
        for minutes in (1, 5, 15, 20):
            n = sum(r[f"quote_available_{minutes}m"] == "True" for r in self.rows)
            self.assertEqual(n, summary["quote_coverage_by_max_candle_end_lag_seconds"][str(minutes * 60)])
        self.assertEqual(summary["preferred_midpoints"], sum(bool(r["preferred_midpoint_price"]) for r in self.rows))
        self.assertEqual(summary["fresh_last_trades"], sum(r["fresh_last_trade_available"] == "True" for r in self.rows))
        with (DATA / "price_comparisons.csv").open() as f:
            comparisons = list(csv.DictReader(f))
        fields = {"preferred": "preferred_midpoint_price", "earlier": "earlier_midpoint_price", "exact": "midpoint_price"}
        for comparison in comparisons:
            part = self.rows if comparison["group_type"] == "all" else [r for r in self.rows if r["month"] == comparison["group"]]
            left, right = comparison["comparison"].split("_minus_")
            differences = []
            for row in part:
                a = row[fields[left]]
                if right == "fresh_trade":
                    b = row["last_trade_price"] if row["fresh_last_trade_available"] == "True" else ""
                else:
                    b = row[fields[right]]
                if a and b:
                    differences.append((Decimal(a) - Decimal(b)) * 100)
            self.assertEqual(len(differences), int(comparison["paired_games"]))
            if differences:
                self.assertAlmostEqual(float(comparison["mean_signed_difference_pp"]), float(sum(differences) / len(differences)))
                self.assertAlmostEqual(float(comparison["mean_absolute_difference_pp"]), float(sum(abs(d) for d in differences) / len(differences)))
                self.assertAlmostEqual(float(comparison["max_absolute_difference_pp"]), float(max(abs(d) for d in differences)))
                self.assertAlmostEqual(float(comparison["median_absolute_difference_pp"]), float(median(abs(d) for d in differences)))
        # Reconcile the human-facing monthly report, not just machine-readable totals.
        lines = (DATA / "coverage_report.md").read_text().splitlines()
        monthly = {g["group"]: g for g in coverage if g["group_type"] == "month"}
        checked = set()
        for line in lines:
            if not line.startswith("|"):
                continue
            cells = [v.strip() for v in line.strip("|").split("|")]
            if cells[0] in monthly:
                group = monthly[cells[0]]
                expected = [group["group"], group["selected_games"],
                            str(int(group["selected_games"]) - int(group["missing_midpoint"])),
                            group["quote_coverage_1m"], group["quote_coverage_5m"], group["quote_coverage_15m"], group["preferred_midpoints"],
                            group["missing_preferred_midpoint"], group["fresh_last_trades"], group["stale_last_trade"],
                            group["missing_last_trade"], group["missing_outcome"], group["recorded_start_disagreement"]]
                self.assertEqual(cells, expected)
                checked.add(cells[0])
        self.assertEqual(checked, set(monthly))


if __name__ == "__main__":
    unittest.main()
