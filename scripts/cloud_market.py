"""Independent market lane. Evidence/forecast implementation never imports this."""
import json
import time

from cloud_state import durable_json, process_lock
from cloud_prospective import CloudDocuments, TargetSession, windows, native, discovery, SourceBudget, check_assets,target_discovery_days
from prospective_evaluate import quote_record, verify_source_capture
from build_dataset import event_ticker
from evidence_documents import digest
from investigate_kalshi import BASE, iso
from prospective_sources import url


class MarketEngine:
    def __init__(self,state,allow_live=False,clock_sleep=time.sleep):self.state=state;self.allow_live=allow_live;self.sleep=clock_sleep
    def capture(self,key,folder):
        s=self.state;job=s.job(key);game=job['game'];w=windows(game,s.config)
        if not self.allow_live or job['mode']!='live_explicit_opt_in':raise ValueError('Independent market network disabled')
        check_assets(True)
        if s.clock()>w['target']:raise ValueError('No post-cutoff benchmark/backfill')
        session=TargetSession(folder/'raw',s,key,'market_revalidation',w['target']);session.registered_id=game['game_id']
        games,decisions=discovery.discover_verified(session,s.clock(),target_discovery_days(game,s.clock()))
        durable_json(folder/'schedule.json',{'games':games,'decisions':decisions})
        if len(games)!=1 or discovery.differences(game,games[0]):raise ValueError('Market schedule mapping changed/unverified')
        event=event_ticker(game);milestone=url(BASE+'/milestones',limit=100,related_event_ticker=event)
        quote=BASE+'/markets/'+event+'-'+game['home_code']
        docs=CloudDocuments(folder/'raw',lambda u:u in (milestone,quote),s,key,'market',w['target'])
        mm,mb=docs.get(milestone)
        if mm['http_status']!=200 or mm['truncated']:raise ValueError('Milestone unavailable')
        send=w['target']-s.config['market']['quote_seconds_before_target']
        while s.clock()<send:self.sleep(min(1,send-s.clock()))
        qm,qb=docs.get(quote)
        if qm['http_status']!=200 or qm['truncated']:raise ValueError('Quote unavailable')
        record=quote_record(game,json.loads(qb).get('market',{}),json.loads(mb),native.aware(qm['retrieved_at_utc']))
        durable_json(folder/'quote.json',record)
        durable_json(folder/'manifest.json',{str(p.relative_to(folder)):digest(p.read_bytes()) for p in folder.rglob('*') if p.is_file()})
        return {'eligible':record['eligible'],'missing_reason':record['missing_reason'],'retrieved_at_utc':record['retrieved_at_utc']}
    def advance(self,key):
        s=self.state;job=s.job(key);w=windows(job['game'],s.config)
        with process_lock(s.job_dir(key)/'market.lock'):
            if s.has(key,'market'):return {'status':'market_finished_or_uncertain'}
            if s.clock()<w['target']-s.config['market']['launch_seconds_before_target']:return {'status':'pending'}
            try:return s.stage(key,'market',lambda folder:self.capture(key,folder))
            except (Exception,native.Halt) as e:return {'eligible':False,'missing_reason':str(e)}
