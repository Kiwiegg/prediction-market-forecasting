import copy
import io
import json
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import prospective_discovery as discovery
import prospective_study as study
from evidence_documents import canonical, digest
from prospective_sources import NBA_SCHEDULES, SPORT, SourceSession, url
from test_prospective_pipeline import T, capture, event


def nba(game):
    return {"leagueSchedule": {"gameDates": [{"games": [{"gameId": "0022600001", "gameStatus": 1,
        "gameDateTimeUTC": game["date"], "homeTeam": {"teamTricode": "ATL"}, "awayTeam": {"teamTricode": "BOS"}}]}]}}


def sources(game=None, nba_status=403, board_status=200, team_changes=None):
    game = game or event(start=study.iso(T + 86400))
    docs = {NBA_SCHEDULES[0]: (nba_status, nba(game)),
        url(SPORT + "/scoreboard", dates="20261020", limit=1000): (board_status, {"events": [game]}),
        url(SPORT + "/scoreboard", dates="20261021", limit=1000): (board_status, {"events": []}),
        url(SPORT + "/scoreboard", dates="20261022", limit=1000): (board_status, {"events": []})}
    for tid in ("1", "2"):
        doc = {"team": {"id": tid}, "events": [copy.deepcopy(game)]}
        if team_changes and tid in team_changes: team_changes[tid](doc)
        docs[url(SPORT + "/teams/" + tid + "/schedule", season=2027, seasontype=2)] = (200, doc)
    return docs


def offline(root, docs):
    for value, (status, doc) in docs.items(): capture(root, value, doc, status)
    return SourceSession(root, True)


class Response:
    headers = {}
    status = 200
    def __init__(self, body): self.body = canonical(body)
    def read(self, count): return self.body[:count]
    def __enter__(self): return self
    def __exit__(self, *a): pass


def opener(docs):
    def get(req, **kwargs):
        status, body = docs[req.full_url]
        if status != 200: raise urllib.error.HTTPError(req.full_url, status, "fixture", {}, io.BytesIO(canonical(body)))
        return Response(body)
    return Mock(open=Mock(side_effect=get))


class ProspectiveDiscoveryTests(unittest.TestCase):
    def test_nba_preferred_success_no_fallback_and_field_lineage(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = offline(Path(tmp), sources(nba_status=200))
            games, decisions = discovery.discover_verified(s, T, 1)
            self.assertEqual(len(games), 1)
            self.assertEqual(games[0]["schedule_provider"], "NBA_corroborated_ESPN")
            self.assertEqual(games[0]["nba_game_id"], "0022600001")
            self.assertFalse(decisions[0]["fallback_permitted"])
            self.assertNotIn(NBA_SCHEDULES[1], [m["url"] for m in s.records])
            accepted = decisions[-1]
            self.assertEqual(len(accepted["field_sources"]["recorded_start_utc"]), 4)
            self.assertEqual(len(accepted["field_sources"]["game_id"]), 3)
            self.assertEqual(accepted["target_cutoff_utc"], study.iso(T))
            self.assertNotIn("Kalshi", json.dumps(games))
            self.assertNotIn("999", json.dumps(games))

    def test_live_transport_nba_403_fallback_both_teams_and_no_paid_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); b = study.PilotBudget(root, stop_path=root / "deny.json"); op = opener(sources())
            s = discovery.ScheduleSession(root / "raw", b, opener=op)
            games, _ = discovery.discover_verified(s, T, 1)
            self.assertEqual(games[0]["schedule_provider"], "ESPN_fallback")
            self.assertEqual(op.open.call_count, 4)
            self.assertEqual(b.entries(), []); self.assertIsNone(b.reason)
            self.assertFalse((root / "deny.json").exists())
            sha = digest((root / "raw" / (digest(NBA_SCHEDULES[0].encode()) + ".json")).read_bytes())
            replayed, _ = discovery.discover_verified(SourceSession(root / "raw", True), T, 1)
            self.assertEqual(replayed, games)
            self.assertEqual(sha, digest((root / "raw" / (digest(NBA_SCHEDULES[0].encode()) + ".json")).read_bytes()))

    def test_unavailable_and_non_403_nba_denials(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(discovery.discover_verified(offline(Path(tmp), sources(nba_status=503, board_status=503)), T, 1)[0], [])
        for status in (401, 451):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); b = study.PilotBudget(root, stop_path=root / "deny.json"); op = opener(sources(nba_status=status))
                with self.assertRaises(study.Halt): discovery.discover_verified(discovery.ScheduleSession(root / "raw", b, opener=op), T, 1)
                self.assertEqual(op.open.call_count, 1); self.assertTrue((root / "deny.json").exists())

    def test_espn_403_stops_before_any_paid_request_and_is_immutable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); b = study.PilotBudget(root, stop_path=root / "deny.json"); op = opener(sources(board_status=403))
            with self.assertRaises(study.Halt): discovery.discover_verified(discovery.ScheduleSession(root / "raw", b, opener=op), T, 1)
            self.assertEqual(op.open.call_count, 2)
            self.assertEqual(len(list((root / "raw").glob("*.json"))), 2)
            before = (root / "deny.json").read_bytes()
            with self.assertRaises(study.Halt): b.reserve("paid", "anthropic", .01)
            self.assertEqual(b.entries(), []); self.assertEqual(before, (root / "deny.json").read_bytes())

    def test_conflicting_missing_and_canceled_team_schedules(self):
        def change(doc, kind):
            e = doc["events"][0]
            if kind == "time": e["date"] = study.iso(T + 86460)
            elif kind == "team": e["competitions"][0]["competitors"][0]["team"]["id"] = "7"
            elif kind == "id": e["id"] = "901"
            elif kind == "timezone": e["date"] = "2026-10-21T02:40:00"
            elif kind == "season": e["season"]["type"] = 3
            else: e["competitions"][0]["status"]["type"]["name"] = kind
        for kind in ("time", "team", "id", "timezone", "season", "STATUS_CANCELED", "STATUS_POSTPONED", "STATUS_RESCHEDULED", "STATUS_FINAL"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                docs = sources(team_changes={"2": lambda doc: change(doc, kind)})
                games, decisions = discovery.discover_verified(offline(Path(tmp), docs), T, 1)
                self.assertEqual(games, [])
                self.assertTrue(any(d.get("stage") == "team_corroboration" and not d["accepted"] for d in decisions))

    def test_nba_conflict_and_conflicting_scoreboards_not_silently_overridden(self):
        with tempfile.TemporaryDirectory() as tmp:
            docs = sources(nba_status=200)
            docs[NBA_SCHEDULES[0]][1]["leagueSchedule"]["gameDates"][0]["games"][0]["gameDateTimeUTC"] = study.iso(T + 86500)
            games, decisions = discovery.discover_verified(offline(Path(tmp), docs), T, 1)
            self.assertEqual(games, []); self.assertTrue(any(d.get("reason") == "NBA_ESPN_schedule_conflict" for d in decisions))
        with tempfile.TemporaryDirectory() as tmp:
            docs = sources(); g = event(start=study.iso(T + 86500))
            docs[url(SPORT + "/scoreboard", dates="20261021", limit=1000)] = (200, {"events": [g]})
            games, decisions = discovery.discover_verified(offline(Path(tmp), docs), T, 2)
            self.assertEqual(games, []); self.assertTrue(any(d.get("reason") == "conflicting_scoreboards" for d in decisions))

    def test_timezone_equivalence_and_t24h_window(self):
        g = event(start="2026-10-20T22:40:00-04:00")
        with tempfile.TemporaryDirectory() as tmp:
            games, _ = discovery.discover_verified(offline(Path(tmp), sources(g)), T, 1)
            self.assertEqual(study.timing(games[0], T)["target_cutoff_utc"], study.iso(T))
            self.assertIsNotNone(study.select_game(games, T-300, eligible_only=True))
            self.assertIsNotNone(study.select_game(games, T+300, eligible_only=True))
            self.assertIsNone(study.select_game(games, T+300.001, eligible_only=True))
        g["competitions"][0]["date"] = study.iso(T+86500)
        with self.assertRaises(ValueError): discovery.project(g)

    def test_authorized_attempt_preserves_parent_replays_and_never_forces_off_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); original = root / "old_stop.json"
            original.write_bytes(canonical({"reason": "access_denial", "http_status": 403, "url": NBA_SCHEDULES[0]})); before=original.read_bytes()
            op = opener(sources(event(start=study.iso(T + 86400 + 1000))))
            with patch.object(study, "STOP", original), \
                    patch.object(discovery, "STOP", root / "new_stop.json"), patch.object(discovery, "check_assets", return_value={}), \
                    patch.object(study, "collect_game", side_effect=AssertionError("No off-time collection")):
                result = discovery.run_attempt(root / "attempt", True, clock=lambda: T, opener=op, require_committed=False)
                self.assertEqual(result["status"], "discovery_validated_no_window", result); self.assertEqual(result["paid_requests_reserved"], 0)
                self.assertEqual(discovery.replay(root / "attempt")["games"], 1)
                self.assertEqual(discovery.export_audit(root / "attempt", root / "public")["verified_games"], 1)
                public = (root / "public/audit.json").read_text()
                self.assertNotIn('"headers"', public); self.assertNotIn('"body"', public)
                (root / "public/audit.json").write_text("{}")
                with self.assertRaises(ValueError): discovery.verify_audit(root / "public")
                self.assertEqual(original.read_bytes(), before)
                with self.assertRaises(FileExistsError): discovery.run_attempt(root / "attempt", True, clock=lambda: T, opener=op, require_committed=False)
                meta = next((root / "attempt/discovery_raw").glob("*.body.gz")); meta.write_bytes(b"tamper")
                with self.assertRaises(Exception): discovery.replay(root / "attempt")

    def test_partial_denial_audit_replays_and_new_journal_blocks_reentry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); old=root/"old_stop.json";old.write_bytes(canonical({"reason":"access_denial","http_status":403,"url":NBA_SCHEDULES[0]}))
            op=opener(sources(board_status=403))
            with patch.object(study,"STOP",old),patch.object(discovery,"STOP",root/"new_stop.json"),patch.object(discovery,"check_assets",return_value={}):
                result=discovery.run_attempt(root/"attempt",clock=lambda:T,opener=op,require_committed=False)
                self.assertEqual(result["stop_reason"],"access_denial");self.assertEqual(op.open.call_count,2)
                self.assertTrue(discovery.replay(root/"attempt")["partial_failure"])
                with self.assertRaises(ValueError):discovery.run_attempt(root/"other",clock=lambda:T,opener=op,require_committed=False)
                self.assertEqual(op.open.call_count,2)


if __name__ == "__main__": unittest.main()
