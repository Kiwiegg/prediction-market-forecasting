import copy
import csv
import json
import sys
import unittest
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_dataset import schedule_projection, select_games
from investigate_kalshi import timestamp
from team_evidence import extract_history, make_packet, team_facts

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/nba_2025_26"


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def history_row(gid="past", start="2026-01-01T00:00:00Z", end="2026-01-01T03:00:00Z",
                available="2026-01-01T03:10:00Z", regular=True, winner=True):
    return {"game_id": gid, "recorded_start_utc": start, "end_utc": end,
            "available_by_utc": available, "home_id": "1", "away_id": "2",
            "home_won": winner, "source_id": "source-" + gid,
            "counts_in_regular_season": regular, "excluded_fixture": False}


def target_game():
    return {"game_id": "target", "recorded_start_utc": "2026-01-04T00:00:00Z",
            "home_id": "1", "away_id": "2", "home_name": "Home", "away_name": "Away",
            "neutral_site": False, "schedule_source_ids": ["schedule"]}


class LeakageTests(unittest.TestCase):
    def test_timezone_is_required_and_utc_offset_is_respected(self):
        with self.assertRaises(ValueError):
            timestamp("2026-01-01T19:00:00")
        self.assertEqual(timestamp("2026-01-01T19:00:00-05:00"), timestamp("2026-01-02T00:00:00Z"))

    def test_schedule_projection_never_reads_standings_or_winners(self):
        comp = {"date": "2025-10-23T01:30Z", "type": {"id": "1"}, "timeValid": True,
                "status": {"type": {"name": "STATUS_FINAL"}}, "competitors": [
                    {"homeAway": side, "team": {"id": str(i), "displayName": side, "abbreviation": side},
                     "winner": True, "score": "150", "records": [{"summary": "82-0"}]}
                    for i, side in enumerate(("home", "away"), 1)]}
        event = {"id": "123", "date": comp["date"], "season": {"year": 2026},
                 "seasonType": {"type": 2}, "timeValid": True, "competitions": [comp]}
        expected = schedule_projection(event)
        self.assertIsNone(expected["neutral_site"])
        comp["status"]["type"]["name"] = "STATUS_SCHEDULED"
        for t in comp["competitors"]:
            t.update(winner=False, score="0", records=[], odds={"price": ".99"})
        self.assertEqual(expected, schedule_projection(event))

    def test_extractor_requires_completion_and_publication_clocks(self):
        game = {**target_game(), "counts_in_regular_season": True}
        game["recorded_start_utc"] = "2026-01-01T00:00:00Z"
        comp = {"status": {"type": {"completed": True}}, "competitors": [
            {"id": "1", "homeAway": "home", "score": "111"},
            {"id": "2", "homeAway": "away", "score": "100"}]}
        response = {"header": {"id": "target", "competitions": [comp]},
            "plays": [{"type": {"id": "402"}, "wallclock": "2026-01-01T03:00:00Z",
                       "homeScore": 110, "awayScore": 100}],
            "article": {"gameId": "target", "type": "Recap", "published": "2026-01-01T03:10:00Z",
                        "lastModified": "2026-01-01T03:20:00Z"},
            "meta": {"lastUpdatedAt": "2026-01-01T03:00:00Z"},
            "standings": {"wins": 82}, "odds": {"price": ".99"}}
        row = extract_history(game, response, "test-source")
        self.assertEqual(row["available_by_utc"], "2026-01-01T03:20:00Z")
        self.assertTrue(row["home_won"])
        self.assertIsNone(row["home_points"])
        self.assertEqual(row["issue"], "final_scores_differ_winner_agrees")
        response["article"].pop("published")
        self.assertIsNone(extract_history(game, response, "test-source")["available_by_utc"])
        response["plays"] = []
        self.assertEqual(extract_history(game, response, "test-source")["issue"], "missing_timestamped_end_game")

    def test_excludes_target_and_future_games(self):
        game = target_game()
        history = [history_row()]
        before = make_packet(game, history)
        corrupted = history + [history_row("target"), history_row("future",
            start="2026-01-04T01:00:00Z", end="2026-01-04T04:00:00Z", available="2026-01-04T05:00:00Z")]
        self.assertEqual(before, make_packet(game, corrupted))
        game.update(home_yes_outcome=1, midpoint_price=0.99, last_trade_price=0.01,
                    home_points=150, away_points=50, market_status="finalized")
        self.assertEqual(before, make_packet(game, history))

    def test_end_clock_and_publication_clock_both_required(self):
        cutoff = timestamp("2026-01-03T00:00:00Z")
        late = history_row(available="2026-01-03T01:00:00Z")
        facts, _ = team_facts("1", cutoff, [late], "target")
        self.assertNotIn("regular_season_record", facts)
        self.assertNotIn("recent_regular_season", facts)
        self.assertNotIn("rest_at_cutoff", facts)
        late["available_by_utc"] = "2026-01-03T00:00:00Z"
        facts, _ = team_facts("1", cutoff, [late], "target")
        self.assertEqual(facts["regular_season_record"]["wins"], 1)

    def test_ongoing_game_cannot_supply_result_or_rest(self):
        cutoff = timestamp("2026-01-03T00:00:00Z")
        ongoing = history_row("ongoing", start="2026-01-02T23:00:00Z",
            end="2026-01-03T02:00:00Z", available="2026-01-03T02:10:00Z", winner=False)
        facts, audit = team_facts("1", cutoff, [history_row(), ongoing], "target")
        self.assertEqual(facts["regular_season_record"], {"games_completed": 1, "wins": 1, "losses": 0})
        self.assertNotIn("rest_at_cutoff", facts)
        self.assertNotIn("ongoing", audit["feature_game_ids"]["regular_season_record"])

    def test_cup_final_only_affects_rest_and_zero_is_not_missing(self):
        cutoff = timestamp("2026-01-03T00:00:00Z")
        cup = history_row("cup", regular=False, winner=False,
                          start="2026-01-02T00:00:00Z", end="2026-01-02T03:00:00Z",
                          available="2026-01-02T03:10:00Z")
        facts, audit = team_facts("1", cutoff, [history_row(), cup], "target")
        self.assertEqual(facts["regular_season_record"]["games_completed"], 1)
        self.assertEqual(facts["rest_at_cutoff"]["full_24h_days_since_last_completed_game"], 0)
        self.assertEqual(audit["feature_game_ids"]["rest_at_cutoff"], ["cup"])
        empty, _ = team_facts("1", cutoff, [], "target")
        self.assertEqual(empty["regular_season_record"]["wins"], 0)
        self.assertNotIn("recent_regular_season", empty)
        self.assertNotIn("rest_at_cutoff", empty)

    def test_unknown_completion_omits_aggregates_instead_of_partial_records(self):
        cutoff = timestamp("2026-01-03T00:00:00Z")
        missing = history_row("missing", end=None, available=None)
        facts, _ = team_facts("1", cutoff, [history_row(), missing], "target")
        self.assertNotIn("regular_season_record", facts)
        self.assertNotIn("recent_regular_season", facts)

    def test_selection_independent_of_labels_prices_and_availability(self):
        frame = [{"game_id": str(i), "month": "2025-11" if i < 15 else "2026-02",
                  "recorded_start_utc": str(i).zfill(3), "counts_in_regular_season": True}
                 for i in range(30)]
        chosen, quotas = select_games(frame, 12)
        altered = copy.deepcopy(frame)[::-1]
        for i, game in enumerate(altered):
            game.update(outcome=i % 2, price=0.9, market_available=False)
        again, _ = select_games(altered, 12)
        self.assertEqual([g["game_id"] for g in chosen], [g["game_id"] for g in again])
        self.assertEqual(sum(quotas.values()), 12)
        self.assertEqual(len({g["game_id"] for g in chosen}), 12)


class SavedDatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.games = read_jsonl(DATA / "schedule_frame.jsonl")
        cls.packets = read_jsonl(DATA / "evidence_packets.jsonl")
        cls.history = read_jsonl(DATA / "game_history.jsonl")
        cls.lineage = read_jsonl(DATA / "evidence_lineage.jsonl")
        cls.manifest = json.loads((DATA / "selection_manifest.json").read_text())
        with (DATA / "evaluation.csv").open() as f:
            cls.rows = list(csv.DictReader(f))

    def test_frame_and_selection_reconcile_without_dropping_missing_games(self):
        regular = [g for g in self.games if g["counts_in_regular_season"]]
        self.assertEqual(len(regular), 1230)
        counts = Counter(t for g in regular for t in (g["home_id"], g["away_id"]))
        self.assertEqual(len(counts), 30)
        self.assertEqual(set(counts.values()), {82})
        replay, quotas = select_games(self.games, 200)
        self.assertEqual(replay, self.manifest["games"])
        self.assertEqual(quotas, self.manifest["quotas"])
        self.assertEqual(len(self.rows), 200)
        ids = {g["game_id"] for g in replay}
        self.assertEqual(len(ids), 200)
        self.assertEqual(ids, {p["game_id"] for p in self.packets})
        self.assertEqual(ids, {r["game_id"] for r in self.rows})
        self.assertEqual(len({r["home_yes_ticker"] for r in self.rows}), 200)
        self.assertEqual(len({g["month"] for g in replay}), 7)

    def test_packets_allowlist_and_recomputation(self):
        root = {"schema_version", "game_id", "recorded_tipoff_utc", "cutoff_utc", "neutral_site",
                "reconstruction_status", "point_in_time_verified", "schedule_asof_cutoff_verified", "home", "away",
                "injury_news", "evidence_snapshot_sha256"}
        team = {"team_id", "team_name", "designation", "regular_season_record", "recent_regular_season",
                "rest_at_cutoff", "omitted_features"}
        for g, p, audit in zip(self.manifest["games"], self.packets, self.lineage):
            self.assertEqual(set(p), root)
            base = {k: v for k, v in p.items() if k not in ("injury_news", "evidence_snapshot_sha256")}
            self.assertEqual(make_packet(g, self.history), (base, audit))
            self.assertFalse(p["point_in_time_verified"])
            self.assertFalse(p["schedule_asof_cutoff_verified"])
            for side in ("home", "away"):
                self.assertLessEqual(set(p[side]), team)
                self.assertEqual(p[side]["designation"], side)
                for key, allowed in {
                    "regular_season_record": {"games_completed", "wins", "losses"},
                    "recent_regular_season": {"window_games", "wins", "losses", "results_oldest_to_newest"},
                    "rest_at_cutoff": {"hours_since_last_completed_game", "full_24h_days_since_last_completed_game"},
                }.items():
                    if key in p[side]:
                        self.assertEqual(set(p[side][key]), allowed)

    def test_feature_lineage_clocks_and_target_exclusion(self):
        by_id = {h["game_id"]: h for h in self.history}
        sources = {s["source_id"] for s in read_jsonl(DATA / "sources.jsonl")}
        for audit in self.lineage:
            cutoff = timestamp(audit["cutoff_utc"])
            for side in ("home", "away"):
                for feature, gids in audit[side]["feature_game_ids"].items():
                    self.assertNotIn(audit["game_id"], gids)
                    for gid in gids:
                        h = by_id[gid]
                        self.assertLessEqual(timestamp(h["end_utc"]), cutoff)
                        self.assertLessEqual(timestamp(h["available_by_utc"]), cutoff)
                        for field in ("recap_published_utc", "recap_modified_utc", "event_updated_utc"):
                            self.assertLessEqual(timestamp(h[field]), cutoff)
                        self.assertIn(h["source_id"], sources)
                        if feature != "rest_at_cutoff":
                            self.assertTrue(h["counts_in_regular_season"])

    def test_prices_outcomes_and_missingness_totals(self):
        for r in self.rows:
            cutoff = timestamp(r["cutoff_utc"])
            self.assertEqual(timestamp(r["recorded_tipoff_utc"]) - cutoff, 86400)
            if r["midpoint_price"]:
                self.assertTrue(0 < float(r["yes_bid"]) <= float(r["yes_ask"]) < 1)
                self.assertEqual(r["market_open_at_cutoff"], "True")
                self.assertEqual(timestamp(r["quote_bucket_end_utc"]), cutoff)
                self.assertAlmostEqual(float(r["midpoint_price"]), (float(r["yes_bid"]) + float(r["yes_ask"])) / 2)
            if r["last_trade_price"]:
                self.assertTrue(0 <= float(r["last_trade_price"]) <= 1)
                self.assertEqual(r["trade_query_complete"], "True")
                self.assertLessEqual(timestamp(r["last_trade_utc"]), cutoff)
                age = cutoff - timestamp(r["last_trade_utc"])
                self.assertAlmostEqual(float(r["last_trade_age_seconds"]), age, places=5)
                self.assertEqual(r["last_trade_stale"], str(age > 900))
            self.assertIn(r["home_yes_outcome"], ("", "0", "1"))
            if r["home_yes_outcome"]:
                self.assertEqual(float(r["settlement_value_dollars"]), float(r["home_yes_outcome"]))
            self.assertNotEqual(r["outcome_matches_history"], "False")
        with (DATA / "coverage.csv").open() as f:
            groups = list(csv.DictReader(f))
        for kind in ("date", "month"):
            subset = [g for g in groups if g["group_type"] == kind]
            self.assertEqual(sum(int(g["selected_games"]) for g in subset), 200)
            for col, rowcol in (("missing_outcome", "home_yes_outcome"), ("missing_midpoint", "midpoint_price"),
                                ("missing_last_trade", "last_trade_price")):
                self.assertEqual(sum(int(g[col]) for g in subset), sum(not r[rowcol] for r in self.rows))

    def test_market_lineage_resolves_and_retains_ambiguous_observations(self):
        sources = {s["source_id"] for s in read_jsonl(DATA / "sources.jsonl")}
        lineage = read_jsonl(DATA / "market_lineage.jsonl")
        by_id = {r["game_id"]: r for r in self.rows}
        self.assertEqual(len(lineage), 200)
        for audit in lineage:
            row = by_id[audit["game_id"]]
            self.assertEqual(row["home_mapping_verified"], "True")
            for key in ("market_source_ids", "milestone_source_ids", "trade_source_ids"):
                for sid in audit.get(key, []):
                    self.assertIn(sid, sources)
            if audit.get("candle_source_id"):
                self.assertIn(audit["candle_source_id"], sources)
            if "ambiguous_latest_trade_timestamp" in row["flags"]:
                self.assertEqual(row["last_trade_price"], "")
                self.assertNotIn("selected_trade_id", audit)


if __name__ == "__main__":
    unittest.main()
