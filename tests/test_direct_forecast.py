import copy
import csv
import io
import json
import math
import os
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from direct_forecast import (DEFAULT_CONFIG, PROMPT_HASH, cached_forecast, load_evidence,
    load_experiment, plan_experiment, request_spec, run_experiment, strict_probability_json, verify_experiment)
from evaluate_forecasts import brier, calibration, evaluate_experiment, evaluate_rows, log_loss, market_probability
from evidence_documents import canonical, digest
from forecast_split import DEFAULT_DATA, DEFAULT_SPLIT, immutable_json, load_split, split_manifest
from research_providers import CapturedHTTP
from shared_evidence import freeze_packet, load_game_snapshot

CONFIG = json.loads(DEFAULT_CONFIG.read_text())
SPLIT = load_split()
PILOT = SPLIT['run_order']['development'][:5]
CUTOFF = '2026-01-01T00:00:00Z'


class Response:
    status = 200
    def __init__(self, value): self.body = value if isinstance(value, bytes) else canonical(value)
    def read(self, n): return self.body[:n]
    def __enter__(self): return self
    def __exit__(self, *args): pass


def reply(value=.7, **changes):
    return {'model': CONFIG['model'], 'role': 'assistant', 'stop_reason': 'end_turn',
            'usage': {'input_tokens': 100, 'output_tokens': 15},
            'content': [{'type': 'text', 'text': json.dumps({'home_win_probability': value})}], **changes}


def factory(opener):
    return lambda folder, allow_network=False: CapturedHTTP(folder, allow_network, opener)


def quote(gid='a', outcome='1', price=.6):
    return {'game_id': gid, 'home_yes_outcome': outcome, 'home_mapping_verified': 'True', 'market_status': 'finalized',
        'market_open_at_cutoff': 'True', 'cutoff_utc': CUTOFF, 'preferred_midpoint_price': str(price),
        'preferred_quote_bid': str(price - .01), 'preferred_quote_ask': str(price + .01),
        'preferred_quote_candle_end_utc': '2025-12-31T23:40:00Z', 'preferred_quote_candle_end_lag_seconds': '1200'}


class SplitAndIsolationTests(unittest.TestCase):
    def test_fixed_split_months_seed_and_assignment_ignore_other_fields(self):
        self.assertEqual(split_manifest(), SPLIT)
        self.assertEqual(len(SPLIT['run_order']['development']), 50)
        self.assertEqual(len(SPLIT['run_order']['evaluation']), 150)
        self.assertFalse(set(SPLIT['run_order']['development']) & set(SPLIT['run_order']['evaluation']))
        for month, counts in SPLIT['monthly_counts'].items():
            self.assertLessEqual(abs(counts['development'] - counts['total'] / 4), 1)
            self.assertEqual(counts['development'] + counts['evaluation'], counts['total'])
        selection = json.loads((DEFAULT_DATA / 'selection_manifest.json').read_text())
        for g in selection['games']:
            g.update(outcome='FAKE_LEAK', market_price=.99, injury_available=False)
        selection['games'].reverse()
        with tempfile.TemporaryDirectory() as tmp:
            immutable_json(Path(tmp) / 'selection_manifest.json', selection)
            self.assertEqual(split_manifest(tmp), SPLIT)

    def test_request_is_exact_shared_packet_and_contains_no_other_context(self):
        packet = load_evidence(DEFAULT_DATA, PILOT[0])
        self.assertEqual(packet, load_game_snapshot(DEFAULT_DATA, PILOT[0]))  # future consumer, same loader/hash
        spec = request_spec(packet, CONFIG)
        payload = spec['wire']['payload']
        self.assertEqual(json.loads(payload['messages'][0]['content']), packet)
        self.assertEqual(len(payload['messages']), 1)
        self.assertNotIn('tools', payload)
        self.assertNotIn('thinking', payload)
        self.assertEqual(digest((DEFAULT_CONFIG.parents[1] / 'prompts/direct_home_win_v1.txt').read_bytes()), PROMPT_HASH)
        for key in ('outcome', 'market_price', 'evaluation', 'audit'):
            corrupted = copy.deepcopy(packet); corrupted[key] = 'forbidden'
            with self.assertRaises(ValueError): request_spec(corrupted, CONFIG)
        stale = copy.deepcopy(packet); stale['neutral_site'] = not stale['neutral_site']
        with self.assertRaises(ValueError): request_spec(stale, CONFIG)

    def test_forecasting_does_not_open_evaluation_or_audit_files(self):
        original = Path.open
        forbidden = {'evaluation.csv', 'game_history.jsonl', 'market_metadata.json', 'market_lineage.jsonl', 'evidence_lineage.jsonl', 'injury_lineage.jsonl'}
        def guarded(path, *args, **kwargs):
            if path.name in forbidden:
                raise AssertionError('Evaluation/audit file touched during inference')
            return original(path, *args, **kwargs)
        config = dict(CONFIG, provider='mock', model='offline-constant-0.5')
        with tempfile.TemporaryDirectory() as tmp, patch.object(Path, 'open', guarded), \
                patch('urllib.request.OpenerDirector.open', side_effect=AssertionError('No network')):
            plan, specs = plan_experiment(DEFAULT_DATA, DEFAULT_SPLIT, config, limit=2)
            result = run_experiment(plan, specs, Path(tmp)/'run', Path(tmp)/'cache', max_paid_calls=0, max_cost=0)
            self.assertEqual(result['successful_forecasts'], 2)

    def test_reserved_subset_fails_before_loading_packets_or_outcomes(self):
        with patch('direct_forecast.load_evidence') as loader:
            with self.assertRaises(ValueError):
                plan_experiment(DEFAULT_DATA, DEFAULT_SPLIT, CONFIG, subset='evaluation')
            loader.assert_not_called()
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)/'reserved'; folder.mkdir()
            immutable_json(folder/'run.json', {'subset':'evaluation'})
            with self.assertRaises(ValueError): evaluate_experiment(folder, Path(tmp)/'out')
            with self.assertRaises(ValueError): verify_experiment(folder)


class ProbabilityAndProviderTests(unittest.TestCase):
    def test_strict_probability_json_and_boundaries(self):
        for p in (0, .5, 1):
            self.assertEqual(strict_probability_json(json.dumps({'home_win_probability':p})), p)
        for text in ('bad', '[]', '{}', '{"home_win_probability":true}', '{"home_win_probability":"0.5"}',
                     '{"home_win_probability":NaN}', '{"home_win_probability":1e500}', '{"home_win_probability":null}',
                     '{"home_win_probability":-0.1}', '{"home_win_probability":1.1}',
                     '{"home_win_probability":0.5,"reason":"text"}',
                     '{"home_win_probability":0.5,"home_win_probability":0.6}',
                     '```json\n{"home_win_probability":0.5}\n```'):
            with self.subTest(text=text), self.assertRaises((ValueError, TypeError)):
                strict_probability_json(text)

    @patch.dict(os.environ, {'ANTHROPIC_API_KEY':'test-forecast-secret'})
    def test_real_adapter_mocked_success_failure_raw_and_usage(self):
        spec = request_spec(load_evidence(DEFAULT_DATA, PILOT[0]), CONFIG)
        cases = [reply(0), reply(1), reply(content=[{'type':'text','text':'malformed'}]),
                 reply(stop_reason='max_tokens'), reply(content=[{'type':'tool_use'}]),
                 reply(usage={}), reply(usage={'input_tokens':100,'output_tokens':129}),
                 reply(usage={'input_tokens':100,'output_tokens':15,'cache_creation_input_tokens':1}),
                 reply(role='user'), b'not-provider-json']
        for i, response in enumerate(cases):
            with self.subTest(case=i), tempfile.TemporaryDirectory() as tmp:
                opener = Mock(); opener.open.return_value = Response(response)
                record = cached_forecast(spec, CONFIG, tmp, True, factory(opener))
                self.assertEqual(record['status'], 'success' if i < 2 else 'failed')
                self.assertTrue(record['raw_response'])
                self.assertEqual(record['raw_response']['http_status'], 200)
                if i < 2:
                    self.assertEqual(record['home_win_probability'], i)
                    self.assertEqual(record['usage']['input_tokens'],100)
                else:
                    self.assertIsNone(record['home_win_probability'])
                again = cached_forecast(spec, CONFIG, tmp, True, factory(opener))
                self.assertEqual(record, again); opener.open.assert_called_once()
                for f in Path(tmp).rglob('*.json'):
                    self.assertNotIn('test-forecast-secret',f.read_text())

    @patch.dict(os.environ, {'ANTHROPIC_API_KEY':'fixture'})
    def test_provider_http_failure_and_uncertain_crash_never_retry(self):
        spec = request_spec(load_evidence(DEFAULT_DATA, PILOT[0]), CONFIG)
        with tempfile.TemporaryDirectory() as tmp:
            opener = Mock()
            opener.open.side_effect = urllib.error.HTTPError(spec['wire']['url'],429,'limit',{},io.BytesIO(b'limited'))
            first = cached_forecast(spec, CONFIG, tmp, True, factory(opener))
            second = cached_forecast(spec, CONFIG, tmp, True, factory(opener))
            self.assertEqual(first,second); self.assertEqual(first['status'],'failed')
            self.assertEqual(first['raw_response']['http_status'],429); opener.open.assert_called_once()
        with tempfile.TemporaryDirectory() as tmp:
            immutable_json(Path(tmp)/spec['key']/'attempt.json', {'uncertain_previous_attempt':True})
            opener = Mock()
            record = cached_forecast(spec, CONFIG, tmp, True, factory(opener))
            self.assertEqual(record['status'],'failed'); opener.open.assert_not_called()

    def test_cache_identity_evidence_model_settings_and_tamper(self):
        packet=load_evidence(DEFAULT_DATA,PILOT[0]); spec=request_spec(packet,CONFIG)
        for config in (dict(CONFIG,model='another-model'), dict(CONFIG,provider='json_gateway',endpoint='https://gateway.example/forecast'),
                       dict(CONFIG,generation=dict(CONFIG['generation'],max_tokens=64))):
            self.assertNotEqual(request_spec(packet,config)['key'],spec['key'])
        with tempfile.TemporaryDirectory() as tmp:
            changed=copy.deepcopy(packet);changed['neutral_site']=not changed['neutral_site']
            frozen=freeze_packet(changed,Path(tmp)/'evidence')
            self.assertNotEqual(request_spec(frozen,CONFIG)['key'],spec['key'])
            mock=dict(CONFIG,provider='mock',model='offline-constant-0.5'); mspec=request_spec(packet,mock)
            cached_forecast(mspec,mock,Path(tmp)/'cache')
            path=Path(tmp)/'cache'/mspec['key']/'forecast.json'
            data=json.loads(path.read_text());data['home_win_probability']=.9;path.write_text(json.dumps(data))
            with self.assertRaises(ValueError):cached_forecast(mspec,mock,Path(tmp)/'cache')

    @patch.dict(os.environ, {'ANTHROPIC_API_KEY':'fixture'})
    def test_configurable_gateway_probability_contract(self):
        config=dict(CONFIG,provider='json_gateway',endpoint='https://gateway.example/forecast')
        spec=request_spec(load_evidence(DEFAULT_DATA,PILOT[0]),config)
        opener=Mock();opener.open.return_value=Response({'model':config['model'],'stop_reason':'end_turn',
            'response':{'home_win_probability':.4},'usage':{'input_tokens':100,'output_tokens':15}})
        with tempfile.TemporaryDirectory() as tmp:
            r=cached_forecast(spec,config,tmp,True,factory(opener))
            self.assertEqual(r['home_win_probability'],.4)
            request=opener.open.call_args.args[0]
            self.assertEqual(json.loads(json.loads(request.data)['messages'][0]['content'])['evidence_snapshot_sha256'],spec['evidence_sha256'])
        for bad in (dict(CONFIG,endpoint='https://gateway.example/forecast'), dict(CONFIG,api_key='not-a-real-key'),
                    dict(config,endpoint='https://gateway.example/forecast?token=not-a-real-key')):
            with self.assertRaises(ValueError):request_spec(load_evidence(DEFAULT_DATA,PILOT[0]),bad)


class RunnerAndEvaluationTests(unittest.TestCase):
    def test_verification_does_not_create_or_repair_missing_cache_records(self):
        config=dict(CONFIG,provider='mock',model='offline-constant-0.5')
        plan,specs=plan_experiment(DEFAULT_DATA,DEFAULT_SPLIT,config,limit=1)
        with tempfile.TemporaryDirectory() as tmp:
            output,cache=Path(tmp)/'run',Path(tmp)/'cache'
            run_experiment(plan,specs,output,cache)
            missing=cache/specs[0]['key']/'forecast.json';missing.unlink()
            before={str(p):p.read_bytes() for p in Path(tmp).rglob('*') if p.is_file()}
            with self.assertRaises(ValueError):verify_experiment(output)
            self.assertEqual(before,{str(p):p.read_bytes() for p in Path(tmp).rglob('*') if p.is_file()})

    def test_mock_idempotency_offline_replay_and_refusal_to_overwrite(self):
        config=dict(CONFIG,provider='mock',model='offline-constant-0.5')
        plan,specs=plan_experiment(DEFAULT_DATA,DEFAULT_SPLIT,config,limit=2)
        with tempfile.TemporaryDirectory() as tmp, patch('urllib.request.OpenerDirector.open',side_effect=AssertionError('No network')):
            output,cache=Path(tmp)/'run',Path(tmp)/'cache'
            result=run_experiment(plan,specs,output,cache)
            before={str(p):p.read_bytes() for p in output.rglob('*') if p.is_file()}
            self.assertEqual(run_experiment(plan,specs,output,cache),result)
            self.assertEqual(before,{str(p):p.read_bytes() for p in output.rglob('*') if p.is_file()})
            self.assertEqual(verify_experiment(output),result)
            bad=copy.deepcopy(plan);bad['config']['model']='new-model'
            with self.assertRaises(ValueError):run_experiment(bad,specs,output,cache)
            (output/'forecasts'/(PILOT[0]+'.json')).write_text('{}')
            with self.assertRaises(ValueError):load_experiment(output)

    @patch.dict(os.environ, {'ANTHROPIC_API_KEY':'fixture'})
    def test_budgets_pre_call_and_cache_shared_across_experiments(self):
        plan,specs=plan_experiment(DEFAULT_DATA,DEFAULT_SPLIT,CONFIG,limit=2)
        opener=Mock();opener.open.return_value=Response(reply())
        with tempfile.TemporaryDirectory() as tmp:
            cache=Path(tmp)/'cache'
            first=run_experiment(plan,specs,Path(tmp)/'one',cache,max_paid_calls=1,max_cost=1,allow_paid=True,transport_factory=factory(opener))
            self.assertEqual(first['successful_forecasts'],1);self.assertEqual(first['not_attempted'],1)
            opener.open.assert_called_once()
            second=run_experiment(plan,specs,Path(tmp)/'two',cache,max_paid_calls=0,max_cost=0,allow_paid=True,transport_factory=factory(opener))
            self.assertEqual(second['successful_forecasts'],1);self.assertEqual(second['paid_call_reservations'],0)
            opener.open.assert_called_once()
            third=run_experiment(plan,specs,Path(tmp)/'three',Path(tmp)/'fresh',max_paid_calls=2,max_cost=0,allow_paid=True,transport_factory=factory(opener))
            self.assertEqual(third['successful_forecasts'],0);self.assertEqual(third['not_attempted'],2)
            opener.open.assert_called_once()

    def test_scores_clipping_buckets_and_paired_missingness(self):
        self.assertAlmostEqual(brier(.8,1),.04)
        self.assertAlmostEqual(log_loss(.8,1),-math.log(.8))
        self.assertAlmostEqual(log_loss(0,1),-math.log(1e-15))
        self.assertAlmostEqual(log_loss(1,0),-math.log1p(-(1-1e-15)))
        self.assertEqual(brier(1,1),0)
        self.assertEqual(brier(.5,0),.25)
        records=[{'game_id':g,'evidence_sha256':'test','status':s,'home_win_probability':p}
                 for g,s,p in [('a','success',.8),('b','success',0),('c','failed',None),('d','not_attempted_budget',None),('e','success',1)]]
        labels={g:quote(g) for g in 'abcde'};labels['b']['preferred_midpoint_price']='';labels['e']['home_yes_outcome']=''
        rows,summary=evaluate_rows(records,labels,{g:CUTOFF for g in 'abcde'})
        self.assertEqual(summary['coverage']['successful_responses'],3)
        self.assertEqual(summary['coverage']['failed_responses'],1)
        self.assertEqual(summary['coverage']['not_attempted_budget'],1)
        self.assertEqual(summary['coverage']['missing_outcomes'],1)
        self.assertEqual(summary['paired']['game_ids'],['a'])
        self.assertEqual(summary['forecast_available']['direct']['n'],2)
        for method in ('direct','kalshi','constant_50'):self.assertEqual(summary['paired'][method]['n'],1)
        self.assertAlmostEqual(rows[0]['direct_minus_market_brier'],.04-.16)
        self.assertIsNone(rows[2]['home_win_probability'])
        self.assertEqual(sum(b['count'] for b in summary['calibration_paired']['direct']),1)
        buckets=calibration([{'p':0,'outcome':0},{'p':1,'outcome':1}],'p')
        self.assertEqual(buckets[0]['count'],1);self.assertEqual(buckets[-1]['count'],1)
        _,empty=evaluate_rows([],{},{});self.assertIsNone(empty['paired']['direct']['brier_score'])

    def test_market_twenty_minute_boundaries_and_invalid_prices(self):
        self.assertEqual(market_probability(quote(),CUTOFF),(.6,None))
        for changed in ({'preferred_quote_candle_end_lag_seconds':'1201'},
                        {'preferred_quote_candle_end_utc':'2026-01-01T00:00:01Z','preferred_quote_candle_end_lag_seconds':'-1'},
                        {'preferred_quote_bid':'.7','preferred_quote_ask':'.5'},
                        {'preferred_midpoint_price':'nan'},{'home_mapping_verified':'False'},
                        {'cutoff_utc':'2026-01-01T00:00:01Z'}):
            self.assertIsNone(market_probability(dict(quote(),**changed),CUTOFF)[0])

    def test_evaluator_requires_seal_and_skips_reserved_rows_before_parsing(self):
        config=dict(CONFIG,provider='mock',model='offline-constant-0.5')
        plan,specs=plan_experiment(DEFAULT_DATA,DEFAULT_SPLIT,config,limit=2)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);out=root/'run';data=root/'data';data.mkdir()
            immutable_json(out/'run.json',plan)
            with self.assertRaises(FileNotFoundError):evaluate_experiment(out,root/'eval',allow_mock=True)
            # Only the source identity/snapshot manifests and synthetic labels
            # are used here. No real reserved outcomes are read or evaluated.
            (out/'run.json').unlink()
            run_experiment(plan,specs,out,root/'cache')
            for name in ('selection_manifest.json','evidence_snapshot_manifest.json'):
                (data/name).write_bytes((DEFAULT_DATA/name).read_bytes())
            rows=[quote(gid) for gid in PILOT[:2]]
            for r in rows:r.update(cutoff_utc='unused')
            rows.append({'game_id':SPLIT['run_order']['evaluation'][0],'home_yes_outcome':'DO_NOT_PARSE_RESERVED','preferred_midpoint_price':'DO_NOT_PARSE_RESERVED'})
            fields=set().union(*(r.keys() for r in rows))
            with (data/'evaluation.csv').open('w',newline='') as f:
                writer=csv.DictWriter(f,fieldnames=sorted(fields));writer.writeheader();writer.writerows(rows)
            summary=evaluate_experiment(out,root/'eval',dataset=data,allow_mock=True)
            self.assertEqual(summary['coverage']['planned'],2)
            self.assertEqual(summary['coverage']['successful_responses'],2)
            self.assertEqual(set(summary['forecast_available']['game_ids']),set(PILOT[:2]))
            self.assertEqual(evaluate_experiment(out,root/'eval',dataset=data,allow_mock=True),summary)


if __name__=='__main__':unittest.main()
