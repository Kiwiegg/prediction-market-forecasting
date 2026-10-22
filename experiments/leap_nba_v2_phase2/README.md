# Historical v2 pilot reproduction

Read the [frozen protocol](protocol.md). This is development-informed, not an independent test. The default scope is exactly the existing five pilot games. No command below changes packets, direct/v1 or synthetic observations, sample selection or the 20-minute market quote rule.

```sh
# No network or credentials needed.
.venv/bin/python scripts/leap_v2_forecast.py --plan
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/leap_v2_forecast.py --mock --output captures/leap_nba_v2_phase2/mock_frozen
.venv/bin/python scripts/leap_v2_forecast.py --verify captures/leap_nba_v2_phase2/mock_frozen
.venv/bin/python scripts/compare_leap_v2.py --run captures/leap_nba_v2_phase2/mock_frozen --output captures/leap_nba_v2_phase2/mock_frozen_comparison_final --allow-mock

# Only after committing the tested frozen implementation and obtaining authorization.
# Export ANTHROPIC_API_KEY into the invoking process; .env is ignored and not
# automatically loaded. Load a trusted local .env with shell tracing disabled.
.venv/bin/python scripts/leap_v2_forecast.py --live --allow-network --allow-inference --max-paid-calls 20 --max-estimated-cost-usd 1 --output captures/leap_nba_v2_phase2/paid
.venv/bin/python scripts/leap_v2_forecast.py --verify captures/leap_nba_v2_phase2/paid
.venv/bin/python scripts/compare_leap_v2.py --run captures/leap_nba_v2_phase2/paid --output reports/leap_nba_v2_pilot

# Saved public arithmetic replay, no credentials/private captures or paid calls.
.venv/bin/python scripts/compare_leap_v2.py --replay reports/leap_nba_v2_pilot
```

The plan prints source-missing groups and the whole uncached reservation, not an invoice. The private cache is `captures/leap_nba_v2_phase2_cache`; previous caches are read-only. Request identity binds the exact wire, parent and group evidence hashes, orientation and registered protocol. A's game identity and X/Y assignment stay outside model context. Native HTTP capture has a separate wire hash. No numeric v1 response can become a qualitative v2 response. All original raw responses and failed attempts remain private and immutable. Completed runs and cached terminal failures cannot be overwritten or automatically retried, including from a new output path. The first HTTP 403 seals partial results with subsequent required groups explicitly unattempted.

Legitimate source absence contributes LR=1 with an explicit skip. Valid insufficient responses are abstentions with null LR; invalid/failed/blocked required groups likewise make both final probabilities missing. Raw and conservative variants use the same observations, as does offline leave-one-group-out recomputation. Comparison scores/calibration/removal diagnostics use only the identical seven-method intersection, reporting every exclusion. Provider usage, cost and latency are separate from prior baseline inference resources.

The public bundle includes validated assessments, request/raw-body hashes, clocks, settings, mapped LRs, probabilities, per-game losses, calibration and diagnostics; no HTTP bodies/auth headers. Public replay checks frozen projections/request identities, mappings, aggregation, baseline provenance and all scores. Private `--verify` additionally checks the original captured response bytes and reparses them. Neither replay reproduces paid inference.

Future full-development inference is implemented behind **both** `--full-development --authorize-development`, all live opt-ins, and explicitly supplied `--max-paid-calls` / `--max-estimated-cost-usd` (hard ceiling 200/$10). It follows the unchanged development order and can reuse matching pilot cache records. This pilot task does not authorize or run it. The comparison command is intentionally restricted to the five-game pilot; a future development comparison needs its own authorized scope. No reserved evaluation runner exists in v2. Do not delete authorization/cache records to bypass no-retry controls.
