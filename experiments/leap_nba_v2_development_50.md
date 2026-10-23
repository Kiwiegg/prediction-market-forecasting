# Frozen v2: full development execution and diagnostics

The [diagnostic plan](leap_nba_v2_development_50_analysis_plan.json) must be committed with the tested execution/analysis code before paid inference. The original historical protocol, four prompts, schemas, mapping, projections, settings and cache identities stay byte-identical to `8520406`. The new execution wrapper reuses the existing cache/claim/HTTP/aggregation functions; it adds access-denial stopping for HTTP401/403/407/451 and explicit provider permission/authentication errors (including error/HTML denial pages), plus offline interruption sealing. It changes no forecast method.

Default planning verifies the original pilot, all direct/v1 merged records, original frozen Git assets, source bindings and every existing matching cache entry. It loads only development packets, never reserved packets. Original requests with uncertain claims prevent paid execution. Direct and v1 are verification/evaluation inputs only; their inference runners are never invoked to request a new forecast. The native shared cache remains `captures/leap_nba_v2_phase2_cache`. No cache override or retry flag is provided by this execution CLI.

```sh
# No network or credentials required.
.venv/bin/python scripts/run_v2_development.py --plan
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/run_v2_development.py --mock
.venv/bin/python scripts/analyze_v2_development.py --run captures/leap_nba_v2_phase2_development_50/mock --output captures/leap_nba_v2_phase2_development_50/mock_analysis --allow-mock

# After committing this plan and passing tests, save immutable preflight metadata.
.venv/bin/python scripts/run_v2_development.py --plan --save-preflight

# Requires the separately authorized 180-call/$5 development budget and a key
# exported into this process. .env is ignored and not automatically loaded;
# load only a trusted local file with shell tracing disabled.
.venv/bin/python scripts/run_v2_development.py --live --allow-network --allow-inference

# After completion/access-denial stop, verify and analyze without new calls.
.venv/bin/python scripts/run_v2_development.py --verify captures/leap_nba_v2_phase2_development_50/run
.venv/bin/python scripts/analyze_v2_development.py --run captures/leap_nba_v2_phase2_development_50/run --output reports/leap_nba_v2_development_50
.venv/bin/python scripts/analyze_v2_development.py --replay reports/leap_nba_v2_development_50
```

Keyboard interruption seals partial work automatically. After an external process kill, use `scripts/run_v2_development.py --seal-interrupted` to seal cached observations and mark unknown claims without network calls. A claimed request with no terminal record stays explicitly uncertain; do not delete the claim or change output/cache directories to resend it. Completed output is immutable. The existing full-development authorization registry also prevents launching another paid batch in a new output directory. No paid retries or resumption after denial are authorized.

Public outputs contain all 50 rows, A's five-method intersection, B's seven-method intersection, exclusions, paired scores/differences, fixed-seed bootstrap intervals, calibration, directionality and group/injury/dependence/removal diagnostics, and a usage/failure/reservation audit. A uses all eligible v2/direct/market games; B additionally requires v1, so their denominators can differ. Bootstrap comparisons against direct/Kalshi use A; comparisons against v1 use B. Every figure retains its n and IDs. Classification uses p>=0.5, extremes use p<=0.1 or p>=0.9. These secondary definitions were fixed before inference and do not tune the model.

Claims, reservation timestamps and response hashes permit offline consistency checks; HTTP bodies and credentials stay private. Public replay reprojects exactly the frozen development evidence, checks original pilot identity, reaggregates and rescores, and reproduces all derived outputs. Private verification additionally checks HTTP bytes, parsers and denial classifications. Neither replay recreates provider inference or proves independent statistical calibration. Prior v1 merged resource totals describe selected effective observations; its superseded failures and retry costs remain in the original attempt audit rather than being erased or attributed to new v2 spend.
