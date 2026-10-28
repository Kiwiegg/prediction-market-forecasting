"""Prospective-only, explicitly adopted publisher-403 policy. No provider bypass."""
import gzip
import json
import re
import urllib.parse
from dataclasses import asdict

import cloud_news
import cloud_prospective as cloud
from cloud_state import durable_json,paid_gate
from evidence_documents import DocumentStore,canonical,digest
from prospective_research import Budget,CATEGORIES,allowed_page,planned_queries,validate_page
from research_providers import EXTRACTION_INSTRUCTIONS

POLICY=cloud.ROOT/'experiments/prospective_news_denial_v1.json'
AUTHORIZATION='news_denial_authorization.json'
RESTRICTION_MARKERS=('invalid_api_key','api key','authentication_error','permission_error','account suspended',
    'account disabled','account-wide','billing restriction','credential','quota exceeded','unauthorized','authentication required',
    'sign in to continue','log in to continue','account locked','account restricted','subscription required','payment required')
PASSWORD_FIELD=re.compile(r'<input\b[^>]*\btype\s*=\s*[\"\']?password\b')


class ArticleUnavailable(ValueError):pass


def cloudflare_challenge(headers,text):
    """Documented response marker plus corroborating HTML; never execute scripts."""
    return (headers.get('cf-mitigated','').strip().casefold()=='challenge'
        and headers.get('content-type','').split(';',1)[0].strip().casefold()=='text/html'
        and '<html' in text and '_cf_chl_opt' in text and '/cdn-cgi/challenge-platform/' in text)


def host_key(url):
    return (urllib.parse.urlsplit(url).hostname or '').lower().removeprefix('www.')


def classification_diagnostics(meta,body):
    """Safe flags only; no response text, headers or account information exported."""
    headers={k.lower():v for k,v in meta.get('headers',{}).items()};text=body.decode(errors='replace').casefold()
    return {'allowed_article':third_party_article(meta['url']),'status_403':meta.get('http_status')==403,
        'truncated':bool(meta.get('truncated')),'empty_body':not bool(body),
        'credential_challenge_header':'www-authenticate' in headers or 'proxy-authenticate' in headers,
        'json_or_api_shape':'json' in headers.get('content-type','') or text.lstrip().startswith(('{','[')),
        'cloudflare_browser_challenge':cloudflare_challenge(headers,text),
        'recognized_denial_text':any(w in text for w in ('access denied','accessdenied','forbidden','request blocked','403','could not be satisfied','permission to access')),
        'password_form_present':bool(PASSWORD_FIELD.search(text)),
        'restriction_marker_names':[w for w in RESTRICTION_MARKERS if w in text]}


def third_party_article(url):
    return allowed_page(url,dated_articles=True) and urllib.parse.urlsplit(url).hostname in json.loads(POLICY.read_text())['third_party_hosts']


def ordinary_403(meta,body):
    if meta.get('provider') or meta.get('http_status')!=403 or not third_party_article(meta['url']) or meta.get('truncated'):return False
    if 'body_sha256' in meta and meta['body_sha256']!=digest(body):return False
    if 'body_size' in meta and meta['body_size']!=len(body):return False
    headers={k.lower():v for k,v in meta.get('headers',{}).items()}
    if 'www-authenticate' in headers or 'proxy-authenticate' in headers:return False
    text=body.decode(errors='replace').casefold()
    if 'json' in headers.get('content-type','') or text.lstrip().startswith(('{','[')):return False
    if any(word in text for word in RESTRICTION_MARKERS) or PASSWORD_FIELD.search(text):return False
    return (any(word in text for word in ('access denied','accessdenied','forbidden','request blocked','403','could not be satisfied','permission to access'))
            or cloudflare_challenge(headers,text))


def authorization(state):
    p=state.root/AUTHORIZATION
    if not p.exists():raise ValueError('News-denial policy has not been explicitly adopted')
    value=json.loads(p.read_text())
    if value['policy_sha256']!=digest(POLICY.read_bytes()) or value['store_uuid']!=state.uuid:
        raise ValueError('News-denial policy/store mismatch')
    approval=state.campaign()
    if value['approval_sha256']!=digest(canonical(approval)):raise ValueError('News-denial authorization differs from campaign')
    return value


def bypass_historical_circuit(state,key,body):
    """Original rows stay immutable; only exact operator-approved snapshots qualify."""
    path=state.root/AUTHORIZATION
    if key not in ('network','paid') or not path.exists():return False
    value=authorization(state)
    return value['circuit_sha256'].get(key)==digest(body.encode())


class ArticleBudget(cloud.SourceBudget):
    def __init__(self,state,job,folder):
        super().__init__(state,job);self.folder=folder
    def stop(self,reason,**details):
        if not third_party_article(details['url']):return super().stop(reason,**details)
        meta,body=DocumentStore(self.folder,True,lambda u:third_party_article(u)).get(details['url'])
        if ordinary_403(meta,body):
            self.state.circuit('host:'+host_key(details['url']),
                reason='optional_article_403',policy='prospective_news_denial_v1',**details)
            return
        return super().stop(reason,**details)


class NewsDocuments(cloud.CloudDocuments):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs);self.budget=ArticleBudget(self.state,self.job,self.folder)
    def _get(self,url):
        if not self.allowed_url(url):raise ValueError('Unapproved article URL')
        host=host_key(url)
        with paid_gate(self.state.root/'locks'/('news-host-'+digest(host.encode())+'.lock'),self.cutoff,self.state.clock):
            self.guard()
            with self.state.db() as c:old=c.execute('SELECT body FROM circuits WHERE id=?',('host:'+host,)).fetchone()
            if old:
                deny=json.loads(old['body'])
                if deny.get('http_status')==403 and third_party_article(url):raise ArticleUnavailable('denied_host_not_retried')
                self.state.check_circuit('host:'+host)
            try:return super()._get(url)
            except ValueError:
                # The one-shot transport has already saved the denied response.
                p=self.folder/(digest(url.encode())+'.json')
                if p.exists():
                    meta,body=DocumentStore(self.folder,True,self.allowed_url).get(url)
                    if ordinary_403(meta,body):return meta,body
                raise


def acquire(game,cutoff,provider,documents,settings,clock):
    """Same frozen queries/validation/context as cloud_news; skips known denied hosts."""
    budget=Budget(**{k:v for k,v in settings.items() if k!='max_extraction_calls'})
    results=[];decisions=[];sources=[];seen=set();pages=0;tokens=0
    for index,query in enumerate(planned_queries(game,budget,dated_articles=True)):
        if clock()>cutoff:raise ValueError('News retrieval deadline passed')
        tokens+=provider.search_token_bound
        if tokens>budget.max_tokens:raise ValueError('Search token budget exceeded')
        rows=provider.search(query,cutoff);results.append({'query':query,'results':rows})
        for row in rows:
            url=row['url']
            if url in seen or not allowed_page(url,dated_articles=True):
                decisions.append({'url':url,'reason':'duplicate_or_disallowed_source'});continue
            if pages>=budget.max_pages or index==0 and pages>=(budget.max_pages+1)//2:
                decisions.append({'url':url,'reason':'page_budget_exhausted_for_query'});continue
            seen.add(url)
            try:meta,body=documents.get(url)
            except ArticleUnavailable as e:
                decisions.append({'url':url,'reason':str(e),'observation_retrieved':False});continue
            pages+=1
            value=validate_page(url,body,meta,cutoff,enforce_retrieval=True,dated_articles=True)
            if clock()<cloud.native.aware(meta['retrieved_at_utc']):raise ValueError('Source retrieval clock is in the future')
            sources.append(value)
    safe=[{k:s[k] for k in ('source_id','published_at_utc','snippets')} for s in sources if s.get('usable')]
    context={'home_team':game['home_name'],'away_team':game['away_name'],'cutoff_utc':cloud.iso(cutoff),
             'allowed_categories':CATEGORIES,'sources':safe}
    if len(canonical(context))+2048+budget.max_output_tokens+tokens>budget.max_tokens:raise ValueError('Combined news token budget exceeded')
    return {'context':context,'context_sha256':digest(canonical(context)),'sources_and_validation':sources,
            'raw_search_results':results,'decisions':decisions,'budgets':asdict(budget),'captured_at_utc':cloud.iso(clock()),
            'extraction_prompt':EXTRACTION_INSTRUCTIONS,'extraction_prompt_sha256':digest(EXTRACTION_INSTRUCTIONS.encode()),
            'operational_amendment':'prospective_news_denial_v1'}


class NewsBackend(cloud.LiveBackend):
    def news(self,key,folder):
        self.gate(key);s=self.state;game=s.job(key)['game'];w=cloud.windows(game,s.config);auth=authorization(s)
        if w['target']<=cloud.native.aware(auth['effective_after_utc']):raise ValueError('No retroactive policy application')
        if not w['collect']<=s.clock()<=w['retrieve']:raise ValueError('News collection window missed')
        durable_json(s.root/'news_policy_applications'/(key+'.json'),{'job_id':key,'policy_sha256':auth['policy_sha256'],
            'effective_after_utc':auth['effective_after_utc'],'information_cutoff_utc':cloud.iso(w['target'])})
        s.sync()
        documents=NewsDocuments(folder/'raw',lambda u:allowed_page(u,dated_articles=True),s,key,'news',w['retrieve'],article=True)
        provider=self.provider(key,folder,'search')
        result=acquire(game,w['retrieve'],provider,documents,s.config['research'],s.clock)
        result.update(provider_requests=provider.http.calls,document_directory='raw');return result
