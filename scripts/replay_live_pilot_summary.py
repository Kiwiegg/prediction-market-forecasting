"""Offline consistency check of the sanitized pilot summary, not raw-source proof."""
import argparse
import hashlib
import json
import math
from datetime import datetime
from pathlib import Path


def verify(folder):
    folder = Path(folder)
    manifest = json.loads((folder / 'manifest.json').read_text())
    payload = (folder / 'audit.json').read_bytes()
    if hashlib.sha256(payload).hexdigest() != manifest['audit_sha256']:
        raise ValueError('Sanitized audit hash mismatch')
    a = json.loads(payload)
    if a['game_id'] != manifest['game_id'] or not all(a['checks'].values()):
        raise ValueError('Pilot checks/game identity differ')
    aware = lambda t: datetime.fromisoformat(t.replace('Z', '+00:00'))
    target, frozen, sealed = map(aware, (a['cutoff_utc'], a['frozen_at_utc'], a['sealed_at_utc']))
    if not target <= frozen <= aware(a['freeze_deadline_utc']) or not frozen <= sealed <= aware(a['forecast_deadline_utc']):
        raise ValueError('Invalid freeze/seal timing')
    if a['outcome_verified'] or a['brier_score'] is not None or a['log_loss'] is not None:
        raise ValueError('This pre-outcome audit must remain unscored')
    if a['raw_provider_responses_included']:
        raise ValueError('Private response included')
    for m in a['methods'].values():
        if m['status'] != 'success' or m['parent_hash'] != a['packet_sha256']:
            raise ValueError('Method status/shared packet differs')
        for o in m['observations']:
            if o['status'] == 'skipped_missing':
                if o['likelihood_ratio'] != 1 or not o['missing_reason'] or o['usage'] is not None:
                    raise ValueError('Invalid source-missing skip')
            elif o['status'] != 'success' or not o['raw_response_hash_verified']:
                raise ValueError('Missing successful raw-response verification')
            else:
                if not frozen <= aware(o['request_started_at_utc']) <= aware(o['response_retrieved_at_utc']) <= sealed:
                    raise ValueError('Model clock outside frozen inference interval')
        if any(not math.isfinite(p) or not 0 <= p <= 1 for p in m['probabilities'].values()):
            raise ValueError('Invalid probability')
    for method, variants in [('v1', ('leap_raw', 'leap_conservative')), ('v2', ('leap_v2_raw', 'leap_v2_conservative'))]:
        m = a['methods'][method]
        log_odds = sum(math.log(o['likelihood_ratio']) for o in m['observations'])
        for alpha, name in zip((1, .5), variants):
            if not math.isclose(m['probabilities'][name], 1 / (1 + math.exp(-alpha * log_odds)), abs_tol=1e-12):
                raise ValueError('LR aggregation differs')
    for s in a['source_metadata']:
        if s.get('retrieved_at_utc') and aware(s['retrieved_at_utc']) > target:
            raise ValueError('Post-cutoff retrieval')
    market = a['market']
    if market['eligible'] and (aware(market['retrieved_at_utc']) > target or
            not 0 < market['yes_bid'] <= market['yes_ask'] < 1 or
            not math.isclose(market['midpoint'], (market['yes_bid'] + market['yes_ask']) / 2)):
        raise ValueError('Invalid independent quote')
    obs = [o for m in a['methods'].values() for o in m['observations'] if o['status'] == 'success']
    costs = a['costs']
    for token in ('input_tokens', 'output_tokens'):
        if sum(o['usage'][token] for o in obs) != costs['forecast_tokens'][token]:
            raise ValueError('Token accounting differs')
    if len(obs) != costs['claims_by_kind']['forecast'] or not math.isclose(sum(o['estimated_cost_usd'] for o in obs), costs['forecast_configured_rate_estimate_usd']):
        raise ValueError('Forecast request/cost accounting differs')
    calls = a['provider_calls']
    if sum(c['provider'] == 'brave' for c in calls) != costs['claims_by_kind']['search'] or any(c['http_status'] != 200 for c in calls):
        raise ValueError('Provider accounting differs')
    return {'verified': True, 'game_id': a['game_id'], 'packet_sha256': a['packet_sha256'],
            'scope': 'Sanitized hash/arithmetic/clock/accounting consistency; private replay separately required'}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('folder', type=Path)
    print(json.dumps(verify(p.parse_args().folder), indent=2))
