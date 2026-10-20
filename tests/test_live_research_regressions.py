"""Offline regressions for the observed 2026-10-20 live-search failure path.

Only public URLs are taken from the run. HTML/provider bodies below are synthetic;
no private provider responses, credentials or invented live claims are fixtures.
"""
import copy
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from collect_prospective import audit_text
from evidence_documents import digest
from investigate_kalshi import iso
from prospective_research import Budget, research, validate_page
from research_diagnostics import summarize_research
from test_prospective_pipeline import CONFIG, ROOT, T, event
from prospective_sources import event_projection


URLS = [
    "https://www.si.com/nba/magic/onsi/orlando-magic-provide-franz-wagner-injury-update-early-exit-preseason-finale-01m56by3dhpy",
    "https://www.orlandosentinel.com/2026/10/18/orlando-magic-practice-franz-wagner-noah-penda-jonathan-isaac-anthony-black-injury-updates-nba-preseason-kia-center-sean-sweeney/",
    "https://www.espn.com/nba/injuries",
    "https://basketnews.com/news-257608-orlando-magic-coach-provides-injury-update-on-franz-wagner-other-players.html",
]


class LiveResearchRegressionTests(unittest.TestCase):
    def test_disallowed_results_and_undated_tracker_skip_inference_without_retry(self):
        provider = Mock()
        provider.search.return_value = [{"url": u} for u in URLS]
        provider.extract.side_effect = AssertionError("No usable dated article: inference forbidden")
        body = b"<main><p>Atlanta Hawks player Example Player is questionable with an ankle injury.</p></main>"
        meta = {"source_id": digest(URLS[2].encode()), "http_status": 200,
                "retrieved_at_utc": iso(T), "body_sha256": digest(body),
                "headers": {"date": "Tue, 20 Oct 2026 02:40:00 GMT",
                            "last-modified": "Tue, 20 Oct 2026 02:39:00 GMT"}}
        fetch = Mock(return_value=(meta, body))
        with patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("Offline test")):
            result = research(event_projection(event()), T, provider, fetch,
                Budget(max_queries=1, max_pages=2, max_tokens=320000,
                       max_output_tokens=2000, max_estimated_cost_usd=.35), CONFIG["prices"],
                now=T, live_window=True, clock=lambda: T + 1, use_model=True, diagnostics=True)
        provider.search.assert_called_once()
        provider.extract.assert_not_called()
        fetch.assert_called_once_with(URLS[2])
        self.assertEqual(result["news"]["findings"], [])
        self.assertEqual(result["news"]["state"], "no_usable_evidence")
        audit = result["audit"]
        self.assertEqual(audit["sources_and_validation"][0]["reason"], "publication_time_unverifiable")
        self.assertEqual(audit["usage_upper_bounds"]["estimated_cost_usd"], .01)
        summary = summarize_research(audit, [], CONFIG["prices"])
        self.assertEqual(summary["counters"]["results_discovered"], 4)
        self.assertEqual(summary["counters"]["pages_retrieved"], 1)
        self.assertEqual(summary["counters"]["pages_rejected"], 1)
        self.assertEqual(summary["rejection_reasons"],
                         {"disallowed_source_url": 3, "publication_time_unverifiable": 1})

    def test_retrieval_headers_and_search_dates_cannot_replace_article_publication(self):
        body = b'<script>window.updated="2026-10-20T02:39:00Z"</script><main><p>Atlanta Hawks injury update.</p></main>'
        meta = {"source_id": "fixture", "http_status": 200, "retrieved_at_utc": iso(T),
                "body_sha256": digest(body), "headers": {"last-modified": iso(T - 1)},
                "search_published_at_utc": iso(T - 100)}
        self.assertEqual(validate_page(URLS[2], body, meta, T + 1, True)["reason"],
                         "publication_time_unverifiable")

    def test_audit_distinguishes_enabled_extraction_from_actual_requests(self):
        folder = ROOT / "reports/prospective_validation/one_game_public_capture_complete"
        packet = json.loads((folder / "evidence_packet.json").read_text())
        lineage = json.loads((folder / "lineage.json").read_text())
        lineage["news"].update(model_extraction_enabled=True, provider_requests=[], sources_and_validation=[])
        skipped = audit_text(packet, lineage)
        self.assertIn("inference requests: 0", skipped)
        self.assertIn("Extraction skipped", skipped)
        self.assertNotIn("Method: bounded model extraction", skipped)
        attempted = copy.deepcopy(lineage)
        attempted["news"]["provider_requests"] = [{"method": "POST"}]
        attempted["news"]["decisions"].append({"reason": "provider_failure"})
        text = audit_text(packet, attempted)
        self.assertIn("inference requests: 1", text)
        self.assertIn("an attempted request does not prove successful extraction", text)
        self.assertIn("provider_failure", text)


if __name__ == "__main__":
    unittest.main()
