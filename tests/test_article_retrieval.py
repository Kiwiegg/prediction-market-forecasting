"""Dated-article policy tests, entirely offline and without provider credentials."""
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
from collect_prospective import check_config, main
from evidence_documents import DocumentStore, canonical, digest
from prospective_research import (ARTICLE_DOMAINS, Budget, allowed_page, planned_queries,
                                  research, validate_findings, validate_page)
from research_diagnostics import summarize_research
from test_prospective_pipeline import CONFIG, PAGE, T, CLAIM, event
from prospective_sources import event_projection
from investigate_kalshi import iso, timestamp

FIXTURES = Path(__file__).parent / "fixtures/articles"


def html(node=None, head="", body=None):
    ld = '' if node is None else '<script type="application/ld+json">' + json.dumps(node) + '</script>'
    return (head + ld + '<article><p>' + (body or CLAIM) + '</p></article>').encode()


def article(**changes):
    return {"@context": "https://schema.org", "@type": "NewsArticle", "url": PAGE,
            "datePublished": iso(T - 100), "dateModified": iso(T - 1), **changes}


def validate(body, url=PAGE, cutoff=T, retrieved=T):
    meta = {"source_id": digest(url.encode()), "http_status": 200,
            "retrieved_at_utc": iso(retrieved), "body_sha256": digest(body)}
    return validate_page(url, body, meta, cutoff, True, dated_articles=True)


class ArticleMetadataTests(unittest.TestCase):
    def test_reduced_real_public_fixtures_parse_and_resolve(self):
        for source in json.loads((FIXTURES / 'sources.json').read_text()):
            body = (FIXTURES / source['fixture']).read_bytes()
            self.assertEqual(digest(body), source['fixture_sha256'])
            clock = timestamp(source['retrieved_at_utc'])
            result = validate(body, source['url'], clock, clock)
            self.assertTrue(result['usable'], result)
            self.assertEqual(timestamp(result['published_at_utc']), timestamp(source['publication_utc']))
            self.assertEqual(timestamp(result['modified_at_utc']), timestamp(source['modified_utc']))
            self.assertTrue(result['timestamp_fields'])
            self.assertNotIn('jsonld:', result['snippets'][0]['excerpt'])

    def test_jsonld_array_graph_and_current_article_identity(self):
        unrelated = article(url='https://www.nba.com/news/another-story', datePublished=iso(T + 100))
        unrelated['@id'] = unrelated['url']
        current = article(**{'@type': ['Thing', 'https://schema.org/NewsArticle'],
                             '@id': PAGE + '#article', 'mainEntityOfPage': {'@id': PAGE}})
        for node in ([unrelated, current], {'@graph': [unrelated, current]}):
            result = validate(html(node))
            self.assertTrue(result['usable'])
            self.assertEqual(result['published_at_utc'], iso(T - 100))
        self.assertFalse(validate(html(unrelated))['usable'])
        self.assertFalse(validate(html(article(**{'mainEntityOfPage': unrelated['url']})))['usable'])

    def test_metadata_consensus_microdata_and_explicit_timezone(self):
        same = '<meta property="article:published_time" content="' + iso(T - 100) + '">'
        self.assertTrue(validate(html(article(), head=same))['usable'])
        for head in ('<meta itemprop="datePublished" content="' + iso(T - 100) + '">',
                     '<time itemprop="datePublished" datetime="' + iso(T - 100) + '"></time>',
                     '<meta name="parsely-pub-date" content="' + iso(T - 100) + '">',
                     '<meta name="dcterms.issued" content="' + iso(T - 100) + '">'):
            self.assertTrue(validate(html(head=head))['usable'])
        for published in ('2026-10-20', '2026-10-20T02:39:00', None, {}, [iso(T - 1)]):
            self.assertEqual(validate(html(article(datePublished=published)))['reason'], 'publication_time_unverifiable')
        conflicting = '<meta property="article:published_time" content="' + iso(T - 10) + '">'
        self.assertEqual(validate(html(article(), head=conflicting))['reason'], 'publication_time_unverifiable')

    def test_future_modification_and_retrieval_bounds(self):
        for node in (article(datePublished=iso(T + 1)), article(dateModified=iso(T + 1))):
            self.assertEqual(validate(html(node))['reason'], 'published_or_modified_after_cutoff')
        self.assertTrue(validate(html(article(dateModified=iso(T))))['usable'])
        self.assertEqual(validate(html(article()), retrieved=T + 1)['reason'], 'retrieved_after_snapshot')
        # An article cannot claim an edit that happened after it was fetched,
        # even if the snapshot itself is later.
        self.assertEqual(validate(html(article(dateModified=iso(T + 1))), cutoff=T + 2)['reason'],
                         'published_or_modified_after_cutoff')
        self.assertEqual(validate(html(article(dateModified=iso(T - 101))))['reason'],
                         'modification_precedes_publication')

    def test_undated_dynamic_malformed_and_ambiguous_metadata_fail_closed(self):
        bodies = [html(), html({'@type': 'WebPage', 'datePublished': iso(T - 1)}),
                  html(article(**{'@type': 'LiveBlogPosting'})),
                  html([{'@type': 'Article', 'datePublished': iso(T - 1)},
                        {'@type': 'Article', 'datePublished': iso(T - 1)}]),
                  html(head='<script type="application/ld+json">bad</script>'),
                  html(head='<script type="application/ld+json">'),
                  html(head='<meta property><script type></script><time itemprop datetime></time>'),
                  html(head='<time datetime="' + iso(T - 1) + '"></time>')]
        for body in bodies:
            self.assertFalse(validate(body)['usable'])

    def test_claims_require_verbatim_safe_paragraphs_not_jsonld_or_search_text(self):
        node = article(articleBody='Atlanta Hawks Example Player is available.',
                       description='Kalshi price 0.99 and a target winner')
        source = validate(html(node, body=CLAIM))
        self.assertEqual(source['snippets'][0]['excerpt'], CLAIM)
        candidate = {'category': 'injury_update', 'team': 'Atlanta Hawks', 'player': 'Example Player',
                     'claim': CLAIM, 'source_ref': source['snippets'][0]['source_ref']}
        accepted, _ = validate_findings([candidate], [source], event_projection(event()), T)
        self.assertEqual(accepted[0]['claim'], CLAIM)
        candidate['claim'] = node['articleBody']
        self.assertEqual(validate_findings([candidate], [source], event_projection(event()), T)[0], [])
        leaked = validate(html(node, body='Atlanta Hawks won 110-100. Kalshi odds moved.'))
        self.assertFalse(leaked['usable'])

    def test_case_recovery_emits_only_the_original_unique_verbatim_span(self):
        text = 'Atlanta Hawks player Example Player is day-to-day with low back soreness.'
        # The article itself still requires dated, relevant source paragraphs.
        # Add an explicit injury context, as in the captured live article.
        source = validate(html(article(), body='Atlanta Hawks injury update: ' + text))
        candidate = {'category': 'injury_update', 'team': 'Atlanta Hawks', 'player': 'Example Player',
                     'claim': 'Day-to-day with low back soreness', 'source_ref': source['snippets'][0]['source_ref']}
        self.assertEqual(validate_findings([candidate], [source], event_projection(event()), T)[0], [])
        findings, decisions = validate_findings([candidate], [source], event_projection(event()), T, format_recovery=True)
        self.assertEqual(findings[0]['claim'], 'day-to-day with low back soreness')
        self.assertIn(findings[0]['claim'], source['snippets'][0]['excerpt'])
        self.assertEqual(candidate['claim'], 'Day-to-day with low back soreness')  # original interpretation retained
        self.assertIn('source_case_normalization', decisions[0])
        for changed in ('Day to day with low back soreness', 'Day-to-day with back injury',
                        'Not day-to-day with low back soreness', 'Day-to-day with low back soreness!'):
            rejected = dict(candidate, claim=changed)
            self.assertEqual(validate_findings([rejected], [source], event_projection(event()), T, format_recovery=True)[0], [])
        repeated = validate(html(article(), body='Atlanta Hawks injury update: ' + text + ' ' + text))
        self.assertEqual(validate_findings([candidate], [repeated], event_projection(event()), T, format_recovery=True)[0], [])


class ArticleRetrievalPolicyTests(unittest.TestCase):
    def test_queries_cover_both_teams_all_topics_and_approved_sites_with_two_calls(self):
        queries = planned_queries(event_projection(event()), Budget(max_queries=8), dated_articles=True)
        self.assertEqual(len(queries), 2)
        for query in queries:
            self.assertIn('"Atlanta Hawks"', query)
            self.assertIn('"Boston Celtics"', query)
            for domain in ARTICLE_DOMAINS:
                self.assertIn('site:' + domain, query)
            self.assertIn('-tracker', query)
        for word in ('injury', 'lineup', 'availability', 'signed', 'waived', 'traded', 'coach'):
            self.assertIn(word, ' '.join(queries))
        self.assertEqual(len(planned_queries(event_projection(event()), Budget(max_queries=1), dated_articles=True)), 1)

    def test_path_domain_and_credential_restrictions(self):
        for source in json.loads((FIXTURES / 'sources.json').read_text()):
            self.assertTrue(allowed_page(source['url'], dated_articles=True))
        for url in ('https://www.espn.com/nba/injuries', 'https://www.nba.com/magic/',
                    'https://www.nba.com/news', 'https://www.nba.com/standings',
                    'https://www.si.com/nba/magic/archive', 'https://www.si.com/nba/magic',
                    'https://www.orlandosentinel.com/sports/orlando-magic/',
                    'https://www.orlandosentinel.com.evil.test/2026/10/18/fake/',
                    'https://basketnews.com/news/injury', 'https://www.nba.com:bad/news/story',
                    'https://secret@www.nba.com/news/story', 'http://www.nba.com/news/story',
                    'https://www.nba.com/game/test/news/odds'):
            self.assertFalse(allowed_page(url, dated_articles=True), url)
        # Original paid capture rejected these; its saved policy remains valid.
        self.assertFalse(allowed_page(next(s['url'] for s in json.loads((FIXTURES / 'sources.json').read_text())
                                          if 'www.si.com/' in s['url'])))

    def test_redirect_is_recorded_and_never_followed(self):
        for code in (301, 302, 307, 308):
            with self.subTest(code=code), tempfile.TemporaryDirectory() as tmp:
                opener = Mock()
                opener.open.side_effect = urllib.error.HTTPError(PAGE, code, 'redirect',
                    {'Location': 'https://unsupported.example/news/article'}, io.BytesIO(b'redirect'))
                with patch('urllib.request.build_opener', return_value=opener) as builder:
                    store = DocumentStore(tmp, False, lambda u: allowed_page(u, dated_articles=True))
                    meta, body = store.get(PAGE)
                self.assertIsNone(builder.call_args.args[0]().redirect_request(None, None, code, 'redirect', {}, 'https://unsupported.example'))
                opener.open.assert_called_once()
                self.assertEqual(meta['http_status'], code)
                self.assertEqual(validate_page(PAGE, body, meta, T, dated_articles=True)['reason'], 'page_unavailable_or_truncated')

    def test_filtered_pages_and_search_snippets_never_reach_extractor(self):
        provider = Mock()
        provider.search.side_effect = [[{'url': 'https://www.espn.com/nba/injuries', 'description': 'Kalshi price .99'},
                                        {'url': PAGE, 'description': 'target winner'}], []]
        body = html(article())
        meta = {'source_id': digest(PAGE.encode()), 'http_status': 200, 'retrieved_at_utc': iso(T), 'body_sha256': digest(body)}
        fetch = Mock(return_value=(meta, body))
        provider.extract.return_value = []
        result = research(event_projection(event()), T, provider, fetch, Budget(max_queries=2, max_pages=4),
            CONFIG['prices'], now=T, use_model=True, diagnostics=True, dated_articles=True)
        fetch.assert_called_once_with(PAGE)
        provider.extract.assert_called_once()
        context = provider.extract.call_args.args[0]
        self.assertNotIn('Kalshi', json.dumps(context))
        self.assertNotIn('target winner', json.dumps(context))
        self.assertNotIn('timestamp_fields', json.dumps(context))
        self.assertEqual(len(context['sources']), 1)
        summary = summarize_research(result['audit'], [], CONFIG['prices'])
        self.assertEqual(summary['searches'][0]['url_status'][0]['status'], 'disallowed_source_url')

    def test_live_test_hard_caps_and_missing_flags_no_paid_calls(self):
        config = copy.deepcopy(CONFIG)
        config['budget'].update(max_queries=99, max_pages=99, max_estimated_cost_usd=99)
        observed = []
        def checked(value):
            observed.append(copy.deepcopy(value))
            return check_config(value)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'config.json'; path.write_text(json.dumps(config))
            args = ['collect_prospective.py', '--config', str(path), '--live-test', '--live', '--allow-network',
                    '--allow-search', '--allow-inference', '--dry-run']
            with patch.object(sys, 'argv', args), patch('collect_prospective.check_config', side_effect=checked), \
                    patch('urllib.request.OpenerDirector.open', side_effect=AssertionError('Dry run must not call providers')), patch('sys.stdout'):
                main()
        self.assertEqual(observed[0]['budget']['max_queries'], 2)
        self.assertEqual(observed[0]['budget']['max_pages'], 4)
        self.assertEqual(observed[0]['budget']['max_estimated_cost_usd'], .35)

    def test_article_budget_reserves_space_for_both_topics(self):
        provider = Mock()
        urls = [PAGE + str(i) for i in range(8)]
        provider.search.side_effect = [[{'url': u} for u in urls[:4]], [{'url': u} for u in urls[4:]]]
        def fetch(url):
            body = html(article(url=url))
            return {'source_id': digest(url.encode()), 'http_status': 200, 'retrieved_at_utc': iso(T),
                    'body_sha256': digest(body)}, body
        result = research(event_projection(event()), T, provider, fetch, Budget(max_queries=2, max_pages=4),
            CONFIG['prices'], now=T, diagnostics=True, dated_articles=True)
        self.assertEqual([s['url'] for s in result['audit']['sources_and_validation']],
                         [urls[0], urls[1], urls[4], urls[5]])
        self.assertEqual(result['audit']['usage_upper_bounds']['pages'], 4)
        self.assertEqual(provider.search.call_count, 2)


if __name__ == '__main__':
    unittest.main()
