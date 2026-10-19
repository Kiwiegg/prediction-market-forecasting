"""Checks for leakage, missing observations, and ambiguous trade timestamps."""

import csv
import json
import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from investigate_kalshi import midpoint, select_candle, select_trade, timestamp


class HistoricalSelectionTests(unittest.TestCase):
    def test_rejects_candle_straddling_cutoff(self):
        before = {"end_period_ts": 60}
        after = {"end_period_ts": 120}
        self.assertEqual(select_candle([after, before], 90), before)
        self.assertIsNone(select_candle([after], 90))
        self.assertEqual(select_candle([before], 60), before)

    def test_does_not_replace_missing_or_empty_book_quotes(self):
        for bid, ask in ((None, ".6"), ("0", "1"), (".7", ".6")):
            self.assertIsNone(midpoint({"yes_bid": {"close": bid}, "yes_ask": {"close": ask}}))
        self.assertIsNone(midpoint({"price": {"previous": ".5"}}))
        self.assertEqual(midpoint({"yes_bid": {"close": ".4"},
                                   "yes_ask": {"close": ".6"}}), Decimal(".5"))

    def test_last_trade_is_at_or_before_cutoff_and_not_block(self):
        def trade(second, price, **extra):
            return {"trade_id": str(second), "created_time": f"2026-01-01T00:00:{second:02d}Z",
                    "yes_price_dollars": price, **extra}
        target = timestamp("2026-01-01T00:00:30Z")
        before = trade(20, ".4")
        chosen, ambiguous = select_trade([trade(31, ".9"), before,
                                          trade(29, ".8", is_block_trade=True)], target)
        self.assertEqual(chosen, before)
        self.assertFalse(ambiguous)
        self.assertEqual(select_trade([], target), (None, False))
        self.assertEqual(select_trade([before, trade(20, ".5")], target), (None, True))


class SavedEvidenceTests(unittest.TestCase):
    def test_sample_identity_outcomes_and_temporal_integrity(self):
        folder = Path(__file__).resolve().parents[1] / "data/kalshi_nba_2025_26"
        with (folder / "markets.csv").open() as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 20)
        self.assertEqual(len({r["event_ticker"] for r in rows}), 20)
        self.assertEqual({r["ticker"] for r in rows},
                         {r["ticker"] for r in json.loads((folder / "manifest.json").read_text())})
        for r in rows:
            self.assertEqual(r["status"], "finalized")
            self.assertEqual(r["season_year"], "2026")
            self.assertEqual(r["season_type"], "2")
            self.assertEqual(r["outcome_matches_espn"], "True")
            self.assertEqual(Decimal(r["settlement_value_dollars"]), Decimal(r["yes_outcome"]))
            target = timestamp(r["analysis_target_utc"])
            self.assertEqual(timestamp(r["espn_recorded_start_utc"]) - target, 86400)
            if r["last_trade_utc"]:
                self.assertLessEqual(timestamp(r["last_trade_utc"]), target)
                self.assertAlmostEqual(float(r["last_trade_age_seconds"]),
                                       target - timestamp(r["last_trade_utc"]))
            self.assertEqual(r["point_in_time_verified_p24h"], "")
            if r["recorded_schedule_midpoint_p24h"]:
                self.assertEqual(r["schedule_sources_agree"], "True")
                self.assertEqual(timestamp(r["quote_bucket_end_utc"]), target)
                self.assertEqual(Decimal(r["recorded_schedule_midpoint_p24h"]),
                                 (Decimal(r["yes_bid"]) + Decimal(r["yes_ask"])) / 2)


if __name__ == "__main__":
    unittest.main()
