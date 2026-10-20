# News retrieval and extraction validation — October 20, 2026

**Two real Brave searches found one eligible article; one real Anthropic request returned five candidates. One supported finding was recovered offline from that same response; four paraphrases were rejected. Estimated provider cost: $0.029774. No paid retries or additional tests occurred.** The initial run froze zero findings because Claude wrapped JSON in Markdown. That original capture remains unchanged; the recovered packet is explicitly derived offline with a new creation time. This is pipeline validation, not an eligible prospective forecast.

## Changes and offline evidence

Reviewed `90c1f54`, its report and the current collector/providers; `git pull --ff-only` was already current. Reused the existing collector, document store, provider transport, validators, audit and shared packet utilities; no dependencies or historical dataset files changed.

* Two deterministic publisher-scoped queries cover both teams and injury/lineup availability plus transactions/coaching developments. Local article-path rules block trackers, indexes and general team pages regardless of search ranking. The first topic cannot consume the second topic's article allowance.
* Added explicit page-bound JSON-LD article dates, alongside existing metadata and explicitly labeled publication fields. Publication clocks must agree; all dates require timezone information. Unrelated article objects, conflicting dates, live blogs, post-cutoff edits and redirects stay unusable. Source clocks and leakage filters are unchanged.
* Free unauthenticated retrieval validated actual NBA, SI and Orlando Sentinel HTML before paid calls. SI is admitted only on NBA team-article paths; Sentinel only on dated article paths. Original bodies remain in ignored captures; small attributed fixtures and original hashes are committed under `tests/fixtures/articles/`. No access controls were bypassed. Sentinel declares subscription content; only the returned text was inspected.

| Public article probe | Publication UTC | Modification UTC | Deterministic result |
| --- | --- | --- | --- |
| [NBA Magic preview](https://www.nba.com/news/2026-27-season-preview-orl) | Sep 22, 17:57:08 | Oct 3, 20:11:51 | JSON-LD only; three filtered paragraphs |
| [SI injury update](https://www.si.com/nba/magic/onsi/orlando-magic-provide-franz-wagner-injury-update-early-exit-preseason-finale-01m56by3dhpy) | Oct 18, 02:55:11 | Oct 18, 02:55:11 | Matching HTML + JSON-LD; three filtered paragraphs |
| [Sentinel practice update](https://www.orlandosentinel.com/2026/10/18/orlando-magic-practice-franz-wagner-noah-penda-jonathan-isaac-anthony-black-injury-updates-nba-preseason-kia-center-sean-sweeney/) | Oct 18, 21:19:17 | Oct 18, 21:19:17 | Matching HTML + JSON-LD; three filtered paragraphs |

All dates above are 2026, asserted by the publisher, not independently verified first publication. JSON-LD handling follows [article metadata semantics](https://developers.google.com/search/docs/appearance/structured-data/article); query targeting uses [documented Brave operators](https://api-dashboard.search.brave.com/documentation/resources/search-operators). Operators remain experimental and do not guarantee article-only results.

**Before paid calls:** the full 78-test suite, no-cost dry run, free article probes and replay of all three existing captures passed. Both credentials were loaded from ignored `.env` without displaying values. The selected model was the existing `claude-haiku-4-5-20251001`; no substitute provider was used. Limits were two searches, four article URLs, one extraction, 320,000 reserved tokens, 2,000 output tokens and $0.35 estimated cost.

## Live game, timing and queries

Fresh ESPN schedule discovery and both team schedules identified **Atlanta Hawks at Orlando Magic, `401909834`**, still scheduled and upcoming. NBA schedule feeds returned 403; schedule provenance remains `ESPN_fallback`. Recorded tipoff: **October 21, 23:00 UTC**; target T−24h: **October 20, 23:00 UTC**.

Collection started **15:32:35.331314 UTC** on October 20. Actual snapshot/source cutoff: **15:32:59.551277 UTC**; original packet creation: **15:32:59.551278 UTC**. Deviation: **−26,820.448723 seconds**, early by 7h 27m 0.448723s. Exact eligibility and practical ±300-second eligibility are **both false**. The derived packet was created at **15:38:12.089129 UTC**, without backdating creation or changing the original source snapshot.

Both searches used the following shared scope/exclusions:

```text
(site:nba.com OR site:espn.com OR site:apnews.com OR site:reuters.com OR site:si.com OR site:orlandosentinel.com) -standings -tracker -"injury report" -"depth chart"
```

The two query prefixes were `("Orlando Magic" OR "Atlanta Hawks") (injury OR lineup OR availability)` and `("Orlando Magic" OR "Atlanta Hawks") (signed OR waived OR traded OR coach)`. The [sanitized JSON summary](prospective_retrieval_validation.json) preserves both complete query strings and per-query URL decisions.

| Query | Returned URL | Result |
| --- | --- | --- |
| Injury/availability | [ESPN injuries](https://www.espn.com/nba/injuries) | Blocked tracker URL; not retrieved |
| Injury/availability | [AP matchup article](https://apnews.com/article/orlando-magic-atlanta-hawks-ce43e787cec64362b086091669ce40a2) | Retrieved 15:32:52.482445 UTC; HTTP 403; publication unverified; rejected |
| Injury/availability | [SI injury article](https://www.si.com/nba/magic/onsi/orlando-magic-provide-franz-wagner-injury-update-early-exit-preseason-finale-01m56by3dhpy) | Retrieved 15:32:54.236645 UTC; HTTP 200; publication/modification Oct 18, 02:55:11 UTC; accepted |
| Injury/availability | [Hawks roster](https://www.nba.com/hawks/roster) | Blocked roster URL; not retrieved |
| Transactions/developments | [ESPN transactions](https://www.espn.com/nba/transactions) | Blocked dynamic URL; not retrieved |
| Transactions/developments | [Hawks roster](https://www.nba.com/hawks/roster) | Repeated blocked roster URL; not retrieved |
| Transactions/developments | [SI Magic index](https://www.si.com/nba/magic) | Blocked team index; not retrieved |
| Transactions/developments | [ESPN Magic team page](https://www.espn.com/nba/team/_/name/orl/orlando-magic) | Blocked team page; not retrieved |

Totals: **8 results, 7 unique URLs, 2 page requests, 1 rejected page, 1 eligible article**. No publication date was inferred for blocked/unavailable pages. Search snippets stayed audit-only. Only the validated SI paragraphs, their source identifiers/timestamps, team names and allowed categories entered model context.

## Real extraction and deterministic offline recovery

Anthropic returned **HTTP 200, `end_turn`**, model **`claude-haiku-4-5-20251001`**, at **15:32:59.545198 UTC**. It reported **593 input / 533 output tokens**, with zero cache/tool usage. Request latency: **3.860180 seconds**. Response body SHA-256: `0bf076d918bfff408e7a85dcc32198c0f36dbd31a2bbc2d5f0857a710e1d1747`.

The initial adapter rejected its whole-response Markdown JSON fence, freezing zero findings. Offline code now accepts that precise wrapper without accepting prose or repairing malformed JSON. A second deterministic formatting step can map an ASCII-case-only difference to a **single original source span**; emitted claims must still be literally present in the cited text. Day-to-day/soreness are recognized injury terms. Tests reject changed words, punctuation, negation, ambiguous spans, unsupported names and paraphrases. The original candidate and normalization decision remain audit-only. No source/timestamp/leakage requirement was relaxed.

The saved real response yields **one validated finding**: Orlando Magic player **Jase Richardson**, injury update, **“day-to-day with low back soreness”**. The source text explicitly attributes that status to Richardson. Claude's initial capital `D` maps to the actual lowercase `d`; no words or punctuation were supplied by a model repair. This is an October 18 report, not confirmation of availability for October 21. SI attributes the update to Sentinel reporting; it is not an official injury submission.

Citation: the SI article above, published **2026-10-18T02:55:11Z**, retrieved **2026-10-20T15:32:54.236645Z**. Source reference: `2c23258be8e387754e146f3055e2464dca840fe6c08596e18869f0d32544a1d2:paragraph:2`. Original article SHA-256: `a564a62a964dc4789a716496059ea07ae1e3844baf5c2671d48fb91809a354f0`.

The other **four candidates** (two Wagner descriptions plus Richardson/Penda descriptions) paraphrased or omitted source wording and failed `claim_or_player_not_supported_by_excerpt`. None were silently rewritten into substantive claims. The accepted finding's claim, player/team context and source reference were checked against the captured paragraph. Both original and derived packets preserve `point_in_time_verified: false` and unversioned-source uncertainty.

## Costs, packets and remaining limits

Brave latencies: **1.319091s / 1.377461s**, both HTTP 200. At configured conservative rates, search cost is **$0.020000** and reported-token inference cost **$0.009774**, total **$0.029774** (about three cents; not an invoice). Reserved upper bound used: **$0.060449**. Offline recovery cost **$0**; replayed usage records describe the original requests, not new charges.

The official NBA [11:15 AM ET PDF](https://ak-static.cms.nba.com/referee/injury/Injury-Report_2026-10-20_11_15AM.pdf), issue **15:15 UTC**, was captured **15:32:50.518411 UTC**. Both teams were `not_yet_submitted`, with no relevant player rows. Statistics correctly show season-opening 0–0 records; undefined recent form, rest and scoring averages are omitted. Packet structure is complete; injury/roster coverage is incomplete and does not imply health.

* Original immutable packet: `1f7afa70e085ff18c5bf296d4e4a1c3844ec86b033828501c5675c6fe8ab48f1` (zero findings).
* Offline-derived packet: `76c5609a2fe636818795562cadf96557d0f6f5771bc5484ea94d57d8d4d65ffe` (one finding). Derivation binds the original packet and bundle-manifest hash and records current creation time.
* Both future consumer loaders load **identical derived packets/hashes**. Offline replay reproduces both original and derived bundles, the first paid capture and both committed public captures. All **81 tests pass** after the fixes.

The full path has now processed actual search, article and model responses into a supported frozen claim, with the final format fixes validated against saved real responses offline. **The corrected adapter was not subjected to another paid call.** Remaining limitations: search still returns general pages despite targeting; AP may block retrieval; some publishers are subscription-limited; four of five model candidates were not verbatim; source timestamps do not certify historical payload versions. No on-time prospective evaluation was demonstrated. No probability forecasting, LEAP aggregation, trading, historical sample/outcome/market-price changes or new dataset versions were implemented.

Raw provider requests/responses, private captures, local configuration and credentials remain ignored by Git. Only public excerpt fixtures, sanitized audit metadata, code/tests and documentation are committed. To reproduce the exact hashes elsewhere, securely copy the ignored capture directories; the sanitized summary alone is not sufficient.

```sh
# Offline replay, no credentials/network/cost.
.venv/bin/python scripts/collect_prospective.py --replay captures/article_retrieval_validation/live_test
.venv/bin/python scripts/collect_prospective.py --replay captures/article_retrieval_validation/offline_reprocessed
.venv/bin/python -m unittest discover -s tests -q

# Re-derive separately from the same saved responses; no additional API calls.
# A new creation timestamp yields a new hash; replay of that bundle is exact.
.venv/bin/python scripts/collect_prospective.py --reprocess captures/article_retrieval_validation/live_test \
  --output captures/article_retrieval_validation/another_offline_derivation
```
