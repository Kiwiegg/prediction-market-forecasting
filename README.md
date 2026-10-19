# Historical NBA forecasting dataset

A reproducible **200-game** expansion of the Kalshi NBA 2025–26 feasibility study, with separate market evaluation data and blinded pregame team packets. Python 3.10+ and its standard library are sufficient. No LLM forecasting, prompt strategies, or trading are implemented.

Read the [dataset methodology](reports/dataset_methodology.md), [generated coverage report](data/nba_2025_26/coverage_report.md), and [evaluation CSV](data/nba_2025_26/evaluation.csv). All dataset and schedule point-in-time verification flags remain **false**: source event/publication clocks support retrospective reconstruction, while historical payload versions and schedule revisions are unverified.

```sh
# Rebuild the expanded dataset from saved responses, without network access.
python3 scripts/build_dataset.py --offline

# Collect a new dataset from public sources without reusing the original study.
python3 scripts/build_dataset.py --output data/new_dataset --no-reuse

# Run leakage, temporal-boundary, blinding, lineage and consistency checks.
python3 -m unittest discover -s tests -v
```

The builder fetches all 30 team schedules, checks 1,230 games/82 per team, and locks a 200-game selection before joining Kalshi. It allocates slots proportionally across all seven season months and ranks fixed hashes of game IDs within each month. Prices, outcomes, and data availability do not affect selection; unavailable observations never trigger replacement draws. `--max-games` supports 1–200 games in a new output directory; `--workers` controls concurrent public GET requests (default 4).

Existing responses are immutable caches keyed by request URL, including failed requests. Default online builds can reuse matching raw responses from the original study, preserving their original retrieval times. Use a new output directory and `--no-reuse` for a new collection. Offline replay raises an error for absent responses and verifies saved body hashes. The output directory is separate from the original feasibility sample.

Expanded files under `data/nba_2025_26/`:

| File | Role |
| --- | --- |
| `selection_manifest.json` | Locked identities, rule, hashes, and monthly quotas |
| `schedule_frame.jsonl` | Schedule-only projections, including excluded Cup/postponed fixtures |
| `evidence_packets.jsonl` | **LLM-facing input only**: one allowlisted pregame packet per game |
| `evidence_lineage.jsonl` | Audit-only feature game IDs and source references; keep outside LLM inputs |
| `evaluation.csv` | Target outcomes, separate midpoint/last-trade prices, trade ages, missingness, verification flags |
| `game_history.jsonl` | Audit-only normalized completed-game facts and event/publication/update clocks |
| `candle_observations.csv` | Minute observations in two-hour windows ending at each cutoff |
| `market_metadata.json`, `market_lineage.jsonl` | Full target market metadata and price/label source references |
| `coverage.csv`, `coverage_report.md`, `summary.json` | Missingness by selected game date/month, totals, extraction and API limitations |
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
python3 -m unittest discover -s tests -v
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
