import copy
import io
import json
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import Mock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import news_denial_policy as policy
from evidence_documents import digest
from review_article_denial import profile
from test_cloud_news_pipeline import setup

FIXTURES=Path(__file__).parent/'fixtures/denials'
BODY=(FIXTURES/'cloudflare_challenge.html').read_bytes()
HEADERS=json.loads((FIXTURES/'cloudflare_challenge_headers.json').read_text())
URL='https://apnews.com/article/synthetic-basketball-story'


def meta(url=URL,body=BODY):
    return {'url':url,'http_status':403,'headers':dict(HEADERS),'body_sha256':digest(body),'body_size':len(body),'truncated':False}


class ArticleClassificationTests(unittest.TestCase):
    def test_actual_response_shape_is_generic_publisher_challenge_without_denial_words(self):
        m=meta();p=profile(m,BODY)
        self.assertFalse(p['current_diagnostics']['recognized_denial_text'])
        self.assertTrue(p['cf_mitigated_challenge']);self.assertTrue(p['cloudflare_options_present'])
        self.assertTrue(p['cloudflare_challenge_path_present']);self.assertTrue(policy.ordinary_403(m,BODY))
        self.assertEqual(p['known_title'],'just a moment...')
        self.assertEqual(p['document_tags'],{'html':1,'head':1,'title':1,'meta':6,'style':1,'body':1,'div':3,'noscript':1,'span':1,'script':1})

    def test_rule_generalizes_across_approved_article_hosts_not_a_single_url(self):
        urls=[URL,'https://www.espn.com/nba/story/_/id/123/example','https://www.reuters.com/sports/basketball/example/',
              'https://www.si.com/nba/celtics/news/example','https://www.orlandosentinel.com/2026/10/27/example/']
        with patch('urllib.request.OpenerDirector.open',side_effect=AssertionError('Pure classifier cannot fetch')):
            for url in urls:
                with self.subTest(url=url):self.assertTrue(policy.ordinary_403(meta(url),BODY))

    def test_header_and_body_corroboration_all_required_for_new_branch(self):
        for replacement in ('missing-header','wrong-header','wrong-type','no-options','no-platform','no-html'):
            with self.subTest(replacement=replacement):
                m=meta();body=BODY
                if replacement=='missing-header':del m['headers']['cf-mitigated']
                if replacement=='wrong-header':m['headers']['cf-mitigated']='not-a-challenge'
                if replacement=='wrong-type':m['headers']['content-type']='text/plain'
                if replacement=='no-options':body=body.replace(b'_cf_chl_opt',b'_other_options')
                if replacement=='no-platform':body=body.replace(b'/cdn-cgi/challenge-platform/',b'/other-platform/')
                if replacement=='no-html':body=b'<div>Unknown challenge page</div>'
                m.update(body_sha256=digest(body),body_size=len(body))
                self.assertFalse(policy.ordinary_403(m,body))

    def test_authentication_account_and_provider_errors_are_never_exempted(self):
        for message in ('authentication_error','invalid_api_key','account suspended','account-wide restriction','billing restriction',
                        'credentials revoked','quota exceeded','unauthorized','sign in to continue','subscription required'):
            body=BODY.replace(b'</body>',message.encode()+b'</body>');m=meta(body=body)
            with self.subTest(message=message):self.assertFalse(policy.ordinary_403(m,body))
        for header in ('WWW-Authenticate','Proxy-Authenticate'):
            m=meta();m['headers'][header]='challenge'
            self.assertFalse(policy.ordinary_403(m,BODY))
        m=meta();m['provider']='anthropic';self.assertFalse(policy.ordinary_403(m,BODY))
        for url in ('https://api.anthropic.com/v1/messages','https://api.search.brave.com/res/v1/web/search',
                    'https://www.nba.com/news/example','https://official.nba.com/nba-injury-report-2026-27-season/',
                    'https://unknown.example/article/story','https://evil.apnews.com/article/story'):
            with self.subTest(url=url):self.assertFalse(policy.ordinary_403(meta(url),BODY))

    def test_login_forms_json_unknown_denials_and_other_statuses_remain_fatal(self):
        forms=[b'<input type="password">',b"<input name='login' TYPE = 'PASSWORD'>"]
        for form in forms:
            body=BODY.replace(b'</body>',form+b'</body>');self.assertFalse(policy.ordinary_403(meta(body=body),body))
        for body in (b'',b'opaque publisher response',b'{"error":"forbidden"}',b'<html>Account check pending</html>'):
            self.assertFalse(policy.ordinary_403(meta(body=body),body))
        for status in (200,301,401,407,429,451,500,503):
            m=meta();m['http_status']=status;self.assertFalse(policy.ordinary_403(m,BODY))

    def test_integrity_truncation_and_header_case(self):
        for change in ({'body_sha256':'bad'},{'body_size':1},{'truncated':True}):
            self.assertFalse(policy.ordinary_403({**meta(),**change},BODY))
        m=meta();m['headers']={'CF-Mitigated':' challenge ','Content-Type':'Text/HTML; charset=utf-8'}
        self.assertTrue(policy.ordinary_403(m,BODY))

    def test_host_normalization_preserves_no_retry_with_challenge_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            state,key,clock,backend=setup(Path(tmp),live=True)
            op=Mock();op.open.side_effect=urllib.error.HTTPError(URL,403,'Forbidden',HEADERS,io.BytesIO(BODY))
            docs=policy.NewsDocuments(state.job_dir(key)/'news/raw',lambda u:True,state,key,'news',clock[0]+60,article=True,opener=op)
            result,_=docs.get(URL);self.assertEqual(result['http_status'],403)
            for url in (URL,URL.replace('apnews.com','www.apnews.com'),URL.replace('apnews.com','APNEWS.COM:443')):
                self.assertEqual(policy.host_key(url),'apnews.com')
                self.assertTrue(policy.ordinary_403(meta(url),BODY))
                with self.assertRaises(policy.ArticleUnavailable):docs.get(url)
            self.assertEqual(op.open.call_count,1)
            state.check_circuit('network');state.check_circuit('paid')


if __name__=='__main__':unittest.main()
