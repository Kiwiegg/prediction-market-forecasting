import copy
import gzip
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
import urllib.error
from unittest.mock import Mock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import news_denial_policy as policy
import campaign_recovery as recovery
import actions_campaign as campaign
import cloud_prospective as cloud
from actions_storage import StorageStop
from audit_blocked_campaign import FAILED_COMMIT,FAILED_RUN
from evidence_documents import canonical,digest
from test_cloud_news_pipeline import setup as cloud_setup
from test_actions_prospective import setup,approve

URL='https://apnews.com/article/houston-rockets-milwaukee-bucks-b7241eb0f8184acda98b213c436c17e5'
PROOF={'id':40600612996,'status':'completed','conclusion':'failure','head_sha':FAILED_COMMIT,'run_attempt':1}


def fixture(root,live=False):
    state,game,clock,objects,cp=setup(root)
    if live:
        state.approve([game['game_id']],cloud.iso(clock[0]+86400))
        key=state.enroll(game,state.authorize([game['game_id']]))
    else:key=approve(state,game,clock)
    approval=json.loads((root/'campaign.json').read_text());approval['assets_sha256']='0092b665df1319d076d66dff9f3ecbfc023f073382d4ff0224b5d5606d9c3913'
    (root/'campaign.json').write_bytes(canonical(approval))
    claims=[]
    for i,usd in enumerate([.01]*16+[.122501]):
        kind='search' if i<9 else 'forecast' if i<16 else 'extraction'
        with state.db() as c:c.execute('INSERT INTO requests VALUES(?,?,?,?,?)',(str(i),key,kind,usd,'claimed'))
        claims.append({'id':str(i),'job':key,'kind':kind,'usd':usd,'status':'claimed'})
    for name in ('host:apnews.com','network','paid'):
        state.circuit(name,http_status=403,url=URL,**({'reason':'source_access_denial'} if name!='host:apnews.com' else {}))
    folder=state.job_dir(key)/'news/raw';folder.mkdir(parents=True,exist_ok=True)
    body=b'<html>Access denied</html>';m={'url':URL,'http_status':403,'body_sha256':digest(body),'headers':{}}
    (folder/(digest(URL.encode())+'.json')).write_bytes(canonical(m));(folder/(digest(URL.encode())+'.body.gz')).write_bytes(gzip.compress(body))
    with state.db() as c:
        rows=[dict(r) for r in c.execute('SELECT * FROM requests ORDER BY id')];circuits=[dict(r) for r in c.execute('SELECT * FROM circuits ORDER BY id')]
    report={'paid_claim_count':17,'reserved_usd':.282501,'claims':[{'attempt_state':'saved_http_response','http_status':200} for _ in range(17)],
        'jobs':[{'game_id':game['game_id'],'disposition':'preserved_completed','private_replay':{'forecasts':True}}],
        'request_ledger_sha256':digest(canonical(rows)),'circuits_sha256':digest(canonical(circuits)),
        'circuits':circuits,'snapshot_sha256':cp.root['snapshot'],'owner_sha256':digest(canonical(cp.owner))}
    state.sync();return state,key,clock,objects,cp,report


class NewsPolicyTests(unittest.TestCase):
    def test_article403_missing_and_host_never_retried(self):
        with tempfile.TemporaryDirectory() as tmp:
            state,key,clock,backend=cloud_setup(Path(tmp),live=True)
            op=Mock();op.open.side_effect=urllib.error.HTTPError(URL,403,'Denied',{},io.BytesIO(b'<html>Access denied</html>'))
            docs=policy.NewsDocuments(state.job_dir(key)/'news/raw',lambda u:True,state,key,'news',clock[0]+60,article=True,opener=op)
            self.assertIs(docs.budget.clock,state.clock)
            meta,body=docs.get(URL);self.assertEqual(meta['http_status'],403)
            state.check_circuit('network');state.check_circuit('paid')
            with self.assertRaises(policy.ArticleUnavailable):docs.get(URL+'-another')
            self.assertEqual(op.open.call_count,1)
            with self.assertRaises(ValueError):state.check_circuit('host:apnews.com')

    def test_credentials_official_sources_and_other_denials_stay_fatal(self):
        for status,headers,body,url in [(403,{},b'authentication_error invalid_api_key',URL),
                (403,{},b'{}',URL),(403,{},b'',URL),
                (403,{'WWW-Authenticate':'Basic'},b'denied',URL),(401,{},b'denied',URL),
                (407,{},b'denied',URL),(451,{},b'denied',URL),
                (403,{},b'denied','https://www.nba.com/news/test-injury-update')]:
            with self.subTest(status=status,url=url),tempfile.TemporaryDirectory() as tmp:
                state,key,clock,backend=cloud_setup(Path(tmp),live=True)
                op=Mock();op.open.side_effect=urllib.error.HTTPError(url,status,'Denied',headers,io.BytesIO(body))
                docs=policy.NewsDocuments(state.job_dir(key)/'news/raw',lambda u:True,state,key,'news',clock[0]+60,article=True,opener=op)
                with self.assertRaises(ValueError):docs.get(url)
                with self.assertRaises(ValueError):state.check_circuit('paid')

    def test_missing_host_creates_no_fabricated_response_or_findings(self):
        game={'home_name':'Team H','away_name':'Team A'}
        provider=Mock();provider.search_token_bound=1;provider.search.return_value=[{'url':URL}]
        docs=Mock();docs.get.side_effect=policy.ArticleUnavailable('denied_host_not_retried')
        cfg=json.loads(cloud.CONFIG.read_text())['research']
        a=policy.acquire(game,100,provider,docs,cfg,lambda:99)
        self.assertEqual(a['context']['sources'],[]);self.assertEqual(a['sources_and_validation'],[])
        self.assertTrue(any(d.get('observation_retrieved') is False for d in a['decisions']))
        with self.assertRaises(ValueError):policy.acquire(game,98,provider,docs,cfg,lambda:99)

    def test_no_policy_adoption_means_no_exception(self):
        with tempfile.TemporaryDirectory() as tmp:
            state,key,clock,objects,cp,report=fixture(Path(tmp))
            with self.assertRaises(ValueError):state.check_circuit('paid')
            self.assertFalse(policy.bypass_historical_circuit(state,'paid',report['circuits'][-1]['body']))

    def test_explicit_adoption_preserves_ledger_denials_scope_and_old_claims(self):
        with tempfile.TemporaryDirectory() as tmp:
            state,key,clock,objects,cp,report=fixture(Path(tmp));sha=digest(canonical(report))
            objects.write('recovery_audits/'+sha,canonical(report),create=True)
            old=state.campaign_history();before=(state.root/'campaign.json').read_bytes()
            with self.assertRaises(ValueError):recovery.adopt(state,objects,sha,digest(canonical(old)))
            new=recovery.adopt(state,objects,sha,digest(canonical(old)),True)
            for field in ('expires_at_utc','game_ids','max_games','max_usd','per_game_usd','automatic_enrollment'):
                self.assertEqual(new[field],old[field])
            self.assertEqual((state.root/'campaign.json').read_bytes(),before)
            state.check_circuit('paid');state.check_circuit('network')
            with self.assertRaises(ValueError):state.check_circuit('host:apnews.com')
            with self.assertRaises(ValueError):state.reserve('0',key,'forecast',.01)
            with state.db() as c:
                rows=[dict(r) for r in c.execute('SELECT * FROM requests ORDER BY id')]
                circuits=[dict(r) for r in c.execute('SELECT * FROM circuits ORDER BY id')]
            self.assertEqual(digest(canonical(rows)),report['request_ledger_sha256'])
            self.assertEqual(digest(canonical(circuits)),report['circuits_sha256'])
            changed=copy.deepcopy(json.loads(report['circuits'][-1]['body']));changed['provider']='anthropic'
            self.assertFalse(policy.bypass_historical_circuit(state,'paid',canonical(changed).decode()))
            # A new actual provider denial must not be hidden by INSERT OR IGNORE
            # on the preserved original `paid` row.
            state.circuit('paid',provider='anthropic',http_status=403)
            with self.assertRaises(ValueError):state.check_circuit('paid')
            with self.assertRaises(ValueError):state.check_circuit('network')
            with state.db() as c:
                self.assertEqual(c.execute('SELECT count(*) FROM circuits').fetchone()[0],4)

    def test_denied_host_aliases_deadlines_and_uncertain_public_claims(self):
        with tempfile.TemporaryDirectory() as tmp:
            state,key,clock,backend=cloud_setup(Path(tmp),live=True)
            op=Mock();op.open.side_effect=urllib.error.HTTPError(URL,403,'Denied',{},io.BytesIO(b'Access denied'))
            docs=policy.NewsDocuments(state.job_dir(key)/'news/raw',lambda u:True,state,key,'news',clock[0]+60,article=True,opener=op)
            docs.get(URL)
            for url in [URL.replace('apnews.com','www.apnews.com'),URL.replace('apnews.com','APNEWS.COM:443')]:
                with self.assertRaises(policy.ArticleUnavailable):docs.get(url)
            self.assertEqual(op.open.call_count,1)
            clock[0]+=61
            with self.assertRaises(ValueError):docs.get('https://www.espn.com/nba/story/_/id/123/story')
            op.open.assert_called_once()
        with tempfile.TemporaryDirectory() as tmp:
            state,key,clock,backend=cloud_setup(Path(tmp),live=True)
            folder=state.job_dir(key)/'news/raw';op=Mock()
            marker=digest((key+'news'+URL).encode())
            (state.root/'public_claims').mkdir(exist_ok=True)
            (state.root/'public_claims'/(marker+'.json')).write_text('{}')
            docs=policy.NewsDocuments(folder,lambda u:True,state,key,'news',clock[0]+60,article=True,opener=op)
            with self.assertRaises(ValueError):docs.get(URL)
            op.open.assert_not_called()

    def test_denial_and_ledger_changes_prevent_adoption(self):
        for alter in ('ledger','denial'):
            with self.subTest(alter=alter),tempfile.TemporaryDirectory() as tmp:
                state,key,clock,objects,cp,report=fixture(Path(tmp));sha=digest(canonical(report))
                objects.write('recovery_audits/'+sha,canonical(report),create=True)
                if alter=='ledger':
                    with state.db() as c:c.execute('INSERT INTO requests VALUES(?,?,?,?,?)',('new',key,'forecast',.01,'claimed'))
                else:state.circuit('other',http_status=401)
                with self.assertRaises(ValueError):recovery.adopt(state,objects,sha,digest(canonical(state.campaign_history())),True)
                self.assertFalse((state.root/policy.AUTHORIZATION).exists())

    def test_provider403_after_adoption_still_stops_and_is_never_retried(self):
        with tempfile.TemporaryDirectory() as tmp:
            state,key,clock,objects,cp,report=fixture(Path(tmp),live=True)
            p=state.root/'campaign.json';old=json.loads(p.read_text())
            # Synthetic fixture for the real campaign's already-approved scope.
            old.update(max_games=30,automatic_enrollment=True,game_ids=[]);p.write_bytes(canonical(old))
            sha=digest(canonical(report));objects.write('recovery_audits/'+sha,canonical(report),create=True)
            recovery.adopt(state,objects,sha,digest(canonical(old)),True)
            game=copy.deepcopy(state.job(key)['game']);game['game_id']='901'
            game['recorded_start_utc']=cloud.iso(cloud.native.aware(game['recorded_start_utc'])+3600)
            future=state.enroll(game,state.authorize(['901']))
            op=Mock();op.open.side_effect=urllib.error.HTTPError('https://api.anthropic.com/v1/messages',403,'Denied',{},io.BytesIO(b'{}'))
            http=cloud.CloudHTTP(state.root/'mock-provider',state,future,'extraction',clock[0]+60,True,opener=op)
            from research_providers import ProviderError
            with self.assertRaises(ProviderError):http.request('anthropic','POST','https://api.anthropic.com/v1/messages',{'max_tokens':128},{},1000)
            with self.assertRaises(ValueError):http.request('anthropic','POST','https://api.anthropic.com/v1/messages',{'max_tokens':128},{},1000)
            op.open.assert_called_once()
            with state.db() as c:self.assertEqual(c.execute('SELECT count(*) FROM requests').fetchone()[0],18)

    def test_release_requires_exact_audit_and_terminated_owner_and_never_clears_circuits(self):
        with tempfile.TemporaryDirectory() as tmp:
            state,key,clock,objects,cp,report=fixture(Path(tmp))
            # An explicitly synthetic already-audited checkpoint tests CAS mechanics.
            raw,tag=objects.read('root.json');root=json.loads(raw);root['owner']['run']=FAILED_RUN
            objects.write('root.json',canonical(root),tag)
            report.update(snapshot_sha256=root['snapshot'],owner_sha256=digest(canonical(root['owner'])))
            sha=digest(canonical(report));writes=objects.writes
            with patch.object(recovery,'inspect',return_value=report):
                for expected,confirm in [(sha,False),('changed',True)]:
                    with self.assertRaises(ValueError):recovery.release(objects,state.uuid,state.root,PROOF,expected,confirm)
                self.assertEqual(objects.writes,writes)
                result=recovery.release(objects,state.uuid,state.root,PROOF,sha,True)
            self.assertTrue(result['owner_released']);self.assertFalse(result['circuits_cleared'])
            after=json.loads(objects.read('root.json')[0]);self.assertIsNone(after['owner']);self.assertEqual(after['snapshot'],root['snapshot'])
            with state.db() as c:self.assertEqual(c.execute('SELECT count(*) FROM circuits').fetchone()[0],3)

    def test_future_or_provider_denial_cannot_pass_recovery_preconditions(self):
        with tempfile.TemporaryDirectory() as tmp:
            state,key,clock,objects,cp,report=fixture(Path(tmp))
            for mutation in ('future','provider','unknown_usage'):
                bad=copy.deepcopy(report)
                if mutation=='future':bad['jobs'][0]['disposition']='incomplete_not_authorized_to_retry'
                if mutation=='provider':
                    row=bad['circuits'][-1];value=json.loads(row['body']);value['provider']='anthropic';row['body']=json.dumps(value)
                if mutation=='unknown_usage':bad['claims'][0]['attempt_state']='uncertain_no_saved_response'
                with self.assertRaises(ValueError):recovery.preconditions(state,bad)


if __name__=='__main__':unittest.main()
