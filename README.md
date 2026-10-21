# Historical NBA forecasting dataset

A reproducible **200-game** expansion of the Kalshi NBA 2025–26 feasibility study, with separate market evaluation data, frozen pregame team/injury packets, a direct-LLM probability baseline and LEAP-inspired structured likelihood elicitation. Python 3.10+ and the pinned PDF parser are required for the expanded build. No trading is implemented.

The [LEAP-NBA v1 guide](reports/leap_nba_v1.md) documents four isolated evidence groups, immutable LR inference, neutral-prior Bayesian log-odds aggregation, fixed raw/conservative variants, and paired comparison with the saved direct baseline, Kalshi and constant 50%. Its [protocol](experiments/leap_nba_v1_protocol.md) was committed before paid inference. The historical sample, frozen packets, direct protocol, 50/150 split and 20-minute market-price rule remain unchanged. See the [five-game pilot report](reports/leap_nba_v1_pilot.md) for actual validation and limitations.

The [full development experiment](reports/development_50/report.md) attempted all 50 games using unchanged methods and pilot caches. Direct succeeded on 50/50; provider/transport failures left LEAP at 34/50, with no retries or imputation. Five-method scores and descriptive paired bootstrap intervals use the same **34 eligible games**; all 50 results and exclusions are preserved. [Sanitized replay](reports/development_50/manifest.json) reproduces scores, LR/contribution diagnostics, calibration, and usage without credentials: `.venv/bin/python scripts/analyze_development.py --replay reports/development_50`. The reserved 150 games remain unforecast and unscored.

The separately [authorized retry and merge](reports/development_50/merged/report.md) recovered six games from 15 successful group retries, raising LEAP coverage to **40/50**. A renewed HTTP 403 stopped that batch; 24 remaining requests were not retried. Original runs and observations remain immutable, and all methods are compared on the same 40 games. Replay the merged results with `.venv/bin/python scripts/analyze_development.py --replay reports/development_50/merged`.

The [direct baseline guide](reports/direct_baseline.md) documents a fixed prompt, hash-bound evidence-only requests, immutable request caching, cost limits and a separate paired evaluator. A [precommitted split](experiments/nba_2025_26_split.json) reserves **50 development / 150 evaluation** games by month. The [implementation report](reports/direct_baseline_implementation.md) records five successful paid development forecasts ($0.039423 conservative estimated cost); the evaluation subset remains unforecast and unscored. Historical results are exploratory because model memorization and historical source revisions cannot be ruled out. Prospective evidence remains the eventual primary out-of-sample evaluation.

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
