# Historical NBA dataset coverage

Selected 200 distinct games from a 1230-game frame. Outcomes: 200; cutoff midpoints: 114; last trades: 192; last trades older than 15 minutes: 36.

Missing cutoff midpoints: 86; missing last-trade prices: 8. Of the latter, 8 have conflicting prices at the same latest trade timestamp. No arbitrary ordering resolves those ties.

These are retrospective reconstructions. Zero games have a verified as-of schedule version. Raw retrieval times, source event/publication clocks, and reconstructed assumptions are distinct. See the methodology in ../../reports/dataset_methodology.md.

| Month | Selected | Missing outcome | Missing midpoint | Missing trade | Stale trade | Missing home/away record | Missing home/away recent | Missing home/away rest | Start disagreements |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- | --- | ---: |
| 2025-10 | 13 | 0 | 4 | 0 | 2 | 0/0 | 3/4 | 5/6 | 1 |
| 2025-11 | 36 | 0 | 12 | 2 | 8 | 1/2 | 1/2 | 4/6 | 0 |
| 2025-12 | 32 | 0 | 14 | 0 | 9 | 1/2 | 1/2 | 2/1 | 0 |
| 2026-01 | 38 | 0 | 13 | 2 | 4 | 3/4 | 3/4 | 3/3 | 0 |
| 2026-02 | 27 | 0 | 12 | 2 | 3 | 4/3 | 4/3 | 3/3 | 0 |
| 2026-03 | 39 | 0 | 22 | 2 | 8 | 4/6 | 4/6 | 5/8 | 0 |
| 2026-04 | 15 | 0 | 9 | 0 | 2 | 4/3 | 4/3 | 1/2 | 0 |

## Missingness by selected game date

H/A columns count missing features separately for home and away teams. All selected games remain in the denominator.

| Date | Selected | Missing outcome | Missing midpoint | Missing trade | Stale trade | Record H/A | Recent H/A | Rest H/A |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |
| 2025-10-22 | 3 | 0 | 0 | 0 | 0 | 0/0 | 3/3 | 3/3 |
| 2025-10-23 | 1 | 0 | 0 | 0 | 0 | 0/0 | 0/1 | 0/1 |
| 2025-10-24 | 3 | 0 | 2 | 0 | 1 | 0/0 | 0/0 | 0/0 |
| 2025-10-26 | 1 | 0 | 0 | 0 | 0 | 0/0 | 0/0 | 0/0 |
| 2025-10-27 | 1 | 0 | 0 | 0 | 0 | 0/0 | 0/0 | 0/0 |
| 2025-10-28 | 1 | 0 | 0 | 0 | 1 | 0/0 | 0/0 | 0/0 |
| 2025-10-29 | 1 | 0 | 0 | 0 | 0 | 0/0 | 0/0 | 0/0 |
| 2025-10-31 | 2 | 0 | 2 | 0 | 0 | 0/0 | 0/0 | 2/2 |
| 2025-11-03 | 1 | 0 | 0 | 0 | 0 | 0/0 | 0/0 | 0/0 |
| 2025-11-05 | 5 | 0 | 0 | 1 | 1 | 0/0 | 0/0 | 0/1 |
| 2025-11-07 | 2 | 0 | 1 | 0 | 0 | 0/0 | 0/0 | 0/0 |
| 2025-11-08 | 1 | 0 | 0 | 0 | 1 | 0/0 | 0/0 | 1/0 |
| 2025-11-09 | 1 | 0 | 0 | 0 | 0 | 0/0 | 0/0 | 0/0 |
| 2025-11-10 | 2 | 0 | 0 | 0 | 0 | 0/1 | 0/1 | 0/1 |
| 2025-11-11 | 1 | 0 | 0 | 0 | 0 | 0/0 | 0/0 | 0/0 |
| 2025-11-12 | 4 | 0 | 1 | 0 | 3 | 1/0 | 1/0 | 0/0 |
| 2025-11-14 | 1 | 0 | 1 | 0 | 0 | 0/1 | 0/1 | 0/0 |
| 2025-11-15 | 1 | 0 | 0 | 0 | 0 | 0/0 | 0/0 | 0/0 |
| 2025-11-16 | 2 | 0 | 1 | 0 | 1 | 0/0 | 0/0 | 0/0 |
| 2025-11-17 | 3 | 0 | 2 | 0 | 1 | 0/0 | 0/0 | 1/1 |
| 2025-11-18 | 1 | 0 | 0 | 0 | 0 | 0/0 | 0/0 | 0/0 |
| 2025-11-19 | 1 | 0 | 0 | 0 | 0 | 0/0 | 0/0 | 0/0 |
| 2025-11-21 | 1 | 0 | 0 | 0 | 0 | 0/0 | 0/0 | 0/0 |
| 2025-11-23 | 2 | 0 | 2 | 0 | 0 | 0/0 | 0/0 | 0/0 |
| 2025-11-24 | 1 | 0 | 1 | 0 | 0 | 0/0 | 0/0 | 0/1 |
| 2025-11-26 | 1 | 0 | 0 | 0 | 0 | 0/0 | 0/0 | 0/0 |
| 2025-11-28 | 1 | 0 | 0 | 0 | 0 | 0/0 | 0/0 | 0/0 |
| 2025-11-29 | 1 | 0 | 1 | 0 | 1 | 0/0 | 0/0 | 1/1 |
| 2025-11-30 | 3 | 0 | 2 | 1 | 0 | 0/0 | 0/0 | 1/1 |
| 2025-12-01 | 1 | 0 | 0 | 0 | 0 | 0/0 | 0/0 | 0/1 |
| 2025-12-02 | 2 | 0 | 0 | 0 | 0 | 0/0 | 0/0 | 0/0 |
| 2025-12-04 | 3 | 0 | 2 | 0 | 0 | 0/0 | 0/0 | 0/0 |
| 2025-12-06 | 1 | 0 | 1 | 0 | 1 | 0/1 | 0/1 | 1/0 |
| 2025-12-07 | 2 | 0 | 1 | 0 | 0 | 1/0 | 1/0 | 0/0 |
| 2025-12-11 | 1 | 0 | 1 | 0 | 0 | 0/0 | 0/0 | 0/0 |
| 2025-12-14 | 1 | 0 | 0 | 0 | 0 | 0/0 | 0/0 | 0/0 |
| 2025-12-15 | 1 | 0 | 0 | 0 | 1 | 0/0 | 0/0 | 0/0 |
| 2025-12-17 | 1 | 0 | 0 | 0 | 0 | 0/0 | 0/0 | 0/0 |
| 2025-12-18 | 1 | 0 | 0 | 0 | 0 | 0/0 | 0/0 | 0/0 |
| 2025-12-20 | 4 | 0 | 1 | 0 | 2 | 0/0 | 0/0 | 0/0 |
| 2025-12-21 | 2 | 0 | 1 | 0 | 1 | 0/0 | 0/0 | 0/0 |
| 2025-12-22 | 1 | 0 | 1 | 0 | 1 | 0/0 | 0/0 | 0/0 |
| 2025-12-23 | 3 | 0 | 2 | 0 | 1 | 0/1 | 0/1 | 0/0 |
| 2025-12-26 | 3 | 0 | 1 | 0 | 1 | 0/0 | 0/0 | 0/0 |
| 2025-12-27 | 1 | 0 | 1 | 0 | 1 | 0/0 | 0/0 | 1/0 |
| 2025-12-29 | 2 | 0 | 0 | 0 | 0 | 0/0 | 0/0 | 0/0 |
| 2025-12-31 | 2 | 0 | 2 | 0 | 0 | 0/0 | 0/0 | 0/0 |
| 2026-01-02 | 2 | 0 | 2 | 0 | 0 | 0/0 | 0/0 | 0/1 |
| 2026-01-04 | 1 | 0 | 0 | 0 | 0 | 1/0 | 1/0 | 0/0 |
| 2026-01-05 | 2 | 0 | 1 | 0 | 0 | 0/0 | 0/0 | 0/0 |
| 2026-01-06 | 1 | 0 | 0 | 0 | 0 | 1/0 | 1/0 | 1/0 |
| 2026-01-07 | 2 | 0 | 0 | 0 | 0 | 0/0 | 0/0 | 0/0 |
| 2026-01-08 | 1 | 0 | 0 | 0 | 0 | 0/0 | 0/0 | 1/0 |
| 2026-01-09 | 2 | 0 | 0 | 0 | 0 | 0/0 | 0/0 | 0/0 |
| 2026-01-13 | 1 | 0 | 1 | 0 | 0 | 0/0 | 0/0 | 0/0 |
| 2026-01-15 | 2 | 0 | 1 | 0 | 0 | 0/0 | 0/0 | 0/0 |
| 2026-01-16 | 1 | 0 | 0 | 0 | 0 | 0/0 | 0/0 | 0/0 |
| 2026-01-17 | 2 | 0 | 0 | 0 | 0 | 0/0 | 0/0 | 0/0 |
| 2026-01-18 | 2 | 0 | 1 | 0 | 1 | 0/0 | 0/0 | 0/0 |
| 2026-01-19 | 2 | 0 | 1 | 0 | 0 | 0/0 | 0/0 | 0/0 |
| 2026-01-21 | 2 | 0 | 0 | 0 | 0 | 0/0 | 0/0 | 0/0 |
| 2026-01-22 | 1 | 0 | 0 | 0 | 0 | 0/0 | 0/0 | 0/0 |
| 2026-01-23 | 2 | 0 | 0 | 0 | 1 | 0/1 | 0/1 | 0/0 |
| 2026-01-24 | 3 | 0 | 1 | 0 | 1 | 1/0 | 1/0 | 0/1 |
| 2026-01-25 | 1 | 0 | 1 | 0 | 0 | 0/0 | 0/0 | 0/0 |
| 2026-01-26 | 1 | 0 | 0 | 0 | 0 | 0/0 | 0/0 | 0/0 |
| 2026-01-27 | 2 | 0 | 2 | 1 | 0 | 0/1 | 0/1 | 0/0 |
| 2026-01-28 | 2 | 0 | 1 | 0 | 0 | 0/1 | 0/1 | 0/0 |
| 2026-01-29 | 1 | 0 | 0 | 0 | 0 | 0/0 | 0/0 | 1/0 |
| 2026-01-30 | 2 | 0 | 1 | 1 | 1 | 0/1 | 0/1 | 0/1 |
| 2026-02-02 | 1 | 0 | 0 | 0 | 0 | 0/0 | 0/0 | 0/0 |
| 2026-02-03 | 2 | 0 | 0 | 0 | 1 | 0/0 | 0/0 | 0/0 |
| 2026-02-04 | 2 | 0 | 1 | 0 | 0 | 0/0 | 0/0 | 0/1 |
| 2026-02-05 | 3 | 0 | 1 | 1 | 0 | 0/1 | 0/1 | 0/0 |
| 2026-02-07 | 1 | 0 | 0 | 0 | 0 | 0/0 | 0/0 | 0/0 |
| 2026-02-09 | 1 | 0 | 0 | 1 | 0 | 1/0 | 1/0 | 1/0 |
| 2026-02-10 | 2 | 0 | 1 | 0 | 1 | 0/1 | 0/1 | 1/0 |
| 2026-02-11 | 2 | 0 | 2 | 0 | 0 | 0/1 | 0/1 | 0/0 |
| 2026-02-12 | 1 | 0 | 0 | 0 | 0 | 0/0 | 0/0 | 0/1 |
| 2026-02-19 | 3 | 0 | 1 | 0 | 0 | 1/0 | 1/0 | 0/0 |
| 2026-02-22 | 2 | 0 | 1 | 0 | 0 | 0/0 | 0/0 | 1/0 |
| 2026-02-23 | 1 | 0 | 0 | 0 | 0 | 0/0 | 0/0 | 0/0 |
| 2026-02-24 | 2 | 0 | 2 | 0 | 0 | 1/0 | 1/0 | 0/0 |
| 2026-02-25 | 1 | 0 | 1 | 0 | 0 | 0/0 | 0/0 | 0/1 |
| 2026-02-26 | 2 | 0 | 1 | 0 | 1 | 1/0 | 1/0 | 0/0 |
| 2026-02-28 | 1 | 0 | 1 | 0 | 0 | 0/0 | 0/0 | 0/0 |
| 2026-03-01 | 2 | 0 | 1 | 0 | 0 | 0/1 | 0/1 | 1/0 |
| 2026-03-02 | 2 | 0 | 0 | 0 | 0 | 0/1 | 0/1 | 0/1 |
| 2026-03-04 | 2 | 0 | 1 | 0 | 0 | 0/0 | 0/0 | 0/1 |
| 2026-03-05 | 1 | 0 | 0 | 0 | 1 | 1/0 | 1/0 | 0/0 |
| 2026-03-06 | 2 | 0 | 1 | 0 | 1 | 0/1 | 0/1 | 1/0 |
| 2026-03-08 | 4 | 0 | 2 | 0 | 0 | 0/0 | 0/0 | 0/0 |
| 2026-03-10 | 1 | 0 | 0 | 0 | 0 | 0/0 | 0/0 | 0/0 |
| 2026-03-12 | 1 | 0 | 1 | 1 | 0 | 0/0 | 0/0 | 0/0 |
| 2026-03-15 | 3 | 0 | 2 | 0 | 1 | 1/1 | 1/1 | 0/1 |
| 2026-03-16 | 1 | 0 | 0 | 0 | 0 | 0/0 | 0/0 | 0/1 |
| 2026-03-18 | 2 | 0 | 2 | 0 | 0 | 0/0 | 0/0 | 0/1 |
| 2026-03-19 | 3 | 0 | 1 | 0 | 0 | 1/1 | 1/1 | 0/0 |
| 2026-03-20 | 1 | 0 | 1 | 0 | 0 | 0/0 | 0/0 | 0/0 |
| 2026-03-21 | 1 | 0 | 1 | 0 | 1 | 0/0 | 0/0 | 0/0 |
| 2026-03-23 | 1 | 0 | 1 | 0 | 1 | 1/0 | 1/0 | 1/0 |
| 2026-03-24 | 2 | 0 | 2 | 0 | 0 | 0/0 | 0/0 | 0/1 |
| 2026-03-25 | 1 | 0 | 0 | 0 | 1 | 0/0 | 0/0 | 0/0 |
| 2026-03-27 | 2 | 0 | 1 | 0 | 0 | 0/1 | 0/1 | 0/0 |
| 2026-03-28 | 2 | 0 | 1 | 1 | 1 | 0/0 | 0/0 | 0/1 |
| 2026-03-29 | 1 | 0 | 1 | 0 | 0 | 0/0 | 0/0 | 0/0 |
| 2026-03-30 | 2 | 0 | 1 | 0 | 0 | 0/0 | 0/0 | 1/0 |
| 2026-03-31 | 2 | 0 | 2 | 0 | 1 | 0/0 | 0/0 | 1/1 |
| 2026-04-01 | 1 | 0 | 0 | 0 | 0 | 0/0 | 0/0 | 0/0 |
| 2026-04-05 | 3 | 0 | 1 | 0 | 0 | 2/1 | 2/1 | 1/1 |
| 2026-04-06 | 1 | 0 | 1 | 0 | 0 | 0/0 | 0/0 | 0/1 |
| 2026-04-07 | 5 | 0 | 5 | 0 | 1 | 1/2 | 1/2 | 0/0 |
| 2026-04-08 | 2 | 0 | 1 | 0 | 0 | 0/0 | 0/0 | 0/0 |
| 2026-04-12 | 3 | 0 | 1 | 0 | 1 | 1/0 | 1/0 | 0/0 |

## Source and reconstruction limits

* Verified in saved responses: identities, recorded schedule values, explicit End Game event timestamps/scores, game-specific recap publication/modification clocks, Kalshi settlement results and trade timestamps. This does not authenticate an unchanged historical payload or prove its first public availability.
* Reconstructed: season records and last-five results, filtered by event and publication/update clocks before each cutoff. Unresolvable histories cause feature omission, not partial records presented as complete records.
* Exact End Game/header score differences are retained as issues when both agree on the winner. Only the agreed W/L fact is used; exact points and margins are omitted. Missing completion/publication clocks can suppress later record/recent-form features for the affected teams.
* Rest counts completed 24-hour periods since the latest reliably completed game AT the cutoff, including the Cup final. It is not a prediction of rest at tipoff. Ongoing or unresolved latest games cause omission.
* Recorded home/away designation and neutral-site flag come from the retrospective schedule. No historical schedule version is asserted. Last-trade lookup starts with the prior hour and expands back to listing if no eligible trade is found. An empty response does not establish complete exchange archival retention.
* Midpoints require a valid two-sided candle ending exactly at the cutoff. No carry-forward or substitution is used. Quote-update age is unknown. Stale trades remain stored and flagged.
* LLM-facing evidence_packets.jsonl contains only allowlisted schedule identities and historical team facts. Market prices, target outcomes, target scores and raw response links live outside that file.

Source HTTP statuses: `{"200": 1874}`. History extraction issues: `{"excluded_postponed_or_cancelled_fixture": 4, "final_scores_differ_winner_agrees": 9, "missing_game_specific_publication_clocks": 1, "missing_timestamped_end_game": 1}`.
