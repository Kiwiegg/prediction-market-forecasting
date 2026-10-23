"""Held-out scope/control tests; real held-out labels are never read pre-inference."""
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
import heldout_forecast as run
import analyze_heldout as analysis
from evidence_documents import canonical, digest
from forecast_split import ROOT, load_split
from test_leap_forecast import Response, factory


def forbidden_labels(p, original, *args, **kwargs):
    if p.name in ("evaluation.csv", "markets.jsonl") or p.name == ".env":
        raise AssertionError("Inference accessed evaluation data or credentials file")
    return original(p, *args, **kwargs)


def synthetic_labels(plan):
    # Explicitly artificial fixture labels and prices. No actual held-out
    # result or Kalshi source row is read by these tests before the live seal.
    out = {}
    for i, gid in enumerate(plan["game_ids"]):
        packet = run.direct.load_evidence(run.DEFAULT_DATA, gid)
        out[gid] = {"game_id": gid, "home_yes_outcome": str(i % 2), "market_status": "finalized",
            "home_mapping_verified": "True", "market_open_at_cutoff": "True", "cutoff_utc": packet["cutoff_utc"],
            "preferred_quote_missing_reason": "", "preferred_midpoint_price": "0.5", "preferred_quote_bid": "0.4",
            "preferred_quote_ask": "0.6", "preferred_quote_candle_end_lag_seconds": "0",
            "preferred_quote_candle_end_utc": packet["cutoff_utc"]}
    return out


class HeldoutTests(unittest.TestCase):
    def test_authorization_exact_split_and_frozen_evidence(self):
        with self.assertRaises(ValueError): run.make_plan()
        original = Path.open
        with patch.object(Path, "open", lambda p, *a, **k: forbidden_labels(p, original, *a, **k)):
            plan, specs = run.frozen_plan(True)
        ids = load_split()["run_order"]["evaluation"]
        self.assertEqual(plan["game_ids"], ids); self.assertEqual(len(set(ids)), 150)
        self.assertFalse(set(ids) & set(load_split()["run_order"]["development"]))
        order = run.sequence(plan, specs)
        self.assertEqual([n for n, s in order[:9]], ["direct", "v2", "v2", "v2", "v2", "v1", "v1", "v1", "v1"])
        for i in range(150):
            parents = {plan["plans"][n]["games"][i]["evidence_sha256"] for n in run.ORDER}
            self.assertEqual(len(parents), 1)
        with tempfile.TemporaryDirectory() as tmp:
            caches = {n: Path(tmp) / n for n in run.ORDER}; cp = run.cost_plan(plan, specs, caches)
        self.assertEqual(cp["planned_new_requests"], 914); self.assertAlmostEqual(cp["additional_reservation_usd"], 22.943654)
        self.assertEqual(cp["by_method"]["v2"]["source_missing_groups"], 218)
        self.assertEqual(plan["plans"]["v2"]["config"]["generation"], {"temperature": 0., "max_tokens": 128})

    def test_global_budget_boundaries_and_invalid_inputs(self):
        self.assertTrue(run.can_reserve(1199, 39.9, .1))
        self.assertFalse(run.can_reserve(1200, 0, .1))
        self.assertFalse(run.can_reserve(2, 39.9, .10001))
        for values in ((True, 0, 1), (0, float("nan"), 1), (0, 0, -1)):
            with self.assertRaises(ValueError): run.can_reserve(*values)

    def test_full_mock_offline_idempotence_and_shared_parent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); original = Path.open
            with patch.object(Path, "open", lambda p, *a, **k: forbidden_labels(p, original, *a, **k)), \
                    patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("Offline test")):
                plan, specs = run.frozen_plan(True, True); caches = {n: root / n for n in run.ORDER}
                pre = {"cost_plan": run.cost_plan(plan, specs, caches)}
                complete = run.execute(plan, specs, root / "run", caches, pre)
                saved = {p: digest(p.read_bytes()) for p in root.rglob("*") if p.is_file()}
                self.assertEqual(run.execute(plan, specs, root / "run", caches, pre), complete)
                verified = run.verify(root / "run", True)
                self.assertEqual(saved, {p: digest(p.read_bytes()) for p in saved})
            self.assertEqual(complete["paid_call_reservations"], 0)
            self.assertTrue(all(r["successful_forecasts"] == 150 for r in complete["resources"].values()))
            obs = self.observations(root / "run", verified)
            artifacts, _ = analysis.compute(obs, synthetic_labels(plan), allow_mock=True)
            self.assertEqual(artifacts["summary.json"]["cohorts"]["primary"]["n"], 150)
            self.assertEqual(artifacts["summary.json"]["cohorts"]["B_seven_method"]["n"], 150)
            self.assertEqual(artifacts["summary.json"]["cohorts"]["primary"]["scores"]["direct"]["brier_score"], .25)
            with self.assertRaises(ValueError): analysis.compute(obs, synthetic_labels(plan))
            with self.assertRaises(ValueError): analysis.export(root / "run", root / "public", True)

    def observations(self, output, verified):
        manifest, specs, games, complete, execution = verified
        fresh = manifest["preflight"]["cost_plan"]["new_request_ids"]; claims = {}
        for key in fresh:
            n, sha = key.split(":"); p = Path(manifest["cache_directories"][n]) / sha / "attempt.json"
            if p.exists() and manifest["plan"]["plans"][n]["config"]["provider"] != "mock": claims[key] = json.loads(p.read_text())
        return {"run": {k: v for k, v in manifest.items() if k != "cache_directories"}, "games": games,
            "completion": {k: v for k, v in complete.items() if k != "files"}, "execution": execution,
            "claims": claims, "rules": run.rules(), "provider_raw_bodies_included": False,
            "reservations": [json.loads(p.read_text()) for p in sorted((output / "reservations").glob("*.json"))]}

    def denied(self, code):
        return urllib.error.HTTPError("https://api.anthropic.com/v1/messages", code, "Denied", {},
            io.BytesIO(canonical({"error": {"type": "permission_error", "message": "Request not allowed"}})))

    def test_first_denial_globally_stops_all_methods_and_replay_is_partial(self):
        for code in (401, 403):
            with self.subTest(code=code), tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"ANTHROPIC_API_KEY": "fixture-never-export"}):
                root = Path(tmp); plan, specs = run.frozen_plan(True); caches = {n: root / n for n in run.ORDER}
                pre = {"cost_plan": run.cost_plan(plan, specs, caches)}; opener = Mock()
                opener.open.side_effect = [Response({"role": "assistant", "model": "claude-haiku-4-5-20251001", "stop_reason": "end_turn",
                    "usage": {"input_tokens": 100, "output_tokens": 20}, "content": [{"type": "text", "text": '{"home_win_probability":0.55}'}]}), self.denied(code)]
                result = run.execute(plan, specs, root / "run", caches, pre, True, factory(opener), root / "auth.json")
                self.assertEqual(opener.open.call_count, 2); self.assertEqual(result["paid_call_reservations"], 2)
                self.assertEqual(result["stop_reason"]["category"], "access_denial")
                verified = run.verify(root / "run", True)
                self.assertEqual(run.execute(plan, specs, root / "run", caches, pre, True, factory(opener), root / "auth.json"), result)
                self.assertEqual(opener.open.call_count, 2)
                with self.assertRaises(ValueError): run.execute(plan, specs, root / "second", caches, {"cost_plan": run.cost_plan(plan, specs, caches)}, True, factory(opener), root / "auth.json")
                obs = self.observations(root / "run", verified); audit = analysis.audit(obs, specs)
                self.assertEqual(audit["claimed_new_requests"], 2); self.assertEqual(audit["unattempted_new_requests"], 912)
                self.assertGreater(audit["additional_recorded_estimate_usd"], .0005)
                artifacts, _ = analysis.compute(obs, synthetic_labels(plan))
                self.assertEqual(artifacts["summary.json"]["coverage"]["direct"], 1)
                self.assertEqual(artifacts["summary.json"]["cohorts"]["primary"]["n"], 0)
                self.assertIsNone(artifacts["bootstrap.json"]["primary"]["comparisons"]["leap_v2_raw_minus_direct"]["lower_95"])
                if code == 403:
                    # Test the public export/replay contract against explicitly
                    # synthetic source rows, without parsing actual held-out labels.
                    with patch.object(analysis, "labels_after_seal", return_value=synthetic_labels(plan)):
                        summary = analysis.export(root / "run", root / "public", True)
                        self.assertEqual(analysis.replay(root / "public", True), summary)
                        (root / "public/bootstrap.json").write_text("{}")
                        with self.assertRaises(ValueError): analysis.replay(root / "public", True)
                for p in (root / "run").rglob("*"):
                    if p.is_file(): self.assertNotIn(b"fixture-never-export", p.read_bytes())

    def test_interruption_unknown_claim_never_resends(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"ANTHROPIC_API_KEY": "fixture"}):
            root = Path(tmp); plan, specs = run.frozen_plan(True); caches = {n: root / n for n in run.ORDER}
            pre = {"cost_plan": run.cost_plan(plan, specs, caches)}; opener = Mock(); opener.open.side_effect = KeyboardInterrupt()
            result = run.execute(plan, specs, root / "run", caches, pre, True, factory(opener), root / "auth.json")
            self.assertEqual(result["stop_reason"]["category"], "interrupted"); self.assertEqual(opener.open.call_count, 1)
            verified = run.verify(root / "run", True); obs = self.observations(root / "run", verified)
            self.assertGreater(analysis.audit(obs, specs)["additional_recorded_estimate_usd"], 0)
            with self.assertRaises(ValueError): run.cache_state(plan, specs, caches)
            self.assertEqual(run.execute(plan, specs, root / "run", caches, pre, seal_interrupted=True), result)
            self.assertEqual(opener.open.call_count, 1)

    def test_no_outcome_access_until_seal_or_without_authorization(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(analysis, "labels_after_seal", side_effect=AssertionError("Unsealed evaluation")):
            with self.assertRaises(ValueError): analysis.export(Path(tmp), Path(tmp) / "out")
            with self.assertRaises(FileNotFoundError): analysis.export(Path(tmp), Path(tmp) / "out", True)
        with self.assertRaises(ValueError): run.verify(Path("missing"))
        with self.assertRaises(ValueError): analysis.replay(Path("missing"))

    def test_budget_stop_occurs_before_first_network_claim(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"ANTHROPIC_API_KEY": "fixture"}):
            root = Path(tmp); plan, specs = run.frozen_plan(True); caches = {n: root / n for n in run.ORDER}
            pre = {"cost_plan": run.cost_plan(plan, specs, caches)}; opener = Mock()
            with patch.object(run, "can_reserve", return_value=False):
                complete = run.execute(plan, specs, root / "run", caches, pre, True, factory(opener), root / "auth.json")
            self.assertEqual(complete["paid_call_reservations"], 0); self.assertEqual(complete["stop_reason"]["category"], "budget")
            self.assertEqual(opener.open.call_count, 0); run.verify(root / "run", True)
            self.assertFalse(any(p.name == "attempt.json" for c in caches.values() for p in c.rglob("*")))

    def test_malformed_model_json_is_saved_and_never_retried(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"ANTHROPIC_API_KEY": "fixture"}):
            root = Path(tmp); plan, specs = run.frozen_plan(True); caches = {n: root / n for n in run.ORDER}
            pre = {"cost_plan": run.cost_plan(plan, specs, caches)}; opener = Mock()
            opener.open.side_effect = [Response({"role": "assistant", "model": "claude-haiku-4-5-20251001", "stop_reason": "end_turn",
                "usage": {"input_tokens": 100, "output_tokens": 20}, "content": [{"type": "text", "text": '{"home_win_probability":NaN}'}]}), self.denied(403)]
            run.execute(plan, specs, root / "run", caches, pre, True, factory(opener), root / "auth.json")
            verified = run.verify(root / "run", True)
            self.assertEqual(opener.open.call_count, 2); self.assertEqual(verified[2]["direct"][0]["status"], "failed")
            obs = self.observations(root / "run", verified); audit = analysis.audit(obs, specs)
            first = next(e for e in audit["per_observation"] if e["method"] == "direct")
            self.assertEqual(first["response_category"], "invalid_response")
            self.assertEqual(run.cache_state(plan, specs, caches)[0].count("direct:" + specs["direct"][0]["key"]), 1)

    def test_primary_pair_does_not_depend_on_v1_or_market_missingness(self):
        from analyze_v2_development import evaluated, bootstrap
        row = {"game_id": "synthetic", "outcome": 1, "direct": .6, "leap_v2_raw": .7,
            "leap_v2_conservative": .6, "kalshi": None, "constant_50": .5, "leap_v1_raw": None,
            "leap_v1_conservative": None, "outcome_missing_reason": None, "market_missing_reason": "missing quote",
            "direct_status": "success", "v1_status": "failed", "v2_status": "success", "v2_failed_groups": [],
            "scores": {}, "v2_variants": {"leap_v2_raw": {"leave_one_group_out": {}, "group_log_odds_contributions": {}}}}
        for g in run.evidence_v2.GROUPS:
            row["v2_variants"]["leap_v2_raw"]["leave_one_group_out"][g] = {"home_win_probability": .6}
            row["v2_variants"]["leap_v2_raw"]["group_log_odds_contributions"][g] = .1
        from evaluate_forecasts import brier, log_loss
        row["scores"] = {m: {"brier": brier(row[m], 1), "log_loss": log_loss(row[m], 1)} if row[m] is not None else None for m in analysis.METHODS}
        primary = evaluated([row], run.rules()["cohorts"]["primary"])
        self.assertEqual(primary["n"], 1)
        interval = bootstrap([row], [["leap_v2_raw", "direct"]], 20261023, 10000)
        self.assertAlmostEqual(interval["comparisons"]["leap_v2_raw_minus_direct"]["lower_95"], -.07)
        # Empty A/B never needs unavailable method contributions.
        for key in ("A_v2_market", "B_seven_method"):
            result = evaluated([row], run.rules()["cohorts"][key])
            self.assertEqual(result["n"], 0); self.assertEqual(result["exclusions"][0]["game_id"], "synthetic")


if __name__ == "__main__": unittest.main()
