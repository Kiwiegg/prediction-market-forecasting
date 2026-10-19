# NBA market history feasibility study

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
