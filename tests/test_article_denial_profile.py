import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from review_article_denial import profile


class ProfileTests(unittest.TestCase):
    def test_structure_report_never_exposes_source_tokens_or_header_values(self):
        meta={'url':'https://apnews.com/article/fixture','http_status':403,'headers':{'Content-Type':'text/html; charset=UTF-8','Set-Cookie':'private-cookie-value','X-Request-ID':'private-id'}}
        body=b'<html><head><title>apnews.com</title></head><body><p>Please enable JS and disable any ad blocker</p><script>var dd={"cookie":"secret-source-token"};</script><script src="https://ct.captcha-delivery.com/c.js?secret-token"></script></body></html>'
        result=profile(meta,body)
        self.assertTrue(result['visible_phrases']['please enable js and disable any ad blocker'])
        self.assertEqual(result['known_challenge_script_hosts'],['ct.captcha-delivery.com'])
        self.assertTrue(result['datadome_options_present']);self.assertTrue(result['set_cookie_present'])
        for token in ('private-cookie-value','private-id','secret-source-token','secret-token'):
            self.assertNotIn(token,str(result))


if __name__=='__main__':unittest.main()
