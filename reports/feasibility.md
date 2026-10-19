# Kalshi NBA 2025–26 history: feasibility investigation

Collected **October 19, 2026** using unauthenticated public GET requests. Evidence and normalized exports are in [`data/kalshi_nba_2025_26`](../data/kalshi_nba_2025_26/); the rerun commands are in the [README](../README.md).

**Finding: a small retrospective dataset is feasible, with explicit schedule and freshness qualifications.** All 20 selected contracts have final outcomes and timestamped trades before the analysis cutoff. Fourteen have a valid bid/ask candle ending at the cutoff. A fully verified reconstruction of information available at that historical instant remains unestablished: historical schedule versions and exact quote-update times were not recovered.

## Sample and evidence

The relevant series is **`KXNBAGAME` (NBA Game)**, governed by the [basketball game-winner contract](https://assets.kalshi.com/contract_terms/BASKETBALLGAMEWIN.pdf). It includes postseason games, so the series alone does not establish regular-season membership. Archive discovery returned 2,898 contracts across dates, not 2,898 eligible games.

We selected five games on each of four fixed dates, ordered by ESPN's recorded start and game ID, before inspecting prices/outcomes. One home-team YES contract per game avoids counting opposing contracts as independent games. All 20 ESPN records identify season year 2026 and season type 2 (regular season); Kalshi home-team IDs match the selected contracts. All are `finalized`, have a `yes`/`no` result and $1/$0 settlement value, and agree with ESPN's home-team winner flag. Full rules and metadata are exported, rather than deriving outcomes from the terminal traded price.

| Game date | Resolved markets | Pre-cutoff last trades | Exact-boundary bid/ask midpoints |
| --- | ---: | ---: | ---: |
| 2025-10-22 | 5 | 5 | 5 |
| 2025-12-01 | 5 | 5 | 5 |
| 2026-01-15 | 5 | 5 | 3 |
| 2026-03-15 | 5 | 5 | 1 |
| **Total** | **20** | **20** | **14** |

## Reconstructing T − 24 hours

`analysis_target_utc` is ESPN's currently recorded game start minus exactly 86,400 seconds. For all 20 sampled games it agrees with Kalshi's separate milestone `start_date`. Market `close_time`, `expected_expiration_time`, `expiration_time`, and ticker dates are **not treated as scheduled tipoff**. `occurrence_datetime` is missing for all 20.

Two price measurements are kept separate:

* **Quote estimate:** `(YES bid close + YES ask close) / 2`, using a minute candle whose end equals the target and `0 < bid <= ask < 1`. This gives 14 conditional estimates with spreads of $0.01–$0.03. The six missing target candles remain blank; nearest earlier quote buckets lag by 60–1,680 seconds. No forward filling, interpolation, trade-price fallback, or opposing-market substitution is applied to this column.
* **Last-trade estimate:** the latest non-block trade at or before the target, with its actual timestamp and age. Every returned page in the preceding hour was retrieved; all 20 markets had eligible trades. Their ages span **16.55–2,884.39 seconds** (median 332.17 seconds). Four exceed the explicit **15-minute** staleness threshold: `25DEC01ATLDET-DET`, `26MAR15DALCLE-CLE`, `26MAR15DETTOR-TOR`, and `26MAR15PORPHI-PHI` (all prefixed `KXNBAGAME-`). Prices remain exported and flagged; a 15-minute freshness requirement leaves 16 usable trade observations. The threshold is configurable.

Dollar prices of $1 binary payoffs are probability proxies, not calibrated win probabilities or guaranteed executable prices. Candle ends bound the observation period; they do not identify the last quote update. Quote-update age is unknown for all 20.

## Gaps and API limitations

* **Archive routing matters.** The saved cutoff puts settled markets and trades before **2026-08-20 00:00 UTC** in historical storage. The tested live market and live candle endpoints returned 404; their historical counterparts returned 200. The original event endpoint returned metadata but an empty `markets` array. See Kalshi's [historical-data guide](https://docs.kalshi.com/getting_started/historical_data).
* **Candles are sparse.** Across the two-hour minute windows, 1,545 of 2,420 possible inclusive minute endpoints were returned; 875 are absent. Of returned minute candles, 1,085 have zero volume and a null trade close. `price.previous` is not substituted for an observation. The exports contain 2,752 hourly/minute rows and 379 trades; these are bounded windows, not lifetime histories.
* **Pagination and schema differ.** Market/trade lists use cursors with a documented maximum page size of 1,000. Historical candle prices are decimal dollar strings under `close`; live documentation uses `close_dollars`. Supported candle intervals are 1, 60 and 1,440 minutes; this study tested 1 and 60. Sources: [historical markets](https://docs.kalshi.com/api-reference/historical/get-historical-markets), [historical trades](https://docs.kalshi.com/api-reference/historical/get-historical-trades), [historical candles](https://docs.kalshi.com/api-reference/historical/get-historical-market-candlesticks).
* **Schedule agreement is retrospective.** Milestone records were updated after the sampled games; this does not prove that their starts changed, but it does not establish the schedule known at the target. All `schedule_asof_target_verified` values are false and `point_in_time_verified_p24h` cells are blank. Kalshi documents [milestones](https://docs.kalshi.com/api-reference/milestone/get-milestones), not an as-of schedule-version lookup.
* **A concrete clock disagreement exists outside the sample.** For Spurs–Mavericks on October 22, ESPN currently returns **01:47 UTC** the next day; Kalshi's milestone returns **01:30 UTC**, consistent with the NBA's [published 9:30 p.m. Eastern schedule](https://www.nba.com/news/10-must-see-matchups-during-first-2-plus-months-of-2025-26-nba-season). Both API responses are retained. Do not silently use retrospective scoreboard times as original schedules. The NBA's official schedule JSON feed returned HTTP 403 from this environment; ESPN's public scoreboard is the separately identified schedule/season cross-check, not a substitute for missing Kalshi prices.

The 95 saved request results comprise 92 HTTP 200s, two expected 404 probes, and the NBA 403. Requests, retrieval timestamps, response hashes, retries, and original bytes are retained. No authentication or paid historical service was needed for the successful requests. This sample does not establish season-wide coverage, stable archive retention, historical publication latency, schedule revision history, or quote freshness. Before expanding, recover schedule evidence valid at each target and agree on a price definition and freshness threshold. No forecasting models or production pipeline were built.
