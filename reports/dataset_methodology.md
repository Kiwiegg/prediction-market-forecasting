# Historical dataset methodology

This expands the [20-market feasibility study](feasibility.md) into a 200-game retrospective dataset. It does not assert that the dataset is a verified snapshot of information publicly available at each historical instant. No forecasting, prompts, or trading logic is included.

## Selection before market joins

Fetch all 30 ESPN team schedules for `season=2026&seasontype=2`. Use each **event's** season metadata: the response's outer `season` can describe the current 2026–27 season even when its events belong to 2025–26. Deduplicate by ESPN event ID and require agreement between the two team feeds on the projected schedule fields.

The eligible frame contains events in 2025–26 regular season, October 21 through April 12 inclusive, using **America/New_York calendar dates**. Explicitly postponed/cancelled original fixtures are excluded, without requiring final status, a known winner, a Kalshi market, or a price. Their rescheduled games have distinct event IDs and remain eligible. Exclude competition type `39`, the NBA Cup championship, from selection and regular-season records. The Cup final does affect rest. These exclusions reconcile the frame to **1,230 distinct games and 82 per team**; collection stops if reconciliation fails. The frame preserves the four postponed fixtures and Cup final for auditing.

The [NBA's 2025–26 schedule announcement](https://www.nba.com/news/2025-26-nba-regular-season-schedule) and [Cup explanation](https://www.nba.com/news/in-season-tournament-101?trk=public_post_comment-text) establish the season calendar and championship exclusion.

Allocate 200 slots proportionally to monthly eligible-game counts. Take integer floors, then assign remaining slots by largest fractional remainder, breaking ties by ascending month. Within each month rank `SHA256("nba-2025-26-v1|" + ESPN_game_id)` ascending, with game ID as the tie breaker. Take the monthly quota, then order selected games chronologically. No outcomes, prices, volumes, source completeness, or market availability enter the ranking. Every selected game stays in the denominator; there are no replacement draws. The manifest is written before Kalshi discovery and cannot be overwritten with a changed selection in the same output directory.

## Separate observation and evidence files

`evaluation.csv` holds the target outcome, market observations, staleness, feature-availability flags, and schedule-verification status. `evidence_packets.jsonl` is the only LLM-facing input: it contains game/team identity, recorded tipoff, the cutoff, designation/neutral-site status, and allowlisted historical team facts. It contains no target score, winner, market identifier, price, odds, current standings, narrative, or raw-source URL. `evidence_lineage.jsonl` and all other raw/audit files are evaluation infrastructure and must not be appended to an LLM input.

The target time is exactly **recorded ESPN start minus 86,400 seconds**, in UTC. Kalshi milestone starts are a separate corroboration, with their update clocks retained. Disagreement is flagged without moving the cutoff or replacing the game. Agreement does not prove which schedule was known at the cutoff. All as-of schedule verification and dataset point-in-time verification values remain false.

Market joins use the home-team YES ticker, date and team-code mapping, with an independent home-team UUID check where a milestone exists. An identity conflict suppresses outcome/price extraction. Only finalized binary settlements become labels. Prices require the market to have opened and not closed at the cutoff.

* **Midpoint:** the arithmetic mean of a valid two-sided YES bid/ask close, `0 < bid <= ask < 1`, in a one-minute candle ending **exactly** at the cutoff. Two-hour preceding windows and nearest bucket lag are retained for diagnosing absent target bars. No carry-forward, interpolation, opposing-market substitution, or trade fallback populates missing midpoints. Quote update age is unknown.
* **Last trade:** latest non-block YES-price observation with execution time at or before the cutoff, after exhausting cursor pagination. The preceding hour is queried first; if no eligible trade is found, search back to listing. Conflicting different-price trades with identical latest timestamps remain ambiguous and missing. Actual age is retained; age **greater than 900 seconds** is stale. Stale values are retained, not silently filtered or replaced.

Market and trade routes use their separate archive cutoffs. This historical season's target times precede the captured trade cutoff. See Kalshi's [historical routing](https://docs.kalshi.com/getting_started/historical_data), [candles](https://docs.kalshi.com/api-reference/historical/get-historical-market-candlesticks), and [trades](https://docs.kalshi.com/api-reference/historical/get-historical-trades) documentation. Source availability and archive retention are not guaranteed by a successful empty response.

## Reconstructible team facts

Features are recomputed from individual game summaries, never copied from ESPN's retrospective team record, last-five widget, rankings, or standings. The extractor requires an explicit timestamped **End Game** play, final header status, matching teams, and agreement on the winner between the play and final header. Exact score disagreements with the same winner are flagged; exact points are omitted and no score/margin feature is built. Winner disagreements are unusable.

The game-specific recap must have the correct game ID, type `Recap`, and publication/modification timestamps; the event's `meta.lastUpdatedAt` must exist too. A fact's conservative recorded availability bound is the **maximum of End Game, recap publication, recap modification, and event update clocks**. Only facts whose bound is at or before the cutoff can contribute. These clocks are fields in later-retrieved sources, not independent archived captures of an unchanged historical payload.

| Packet feature | Definition and omission rule |
| --- | --- |
| Regular-season record | Wins/losses from completed eligible regular-season games, ordered by completion. If an earlier potentially completed game lacks a usable result/clock or has a later availability bound, omit the full record rather than report a partial record as complete. Known ongoing games supply no result. |
| Recent performance | W/L sequence and counts over at most five latest eligible completed regular-season games. Omit if none exist or unresolved regular-season history prevents establishing the window. |
| Home/away | Recorded schedule designation plus neutral-site flag; designation does not necessarily imply home-court advantage. Historical schedule version remains unverified. |
| Rest at cutoff | Hours and completed 24-hour periods since the latest reliably completed game in the season feed, including the Cup final. Omit for an ongoing/unresolved latest game or no previous game in the feed. Preseason/offseason rest and rest at future tipoff are not reconstructed. |

A genuine 0–0 season record is distinct from an omitted record. Every omission has a reason. Each feature's game IDs resolve through `game_history.jsonl` to raw source IDs, completion/publication/update clocks, and retrieval metadata. The target game is explicitly excluded even if malformed timestamps would otherwise admit it. Games between the cutoff and target tipoff never contribute results.

## What the timestamps establish

Saved responses substantiate retrospective identities, recorded schedule values, explicit completion clocks, W/L consistency, settlement results, trade executions, and reported publication/update timestamps. Records, recent form and rest are deterministic reconstructions subject to those clocks and source completeness. The stability of historical payload versions, first dissemination latency, retrospective schedule changes, and exact quote-update age are **unverified assumptions/limits**, not verified facts. A later recap edit can conservatively suppress a fact that may actually have been known earlier. No estimate of when an unrecorded game ended is introduced to rescue coverage.

`coverage.csv` and the generated `coverage_report.md` show missingness for every selected game date and every month, retaining the full selected denominator. `evaluation.csv` adds per-game flags; `summary.json` counts source and extraction problems. `sources.jsonl` records URLs, SHA-256, raw file paths, HTTP Date, retrieval time and HTTP status. Raw request metadata retains retries and original response bytes, including failures. Source collection is not one atomic historical snapshot.

Tests cover deterministic selection under reordered/price/label-mutated inputs, future/target exclusion, completion and publication boundaries, unresolved histories, Cup/rest semantics, packet allowlists, source clocks, market timestamps, dataset joins, and coverage reconciliation. Offline rebuilding verifies response hashes and supports byte-for-byte comparison of derived artifacts. These checks validate the reconstruction rules; they do not elevate the dataset to point-in-time verified status.
