# One-game paid research validation — October 20, 2026

**Brave worked; Anthropic extraction was not reached. Zero validated news claims. Estimated provider cost: $0.01.** The search found no eligible dated article, so the pipeline correctly made no inference request. This does not validate live extraction or readiness for forecasting. No paid retry or second test was made.

## Preflight and limits

Pulled `main` with `git pull --ff-only`; it was already current at `d25f834`. Both credentials were present in the Git-ignored `.env` and loaded into the child process without displaying values. The collector does not automatically read `.env`. Configuration validation, the no-network dry run and all **63 existing tests** passed before the paid request.

An authenticated **non-inference** `GET /v1/models/claude-haiku-4-5-20251001` returned HTTP 200 at `2026-10-20T14:57:44.764769Z`, confirming account access to the selected model. This is not an extraction test. Fresh public schedule discovery, followed by a no-cost saved-schedule dry run, selected the closest T−24h target, with game-ID tie breaking; no price, outcome or news availability influenced selection.

The run used the existing Brave/Anthropic adapters and all five requested flags: `--live-test --live --allow-network --allow-search --allow-inference`. An ignored operator configuration additionally fixed limits to **one query, two articles, 320,000 reserved tokens, 2,000 maximum output tokens, and $0.35 estimated provider cost**. Extraction is at most one call by construction. No recurring execution was launched.

## Selected game and frozen capture

| Field | Observed value |
| --- | --- |
| Game | Atlanta Hawks at Orlando Magic, ESPN `401909834` |
| Recorded tipoff | 2026-10-21 23:00:00 UTC |
| Target T−24h | 2026-10-20 23:00:00 UTC |
| Collection start | 2026-10-20 14:58:07.349523 UTC |
| Actual snapshot / packet cutoff | 2026-10-20 14:58:28.761724 UTC |
| Packet creation | 2026-10-20 14:58:28.761725 UTC |
| Target deviation | −28,891.238276 seconds; **early by 8h 1m 31.238276s** |
| Timing eligibility | Exact T−24h: **false**; configured practical ±300 seconds: **false** |
| Frozen packet SHA-256 | `4ed09fe0c0fd34876c7157e00ebeb1382044d8e283f9903bb77dcbd17fb22866` |

No discovered game was within the practical T−24h window at collection time. This was a component/integration test for a genuine upcoming game, not an on-time evaluation capture. For this game the practical window would be October 20, 22:55–23:05 UTC; another paid run requires fresh operator approval.

The NBA CDN schedule endpoints returned 403. ESPN daily scoreboards supplied the explicitly labeled `ESPN_fallback`; both team season schedules corroborated the matchup/tipoff. Both teams had zero completed regular-season games. Packets contain 0–0 records and venue splits, while scoring averages, recent form and rest are explicitly omitted for lack of completed games.

## Search and source validation

Query: **`Orlando Magic injury status update`**. One Brave GET returned HTTP 200 and four distinct URLs; search latency was **1.423164 seconds**. One page was retrieved, one page rejected, zero model candidates/accepted findings/duplicate claims. The two-page limit is a ceiling, not a requirement to fetch ineligible sources.

| Discovered source | Retrieval/publication | Decision |
| --- | --- | --- |
| [Sports Illustrated injury update](https://www.si.com/nba/magic/onsi/orlando-magic-provide-franz-wagner-injury-update-early-exit-preseason-finale-01m56by3dhpy) | Not fetched; publication not assessed | `disallowed_source_url` |
| [Orlando Sentinel practice updates](https://www.orlandosentinel.com/2026/10/18/orlando-magic-practice-franz-wagner-noah-penda-jonathan-isaac-anthony-black-injury-updates-nba-preseason-kia-center-sean-sweeney/) | Not fetched; publication not assessed | `disallowed_source_url` |
| [ESPN injury tracker](https://www.espn.com/nba/injuries) | HTTP 200; retrieved **14:58:28.707727 UTC**; publication **unverifiable** | `publication_time_unverifiable` |
| [BasketNews injury update](https://basketnews.com/news-257608-orlando-magic-coach-provides-injury-update-on-franz-wagner-other-players.html) | Not fetched; publication not assessed | `disallowed_source_url` |

The allowed-source policy remains NBA/team sites, ESPN, AP and Reuters. Three results were outside that policy. The ESPN body (555,293 bytes, SHA-256 `4d44d6fa77abcf656d5addd8b4aa96116382a4de9e98df904229f6724d738ab9`) contained no accepted article publication/modified metadata, no `datePublished` field, no JSON-LD, and no article/main paragraphs recognized by the parser. It is an undated dynamic tracker, not a qualifying captured article. Retrieval time, HTTP headers and dates in search results cannot substitute for publication evidence.

**Diagnosis:** the broad query/source-allowlist mismatch exhausted most results; the remaining tracker lacked publication evidence and usable article text. Extraction was skipped before a model request. There is no observed Claude failure or extracted injury/roster claim. No accepted news claim exists for a source-support check; no player is inferred healthy. A future improvement could scope searches toward approved article sources, validated offline first. Neither source policy nor timing/leakage checks were relaxed here.

## Official injury evidence

The current official 2026–27 archive returned 200. The preceding season URL returned 301 and was not followed, preserving the source policy. The newest eligible linked PDF retrieved was the [October 20, 10:45 AM ET report](https://ak-static.cms.nba.com/referee/injury/Injury-Report_2026-10-20_10_45AM.pdf), issue **14:45 UTC**, captured **14:58:25.630170 UTC**. Original bytes, PDF clocks, hash and the 30-team mapping source are retained locally.

Deterministic PDF parsing mapped **both Orlando and Atlanta to `not_yet_submitted`**, with zero relevant player/status rows and no mapping uncertainty flags. An independent text check of page 2 confirmed the target date/matchup and both `NOT YET SUBMITTED` entries; the PDF creation clock was **14:45:02 UTC**. These are submission states, not evidence that players are available. Retrieval establishes an observed public-availability upper bound, not first publication or globally certified latest-report coverage. Claude was not used for official injuries.

## Usage, validation and remaining work

| Measurement | Actual observation |
| --- | --- |
| Paid provider requests | Brave 1; Anthropic 0; paid retries 0 |
| Anthropic reported input/output tokens | 0 / 0; no inference request or usage receipt |
| Search reservation | 32,768 tokens as a response-byte upper bound; not LLM billing |
| Estimated search / inference cost | **$0.01 / $0.00** at configured conservative rates |
| Reserved cost upper bound used | **$0.01**, below $0.35; not an account invoice |
| Provider latency | Brave 1.423164s; Anthropic not applicable |
| Whole collection duration | 21.412201s |

The packet is schema-valid, frozen and auditable, but its information coverage is incomplete: official player reports are not yet submitted, usable news is absent, and season-opening statistics omit undefined features. It is outside both timing policies. **The pipeline is not yet validated for forecasting use:** live factual extraction, a dated supported claim, and an appropriately timed capture remain untested. All model extraction behavior is still covered only by mocked/offline tests.

Offline replay of this run and both committed public-source runs succeeded. Both future consumer loaders returned identical complete packets and the exact live hash above. No historical dataset file, game selection, outcome or 20-minute market-price rule was changed.

A deterministic audit wording defect was fixed: enabling extraction previously displayed a model-extraction method even when no request occurred. New audits explicitly report enabled state, actual inference-request count, validated source-page count and a skip reason. The original immutable live bundle is preserved unchanged. Three offline regressions cover this exact no-usable-source path, absence of inference/retries, timestamp substitutes, counters and honest audit wording. **All 66 tests pass** after the change.

The [sanitized machine-readable summary](prospective_paid_validation.json) records public URLs, timestamps, counters, costs and hash. Original provider bodies/requests, capture metadata, local configuration and credentials remain under Git-ignored paths; none are committed. The bundle contains 35 hash-bound files and lives at `captures/paid_research_validation/live_20261020T1500Z`; replaying it elsewhere requires securely copying that directory. The committed summary alone cannot reconstruct private original captures.

```sh
# Offline only; no credentials or provider calls.
.venv/bin/python scripts/collect_prospective.py --replay \
  captures/paid_research_validation/live_20261020T1500Z
.venv/bin/python scripts/collect_prospective.py --replay \
  reports/prospective_validation/one_game_public_capture_complete
.venv/bin/python -m unittest discover -s tests -v
```

No second paid test is authorized by this report. A future live validation must rediscover an upcoming game, inspect its dry-run plan, receive operator authorization, and retain the same safeguards.
