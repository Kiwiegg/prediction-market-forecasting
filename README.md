# Historical NBA forecasting dataset

A reproducible **200-game** expansion of the Kalshi NBA 2025–26 feasibility study, with separate market evaluation data, frozen pregame team/injury packets, a direct-LLM probability baseline and LEAP-inspired structured likelihood elicitation. Python 3.10+ and the pinned PDF parser are required for the expanded build. No trading is implemented.

The [cloud news-v1 workflow](reports/prospective_cloud_news_v1/report.md) is **implemented and offline validated, not deployed or activated**. It uses a persistent Linux VM/SQLite, pre-cutoff news research, fixed T−24h information cutoff, T+5 packet freeze and T+15 forecast seal, with independent market capture. **241 tests pass**; a synthetic replay exercises all unchanged native methods against one packet. No new real provider calls or live cloud enrollment occurred. The legacy pilot and historical data remain untouched; the news cohort is separately labeled and does not restart the original100-game plan. [Deployment/activation instructions](deploy/cloud-news/README.md); no-cost plan: `.venv/bin/python scripts/cloud_prospective.py`.

The [legacy one-game pilot setup report](reports/prospective_scheduled_pilot/report.md) records Lakers at Jazz (`401909861`), originally installed/pending for **October25 05:58 Seoul**, with target **06:00 Seoul / October24 21:00 UTC**. Its218-test setup validation and initial$0 spend describe that earlier audit, not its current execution state. Cloud work does not inspect, modify, rerun or migrate that job. It retains its original ±5-minute/no-news protocol and login-persistent launchd timers. [Legacy operations](reports/prospective_scheduled_pilot_operations.md).

The [prospective Phase1 workflow](reports/prospective_phase1_operations.md) connects strict T−24h evidence capture to the unchanged Direct/v1/v2 methods through one frozen packet, with shared cost/access-denial guards and a separate postgame/market evaluator. Its [protocol](experiments/prospective_phase1_protocol.md) was committed before scored collection. [Initial validation](reports/prospective_phase1/report.md) passed **191 offline tests** and reproduced all three methods on an explicitly ineligible synthetic packet. The first real schedule GET returned **HTTP403**; work stopped without fallback or paid calls. That initial attempt left game/window eligibility and integrated live forecasting unvalidated and enabled no scheduler or campaign. Replay the sanitized mock with `.venv/bin/python scripts/prospective_study.py --replay reports/prospective_phase1/mock_validation`.

The subsequent [schedule-only operational amendment](experiments/prospective_schedule_amendment_v1.md), precommitted at `275b508`, permits an audited ESPN fallback specifically for the NBA schedule403. [Live validation](reports/prospective_schedule_discovery_v1/report.md) discovered **24 upcoming games**, all agreeing with both team schedules; none was within T−24h ±5 minutes, so no paid calls or forecasts ran (**$0**). The suite now passes **200 tests**. Use the [amended discovery entry point](reports/prospective_schedule_amendment_v1_operations.md); original journals, frozen methods, evidence and evaluation rules remain unchanged. Verify the committed sanitized audit with `.venv/bin/python scripts/prospective_discovery.py --verify-audit reports/prospective_schedule_discovery_v1/audit`.

The [final historical held-out report](reports/heldout_150/report.md) records the locked 150-game evaluation, precommitted at `3c420af`. All **914 requests** were attempted without retries; complete forecasts are direct **148/150**, v1 **144/150**, v2 **144/150**. On the **143-game primary pair**, v2 raw Brier is **0.220942** versus direct **0.209123**: difference **+0.011819**, descriptive 95% bootstrap interval **[−0.007015, +0.030833]**. V2 did not improve the observed primary score despite better strength directionality. The separate **139-game seven-method intersection**, all exclusions, calibration, usage and development comparisons are preserved. Recorded cost estimate: **$4.016163**, including unknown-usage reserves; pre-call reservations **$22.943654**. Replay without private captures: `.venv/bin/python scripts/analyze_heldout.py --authorize-evaluation --replay reports/heldout_150`. No method or historical evidence was tuned after evaluation.

The [LEAP-NBA v2 Phase 1 protocol](experiments/leap_nba_v2_phase1/protocol.md) compares blinded numeric and qualitative elicitation on 30 fixed synthetic cases. Its [paid validation report](reports/leap_nba_v2_phase1.md) records 54 successful requests ($0.090438 conservative estimate): both arms passed dominance, while qualitative also passed neutrality and swap thresholds. This is an outcome-free methodological experiment; it leaves historical data, v1 and the reserved split unchanged. See [reproduction commands](experiments/leap_nba_v2_phase1/README.md). Default command: `.venv/bin/python scripts/run_synthetic_elicitation.py --plan` (no network or cost).

The [historical v2 protocol](experiments/leap_nba_v2_phase2/protocol.md) freezes blinded strength, separate venue splits, qualitative assessments, fixed heuristic LR mapping and shared raw/conservative aggregation for the same five development pilot games. The [paid pilot report](reports/leap_nba_v2_pilot.md) records 13 successful calls ($0.031432 conservative estimate) and five paired forecasts: v2 improves on v1 but remains behind direct LLM. This is a development-informed integration comparison. See [v2 commands and safeguards](experiments/leap_nba_v2_phase2/README.md); `.venv/bin/python scripts/leap_v2_forecast.py --plan` makes no provider calls.

The [v2 full-development guide](experiments/leap_nba_v2_development_50.md) preserves the frozen forecasting method and pilot cache while adding bounded execution and a [precommitted diagnostic plan](experiments/leap_nba_v2_development_50_analysis_plan.json). It separates five-method v2 coverage from the seven-method intersection with v1, retaining every exclusion. `.venv/bin/python scripts/run_v2_development.py --plan` verifies existing records and estimates remaining costs without network calls.

The [completed v2 development report](reports/leap_nba_v2_development_50/report.md) records **50/50 forecasts**, reusing 13 pilot observations plus 114 successful new calls ($0.266344 additional conservative token estimate). On **50 identical games**, Brier scores are v2 raw 0.209781, v2 conservative 0.215781, direct 0.220757 and Kalshi 0.192294. The separate **40-game seven-method comparison** retains v1's ten failures. Bootstrap intervals, source limitations, group diagnostics and the numerical classification-boundary artifact are documented; no out-of-sample superiority is claimed. Replay sanitized outputs without private captures: `.venv/bin/python scripts/analyze_v2_development.py --replay reports/leap_nba_v2_development_50`.

The [LEAP-NBA v1 guide](reports/leap_nba_v1.md) documents four isolated evidence groups, immutable LR inference, neutral-prior Bayesian log-odds aggregation, fixed raw/conservative variants, and paired comparison with the saved direct baseline, Kalshi and constant 50%. Its [protocol](experiments/leap_nba_v1_protocol.md) was committed before paid inference. The historical sample, frozen packets, direct protocol, 50/150 split and 20-minute market-price rule remain unchanged. See the [five-game pilot report](reports/leap_nba_v1_pilot.md) for actual validation and limitations.

The [full development experiment](reports/development_50/report.md) attempted all 50 games using unchanged methods and pilot caches. Direct succeeded on 50/50; provider/transport failures left LEAP at 34/50, with no retries or imputation. Five-method scores and descriptive paired bootstrap intervals use the same **34 eligible games**; all 50 results and exclusions are preserved. [Sanitized replay](reports/development_50/manifest.json) reproduces scores, LR/contribution diagnostics, calibration, and usage without credentials: `.venv/bin/python scripts/analyze_development.py --replay reports/development_50`. The reserved 150 games were unused during this development experiment; the separately authorized final evaluation is reported above.

The separately [authorized retry and merge](reports/development_50/merged/report.md) recovered six games from 15 successful group retries, raising LEAP coverage to **40/50**. A renewed HTTP 403 stopped that batch; 24 remaining requests were not retried. Original runs and observations remain immutable, and all methods are compared on the same 40 games. Replay the merged results with `.venv/bin/python scripts/analyze_development.py --replay reports/development_50/merged`.

The [direct baseline guide](reports/direct_baseline.md) documents a fixed prompt, hash-bound evidence-only requests, immutable request caching, cost limits and a separate paired evaluator. A [precommitted split](experiments/nba_2025_26_split.json) reserves **50 development / 150 evaluation** games by month. The [implementation report](reports/direct_baseline_implementation.md) records five successful paid development forecasts ($0.039423 conservative estimated cost); the evaluation subset was kept unused at that stage. Historical results are exploratory because model memorization and historical source revisions cannot be ruled out. Prospective evidence remains the eventual primary out-of-sample evaluation.

Read the [dataset methodology](reports/dataset_methodology.md), [shared evidence collection guide](reports/evidence_collection.md), [generated coverage report](data/nba_2025_26/coverage_report.md), and [injury coverage report](data/nba_2025_26/injury_coverage_report.md). All dataset and schedule point-in-time verification flags remain **false**: source event/publication clocks support retrospective reconstruction, while historical payload versions and schedule revisions are unverified.

The [one-game prospective collector](reports/prospective_pipeline.md) integrates schedule discovery, existing statistical reconstruction, official injury PDFs and real Brave Search / Anthropic extraction adapters. Network, paid search and paid inference require separate explicit opt-ins. The [retrieval follow-up](reports/prospective_retrieval_validation.md) found one dated article and made a real Claude extraction request: one supported finding was recovered offline from its saved response, while four paraphrases stayed rejected. Estimated provider cost was $0.029774; this was an early pipeline validation, not an eligible T−24h forecast. The [first paid test](reports/prospective_paid_validation.md) and [public-source examples](reports/prospective_validation/README.md) remain separately documented.

The [focused follow-up](reports/prospective_improvements_validation.md) adds per-query quality diagnostics, separate latency/usage/cost accounting, a configurable practical timing window, and shared point-differential/home-away features. The same 200-game dataset is enriched in place from saved results; original selection, labels, market data and cutoffs remain unchanged. Older successful prospective captures remain immutable and replay to their original hashes.

New research uses two publisher-scoped topic queries, article-path filters, explicit publication metadata including page-bound JSON-LD, and tested SI/Sentinel article paths. `--live-test` caps requests at two searches, four articles, one extraction and $0.35 estimated cost. The offline-only `--reprocess` option can derive a separate frozen bundle from already captured responses; it records a new creation time and original hashes, without provider retries. No new dependency or historical dataset directory is introduced.

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Rebuild the expanded dataset from saved responses, without network access.
.venv/bin/python scripts/build_dataset.py --offline

# Rebuild in place, reusing saved responses and fetching only absent requests.
.venv/bin/python scripts/build_dataset.py

# Run leakage, temporal-boundary, blinding, lineage and consistency checks.
.venv/bin/python -m unittest discover -s tests -v

# Direct baseline: no-cost plan; network/inference are never enabled by default.
.venv/bin/python scripts/direct_forecast.py --plan
.venv/bin/python scripts/forecast_split.py --check

# Prospective research dry-run: no network/model calls or spending.
.venv/bin/python scripts/collect_prospective.py --dry-run

# Offline plan with a real captured upcoming game and deterministic queries.
.venv/bin/python scripts/collect_prospective.py --dry-run \
  --schedule-capture reports/prospective_validation/one_game_public_capture_complete

# Reproduce the committed public-source packet without credentials or network.
.venv/bin/python scripts/collect_prospective.py --replay \
  reports/prospective_validation/one_game_public_capture_complete
```

The builder checks all 30 saved team schedules, reconciles 1,230 games/82 per team, and preserves the locked 200-game selection before joining Kalshi. The selection allocates slots proportionally across all seven season months and ranks fixed hashes of game IDs within each month. Prices, outcomes, and data availability do not affect selection; unavailable observations never trigger replacement draws. Injury enrichment changes neither sampling, statistical features nor market-price selection. `--workers` controls concurrent public GET requests (default 4).

Rebuilds overwrite derived exports in the existing `data/nba_2025_26/` directory. Saved responses are immutable caches keyed by request URL, including failed requests. Offline replay raises an error for absent responses and verifies saved body hashes. The committed official injury captures are sufficient for offline PDF re-extraction; no inference is required. Existing Kalshi/ESPN captures, hashes, outcomes and statistical features are preserved.

The official season page is not a complete historical index. Within an explicit four-hour candidate grid, **130/200 games** have a report supported by the official object's timestamp, containing **1,047 player/status rows**; 12 rows flag uncertain/incomplete reason extraction. Of 400 team-games, 187 are reported, 73 are not yet submitted, and 140 are unavailable. **Independently verified historical publication: 0/200; globally verified latest report: 0/200.** Origin timestamps are not independent proof of historical public visibility. Early-season forbidden URLs remain missing; no current-news backfill or healthy-player inference is used.

`shared_evidence.load_game_snapshot` binds every future forecasting consumer to the same frozen packet hash. The integrated prospective collector adds a hash-pinned audit/source bundle and `load_for_consumer` for both future methods. Prospective `cutoff_utc` is the actual snapshot; separate timing fields record nominal T−24h, creation and deviation. Committed public-source captures are late and locally retained paid tests are early; none qualify for exact T−24h evaluation. Paid provider responses and credentials remain outside Git. See the [prospective guide](reports/prospective_pipeline.md) for real provider configuration, budgets, free discovery, explicit paid opt-ins and immutable replay. The earlier [collection guide](reports/evidence_collection.md) continues to specify historical extraction and the reusable news component.

The preferred market proxy is `preferred_midpoint_price`: the newest valid two-sided YES bid/ask candle ending at or before the cutoff with **candle-end lag <=20 minutes**. It stores the actual selected candle timestamp, lag, bid, ask, spread and midpoint. **Candle-end lag does not establish actual quote age or prove quotes were refreshed at that time**; actual quote age remains unknown. Missing quotes stay missing and never receive a trade-price fallback. The original exact-cutoff `midpoint_price` and separate `last_trade_price` are retained; trades older than 15 minutes remain flagged.

The same 200 games have **114 exact-cutoff midpoints (57%)**, **200 preferred midpoints (100%)**, and **156 fresh last trades (78%)**. Quote coverage is **155 / 187 / 197 / 200** at maximum candle-end lags of **1 / 5 / 15 / 20 minutes**. The three observations missing at 15 minutes are now covered by candles ending 17–18 minutes before the prediction cutoff. Paired price sensitivity compares exact, preferred, strictly earlier quotes, and fresh trades without computing forecasting metrics. See the coverage report for monthly missingness, remaining causes and price differences.

Expanded files under `data/nba_2025_26/`:

| File | Role |
| --- | --- |
| `selection_manifest.json` | Locked identities, rule, hashes, and monthly quotas |
| `schedule_frame.jsonl` | Schedule-only projections, including excluded Cup/postponed fixtures |
| `evidence_packets.jsonl` | **LLM-facing input only**: one allowlisted pregame packet per game |
| `evidence_snapshot_manifest.json`, `evidence_captures/` | Active game/cutoff hashes and immutable packets shared by all future consumers |
| `evidence_lineage.jsonl` | Audit-only feature game IDs and source references; keep outside LLM inputs |
| `injury_raw/`, `injury_extractions.json`, `injury_lineage.jsonl` | Official PDFs/HTML/errors, hashes, clocks, deterministic parsing, candidate decisions and uncertainty |
| `injury_coverage.csv`, `injury_coverage_by_month.csv`, `injury_summary.json`, `injury_coverage_report.md` | Injury coverage, player counts, team states, missingness and publication limitations |
| `evaluation.csv` | Target outcomes, exact/preferred/strictly earlier quote midpoints, separate trade prices, ages/lags, sensitivity eligibility, missingness and verification flags |
| `game_history.jsonl` | Audit-only normalized completed-game facts and event/publication/update clocks |
| `candle_observations.csv` | Minute observations in two-hour windows ending at each cutoff |
| `market_metadata.json`, `market_lineage.jsonl` | Full target market metadata and price/label source references |
| `coverage.csv`, `coverage_report.md`, `summary.json` | Missingness by selected game date/month, totals, extraction and API limitations |
| `price_comparisons.csv` | All-season/monthly paired price differences in percentage points; no outcome-based metrics |
| `sources.jsonl`, `raw/` | URLs, retrieval dates, source IDs, hashes, HTTP status and original compressed responses |

Only the packet file is intended as future model input. Raw ESPN summaries also contain unrelated current standings, news and odds; these are preserved for audit and never copied to packets. Blank CSV cells and omitted packet features mean unavailable/unverified, not zero. Rest measures time since the latest reliably completed game **at the cutoff**, not assumed rest at future tipoff. Source, omission and schedule semantics are specified in the methodology.

## Original 20-market feasibility study

An investigation of Kalshi's public API for **2025–26 NBA regular-season game winners**. No API key, forecasting model, agent framework, or third-party Python package is required.

Start with the [feasibility report](reports/feasibility.md) and the [20-market CSV](data/kalshi_nba_2025_26/markets.csv).

Run from the repository root with Python 3.10 or later:

```sh
# Rebuild the committed sample from saved responses, without network access.
python3 scripts/investigate_kalshi.py --offline

# Repeat the public API investigation with fresh responses in a separate directory.
python3 scripts/investigate_kalshi.py --output data/new_investigation

# Check cutoff selection and the saved sample.
.venv/bin/python -m unittest discover -s tests -v
```

The default output directory is `data/kalshi_nba_2025_26`. Existing responses are reused by URL; use a new directory for a fresh collection. Network failures and HTTP errors are retained. Incomplete discovery or failure to establish 20 finalized markets exits unsuccessfully. Public APIs and their archived coverage can change, so a new collection need not reproduce identical responses.

The sample consists of the first five ESPN-listed games, ordered by recorded start time and game ID, on each of October 22, December 1, January 15, and March 15. Each row selects the **home team's YES contract**, giving 20 distinct games. Dates and the selection rule are fixed before price/outcome inspection. This is a small calendar sample, not a season-wide coverage estimate.

Files in `data/kalshi_nba_2025_26/`:

| File | Contents |
| --- | --- |
| `markets.csv` | Outcomes, timestamp sources, cutoff prices, staleness, missing-data flags |
| `manifest.json` | Deterministic sample identities and ESPN game IDs |
| `market_metadata.json` | Full API metadata for the selected contracts, including rules |
| `candles.csv` | Hourly pregame observations (up to seven days) and minute observations in the two hours ending at the cutoff |
| `trades.csv` | All returned public trades in each queried pre-cutoff window |
| `summary.json` | Coverage counts, issues, cutoff boundary, retrieval dates |
| `requests.csv` | Source URL, HTTP status, retrieval time, response path and SHA-256 |
| `raw/` | Gzipped original response bytes and request metadata, including pagination and errors |

All normalized prices are dollar prices of a $1 YES payoff, on a 0–1 scale. Blank CSV cells mean missing or unverified; zero is an observed numeric value. `recorded_schedule_midpoint_p24h` is conditional on the currently recorded schedule and is **not** a verified snapshot of information available at that historical moment. `point_in_time_verified_p24h` remains blank. See the report for selection and timestamp limitations.
