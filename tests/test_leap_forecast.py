import copy
import json
import math
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from compare_forecasts import compare_experiments, compare_rows, METHODS
from direct_forecast import load_evidence
from evidence_documents import canonical, digest
from forecast_split import ROOT, DEFAULT_DATA, DEFAULT_SPLIT, load_split
from leap_evidence import (GROUPS, aggregate, build_groups, checked_config, frozen_assets,
    likelihood_ratio, sigmoid, strict_lr_json)
from leap_forecast import (DEFAULT_CONFIG, PILOT, base_record, cached_group, game_record,
    load_experiment, plan_experiment, run_experiment, validate_response, verify_experiment)
from research_providers import CapturedHTTP

CONFIG = json.loads(DEFAULT_CONFIG.read_text())
MOCK = dict(CONFIG, provider="mock", model="offline-lr-one")
PACKET = load_evidence(DEFAULT_DATA, PILOT[0])
CUTOFF = "2026-01-01T00:00:00Z"


def rehash(packet):
    packet["evidence_snapshot_sha256"] = digest(canonical({k: v for k, v in packet.items() if k != "evidence_snapshot_sha256"}))
    return packet


def reply(ratio=1.25, sufficiency="adequate", **changes):
    return {"role": "assistant", "model": CONFIG["model"], "stop_reason": "end_turn",
        "content": [{"type": "text", "text": json.dumps({"likelihood_ratio": ratio, "evidence_sufficiency": sufficiency})}],
        "usage": {"input_tokens": 100, "output_tokens": 24}, **changes}


class Response:
    status = 200
    def __init__(self, value): self.body = canonical(value)
    def read(self, n): return self.body[:n]
    def __enter__(self): return self
    def __exit__(self, *args): pass


def factory(opener):
    return lambda folder, allow_network=False: CapturedHTTP(folder, allow_network, opener)


def observation(group, ratio=1.0, status="success"):
    return {"group": group, "likelihood_ratio": ratio, "status": status, "evidence_sufficiency": "adequate",
        "missing_reason": "unavailable" if status == "skipped_missing" else None}


def finding(category="roster_transaction", claim="Player signed a contract.", ref="article:1"):
    return {"category": category, "team": PACKET["home"]["team_name"], "player": "Example Player", "claim": claim,
        "source_url": "https://www.nba.com/news/dated-story", "published_at_utc": "2025-01-01T00:00:00Z",
        "retrieved_at_utc": "2025-01-01T01:00:00Z", "uncertainty_flags": [],
        "source_references": [{"source_ref": ref, "source_id": "article", "url": "https://www.nba.com/news/dated-story",
            "published_at_utc": "2025-01-01T00:00:00Z", "retrieved_at_utc": "2025-01-01T01:00:00Z",
            "supporting_excerpt": claim, "supported_claim": claim, "authority": "official"}]}


def quote(gid, price=.6, outcome="1"):
    return {"game_id": gid, "home_yes_outcome": outcome, "home_mapping_verified": "True", "market_status": "finalized",
        "market_open_at_cutoff": "True", "cutoff_utc": CUTOFF, "preferred_midpoint_price": str(price),
        "preferred_quote_bid": str(price - .01), "preferred_quote_ask": str(price + .01),
        "preferred_quote_candle_end_utc": "2025-12-31T23:40:00Z", "preferred_quote_candle_end_lag_seconds": "1200"}


class GroupTests(unittest.TestCase):
    def test_deterministic_projection_no_mutation_and_parent_consumer_identity(self):
        before = canonical(PACKET)
        groups = build_groups(PACKET)
        self.assertEqual(groups, build_groups(copy.deepcopy(PACKET)))
        self.assertEqual(canonical(PACKET), before)
        self.assertEqual([g["group"] for g in groups], list(GROUPS))
        self.assertTrue(all(g["evidence_sha256"] == PACKET["evidence_snapshot_sha256"] for g in groups))
        self.assertEqual(PACKET, load_evidence(DEFAULT_DATA, PILOT[0]))
        for g in groups:
            self.assertEqual(g["group_evidence_sha256"], digest(canonical(g["content"])))

    def test_group_isolation_under_other_group_changes(self):
        original = build_groups(PACKET)
        p = copy.deepcopy(PACKET); p["home"]["rest_at_cutoff"]["hours_since_last_completed_game"] += 1
        rest = build_groups(rehash(p))
        self.assertNotEqual(original[1]["group_evidence_sha256"], rest[1]["group_evidence_sha256"])
        for i in (0, 2, 3): self.assertEqual(original[i]["content"], rest[i]["content"])
        strength = original[0]["content"]["evidence"]
        self.assertNotIn("rest_at_cutoff", strength["home"])
        self.assertNotIn("neutral_site", original[0]["content"])
        self.assertNotIn("regular_season_record", original[1]["content"]["evidence"]["home"])
        for i in (0, 1, 3): self.assertNotIn("official_injury", canonical(original[i]["content"]).decode())

    def test_leakage_future_and_hash_rejection(self):
        for key in ("outcome", "market_price", "evaluation", "audit"):
            p = copy.deepcopy(PACKET); p[key] = "forbidden"
            with self.assertRaises(ValueError): build_groups(rehash(p))
        p = copy.deepcopy(PACKET); p["injury_news"]["official_injury"]["published_at_utc"] = "2099-01-01T00:00:00Z"
        with self.assertRaises(ValueError): build_groups(rehash(p))
        p = copy.deepcopy(PACKET); p["home"]["regular_season_scoring"]["per_game"][0]["game_id"] = p["game_id"]
        with self.assertRaises(ValueError): build_groups(rehash(p))
        p = copy.deepcopy(PACKET); p["neutral_site"] = not p["neutral_site"]
        with self.assertRaises(ValueError): build_groups(p)
        p = copy.deepcopy(PACKET); f = finding(); f["published_at_utc"] = "2099-01-01T00:00:00Z"
        p["injury_news"]["news"]["findings"] = [f]
        with self.assertRaises(ValueError): build_groups(rehash(p))

    def test_missing_unsubmitted_ambiguous_do_not_imply_health(self):
        for state in ("unavailable", "not_yet_submitted", "ambiguous"):
            p = copy.deepcopy(PACKET)
            for side in ("home", "away"):
                p["injury_news"]["official_injury"][side].update(state=state, players=[])
            group = build_groups(rehash(p))[2]
            self.assertFalse(group["usable"])
            self.assertIn(state, group["missing_reason"])
            self.assertEqual(group["content"]["evidence"]["official_injury"]["home"]["state"], state)
        self.assertTrue(build_groups(PACKET)[2]["usable"])
        self.assertFalse(build_groups(load_evidence(DEFAULT_DATA, PILOT[3]))[2]["usable"])
        self.assertIn("not_collected_historical", build_groups(PACKET)[3]["missing_reason"])

    def test_strength_zero_completed_vs_source_unavailable_venue_still_usable(self):
        for absent in (False, True):
            p = copy.deepcopy(PACKET)
            for side in ("home", "away"):
                for key in ("regular_season_scoring", "regular_season_home_away", "recent_regular_season", "regular_season_record", "rest_at_cutoff"):
                    p[side].pop(key, None)
                if not absent:
                    p[side]["regular_season_record"] = {"games_completed": 0, "wins": 0, "losses": 0}
            groups = build_groups(rehash(p))
            self.assertFalse(groups[0]["usable"])
            self.assertEqual(groups[0]["missing_reason"], "statistical_source_unavailable" if absent else "no_completed_games")
            self.assertTrue(groups[1]["usable"])

    def test_news_category_isolation_verbatim_support_and_deduplication(self):
        p = copy.deepcopy(PACKET)
        p["injury_news"]["news"]["findings"] = [finding(), finding(), finding("injury_update", "Player is Out.", "other:2")]
        groups = build_groups(rehash(p))
        self.assertEqual(len(groups[2]["content"]["evidence"]["news"]["findings"]), 1)
        self.assertEqual(len(groups[3]["content"]["evidence"]["findings"]), 1)
        self.assertEqual(len(groups[3]["deduplication_decisions"]), 1)
        self.assertNotIn("Player is Out", canonical(groups[3]["content"]).decode())
        p["injury_news"]["news"]["findings"][0]["claim"] = "Unsupported paraphrase."
        with self.assertRaises(ValueError): build_groups(rehash(p))

    def test_news_fact_already_in_injuries_is_excluded_from_additional(self):
        p = copy.deepcopy(PACKET)
        p["injury_news"]["news"]["findings"] = [finding("injury_update"), finding("team_development")]
        groups = build_groups(rehash(p))
        self.assertFalse(groups[3]["usable"])
        self.assertEqual(len(groups[3]["deduplication_decisions"]), 1)

    def test_neutral_site_and_unverified_report_preserve_uncertainty(self):
        p = copy.deepcopy(PACKET); p["neutral_site"] = True
        p["injury_news"]["official_injury"]["publication_verification"] = "unavailable"
        groups = build_groups(rehash(p))
        self.assertTrue(groups[1]["content"]["evidence"]["neutral_site"])
        self.assertFalse(groups[2]["usable"])
        self.assertFalse(groups[2]["content"]["point_in_time_verified"])

    def test_inference_opens_no_audit_labels_prices_or_live_tools(self):
        original = Path.open
        def guarded(path, *args, **kwargs):
            if path.name in {"evaluation.csv", "evidence_lineage.jsonl", "injury_lineage.jsonl", "game_history.jsonl", "market_metadata.json"}:
                raise AssertionError("Forbidden audit/evaluation read")
            return original(path, *args, **kwargs)
        with tempfile.TemporaryDirectory() as tmp, patch.object(Path, "open", guarded), \
                patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("No network")):
            plan, specs = plan_experiment(DEFAULT_DATA, DEFAULT_SPLIT, MOCK)
            result = run_experiment(plan, specs, Path(tmp)/"run", Path(tmp)/"cache", 0, 0)
            self.assertEqual(result["successful_forecasts"], 5)
            for s in specs:
                payload = s["wire"]["payload"]
                self.assertNotIn("tools", payload)
                self.assertEqual(len(payload["messages"]), 1)


class LRAndAggregationTests(unittest.TestCase):
    def test_strict_lr_boundaries_and_sufficiency(self):
        for value in (.05, 1, 20): self.assertEqual(likelihood_ratio(value), value)
        for value in (0, -.1, .049999, 20.000001, True, "1", None, float("inf"), float("nan")):
            with self.subTest(value=value), self.assertRaises(ValueError): likelihood_ratio(value)
        for cat in ("adequate", "limited"):
            self.assertEqual(strict_lr_json(json.dumps({"likelihood_ratio": 1.2, "evidence_sufficiency": cat}))["likelihood_ratio"], 1.2)
        for text in ('{"likelihood_ratio":1,"likelihood_ratio":2,"evidence_sufficiency":"adequate"}',
                '{"likelihood_ratio":NaN,"evidence_sufficiency":"adequate"}', '```json\n{}\n```', '{}', '[]', 'null',
                '{"likelihood_ratio":1,"evidence_sufficiency":"insufficient"}',
                '{"likelihood_ratio":1,"evidence_sufficiency":"other"}',
                '{"likelihood_ratio":1,"evidence_sufficiency":"adequate","explanation":"x"}'):
            with self.subTest(text=text), self.assertRaises(ValueError): strict_lr_json(text)

    def test_exact_bayesian_and_leave_one_group_out_arithmetic(self):
        records = [observation(g, lr) for g, lr in zip(GROUPS, (2, 3, .5, 1))]
        result = aggregate(records)
        self.assertAlmostEqual(result["variants"]["leap_raw"]["home_win_probability"], .75)
        self.assertAlmostEqual(result["variants"]["leap_conservative"]["home_win_probability"], math.sqrt(3)/(1+math.sqrt(3)))
        self.assertAlmostEqual(result["variants"]["leap_raw"]["leave_one_group_out"][GROUPS[0]]["home_win_probability"], .6)
        self.assertAlmostEqual(result["variants"]["leap_raw"]["leave_one_group_out"][GROUPS[0]]["full_minus_omission_probability"], .15)
        self.assertEqual(result["variants"]["leap_raw"]["group_log_odds_contributions"][GROUPS[0]], math.log(2))
        self.assertEqual(result["variants"]["leap_conservative"]["group_log_odds_contributions"][GROUPS[0]], .5 * math.log(2))

    def test_failed_group_is_not_neutral_and_missing_is(self):
        records = [observation(g) for g in GROUPS]
        records[2] = observation(GROUPS[2], 1, "skipped_missing")
        self.assertEqual(aggregate(records)["variants"]["leap_raw"]["home_win_probability"], .5)
        for status in ("failed", "not_attempted_budget"):
            records[2] = observation(GROUPS[2], None, status)
            result = aggregate(records)
            self.assertEqual(result["status"], "failed")
            self.assertIsNone(result["variants"]["leap_raw"]["home_win_probability"])
        with self.assertRaises(ValueError): aggregate(records[:-1])

    def test_numerical_stability_and_prespecified_extremes(self):
        for lr in (.05, 20):
            p = aggregate([observation(g, lr) for g in GROUPS])["variants"]["leap_raw"]["home_win_probability"]
            self.assertTrue(0 < p < 1)
        self.assertEqual(sigmoid(1000), 1)
        self.assertEqual(sigmoid(-1000), 0)
        with self.assertRaises(ValueError): sigmoid(float("inf"))


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.plan, self.specs = plan_experiment(DEFAULT_DATA, DEFAULT_SPLIT, CONFIG, limit=1)

    def test_frozen_assets_split_pilot_and_authorization(self):
        self.assertEqual(frozen_assets(), self.plan["frozen_assets"])
        self.assertEqual(load_split()["run_order"]["development"][:5], PILOT)
        self.assertEqual(self.plan["split_sha256"], "300d87a9dbd8165934e1571453eb15a03f93616841c4a450514d42cc75a94043")
        with self.assertRaises(ValueError), patch("leap_forecast.load_evidence", side_effect=AssertionError("Held-out packet opened")):
            plan_experiment(DEFAULT_DATA, DEFAULT_SPLIT, CONFIG, "evaluation")
        for bad in ({**CONFIG, "generation": {**CONFIG["generation"], "temperature": .1}}, {**CONFIG, "prompt_version": "other"}):
            with self.assertRaises(ValueError): checked_config(bad)

    def test_response_model_tools_usage_and_malformed_validation(self):
        self.assertEqual(validate_response(reply(), self.specs[0], CONFIG)["likelihood_ratio"], 1.25)
        for response in (reply(model="other"), reply(stop_reason="max_tokens"), reply(usage={"input_tokens": 0}),
                reply(usage={"input_tokens": 100, "output_tokens": 129}), reply(content=[{"type": "tool_use"}]),
                reply(content=[{"type": "text", "text": "not json"}])):
            with self.assertRaises(ValueError): validate_response(response, self.specs[0], CONFIG)

    def test_configurable_gateway_lr_contract_offline(self):
        config = dict(CONFIG, provider="json_gateway", endpoint="https://gateway.example/llr")
        plan, specs = plan_experiment(DEFAULT_DATA, DEFAULT_SPLIT, config, limit=1)
        response = {"model": config["model"], "stop_reason": "end_turn", "usage": {"input_tokens": 80, "output_tokens": 20},
            "response": {"likelihood_ratio": .8, "evidence_sufficiency": "limited"}}
        opener = Mock(); opener.open.return_value = Response(response)
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"ANTHROPIC_API_KEY": "fixture-placeholder"}):
            r = cached_group(specs[0], config, tmp, True, factory(opener))
            self.assertEqual(r["likelihood_ratio"], .8)
            self.assertEqual(opener.open.call_count, 1)
        with self.assertRaises(ValueError): validate_response({**response, "tool_calls": ["forbidden"]}, specs[0], config)

    def test_success_cache_immutable_identity_and_no_extra_calls_for_variants(self):
        opener = Mock(); opener.open.return_value = Response(reply())
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"ANTHROPIC_API_KEY": "unit-test-placeholder"}):
            path = Path(tmp)
            r = cached_group(self.specs[0], CONFIG, path, True, factory(opener))
            self.assertEqual(r["status"], "success")
            self.assertEqual(cached_group(self.specs[0], CONFIG, path, False, factory(opener)), r)
            self.assertEqual(opener.open.call_count, 1)
            self.assertNotIn(b"unit-test-placeholder", b"".join(p.read_bytes() for p in path.rglob("*.json")))
            changed = copy.deepcopy(PACKET); changed["home"]["rest_at_cutoff"]["hours_since_last_completed_game"] += 1
            from leap_forecast import group_spec
            changed_spec = group_spec(build_groups(rehash(changed))[0], CONFIG)
            self.assertNotEqual(changed_spec["key"], self.specs[0]["key"])  # parent binding also changes

    def test_provider_failure_and_invalid_response_never_retry(self):
        for response in (reply(ratio=0), reply(sufficiency="insufficient"), None):
            opener = Mock()
            if response is None: opener.open.side_effect = OSError("offline fixture failure")
            else: opener.open.return_value = Response(response)
            with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-placeholder"}):
                r = cached_group(self.specs[0], CONFIG, tmp, True, factory(opener))
                self.assertEqual(r["status"], "failed"); self.assertIsNone(r["likelihood_ratio"])
                self.assertEqual(cached_group(self.specs[0], CONFIG, tmp, True, factory(opener)), r)
                self.assertEqual(opener.open.call_count, 1)

    def test_uncertain_attempt_is_not_resent(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-placeholder"}):
            folder = Path(tmp) / self.specs[0]["key"]; folder.mkdir(); (folder / "attempt.json").write_text("{}")
            opener = Mock(); r = cached_group(self.specs[0], CONFIG, tmp, True, factory(opener))
            self.assertEqual(r["status"], "failed"); self.assertIn("uncertain", r["error"]["message"])
            opener.open.assert_not_called()

    def test_budget_zero_calls_or_cost_blocks_before_provider(self):
        for calls, cost in ((0, 1), (20, 0)):
            with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-placeholder"}):
                opener = Mock(); root = Path(tmp)
                result = run_experiment(self.plan, self.specs, root/"run", root/"cache", calls, cost, True, factory(opener))
                self.assertEqual(result["paid_call_reservations"], 0)
                self.assertEqual(result["group_status_counts"]["not_attempted_budget"], 3)
                self.assertEqual(result["successful_forecasts"], 0)
                opener.open.assert_not_called()

    def test_exact_call_limit_and_reuse_in_another_run(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-placeholder"}):
            opener = Mock(); opener.open.return_value = Response(reply())
            root = Path(tmp)
            result = run_experiment(self.plan, self.specs, root/"run", root/"cache", 1, 1, True, factory(opener))
            self.assertEqual(result["paid_call_reservations"], 1)
            self.assertEqual(opener.open.call_count, 1)
            run_experiment(self.plan, self.specs, root/"second", root/"cache", 0, 0, True, factory(opener))
            self.assertEqual(opener.open.call_count, 1)

    def test_mock_seal_replay_read_only_and_refusal_to_overwrite(self):
        plan, specs = plan_experiment(DEFAULT_DATA, DEFAULT_SPLIT, MOCK)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); output, cache = root/"run", root/"cache"
            first = run_experiment(plan, specs, output, cache, 0, 0)
            self.assertEqual(run_experiment(plan, specs, output, cache, 0, 0), first)
            before = {str(p): p.read_bytes() for p in root.rglob("*") if p.is_file()}
            with patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("Offline replay")):
                self.assertEqual(verify_experiment(output, cache_override=cache), first)
            self.assertEqual(before, {str(p): p.read_bytes() for p in root.rglob("*") if p.is_file()})
            games = load_experiment(output)[1]
            self.assertTrue(all(g["variants"]["leap_raw"]["home_win_probability"] == .5 for g in games))
            with self.assertRaises(ValueError): run_experiment({**plan, "subset": "other"}, specs, output, cache, 0, 0)
            target = output/"forecasts"/(PILOT[0]+".json"); target.write_text("{}")
            with self.assertRaises(ValueError): load_experiment(output)

    def test_paid_success_replays_saved_extraction_without_requests(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-placeholder"}):
            root = Path(tmp); opener = Mock(); opener.open.return_value = Response(reply())
            run_experiment(self.plan, self.specs, root/"run", root/"cache", 3, 1, True, factory(opener))
            self.assertEqual(opener.open.call_count, 3)
            with patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("No network")):
                verify_experiment(root/"run", cache_override=root/"cache")


class ComparisonTests(unittest.TestCase):
    def test_end_to_end_sealed_mock_comparison_and_immutable_dataset(self):
        from direct_forecast import plan_experiment as direct_plan, run_experiment as direct_run
        from direct_forecast import DEFAULT_CONFIG as DIRECT_CONFIG
        before = {str(p): digest(p.read_bytes()) for p in DEFAULT_DATA.rglob("*") if p.is_file()}
        dc = dict(json.loads(DIRECT_CONFIG.read_text()), provider="mock", model="offline-constant-0.5")
        dp, ds = direct_plan(DEFAULT_DATA, DEFAULT_SPLIT, dc)
        lp, ls = plan_experiment(DEFAULT_DATA, DEFAULT_SPLIT, MOCK)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            direct_run(dp, ds, root/"direct", root/"dcache", 0, 0)
            run_experiment(lp, ls, root/"leap", root/"lcache", 0, 0)
            with self.assertRaises(ValueError): compare_experiments(root/"direct", root/"leap", root/"score")
            result = compare_experiments(root/"direct", root/"leap", root/"score", allow_mock=True)
            self.assertEqual(result["paired"]["game_ids"], PILOT)
            self.assertEqual(result["paired"]["scores"]["leap_raw"]["brier_score"], .25)
            self.assertEqual(compare_experiments(root/"direct", root/"leap", root/"score", allow_mock=True), result)
        self.assertEqual(before, {str(p): digest(p.read_bytes()) for p in DEFAULT_DATA.rglob("*") if p.is_file()})

    def test_all_methods_share_intersection_and_missingness_is_preserved(self):
        direct, leap, labels, cutoffs = [], [], {}, {}
        for gid in ("a", "b", "c"):
            direct.append({"game_id": gid, "evidence_sha256": gid, "home_win_probability": .7, "status": "success"})
            leap.append(game_record(gid, gid, [observation(g, 1) for g in GROUPS]))
            labels[gid] = quote(gid); cutoffs[gid] = CUTOFF
        labels["b"]["preferred_quote_missing_reason"] = "no_quote"
        leap[2] = game_record("c", "c", [observation(g, None, "failed") if i == 0 else observation(g) for i, g in enumerate(GROUPS)])
        rows, result = compare_rows(direct, leap, labels, cutoffs)
        self.assertEqual(result["paired"]["game_ids"], ["a"])
        for method in METHODS: self.assertEqual(result["paired"]["scores"][method]["n"], 1)
        self.assertAlmostEqual(result["paired"]["scores"]["direct"]["brier_score"], .09)
        self.assertAlmostEqual(result["paired"]["scores"]["direct"]["log_loss"], -math.log(.7))
        self.assertAlmostEqual(rows[0]["paired_score_differences"]["direct_minus_leap_raw"]["brier"], .09-.25)
        for variant in ("leap_raw", "leap_conservative"):
            for group in GROUPS: self.assertEqual(result["leave_one_group_out_same_intersection"][variant][group]["n"], 1)
        self.assertEqual(sum(b["count"] for b in result["paired"]["calibration"]["direct"]), 1)
        with self.assertRaises(ValueError): compare_rows(direct[:-1], leap, labels, cutoffs)
        direct[0]["evidence_sha256"] = "different"
        with self.assertRaises(ValueError): compare_rows(direct, leap, labels, cutoffs)

    def test_reserved_scoring_rejected_before_any_record_access(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("direct", "leap"):
                (root/name).mkdir(); (root/name/"run.json").write_text(json.dumps({"subset": "evaluation"}))
            with self.assertRaises(ValueError): compare_experiments(root/"direct", root/"leap", root/"score")


if __name__ == "__main__":
    unittest.main()
