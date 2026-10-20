import copy
import csv
import gzip
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from evidence_documents import canonical, digest
from historical_injuries import latest_eligible, publication_decision, parse_pdf, collect_injuries
from injury_evidence import official_section
from investigate_kalshi import timestamp, iso
from prospective_research import Budget, Ledger, BudgetExceeded, validate_page, validate_findings, research, prospective_packet, replay_capture, allowed_page
from shared_evidence import freeze_packet, load_frozen_packet, load_game_snapshot, validate_packet

DATA = Path(__file__).resolve().parents[1] / "data/nba_2025_26"
T = timestamp("2026-03-14T21:10:00Z")
GAME = {"game_id": "test", "recorded_start_utc": "2026-03-15T21:10:00Z", "game_date": "2026-03-15",
        "home_id": "5", "away_id": "6", "home_name": "Cleveland Cavaliers", "away_name": "Dallas Mavericks",
        "home_code": "CLE", "away_code": "DAL", "month": "2026-03", "neutral_site": False}


def page_meta():
    return {"source_id": "source", "http_status": 200, "retrieved_at_utc": "2026-03-14T21:10:01Z",
            "body_sha256": "hash", "truncated": False}


def article(published="2026-03-14T20:00:00Z", modified=None):
    text = '<meta property="article:published_time" content="' + published + '">'
    if modified:
        text += '<meta property="article:modified_time" content="' + modified + '">'
    return (text + '<nav>Cavaliers won 110-100.</nav><article><p>Cleveland Cavaliers player Test Player is questionable with an ankle injury.</p>'
            '<p>Cavaliers won 110-100 and betting odds changed.</p></article>').encode()


class HistoricalInjuryTests(unittest.TestCase):
    def test_latest_selection_rejects_future_and_unverified_reports(self):
        before = {"report_issue_utc": "2026-03-14T20:45:00Z", "published_at_utc": "2026-03-14T20:45:08Z", "publication_supported": True}
        exact = {"report_issue_utc": "2026-03-14T21:00:00Z", "published_at_utc": "2026-03-14T21:10:00Z", "publication_supported": True}
        after = {**exact, "published_at_utc": "2026-03-14T21:10:01Z"}
        self.assertEqual(latest_eligible([after, before, exact], T), exact)
        self.assertEqual(latest_eligible([after, before, {**exact, "publication_supported": False}], T), before)
        self.assertIsNone(latest_eligible([after], T))

    def test_issue_is_not_publication_and_retrieval_is_not_publication(self):
        report = {"issue_utc": "2026-03-14T21:00:00Z", "creation_utc": "2026-03-14T21:00:04Z"}
        meta = {"http_status": 200, "headers": {"last-modified": "Sat, 14 Mar 2026 21:00:07 GMT"},
                "retrieved_at_utc": "2026-10-20T00:00:00Z"}
        self.assertFalse(publication_decision(meta, report, timestamp("2026-03-14T21:00:06Z"))[0])
        self.assertTrue(publication_decision(meta, report, timestamp("2026-03-14T21:00:07Z"))[0])
        meta["headers"] = {}
        self.assertEqual(publication_decision(meta, report, T)[2], "official_publication_timestamp_unavailable")

    def test_coordinate_mapping_wrapped_reason_and_not_submitted(self):
        def row(y, *cells):
            return y, list(cells)
        pages = [[row(533, (280, "Injury Report: 03/14/26 05:00 PM")),
            row(480, (200, "Matchup"), (264, "Team"), (424, "Player"), (585, "Current"), (666, "Reason")),
            row(467, (667, "Left knee;")),
            row(459, (24, "03/15/2026"), (201, "DAL@CLE"), (265, "Dallas Mavericks"),
                (425, "Player, Test"), (586, "Out"), (667, "Surgery recovery")),
            row(430, (265, "Cleveland Cavaliers"), (425, "NOT YET SUBMITTED"))]]
        with patch("historical_injuries.pdf_lines", return_value=(pages, "2026-03-14T21:00:04Z")):
            report = parse_pdf(b"fixture", timestamp("2026-03-14T21:00:00Z"),
                               {"6": {"Dallas Mavericks"}, "5": {"Cleveland Cavaliers"}})
        self.assertEqual(report["teams"][0]["players"][0]["reason"], "Left knee; Surgery recovery")
        self.assertEqual(report["teams"][0]["team_id"], "6")
        self.assertEqual(report["teams"][1]["state"], "not_yet_submitted")
        self.assertEqual(report["teams"][1]["players"], [])

    def test_missing_target_does_not_imply_healthy_or_available(self):
        bundle = {"cutoff_candidates": {iso(T): []}, "reports": {}}
        official, audit = official_section(GAME, bundle)
        for side in ("home", "away"):
            self.assertEqual(official[side]["state"], "unavailable")
            self.assertEqual(official[side]["players"], [])

    def test_unrecognized_status_and_team_mapping_stay_explicit(self):
        pages = [[(533, [(280, "Injury Report: 03/14/26 05:00 PM")]),
            (480, [(200, "Matchup"), (264, "Team"), (424, "Player"), (585, "Current"), (666, "Reason")]),
            (459, [(24, "03/15/2026"), (201, "DAL@CLE"), (265, "Dallas Mavericks"),
                   (425, "Player, Test"), (586, "Pending"), (667, "Ankle injury")])]]
        with patch("historical_injuries.pdf_lines", return_value=(pages, "2026-03-14T21:00:04Z")):
            report = parse_pdf(b"fixture", timestamp("2026-03-14T21:00:00Z"), {"6": {"Dallas Mavericks"}})
        self.assertEqual(report["teams"][0]["players"][0]["status"], "ambiguous")
        self.assertEqual(report["teams"][0]["players"][0]["status_raw"], "Pending")
        self.assertEqual(report["teams"][0]["team_id"], "6")

    def test_not_submitted_is_never_an_adjacent_players_reason(self):
        pages = [[(533, [(280, "Injury Report: 03/14/26 05:00 PM")]),
            (480, [(200, "Matchup"), (264, "Team"), (424, "Player"), (585, "Current"), (666, "Reason")]),
            (459, [(24, "03/15/2026"), (201, "DAL@CLE"), (265, "Dallas Mavericks"),
                   (425, "Player, Test"), (586, "Out"), (667, "Ankle injury")]),
            (445, [(265, "Cleveland Cavaliers"), (667, "NOT YET SUBMITTED")])],
            [(533, [(280, "Injury Report: 03/14/26 05:00 PM")]),
             (507, [(667, "Unresolved continuation")])]]
        with patch("historical_injuries.pdf_lines", return_value=(pages, "2026-03-14T21:00:04Z")):
            report = parse_pdf(b"fixture", timestamp("2026-03-14T21:00:00Z"),
                               {"6": {"Dallas Mavericks"}, "5": {"Cleveland Cavaliers"}})
        self.assertEqual(report["teams"][0]["players"][0]["reason"], "Ankle injury")
        self.assertEqual(report["teams"][1]["state"], "not_yet_submitted")
        self.assertEqual(report["unresolved_reason_fragments"][0]["page"], 2)

    def test_historical_path_never_invokes_search(self):
        report = {"extractor": "fixture", "issue_utc": "2026-03-14T21:00:00Z", "creation_utc": "2026-03-14T21:00:04Z", "teams": [], "uncertainty_flags": []}
        def get(url):
            return {"source_id": digest(url.encode()), "url": url, "http_status": 200,
                "headers": {"last-modified": "Sat, 14 Mar 2026 21:00:07 GMT"}, "body_sha256": "hash", "retrieved_at_utc": "2026-10-20T00:00:00Z"}, b"%PDF-fixture"
        with tempfile.TemporaryDirectory() as folder, patch("historical_injuries.DocumentStore") as store, \
                patch("historical_injuries.parse_pdf", return_value=report), \
                patch("prospective_research.JsonGatewayProvider.search", side_effect=AssertionError("Live search forbidden")) as search:
            store.return_value.get.side_effect = get
            bundle = collect_injuries(folder, [GAME], offline=True, workers=1)
            search.assert_not_called()
            self.assertTrue(bundle["cutoff_candidates"][iso(T)][0]["publication_supported"])


class ProspectiveResearchTests(unittest.TestCase):
    def test_page_publication_validation_and_filtering(self):
        source = validate_page("https://nba.com/news/injury", article(), page_meta(), T)
        self.assertTrue(source["usable"])
        self.assertEqual(len(source["snippets"]), 1)
        for pub, modified in (("2026-03-14T21:10:01Z", None), ("2026-03-14T20:00:00Z", "2026-03-15T00:00:00Z"), ("2026-03-14", None)):
            self.assertFalse(validate_page("https://nba.com/news/injury", article(pub, modified), page_meta(), T)["usable"])

    def test_agent_findings_require_verbatim_claim_and_valid_references(self):
        source = validate_page("https://nba.com/news/injury", article(), page_meta(), T)
        claim = source["snippets"][0]["excerpt"]
        candidate = {"category": "injury_update", "team": "Cleveland Cavaliers", "player": "Test Player", "claim": claim, "source_ref": "source:paragraph:1"}
        accepted, decisions = validate_findings([candidate, candidate], [source], GAME, T)
        self.assertEqual(len(accepted), 1)
        self.assertEqual(len(accepted[0]["source_references"]), 2)
        bad = [{**candidate, "source_ref": "invented"}, {**candidate, "claim": "Test Player is available."},
               {**candidate, "category": "win_probability"}, {**candidate, "team": "Unknown Team"}, {**candidate, "player": "Other Player"}]
        self.assertEqual(validate_findings(bad, [source], GAME, T)[0], [])

    def test_historical_dates_fail_before_provider_calls(self):
        provider = unittest.mock.Mock()
        with self.assertRaises(ValueError):
            research(GAME, T, provider, unittest.mock.Mock(), Budget(), {}, now=T + 100000, mode="historical")
        provider.search.assert_not_called()
        provider.extract.assert_not_called()

    def test_bounded_fake_provider_and_offline_replay_share_one_snapshot(self):
        provider = unittest.mock.Mock()
        provider.search.return_value = [{"url": "https://nba.com/news/injury", "snippet": "Kalshi prices and final scores NEVER enter model context"}]
        def extract(context, output_budget):
            self.assertEqual(set(context), {"home_team", "away_team", "cutoff_utc", "allowed_categories", "sources"})
            self.assertNotIn("Kalshi", json.dumps(context))
            self.assertNotIn("110-100", json.dumps(context))
            snippet = context["sources"][0]["snippets"][0]
            return [{"category": "injury_update", "team": GAME["home_name"], "player": "Test Player",
                     "claim": snippet["excerpt"], "source_ref": snippet["source_ref"]}]
        provider.extract.side_effect = extract
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "raw").mkdir()
            url = "https://nba.com/news/injury"
            key, body = digest(url.encode()), article()
            meta = dict(page_meta(), source_id=key, url=url, body_sha256=digest(body))
            (folder / "raw" / (key + ".json")).write_text(json.dumps(meta))
            (folder / "raw" / (key + ".body.gz")).write_bytes(gzip.compress(body, mtime=0))
            result = research(GAME, T, provider, lambda url: (meta, body), Budget(max_queries=2, max_pages=1),
                {"query_usd": .001, "page_usd": 0, "input_usd_per_million": 1, "output_usd_per_million": 1}, now=T, use_model=True)
            self.assertEqual(len(result["news"]["findings"]), 1)
            self.assertEqual(provider.search.call_count, 2)
            provider.extract.assert_called_once()
            self.assertEqual(result["audit"]["usage_upper_bounds"]["pages"], 1)
            result["audit"]["game"] = GAME
            audit = canonical(result["audit"]) + b"\n"
            audit_key = digest(audit)
            (folder / "provider_captures").mkdir()
            (folder / "provider_captures" / (audit_key + ".audit.json")).write_bytes(audit)
            expected = freeze_packet(prospective_packet(GAME, T, result["news"]), folder / "evidence_captures")
            (folder / "research_snapshot_manifest.json").write_text(json.dumps({"audit_sha256": audit_key,
                "evidence_snapshot_sha256": expected["evidence_snapshot_sha256"]}))
            with patch("prospective_research.JsonGatewayProvider", side_effect=AssertionError("No live provider during replay")):
                self.assertEqual(replay_capture(folder), expected)

    def test_deduplication_preserves_distinct_supporting_wording(self):
        first = validate_page("https://nba.com/news/injury", article(), page_meta(), T)
        second_body = article().replace(b"is questionable with an ankle injury", b"remains questionable due to an ankle injury")
        second = validate_page("https://espn.com/nba/story/injury", second_body, dict(page_meta(), source_id="second"), T)
        candidates = [{"category": "injury_update", "team": GAME["home_name"], "player": "Test Player",
                       "claim": s["snippets"][0]["excerpt"], "source_ref": s["snippets"][0]["source_ref"]} for s in (first, second)]
        findings, _ = validate_findings(candidates, [first, second], GAME, T)
        self.assertEqual(len(findings), 1)
        validate_packet(prospective_packet(GAME, T, {"state": "validated_findings", "findings": findings, "missing_reason": None}))
        negated = {**candidates[0], "claim": candidates[0]["claim"].replace("is questionable", "is not questionable")}
        negative_source = validate_page("https://nba.com/news/injury-negative", article().replace(b"is questionable", b"is not questionable"), dict(page_meta(), source_id="negative"), T)
        negated["source_ref"] = "negative:paragraph:1"
        self.assertEqual(len(validate_findings([candidates[0], negated], [first, negative_source], GAME, T)[0]), 2)
        self.assertFalse(allowed_page("https://nba.com:invalid/news"))

    def test_budget_exhaustion_is_pre_call_and_dry_run_has_no_costs(self):
        ledger = Ledger(Budget(max_tokens=10, max_estimated_cost_usd=.01))
        with self.assertRaises(BudgetExceeded):
            ledger.reserve(tokens=11)
        with self.assertRaises(BudgetExceeded):
            ledger.reserve(cost=.02)
        provider = unittest.mock.Mock()
        result = research(GAME, T, provider, unittest.mock.Mock(), Budget(max_tokens=0),
                          {"query_usd": .001}, now=T, use_model=True)
        provider.search.assert_not_called()
        self.assertEqual(result["news"]["state"], "no_usable_evidence")

    def test_frozen_packet_is_shared_and_rejects_leakage_or_tampering(self):
        news = {"state": "no_usable_evidence", "findings": [], "missing_reason": "none_found"}
        packet = prospective_packet(GAME, T, news)
        with tempfile.TemporaryDirectory() as folder:
            frozen = freeze_packet(packet, folder)
            path = Path(folder) / (frozen["evidence_snapshot_sha256"] + ".json")
            self.assertEqual(load_frozen_packet(path), frozen)
            self.assertEqual(load_frozen_packet(path), load_frozen_packet(path))
            corrupt = dict(frozen, midpoint_price=.9)
            with self.assertRaises(ValueError):
                validate_packet(corrupt)
            corrupt = copy.deepcopy(frozen)
            corrupt["injury_news"]["official_injury"]["home"]["outcome"] = "win"
            with self.assertRaises(ValueError):
                validate_packet(corrupt)
            corrupt = copy.deepcopy(frozen)
            corrupt["home"]["regular_season_record"] = {"games_completed": 1, "wins": 1, "losses": 0, "market_price": .8}
            with self.assertRaises(ValueError):
                validate_packet(corrupt)
            path.write_text(json.dumps(dict(frozen, neutral_site=True)))
            with self.assertRaises(ValueError):
                load_frozen_packet(path)


class SavedInjuryEvidenceTests(unittest.TestCase):
    def test_saved_pdf_extraction_reproduces_offline(self):
        bundle = json.loads((DATA / "injury_extractions.json").read_text())
        games = json.loads((DATA / "selection_manifest.json").read_text())["games"]
        names = {}
        for g in games:
            for side in ("home", "away"):
                names.setdefault(g[side + "_id"], set()).add(g[side + "_name"])
        for labels in names.values():
            if "LA Clippers" in labels:
                labels.add("Los Angeles Clippers")
        saved = next(r for r in bundle["reports"].values() if r.get("issue_utc") and r["teams"])
        body = gzip.decompress((DATA / "injury_raw" / (saved["source_id"] + ".body.gz")).read_bytes())
        with patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("No network during extraction")):
            parsed = parse_pdf(body, timestamp(saved["issue_utc"]), names)
        self.assertEqual(parsed, {k: saved[k] for k in parsed})

    def test_coverage_reconciles_with_all_200_packets(self):
        packets = [json.loads(l) for l in (DATA / "evidence_packets.jsonl").read_text().splitlines()]
        summary = json.loads((DATA / "injury_summary.json").read_text())
        rows = list(csv.DictReader((DATA / "injury_coverage.csv").read_text().splitlines()))
        monthly = list(csv.DictReader((DATA / "injury_coverage_by_month.csv").read_text().splitlines()))
        self.assertEqual(len(rows), 200)
        self.assertEqual({r["game_id"] for r in rows}, {p["game_id"] for p in packets})
        players = [x for p in packets for side in ("home", "away") for x in p["injury_news"]["official_injury"][side]["players"]]
        self.assertEqual(summary["player_status_records"], len(players))
        self.assertEqual(summary["uncertain_player_records"], sum(bool(p["uncertainty_flags"]) for p in players))
        self.assertEqual(summary["origin_timestamp_supported_reports"], sum(bool(p["injury_news"]["official_injury"]["report_source_id"]) for p in packets))
        self.assertEqual(sum(int(r["games"]) for r in monthly), 200)
        for m in monthly:
            part = [r for r in rows if r["month"] == m["month"]]
            self.assertEqual(int(m["games"]), len(part))
            self.assertEqual(int(m["player_status_records"]), sum(int(r["home_players"]) + int(r["away_players"]) for r in part))
        self.assertEqual(summary["independently_verified_publication"], 0)

    def test_all_200_packets_lineage_and_cutoff_clocks(self):
        packets = [json.loads(line) for line in (DATA / "evidence_packets.jsonl").read_text().splitlines()]
        lineage = {a["game_id"]: a for a in map(json.loads, (DATA / "injury_lineage.jsonl").read_text().splitlines())}
        self.assertEqual(len(packets), 200)
        for p in packets:
            validate_packet(p)
            self.assertEqual(load_game_snapshot(DATA, p["game_id"]), p)
            official = p["injury_news"]["official_injury"]
            self.assertEqual(p["injury_news"]["news"]["state"], "not_collected_historical")
            self.assertEqual(p["injury_news"]["news"]["findings"], [])
            if official["report_source_id"]:
                self.assertEqual(lineage[p["game_id"]]["selected_source_id"], official["report_source_id"])
                self.assertLessEqual(timestamp(official["published_at_utc"]), timestamp(p["cutoff_utc"]))
                self.assertLessEqual(timestamp(official["report_issue_utc"]), timestamp(p["cutoff_utc"]))
                key = official["report_source_id"]
                meta = json.loads((DATA / "injury_raw" / (key + ".json")).read_text())
                body = gzip.decompress((DATA / "injury_raw" / (key + ".body.gz")).read_bytes())
                self.assertEqual(hashlib.sha256(body).hexdigest(), meta["body_sha256"])
            for side in ("home", "away"):
                if official[side]["state"] == "not_yet_submitted":
                    self.assertEqual(official[side]["players"], [])


if __name__ == "__main__":
    unittest.main()
