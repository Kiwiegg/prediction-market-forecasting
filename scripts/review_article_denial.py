"""Review saved publisher bytes only; export safe structure, never challenge tokens."""
import argparse
import gzip
import json
import os
import re
import tempfile
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit


class Structure(HTMLParser):
    def __init__(self):
        super().__init__();self.tags=Counter();self.text=[];self.hidden=0;self.scripts=[];self.title=[];self.in_title=False
    def handle_starttag(self,tag,attrs):
        self.tags[tag]+=1
        if tag in ('script','style'):self.hidden+=1
        if tag=='title':self.in_title=True
        if tag=='script':self.scripts.append(dict(attrs).get('src',''))
    def handle_endtag(self,tag):
        if tag in ('script','style'):self.hidden=max(0,self.hidden-1)
        if tag=='title':self.in_title=False
    def handle_data(self,data):
        if not self.hidden:self.text.append(data)
        if self.in_title:self.title.append(data)


def profile(meta,body):
    from evidence_documents import digest
    from news_denial_policy import classification_diagnostics,ordinary_403
    html=body.decode(errors='replace');parser=Structure();parser.feed(html)
    visible=re.sub(r'\s+',' ',' '.join(parser.text)).strip().casefold()
    title=re.sub(r'\s+',' ',' '.join(parser.title)).strip().casefold()
    headers={k.lower():v for k,v in meta.get('headers',{}).items()}
    content_type=headers.get('content-type','').split(';',1)[0].strip().casefold()
    # Only vendor names/constants and boolean features leave the private runner.
    known_hosts={'ct.captcha-delivery.com','geo.captcha-delivery.com','js.datadome.co','challenges.cloudflare.com'}
    script_hosts=sorted({urlsplit(s).hostname for s in parser.scripts if urlsplit(s).hostname in known_hosts})
    known_titles=('just a moment...','access denied','forbidden','attention required! | cloudflare')
    return {'http_status':meta['http_status'],'content_type':content_type if re.fullmatch(r'[a-z0-9.+-]+/[a-z0-9.+-]+',content_type) else 'unrecognized',
        'body_sha256':digest(body),'body_bytes':len(body),'truncated':bool(meta.get('truncated')),
        'header_names':sorted(headers),'set_cookie_present':'set-cookie' in headers,
        'authentication_challenge_present':'www-authenticate' in headers or 'proxy-authenticate' in headers,
        'cf_mitigated_challenge':headers.get('cf-mitigated','').casefold()=='challenge',
        'datadome_header_present':any(k.startswith('x-datadome') for k in headers),
        'document_tags':dict(sorted(parser.tags.items())),'visible_text_characters':len(visible),
        'known_title':title if title in known_titles else None,
        'title_matches_publisher_host':title in ((urlsplit(meta['url']).hostname or ''),(urlsplit(meta['url']).hostname or '').removeprefix('www.')),
        'visible_phrases':{phrase:phrase in visible for phrase in ('please enable js and disable any ad blocker','enable javascript and cookies','verify you are human','checking your browser','performing security verification','access denied','forbidden')},
        'known_challenge_script_hosts':script_hosts,
        'datadome_options_present':bool(re.search(r'\b(?:var\s+)?dd\s*=\s*\{',html)),
        'cloudflare_options_present':'_cf_chl_opt' in html,
        'cloudflare_challenge_path_present':'/cdn-cgi/challenge-platform/' in html,
        'current_classifier':ordinary_403(meta,body),'current_diagnostics':classification_diagnostics(meta,body),
        'raw_body_or_header_values_included':False}


def inspect(objects,expected_uuid,destination):
    from evidence_documents import digest,canonical
    from actions_storage import Checkpoints,StorageStop
    from audit_live_pilot import ReadOnlyState
    from unittest.mock import patch
    import cloud_prospective as cloud
    raw,_=objects.read('root.json');root=json.loads(raw or b'{}')
    if not expected_uuid or root.get('store_uuid')!=expected_uuid or root.get('owner') is not None:
        raise StorageStop('Original idle checkpoint required')
    cp=Checkpoints(objects,expected_uuid);cp.root=root;cp.restore(destination)
    state=ReadOnlyState(destination,json.loads(cloud.CONFIG.read_text()))
    with state.db() as c:
        circuits=[dict(r) for r in c.execute('SELECT * FROM circuits ORDER BY id')]
        ledger=[dict(r) for r in c.execute('SELECT * FROM requests ORDER BY id')]
    host=[r for r in circuits if r['id']=='host:apnews.com']
    if len(host)!=1:raise ValueError('Exactly one preserved AP denial required')
    url=json.loads(host[0]['body'])['url'];matches=[]
    with patch('urllib.request.OpenerDirector.open',side_effect=AssertionError('No publisher/model access permitted')):
        for p in sorted(state.root.glob('jobs/*/news/raw/*.json')):
            meta=json.loads(p.read_text())
            if meta.get('url')!=url:continue
            body=gzip.decompress(p.with_suffix('.body.gz').read_bytes())
            if digest(body)!=meta['body_sha256']:raise ValueError('Preserved response hash mismatch')
            matches.append({'source_url':url,'retrieved_at_utc':meta['retrieved_at_utc'],'profile':profile(meta,body)})
        if len(matches)!=1:raise ValueError('Unique original response required')
        from audit_blocked_campaign import audit
        from campaign_recovery import preconditions
        accounting=audit(state)
        replays=[j['private_replay'] for j in accounting['jobs']]
        try:
            preconditions(state,accounting)
            adoption={'verified':True}
        except ValueError as e:adoption={'verified':False,'reason':str(e)}
    if any(digest((Path(destination)/n).read_bytes())!=sha for n,sha in cp.files.items()):raise StorageStop('Private files changed')
    if objects.read('root.json')[0]!=raw:raise StorageStop('Root changed during review')
    return {'schema_version':1,'snapshot_sha256':root['snapshot'],'owner':None,'source':matches[0],
        'paid_claims':sum(r['kind']!='article' for r in ledger),'reserved_usd':sum(r['usd'] for r in ledger),
        'ledger_sha256':digest(canonical(ledger)),'circuits_sha256':digest(canonical(circuits)),
        'private_files_verified_unchanged':len(cp.files),'private_replays':replays,
        'policy_adoption_preconditions':adoption,
        'policy_authorization_present':(state.root/'news_denial_authorization.json').exists(),
        'remote_writes':0,'publisher_requests':0,'paid_calls':0,'raw_private_responses_included':False}


def main():
    from actions_campaign import settings
    from actions_storage import S3Objects
    from evidence_documents import canonical
    from inspect_actions_storage import sanitized
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    objects=S3Objects(os.environ.get('NBA_ACTIONS_BUCKET'),settings()['storage_prefix'],os.environ.get('AWS_REGION'),os.environ.get('NBA_ACTIONS_ENDPOINT'))
    with tempfile.TemporaryDirectory(prefix='nba-article-review-') as tmp:result=inspect(objects,os.environ.get('NBA_ACTIONS_STORE_UUID'),Path(tmp)/'state')
    result=sanitized(result,os.environ);args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_bytes(canonical(result)+b'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
