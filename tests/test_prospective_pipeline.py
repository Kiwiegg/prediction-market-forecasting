import copy
import gzip
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
from collect_prospective import (assemble, choose_game, load_for_consumer, plan, replay,
    reprocess_capture, run_components, save_completed, verify_bundle, write_json)
from evidence_documents import canonical, digest
from historical_injuries import report_url
from investigate_kalshi import timestamp, iso
from prospective_research import Budget, validate_page, research
from prospective_sources import (NBA_SCHEDULES, SPORT, SourceSession, collect_history,
    collect_official, discover, event_projection, official_at_snapshot, statistical_sections, url)
from research_providers import BraveAnthropicProvider, CapturedHTTP, ProviderError
from shared_evidence import validate_packet

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "examples/prospective_config.example.json").read_text())
T = timestamp("2026-10-20T02:40:00Z")
PAGE = "https://www.nba.com/news/test-only-injury-fixture"
CLAIM = "Atlanta Hawks player Example Player is questionable with an ankle injury."


class Response:
    status = 200
    def __init__(self, body):
        self.body = body
    def read(self, n):
        return self.body[:n]
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass


def model_response(findings=None):
    return {"role": "assistant", "stop_reason": "end_turn", "model": CONFIG["model"],
        "usage": {"input_tokens": 100, "output_tokens": 60},
        "content": [{"type": "text", "text": json.dumps({"findings": findings or []})}]}


def event(gid="900", start=None, scheduled=True):
    return {"id": gid, "date": start or iso(T + 82800), "season": {"year": 2027, "type": 2}, "timeValid": True,
        "competitions": [{"type": {"id": "1"}, "timeValid": True, "neutralSite": False,
            "status": {"type": {"name": "STATUS_SCHEDULED" if scheduled else "STATUS_FINAL", "completed": not scheduled}},
            "competitors": [{"homeAway": side, "team": {"id": tid, "displayName": name, "abbreviation": code},
                             "winner": True, "score": "999", "odds": {"Kalshi": .99}}
                for side, tid, name, code in [("home", "1", "Atlanta Hawks", "ATL"), ("away", "2", "Boston Celtics", "BOS")]]}]}


def capture(folder, value, body, status=200):
    if not isinstance(body, bytes):
        body = canonical(body)
    key = digest(value.encode())
    folder.mkdir(parents=True, exist_ok=True)
    meta = {"source_id": key, "url": value, "http_status": status, "retrieved_at_utc": iso(T + 1),
            "headers": {}, "body_sha256": digest(body), "truncated": False}
    (folder / (key + ".json")).write_bytes(canonical(meta))
    (folder / (key + ".body.gz")).write_bytes(gzip.compress(body, mtime=0))
    return meta


def fixture(folder):
    """Synthetic sources exist only in test tempdirs, never as live validation."""
    raw = folder / "raw"
    for value in NBA_SCHEDULES:
        capture(raw, value, b"forbidden", 403)
    for day in ("20261020", "20261021", "20261022"):
        capture(raw, url(SPORT + "/scoreboard", dates=day, limit=1000), {"events": [event()] if day == "20261021" else []})
    past, future = event("801", iso(T - 86400), False), event("802", iso(T + 500))
    for tid in ("1", "2"):
        capture(raw, url(SPORT + "/teams/" + tid + "/schedule", season=2027, seasontype=2),
                {"team": {"id": tid}, "events": [past, event(), future]})
    capture(raw, url(SPORT + "/summary", event="801"), {
        "header": {"id": "801", "competitions": [{"status": {"type": {"completed": True}}, "competitors": [
            {"id": "1", "homeAway": "home", "score": "110"}, {"id": "2", "homeAway": "away", "score": "100"}]}]},
        "plays": [{"type": {"id": "402"}, "wallclock": iso(T - 80000), "homeScore": 110, "awayScore": 100}],
        "article": {"gameId": "801", "type": "Recap", "published": iso(T - 79900), "lastModified": iso(T - 79800)},
        "meta": {"lastUpdatedAt": iso(T - 79700)}, "odds": {"Kalshi": .99}})
    pdf = report_url(timestamp("2026-10-20T02:30:00Z"))
    capture(raw, "https://official.nba.com/nba-injury-report-2026-27-season/", f'<a href="{pdf}">report</a>'.encode())
    capture(raw, "https://official.nba.com/nba-injury-report-2025-26-season/", b"not found", 404)
    teams = [{"team": {"id": str(i), "displayName": "Atlanta Hawks" if i == 1 else "Boston Celtics" if i == 2 else "Fixture Team " + str(i)}} for i in range(1, 31)]
    capture(raw, SPORT + "/teams", {"sports": [{"leagues": [{"teams": teams}]}]})
    capture(raw, pdf, b"%PDF-test-only-parser-fixture")
    capture(folder / "news_raw", PAGE, ('<meta property="article:published_time" content="' + iso(T - 100) + '">'
        '<article><p>' + CLAIM + '</p><p>Atlanta Hawks won 110-100; Kalshi price .99.</p></article>').encode())


def parsed_fixture(*args):
    issue = "2026-10-20T02:30:00Z"
    return {"extractor": "test-fixture-not-live-evidence", "issue_utc": issue, "creation_utc": "2026-10-20T02:30:04Z",
        "uncertainty_flags": [], "teams": [
            {"team_id": "1", "game_date": "2026-10-20", "matchup": "BOS@ATL", "state": "reported", "uncertainty_flags": [],
             "players": [{"player": "Player, Example", "status": "Questionable", "status_raw": "Questionable", "reason": "Ankle injury", "page": 1, "uncertainty_flags": []}]},
            {"team_id": "2", "game_date": "2026-10-20", "matchup": "BOS@ATL", "state": "not_yet_submitted", "uncertainty_flags": [], "players": []}]}


class RealProviderContractTests(unittest.TestCase):
    def provider(self, folder, responses, enabled=True):
        opener = Mock()
        opener.open.side_effect = [Response(canonical(r) if not isinstance(r, bytes) else r) for r in responses]
        transport = CapturedHTTP(folder, enabled, opener, clock=lambda: T + 6)
        return BraveAnthropicProvider(CONFIG, folder, enabled, enabled, transport), opener

    @patch.dict(os.environ, {"BRAVE_SEARCH_API_KEY": "test-secret-search", "ANTHROPIC_API_KEY": "test-secret-model"})
    def test_documented_requests_usage_and_no_credentials_in_captures(self):
        with tempfile.TemporaryDirectory() as tmp:
            p, opener = self.provider(tmp, [{"web": {"results": [{"url": PAGE, "description": "Kalshi prices 0.99"}]}}, model_response()])
            self.assertEqual(p.search("Atlanta Hawks injury update", T), [{"url": PAGE}])
            self.assertEqual(p.extract({"sources": []}, 1000), [])
            request = opener.open.call_args_list[0].args[0]
            self.assertEqual(request.get_header("X-subscription-token"), "test-secret-search")
            self.assertIn("/res/v1/web/search?", request.full_url)
            payload = json.loads(opener.open.call_args_list[1].args[0].data)
            self.assertEqual(payload["max_tokens"], 1000)
            self.assertNotIn("tools", payload)
            self.assertEqual(p.usage[0]["usage"]["output_tokens"], 60)
            for path in Path(tmp).glob("*.json"):
                self.assertNotIn("test-secret", path.read_text())

    @patch.dict(os.environ, {"BRAVE_SEARCH_API_KEY": "fixture", "ANTHROPIC_API_KEY": "fixture"})
    def test_malformed_truncated_usage_tools_and_provider_failures(self):
        bad = [b"bad-json", {"web": {"results": "invalid"}}, {"web": None}]
        with tempfile.TemporaryDirectory() as tmp:
            for i, result in enumerate(bad):
                p, _ = self.provider(Path(tmp) / str(i), [result])
                with self.assertRaises(ProviderError):
                    p.search("query", T)
            for i, response in enumerate([
                dict(model_response(), usage={}), dict(model_response(), usage={"input_tokens": 1, "output_tokens": 1001}),
                dict(model_response(), stop_reason="max_tokens"), dict(model_response(), content=[{"type": "tool_use"}]),
                dict(model_response(), content=[{"type": "text", "text": "not json"}]), dict(model_response(), usage=None)]):
                p, _ = self.provider(Path(tmp) / ("m" + str(i)), [response])
                with self.assertRaises(ProviderError):
                    p.extract({"sources": []}, 1000)
            http = CapturedHTTP(Path(tmp) / "failure", True, Mock(), clock=lambda: T)
            http.opener.open.side_effect = urllib.error.HTTPError("https://example.invalid", 429, "limit", {}, io.BytesIO(b"limited"))
            for _ in range(2):
                with self.assertRaises(ProviderError):
                    http.request("test", "GET", "https://example.invalid", None, {}, 10)
            http.opener.open.assert_called_once()  # cached errors never cause paid retries

    def test_opt_in_and_budget_failure_before_provider_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            p, opener = self.provider(tmp, [], enabled=False)
            with self.assertRaises(ProviderError):
                p.search("query", T)
            opener.open.assert_not_called()
            game = event_projection(event())
            result = research(game, T, p, Mock(), Budget(max_tokens=1), CONFIG["prices"], now=T, use_model=True)
            self.assertEqual(result["audit"]["usage_upper_bounds"]["queries"], 0)
            self.assertEqual(result["news"]["findings"], [])
            result = research(game, T, p, Mock(), Budget(max_estimated_cost_usd=0), CONFIG["prices"], now=T)
            self.assertEqual(result["audit"]["usage_upper_bounds"]["queries"], 0)
            opener.open.assert_not_called()

    def test_immutable_response_hash_detects_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            transport = CapturedHTTP(tmp, True, Mock(), clock=lambda: T)
            transport.opener.open.return_value = Response(b'{"ok":true}')
            transport.request("test", "GET", "https://example.invalid", None, {}, 100)
            path = next(Path(tmp).glob("*.body.gz"))
            path.write_bytes(gzip.compress(b'{"ok":false}'))
            with self.assertRaises(ProviderError):
                transport.request("test", "GET", "https://example.invalid", None, {}, 100)

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "fixture"})
    def test_whole_json_fence_recovery_rejects_prose_and_malformed_json(self):
        for enabled in (False, True):
            for wrapper, accepted in ((lambda s: '```json\n' + s + '\n```', enabled),
                                      (lambda s: 'Explanation\n```json\n' + s + '\n```', False),
                                      (lambda s: '```json\n' + s[:-1] + '\n```', False)):
                with self.subTest(enabled=enabled, accepted=accepted), tempfile.TemporaryDirectory() as tmp:
                    response = model_response()
                    response['content'][0]['text'] = wrapper(response['content'][0]['text'])
                    p, opener = self.provider(tmp, [response])
                    p.config = dict(CONFIG, extraction_format_recovery=enabled)
                    if accepted:
                        self.assertEqual(p.extract({'sources': []}, 1000), [])
                    else:
                        with self.assertRaises(ProviderError):
                            p.extract({'sources': []}, 1000)
                    opener.open.assert_called_once()

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "fixture"})
    def test_configurable_gateway_and_response_byte_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            http = CapturedHTTP(tmp, True, Mock(), clock=lambda: T)
            http.opener.open.return_value = Response(canonical({"findings": [], "usage": {"input_tokens": 10, "output_tokens": 5}}))
            config = dict(CONFIG, llm_provider="json_gateway", model_endpoint="https://gateway.invalid/extract")
            provider = BraveAnthropicProvider(config, tmp, True, True, http)
            self.assertEqual(provider.extract({"sources": []}, 100), [])
            self.assertEqual(http.calls[0]["provider"], "json_gateway")
            http.opener.open.return_value = Response(b"x" * 20)
            with self.assertRaises(ProviderError):
                http.request("test", "GET", "https://gateway.invalid/oversize", None, {}, 10)
            self.assertTrue(http.calls[-1]["truncated"])


class ProspectiveSourceTests(unittest.TestCase):
    def test_statistics_exclude_future_target_and_late_source_clocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            fixture(folder)
            session = SourceSession(folder / "raw", True)
            games, _ = discover(session, T)
            game = choose_game(games, T)
            history = collect_history(session, game, T + 2)
            self.assertEqual([h["game_id"] for h in history["history"]], ["801"])
            stats, refs = statistical_sections(game, history, T + 20)
            self.assertEqual(stats["home"]["regular_season_record"]["wins"], 1)
            self.assertEqual(stats["away"]["regular_season_record"]["losses"], 1)
            history["history"][0]["available_by_utc"] = iso(T + 21)
            self.assertNotIn("regular_season_record", statistical_sections(game, history, T + 20)[0]["home"])

    def test_official_states_capture_time_and_missing_catalog(self):
        with tempfile.TemporaryDirectory() as tmp, patch("prospective_sources.parse_pdf", side_effect=parsed_fixture):
            folder = Path(tmp)
            fixture(folder)
            session = SourceSession(folder / "raw", True)
            game = choose_game(discover(session, T)[0], T)
            collected = collect_official(session, game, T + 2, use_team_catalog=True)
            section, lineage = official_at_snapshot(game, collected, T + 20)
            self.assertEqual(section["home"]["state"], "reported")
            self.assertEqual(section["away"]["state"], "not_yet_submitted")
            self.assertEqual(section["publication_verification"], "observed_public_capture_upper_bound")
            self.assertTrue(lineage["team_mapping_source_id"])
            self.assertEqual(official_at_snapshot(game, collected, T)[0]["home"]["state"], "unavailable")
            capture(folder / "raw", SPORT + "/teams", {})
            empty = collect_official(SourceSession(folder / "raw", True), game, T + 2, use_team_catalog=True)
            self.assertEqual(official_at_snapshot(game, empty, T + 20)[0]["home"]["state"], "unavailable")

    def test_news_retrieval_and_publication_boundaries(self):
        body = ('<meta property="article:published_time" content="' + iso(T - 1) + '"><article><p>' + CLAIM + '</p></article>').encode()
        meta = {"source_id": "source", "http_status": 200, "body_sha256": digest(body), "retrieved_at_utc": iso(T + 1)}
        self.assertEqual(validate_page(PAGE, body, meta, T, True)["reason"], "retrieved_after_snapshot")
        self.assertTrue(validate_page(PAGE, body, meta, T + 1, True)["usable"])
        future = body.replace(iso(T - 1).encode(), iso(T + 2).encode())
        self.assertFalse(validate_page(PAGE, future, meta, T + 3, True)["usable"])

    def test_historical_or_completed_games_rejected_before_source_calls(self):
        game = event_projection(event(start=iso(T - 1)))
        source = Mock()
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                run_components(Path(tmp), CONFIG, source, game, T, clock=lambda: T)
            source.json.assert_not_called()
        game = event_projection(event(scheduled=False))
        with self.assertRaises(ValueError):
            choose_game([game], T)


class IntegratedProspectiveTests(unittest.TestCase):
    @patch.dict(os.environ, {"BRAVE_SEARCH_API_KEY": "fixture", "ANTHROPIC_API_KEY": "fixture"})
    def test_offline_reprocess_preserves_original_and_records_new_creation_time(self):
        with tempfile.TemporaryDirectory() as tmp, patch('prospective_sources.parse_pdf', side_effect=parsed_fixture):
            folder, output = Path(tmp) / 'original', Path(tmp) / 'derived'
            fixture(folder)
            session = SourceSession(folder / 'raw', True)
            games, decisions = discover(session, T)
            game = choose_game(games, T)
            candidate = {'category': 'injury_update', 'team': 'Atlanta Hawks', 'player': 'Example Player',
                         'claim': 'Questionable with an ankle injury.',
                         'source_ref': digest(PAGE.encode()) + ':paragraph:1'}
            response = model_response([candidate])
            response['content'][0]['text'] = '```json\n' + response['content'][0]['text'] + '\n```'
            def opened(req, **kwargs):
                return Response(canonical({'web': {'results': [{'url': PAGE}]}} if req.method == 'GET' else response))
            config = dict(CONFIG, extraction_format_recovery=False)
            transport = CapturedHTTP(folder / 'provider_captures', True, Mock(), clock=lambda: T + 6)
            transport.opener.open.side_effect = opened
            provider = BraveAnthropicProvider(config, folder / 'provider_captures', True, True, transport)
            clocks = iter([T + 2, T + 3, T + 4, T + 10, T + 20, T + 21])
            packet, lineage, run = run_components(folder, config, session, game, T, True, True,
                                                 clock=lambda: next(clocks), provider=provider)
            original = save_completed(folder, packet, lineage, run, {'started_at': T, 'games': games, 'decisions': decisions})
            before = {str(p.relative_to(folder)): p.read_bytes() for p in folder.rglob('*') if p.is_file()}
            self.assertEqual(original['injury_news']['news']['findings'], [])
            with patch('urllib.request.OpenerDirector.open', side_effect=AssertionError('No provider retry or live fetch')):
                derived = reprocess_capture(folder, output, clock=lambda: T + 40)
                self.assertEqual(replay(folder), original)
                self.assertEqual(replay(output), derived)
                self.assertEqual(load_for_consumer(output, 'direct_llm'), load_for_consumer(output, 'leap'))
            self.assertEqual(before, {str(p.relative_to(folder)): p.read_bytes() for p in folder.rglob('*') if p.is_file()})
            self.assertEqual(len(derived['injury_news']['news']['findings']), 1)
            self.assertEqual(derived['snapshot_timing']['packet_created_at_utc'], iso(T + 40))
            self.assertEqual(derived['snapshot_timing']['actual_snapshot_utc'], original['snapshot_timing']['actual_snapshot_utc'])
            derivation = json.loads((output / 'run.json').read_text())['derivation']
            self.assertEqual(derivation['network_calls'], 0)
            self.assertEqual(derivation['original_packet_sha256'], original['evidence_snapshot_sha256'])
            with self.assertRaises(ValueError):
                reprocess_capture(folder, folder / 'child', clock=lambda: T + 40)

    @patch.dict(os.environ, {"BRAVE_SEARCH_API_KEY": "fixture", "ANTHROPIC_API_KEY": "fixture"})
    def test_frozen_end_to_end_capture_consumer_identity_and_offline_reproduction(self):
        with tempfile.TemporaryDirectory() as tmp, patch("prospective_sources.parse_pdf", side_effect=parsed_fixture):
            folder = Path(tmp)
            fixture(folder)
            session = SourceSession(folder / "raw", True)
            games, decisions = discover(session, T)
            game = choose_game(games, T)
            finding = {"category": "injury_update", "team": "Atlanta Hawks", "player": "Example Player", "claim": CLAIM,
                       "source_ref": digest(PAGE.encode()) + ":paragraph:1"}
            requests = []
            def opened(req, **kwargs):
                requests.append(req)
                if req.method == "GET":
                    return Response(canonical({"web": {"results": [{"url": PAGE, "description": "Kalshi price .99; target winner"},
                        {"url": "https://nba.com/game/test/boxscore"}]}}))
                text = req.data.decode()
                self.assertNotIn("Kalshi", text)
                self.assertNotIn("110-100", text)
                self.assertNotIn("regular_season_record", text)
                self.assertNotIn("evaluation.csv", text)
                return Response(canonical(model_response([finding])))
            transport = CapturedHTTP(folder / "provider_captures", True, Mock(), clock=lambda: T + 6)
            transport.opener.open.side_effect = opened
            provider = BraveAnthropicProvider(CONFIG, folder / "provider_captures", True, True, transport)
            clock = iter([T + 2, T + 3, T + 4, T + 10, T + 20, T + 21])
            packet, lineage, run = run_components(folder, CONFIG, session, game, T, True, True, clock=lambda: next(clock), provider=provider)
            self.assertEqual(packet["snapshot_timing"]["status"], "late")
            self.assertFalse(packet["snapshot_timing"]["strict_t24h_eligible"])
            self.assertEqual(len(packet["injury_news"]["news"]["findings"]), 1)
            discovery = {"started_at": T, "games": games, "decisions": decisions}
            frozen = save_completed(folder, packet, lineage, run, discovery)
            before = {str(p): p.read_bytes() for p in folder.rglob("*") if p.is_file()}
            save_completed(folder, packet, lineage, run, discovery)
            self.assertEqual(before, {str(p): p.read_bytes() for p in folder.rglob("*") if p.is_file()})
            self.assertEqual(load_for_consumer(folder, "direct_llm"), load_for_consumer(folder, "leap"))
            with patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("No network during replay")):
                self.assertEqual(replay(folder), frozen)
            self.assertEqual(before, {str(p): p.read_bytes() for p in folder.rglob("*") if p.is_file()})
            self.assertEqual(len(requests), 3)  # two targeted searches and one extraction
            (folder / "lineage.json").write_text("{}")
            with self.assertRaises(ValueError):
                verify_bundle(folder)

    def test_timing_schema_and_no_cost_plan(self):
        game = event_projection(event())
        history = {"history": [], "complete": {"home": False, "away": False}, "decisions": []}
        injuries = {"reports": {}, "candidates": []}
        news = {"state": "not_collected", "findings": [], "missing_reason": "disabled"}
        packet, _ = assemble(game, history, injuries, news, T, T + 20, T + 21)
        validate_packet(packet)
        corrupted = copy.deepcopy(packet)
        corrupted["snapshot_timing"]["strict_t24h_eligible"] = True
        with self.assertRaises(ValueError):
            validate_packet(corrupted)
        early, _ = assemble(game, history, injuries, news, T - 7200, T - 3601, T - 3600)
        self.assertEqual(early["snapshot_timing"]["status"], "early")
        self.assertFalse(early["snapshot_timing"]["strict_t24h_eligible"])
        with patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("No cost plan must be offline")):
            preview = plan(CONFIG, game, T)
            self.assertEqual(preview["network_calls"], 0)
            self.assertEqual(len(preview["planned_queries"]), 2)
            legacy = dict(CONFIG)
            legacy.pop("dated_article_research")
            self.assertEqual(len(plan(legacy, game, T)["planned_queries"]), 8)


class SavedLiveCaptureTests(unittest.TestCase):
    def test_real_public_captures_replay_offline_with_identical_consumer_hashes(self):
        base = ROOT / "reports/prospective_validation"
        expected = {
            "one_game_public_capture": "23c9c72b48d9fe53862faaa097326b6e99d91074349fb9543e87287d385b4977",
            "one_game_public_capture_complete": "f846b19cc98077000242ebcbc01b594f3efbd6d3d3d4ffbfe2b53058d78df931"}
        with patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("Saved replay must not use network")):
            for name, key in expected.items():
                packet = replay(base / name)
                self.assertEqual(packet["evidence_snapshot_sha256"], key)
                self.assertEqual(load_for_consumer(base / name, "direct_llm"), load_for_consumer(base / name, "leap"))
                self.assertEqual(packet["snapshot_timing"]["status"], "late")
                self.assertFalse(packet["snapshot_timing"]["strict_t24h_eligible"])
                self.assertEqual(packet["injury_news"]["news"]["state"], "not_collected")
                self.assertEqual(packet["injury_news"]["news"]["findings"], [])
                if name.endswith("complete"):
                    players = [p for s in ("home", "away") for p in packet["injury_news"]["official_injury"][s]["players"]]
                    self.assertEqual(len(players), 5)
                    self.assertFalse(any(p["uncertainty_flags"] for p in players))


if __name__ == "__main__":
    unittest.main()
