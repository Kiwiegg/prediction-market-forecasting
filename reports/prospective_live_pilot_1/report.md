# First live prospective pilot audit

Audited 2026-10-27 UTC. **PASS under the frozen cloud-news-v1 eligibility rules:** one eligible shared packet, successful Direct, LEAP v1 and LEAP v2 forecasts, and an eligible independent market benchmark. This establishes reproducibility of this capture, not forecast accuracy or campaign-scale reliability. No outcome was retrieved or verified; Brier score and log loss remain **pending**.

- Capture: [live run 40414074069](https://github.com/Kiwiegg/prediction-market-forecasting/actions/runs/40414074069), code `d65a2e1ceba99f0a4bfd8f055eef4b985d480327`.
- Existing private R2 replay: [40422636551, passed](https://github.com/Kiwiegg/prediction-market-forecasting/actions/runs/40422636551).
- Detailed GET-only private audit: [40432361469, passed](https://github.com/Kiwiegg/prediction-market-forecasting/actions/runs/40432361469), reporting code `0173f046b0f1354290c56b2baf5aea5c5f030e76`.
- [Sanitized observations](audit.json), [hash and provenance manifest](manifest.json), [bounded expansion plan and activation blockers](campaign_plan.md).

## Game and clocks

Brooklyn Nets at Boston Celtics, ESPN `401909877`, 2026–27 regular season. All dates below are October 26, 2026 unless stated otherwise. Eastern time is EDT (UTC−04:00).

| Event | Actual UTC | US Eastern |
|---|---|---|
| Scheduled tipoff | Oct 27 23:30:00 | Oct 27 19:30:00 |
| Fixed information cutoff T | 23:30:00 | 19:30:00 |
| Permitted collection window | 23:00:00–23:30:00 | 19:00:00–19:30:00 |
| Baseline collection | 23:00:02.860507–23:00:06.683041 | 19:00:02.860507–19:00:06.683041 |
| Search response arrivals | 23:00:27.960965; 23:00:31.912509 | 19:00:27.960965; 19:00:31.912509 |
| Public-source refresh | 23:28:01.905542–23:28:06.566453 | 19:28:01.905542–19:28:06.566453 |
| Independent quote response | 23:29:55.143683 | 19:29:55.143683 |
| Packet frozen | 23:30:01.826354 | 19:30:01.826354 |
| Forecast orchestration started | 23:30:07.151875 | 19:30:07.151875 |
| First model request | 23:30:10.392776 | 19:30:10.392776 |
| Forecasts sealed | 23:30:44.584577 | 19:30:44.584577 |
| Freeze deadline | 23:35:00 | 19:35:00 |
| Forecast deadline | 23:45:00 | 19:45:00 |

Freeze finished T+1.826 seconds and sealing T+44.585 seconds, both within their deadlines and before tipoff. Source refresh completed about 113 seconds before T. All included source bytes were captured before T; post-T inference used only the frozen packet. Retrieval clocks establish observed availability, not the exact publisher update time.

## Forecasts and isolated benchmark

Every probability below is **Boston home-win probability**.

| Method | Probability | Individually verified status |
|---|---:|---|
| Direct LLM | 0.9200000000 | success, 1 request |
| LEAP v1 raw | 0.8614190687 | success, 3 group requests |
| LEAP v1 conservative | 0.7137287717 | same v1 observations |
| LEAP v2 raw | 0.7928802589 | success, 3 group requests |
| LEAP v2 conservative | 0.6617690235 | same v2 observations |
| Kalshi midpoint | 0.8100000000 | eligible independent capture |

Shared packet SHA-256:
`e7b0dc9502a0f374f6805bfa0ad16a947a4ce6d1aeff09d6d3f5cb09503c27de`

The audit reconstructed each method's native request from this packet, compared the actual saved request bytes, verified private raw-response hashes, reparsed successful responses, and replayed both aggregations. All parent hashes match. No target outcome, Kalshi quote, audit-only file or post-cutoff retrieval was supplied in model context. Statistical records contain only completed **earlier** games, as required. All seven model responses returned `claude-haiku-4-5-20251001`.

| Group | v1 home-oriented LR / sufficiency | v2 assessment / home-oriented LR |
|---|---|---|
| Team strength | 3.2 / limited | Y (= home), moderate, limited / 1.75 |
| Schedule/venue | 1.85 / adequate | home, moderate, limited / 1.75 |
| Player availability | 1.05 / limited | home, slight, limited / 1.25 |
| Additional news | skipped missing / 1 | skipped missing / 1 |

No group request failed or abstained. News skips were source missingness, not model failures. The home-favoring injury assessments are saved judgments despite Boston's missing submission; this audit does not validate their basketball interpretation or alter them. Correlated group evidence and heuristic LR calibration remain methodological limitations.

Kalshi ticker `KXNBAGAME-26OCT27BKNBOS-BOS`: YES bid **0.80**, ask **0.82**, spread **0.02**, midpoint **0.81**, received **4.856317 seconds before T**. Mapping and quote bytes passed the existing independent benchmark replay. Underlying quote-update age is unknown. This is the prospective live quote procedure, not a backfilled candle; historical 20-minute rules remain unchanged. Market data stayed outside the shared packet.

## Evidence coverage and limitations

**Statistics:** Boston 1–1, average differential −2.0 across two completed regular-season games; Brooklyn 0–3, average differential −12.666667 across three. Home/away splits, recent results and rest-at-cutoff were reproduced from the saved ESPN team schedules and five game summaries. Used game IDs and source hashes are in `audit.json`. End, availability and supplied publication/update clocks were checked against T, and the target game was excluded. No statistical features were omitted. These are very small early-season samples. Capture proves observed pre-T availability; it does not make ESPN's unversioned history independently time-versioned.

**Official injuries:** the latest eligible report among captured archive links was the [19:15 EDT official PDF](https://ak-static.cms.nba.com/referee/injury/Injury-Report_2026-10-26_07_15PM.pdf), issued **23:15 UTC**, observed publicly retrievable **23:28:06.491091 UTC**. PDF issue/creation/capture clocks passed; the observed capture is an upper bound on publication, not independently verified first publication. The report was 15 minutes old at T; globally latest status is not proven. Page 5 lists Brooklyn as reported: Bilodeau, Jefferson, Nelson, Powell and Saraf all Out, for G League/two-way/assignment reasons. Boston is **not yet submitted**, with zero extracted player records. No missing or unlisted player was declared healthy. Original reasons and page references are preserved privately and in sanitized structured lineage.

**News:** 2 successful Brave searches, 8 returned result entries, **0 articles retrieved, 0 validated findings, 0 Claude extraction calls**. All eight entries were rejected before retrieval as duplicate/disallowed source paths: dynamic ESPN injury/transaction/team pages and an injury PDF outside the article path. Full queries and rejected URLs/reasons appear in `audit.json`; no snippets enter the evidence packet. Source-support checks have no accepted news claims to check. The empty extraction stage is deterministic missingness bookkeeping, not a successful live extraction. This pilot does **not** validate live news extraction or support an inference that no relevant developments existed. No later search or backfill was performed.

## Requests, costs and latency

| Provider/method | Requests | Reported input/output tokens | Sum of provider latency | Saved configured-rate estimate |
|---|---:|---:|---:|---:|
| Brave search | 2 | not reported | 1.250939 s | $0.020000 |
| Direct | 1 | 1,764 / 15 | 2.415255 s | $0.005517 |
| LEAP v1 | 3 | 3,793 / 57 | 4.139525 s | $0.012234 |
| LEAP v2 | 3 | 3,104 / 66 | 4.038913 s | $0.006868 |
| Extraction | 0 | 0 / 0 | 0 s | $0 |
| Total | 9 | 8,661 / 138 | 11.844632 s | **$0.044619** |

All nine paid-provider HTTP responses were 200. There were no paid retries, unknown-usage observations or open denial circuits. Model latency sums to 10.593693 seconds; inference orchestration including persistence took 37.432702 seconds. Latency sums are not collection wall time.

**Reserved:** $0.178331 total = $0.158331 for seven forecast claims + $0.02 for two search claims. Reservations remain in the cumulative ledger; they are not invoices and are not reset because measured usage was lower. Remaining cumulative reservation headroom is **$49.821669**.

**Estimated actual tariff cost, invoice unverified:** measured Claude tokens at published Haiku 4.5 base rates ($1/M input, $5/M output) give **$0.009351**; two Brave requests at the published $5/1,000 search rate give **$0.010000**, totaling **$0.019351 before credits/contracts**. Published rates were checked 2026-10-27: [Claude pricing](https://platform.claude.com/docs/en/about-claude/pricing), [Brave Search pricing](https://brave.com/search/api/). Frozen saved rates are deliberately reported separately: Direct/v1/research use $3/$15 per million, v2 uses $2/$10, and search uses $0.01/query. No configuration was changed. Billing plan, account credits and invoices were not inspected; an exact billed amount is unknown.

## Verification and readiness

The initial complete suite passed **276 tests**; the final suite includes summary replay tests (see `validation.json`). The read-only auditor itself is tested for no private-state mutation, denied SQL writes and storage-only credentials. Original **7,953 tracked files**, including **7,411 historical dataset files**, remain byte-identical to the task's baseline. Frozen methods, approvals, original missed attempts and raw captures were not edited. Only sanitized metadata is published.

The private checkpoint restored and verified successfully, with no remote owner left at audit time. Existing replay verified baseline/refresh bytes, deterministic injury/statistics parsing, news acquisition/validation, native request/cache identity, all probabilities and the independent quote. All detailed audit checks passed. This supports one protocol-eligible primary pair; performance scores await a separately verified final outcome.

**Expansion is prepared, not activated.** The private pilot prerequisite passed, but the original approval expired at **2026-10-27T00:30:00Z**. Existing `expand()` first validates that old approval as currently live, so it cannot renew it now. A reviewed explicit renewal/migration path preserving the immutable chain and all reservations is required before the documented activation sequence can succeed. Neither live mode nor automatic enrollment was enabled; no new forecast authorization, source request or paid request was made during this audit. The Actions reviewed-SHA variable was advanced only to run the storage-only audit; it must be reviewed and pinned again before later operational dispatches.

Offline sanitized consistency replay (no source/model access):

```sh
.venv/bin/python scripts/replay_live_pilot_summary.py reports/prospective_live_pilot_1
.venv/bin/python -m unittest discover -s tests -q
```

Private raw-source verification requires the protected environment and exact reviewed SHA. Dispatch `audit-nba-pilot.yml` for GET-only restore plus private replay, or `prospective-nba.yml -f mode=replay` for the existing private replay. The public summary checker validates its manifest, clock/accounting consistency and aggregation; it cannot independently prove private source bytes and is explicitly labeled accordingly.
