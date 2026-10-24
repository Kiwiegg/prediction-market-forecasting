# Schedule discovery amendment v1: operations

Use this narrowly authorized successor to the blocked original Phase1 command.
The [amendment](../experiments/prospective_schedule_amendment_v1.md) changes only
schedule transport/validation. All original source, timing, forecasting and
evaluation assets remain byte-identical. Its separate entry point avoids
invalidating the frozen original orchestration registry or previous public replay.

```sh
# No network, credentials, or provider costs.
.venv/bin/python scripts/prospective_discovery.py
.venv/bin/python -m unittest discover -s tests -q
.venv/bin/python scripts/prospective_study.py --replay reports/prospective_phase1/mock_validation

# Exactly one newly authorized attempt; no automatic retry or alternate output.
# These paid opt-ins matter ONLY if a corroborated game is within ±5 minutes.
.venv/bin/python scripts/prospective_discovery.py --live-attempt --allow-network \
  --allow-search --allow-inference

# Private extraction replay; successful or first-denial partial captures supported.
.venv/bin/python scripts/prospective_discovery.py \
  --replay captures/prospective_discovery_v1/attempt

# Sanitized audit: hashes, source references, timing and decisions only.
.venv/bin/python scripts/prospective_discovery.py \
  --export-audit captures/prospective_discovery_v1/attempt \
  --output reports/prospective_schedule_discovery_v1/audit
.venv/bin/python scripts/prospective_discovery.py \
  --verify-audit reports/prospective_schedule_discovery_v1/audit
```

For discovery alone omit both paid opt-ins. The CLI never requests paid providers
without an eligible fixture, both opt-ins and available process credentials. Load
trusted `.env` values without echoing or shell tracing if needed; never commit them.
All costs, native claim markers, raw captures and credentials stay private. If
eligible collection succeeds, use the original `prospective_study.py --replay`
against the new attempt and its native evidence/forecasts for private replay;
the new discovery replay separately validates both-team schedule corroboration.
The original collector/forecasters never receive prices or final target outcomes.

The original stop journal remains at
`captures/prospective_phase1/access_denial.json`, bound by hash in the new immutable
authorization. New requests/decisions are under
`captures/prospective_discovery_v1/attempt`. A subsequent non-exempt source or paid
denial creates `captures/prospective_discovery_v1/access_denial.json`; do not remove
either journal or retry in another directory. A successful discovery outside the
window spends nothing on research/inference and is not an eligible forecast.

Public audit verification checks sanitized hashes and provenance references; it
does not authenticate publisher history or replay missing private raw documents.
Private replay verifies original raw hashes and deterministic schedule extraction.
Both ESPN team schedules are one provider, not independent corroboration across
publishers. No live reliability claim follows from mocked source responses.
