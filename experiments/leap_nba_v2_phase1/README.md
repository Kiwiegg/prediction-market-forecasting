# Running the frozen synthetic experiment

Read [protocol.md](protocol.md) before inference. This phase uses 30 fictional cases, two elicitation methods and 54 distinct requests; repeated identical payloads reuse immutable cache observations. No historical packets or outcomes are loaded by these commands. Frozen assets are registered in `frozen_assets.json`; `load_phase()` checks their content hashes and regenerates the cases before any run or replay.

```sh
# No credential, network, historical inference or costs.
.venv/bin/python scripts/run_synthetic_elicitation.py --plan
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/run_synthetic_elicitation.py --mock --output captures/leap_nba_v2_phase1/mock
.venv/bin/python scripts/run_synthetic_elicitation.py --verify captures/leap_nba_v2_phase1/mock
.venv/bin/python scripts/evaluate_synthetic_elicitation.py --run captures/leap_nba_v2_phase1/mock --output captures/leap_nba_v2_phase1/mock_public

# Only after committing the protocol and tested implementation, and obtaining authorization.
# ANTHROPIC_API_KEY must be exported in the invoking process. .env is ignored and
# is not automatically loaded; load a trusted local .env with shell tracing disabled.
.venv/bin/python scripts/run_synthetic_elicitation.py --live --allow-network --allow-inference --output captures/leap_nba_v2_phase1/paid
.venv/bin/python scripts/run_synthetic_elicitation.py --verify captures/leap_nba_v2_phase1/paid
.venv/bin/python scripts/evaluate_synthetic_elicitation.py --run captures/leap_nba_v2_phase1/paid --output reports/leap_nba_v2_phase1
.venv/bin/python scripts/evaluate_synthetic_elicitation.py --replay reports/leap_nba_v2_phase1
```

Default execution is a no-cost plan. Live execution requires all three flags, the credential and a full-plan cost reservation within $1/120 requests. Configuration is frozen, not tunable from the command line. There are no historical-subset, case-limit, retry, model-override or tool options. An authorization registry binds this single paid batch to its directory. Successful, invalid and failed requests are terminal, and an interrupted uncertain attempt cannot be resent automatically. A first HTTP 403 stops new requests immediately. Remaining slots are exported as missing; prior observations survive. A completed immutable run can be read repeatedly without additional requests. Never delete the authorization registry or cache to repeat an attempt.

Private raw bodies, malformed responses, wire requests, clocks and credentials stay outside Git under ignored `captures/`. Public exports contain structured assessments, errors, usage, conservative cost estimates, hashes and diagnostics. Public replay verifies the registered synthetic cases and request identities, remaps assessments and recomputes every diagnostic/accounting total without private bodies or credentials. Private verification additionally checks raw-body hashes and reproduces response parsing. No historical scoring is performed.

The deliberately simple mock returns neutral assessments for informative cases; its purpose is to exercise validation, arithmetic, output sealing and failure diagnostics, not simulate favorable empirical results. Restricted response schemas expose unsupported fields but cannot reveal unspoken invented reasoning. The numerical mapping is heuristic and must not be described as calibrated evidence likelihoods.
