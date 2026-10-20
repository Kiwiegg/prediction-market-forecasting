# Prospective validation: actual observations and limits

Validation ran on **2026-10-20 UTC**. `BRAVE_SEARCH_API_KEY` and `ANTHROPIC_API_KEY` were absent. No paid search or inference was executed. Synthetic provider/fixture tests are not presented as real collected news.

## Real one-game public-source capture

The [completed audit](one_game_public_capture_complete/evidence_audit.md) and [frozen packet](one_game_public_capture_complete/evidence_packet.json) concern ESPN game **401909090**, Oklahoma City Thunder at San Antonio Spurs, recorded tipoff **2026-10-21 01:30 UTC**.

| Measurement | Observed value |
| --- | --- |
| Nominal T−24h | 2026-10-20 01:30:00 UTC |
| Collection start | 2026-10-20 03:13:36.092783 UTC |
| Actual snapshot/packet creation | 2026-10-20 03:14:02.076933 UTC |
| Deviation | **+6,242.076933 seconds**, approximately 104 minutes late |
| Strict T−24h eligible | **false** |
| Shared packet SHA-256 | `f846b19cc98077000242ebcbc01b594f3efbd6d3d3d4ffbfe2b53058d78df931` |
| Season records | Genuine 0–0 for both teams; target present in both season feeds |
| Recent form / rest | Omitted: no completed regular-season games / no reliable latest completed game |
| Official PDF issue | 2026-10-20 03:00 UTC (23:00 ET October 19) |
| PDF capture availability bound | 2026-10-20 03:14:01.973824 UTC |
| Relevant player/status rows | **5**, both team sections reported; no extraction ambiguity flags |
| Paid search / inference | Disabled; no news findings and no inferred player availability |

The packet and lineage reproduce offline, and both consumer entrypoints load the same hash. This validates free source integration, schema, temporal labeling, deterministic extraction, freezing and replay. It is **not** a live paid-news test or an exact T−24h capture.

The earlier [public capture](one_game_public_capture/evidence_audit.md), hash `23c9c72b48d9fe53862faaa097326b6e99d91074349fb9543e87287d385b4977`, is preserved unchanged. Its two-team-only parser mapping caused unrelated reason fragments to raise ambiguity flags on a target player. The subsequent capture adds a captured full 30-team catalog and resolves that boundary problem. Its pinned settings retain the older behavior for reproducibility; the example configuration enables the complete catalog. Both original captures replay without network or file changes. These are individual prospective attempts, not historical dataset versions.

## Source behavior actually observed

* Both NBA CDN schedule URLs returned **403**. Discovery used explicitly labeled ESPN daily scoreboards, which returned **200** and upcoming regular-season events for October 20–22. Current NBA/ESPN corroboration could not be live-tested. ESPN feed stability/completeness is not guaranteed by a documented API contract.
* An initial ESPN date-range query returned **400**. The working collector uses separately captured daily requests.
* The 2026–27 official injury page returned **404**. The preceding season's page returned **200** with current rolling links. The latest captured eligible PDF had an October 19 issue date and matching target game sections. The page title alone is not used as a season/timestamp assertion.
* The full ESPN team catalog and both target team schedules returned **200**. No past season games existed for these teams at the snapshot; recent/rest features correctly stayed missing.
* Official availability uses an observed capture upper bound, not independently established first publication. Latest report selection is bounded to linked candidates, not globally certified.

All these responses, including unsuccessful exploratory probes, remain under this directory with URLs, raw bytes, retrieval clocks and SHA-256 hashes. The completed capture's `bundle_manifest.json` additionally pins its source files, settings and audit.

## Offline validation and remaining blockers

All **56 tests pass**. They cover real-provider request/response contracts using mocked transport, opt-in gates, malformed JSON/usage, truncation/tools/errors, pre-call token/cost exhaustion, immutable cache integrity, future/target exclusion from statistics, missing/submitted injury states, publication/retrieval boundaries, source-text/search-result leakage, complete fake-provider end-to-end collection, consumer identity and provider-free offline replay. The existing 200-game leakage/price/lineage suite also passes. No historical dataset files were modified.

Outstanding live validation:

1. **Real paid-provider behavior:** credentials and explicit `--allow-search --allow-inference` are required. The documented Brave/Anthropic adapters are contract-tested but actual authentication, paid quotas, returned-page usefulness, model extraction quality and real usage remain untested. The optional compatible model gateway is also not live-tested.
2. **A real exact T−24h snapshot:** none was attempted at its exact nominal instant. The next target in this saved discovery window was **2026-10-20 23:00 UTC** for games 401909834 and 401909835 (tipoffs October 21 23:00 UTC). Rediscover near that time, verify schedule changes and credentials, and run one chosen game under the documented budgets. Collection latency must be accounted for; invoking at the target does not make a later completed snapshot on-time. Exact deadline synchronization remains unvalidated, and nonzero deviations remain ineligible.
3. **Later-season nonempty live team history:** positive history reconstruction and future-result exclusion are tested offline; these opening-day live teams had no prior games to exercise that branch against current feeds.
4. **Archive/article completeness:** current source availability does not prove universal season coverage, immutable publisher article versions, or accessible dated text on every allowlisted site. Unsupported observations remain missing.

Reproduce the saved capture without keys or network:

```sh
.venv/bin/python scripts/collect_prospective.py --replay \
  reports/prospective_validation/one_game_public_capture_complete
.venv/bin/python -m unittest discover -s tests -v
```
