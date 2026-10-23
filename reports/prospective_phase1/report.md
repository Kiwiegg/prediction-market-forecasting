# Prospective Phase 1: offline validated; live discovery blocked

**The orchestration is implemented and passes offline validation. A live prospective forecast was not produced.** The first public discovery request returned HTTP403 from the official NBA CDN; collection stopped immediately, without ESPN fallback, Brave search, article retrieval or Anthropic inference. Current game/window eligibility remains **unknown**, rather than a verified absence of suitable games. No eligible capture or real forecast is fabricated.

Actual source request: `https://cdn.nba.com/static/json/staticData/scheduleLeagueV2_1.json`; response received **2026-10-23T15:56:13.751484Z**. The exact original clocks/body hash and one-attempt audit are in [discovery_audit.json](discovery_audit.json). The capture body and headers remain private. This unscored discovery preflight happened before the prospective protocol commit; no scored evidence or inference preceded that commit.

| Actual live activity | Count |
| --- | ---: |
| Public source GET attempts | 1 |
| HTTP403 responses | 1 |
| Fallback/source retries | 0 |
| Brave queries / articles | 0 / 0 |
| Anthropic extraction / forecast calls | 0 / 0 |
| Provider tokens / estimated paid cost | 0 / $0 |
| Verified eligible live packets / scored games | 0 / 0 |

The permanent private access-denial journal blocks further live work under the current authorization. No endpoint, credential, header or cache-directory changes were used to circumvent denial. The response does not identify its root cause or establish a problem with model credentials. Provider availability and live source coverage are untested in this phase.

## Frozen protocol and implementation

The [prospective protocol](../../experiments/prospective_phase1_protocol.md), [asset registry](../../experiments/prospective_phase1_assets.json), configuration, tested code and [operating instructions](../prospective_phase1_operations.md) were committed at **`6df24ce`** before any scored prospective collection. Direct, v1 and v2 prompts, model, generation settings, priors, groups, LR bounds/mapping and alpha1/0.5 are unchanged. The original historical 200-game dataset, split, packets and all prior forecasts remain unchanged.

The new [orchestrator](../../scripts/prospective_study.py) reuses existing authoritative discovery, statistical reconstruction, official injury parsing, bounded news research, shared snapshot loading, native request/caching/validation functions and aggregation. It selects one currently upcoming regular-season game, freezes one packet and supplies that exact parent hash to all three methods. No model tools, browsing or independent retrieval is enabled. Raw/conservative variants share their method's group observations.

The study's **primary metric is paired Brier, v2 raw minus Direct**. Secondary measures include log loss, calibration, both v1/v2 variants, constant50% and a separately captured Kalshi benchmark. The eventual fixed target is the first **100 primary-eligible games** in cutoff chronological order, with all attempts and exclusions retained. Market/v1 missingness never removes an otherwise valid primary pair. No prompt/parameter tuning or score-based stopping is allowed. No campaign or recurring scheduler was installed or launched.

## Timing, information boundary and incomplete evidence

Record scheduled tipoff, intended T−24h, collection start, actual snapshot, packet creation, inference start/request/response and final seal. Use elapsed UTC24h, not a local calendar subtraction across daylight-saving time. Exact capture, early/late within ±300 seconds and early/late outside that window remain distinct. Collection start, snapshot and packet creation must all be within tolerance; all method records must seal before tipoff. Operational eligibility is not an exact-time claim.

The source information/retrieval cutoff is **min(actual snapshot,T−24h)**. A late-within-window capture cannot introduce newly retrieved or revised-after-target source material. Previous-game source and retrieval clocks govern statistical eligibility; source failures remain omissions, not zero-game records. Rest retains its existing definition at actual snapshot using eligible past-game facts. Target-game summary endpoints are blocked during collection. Raw feed scores/odds, search snippets, raw audits and later evaluation files stay outside model context.

Both team season schedules must corroborate the fixture and both season records must be reconstructible before forecasting. A verified zero-game record is valid; missing/inconsistent history is not. Unavailable injury reports, not-submitted teams and absent news remain explicit and never mean healthy players. Valid research finding no usable news differs from a failed search/extraction: errors freeze an incomplete audit and block forecasts. Post-cutoff, undated, unsupported, revised-later or late-retrieved articles remain rejected under the existing rules.

Frozen v2's qualifier whitelist does not accept the older collector's prospective label. New packets use its existing conservative `timestamped_history_unversioned_payloads` classification for unversioned timestamped sources, while preserving prospective mode, actual clocks and lineage separately. Verification flags stay false; no historical capture is relabeled. This compatibility choice is explicit in the protocol and does not modify any frozen projection or forecasting prompt.

## Budgets, failures and immutability

One shared append-only ledger caps the full pilot at **20 Anthropic requests, two Brave searches, four article GET attempts and $1 conservative reservations**, including research and all forecasters. Forecast bounds/rates remain those in each frozen method. Each new request is reserved before network use; unknown requests retain their reserves. Public/article retrieval uses one HTTP attempt, avoiding hidden retries against the article cap.

The first HTTP403 or explicit access denial stops subsequent work and preserves a permanent journal. Native caches and claim markers prevent paid retries. Inference failures/insufficiency remain missing; legitimate source skips retain their original LR1 semantics. Interruptions preserve successful observations and seal partial records; a separately requested offline seal never resends an unknown claim. A seal after tipoff is ineligible. One fixed live output/authorization prevents bypassing failed requests through another directory.

## Offline validation actually performed

All **191 unit tests pass**, including 12 new prospective test cases. The full suite also passes in a clean Git snapshot (90.517s), with no `.env` or private captures; sanitized public replay passes there. Hash checks preserve **22,856 original files**, including **7,608 historical data files**, with no differences. See [validation.json](validation.json) and [preservation.json](preservation.json). New tests cover:

- Discovery eligibility, completed-game exclusion, UTC/DST arithmetic, explicit timezones and ±300-second boundaries.
- Source availability after target, missing versus zero-game histories, future/late news rejection, and target-summary isolation.
- Existing collection/statistics/injury/news code feeding all frozen methods against one parent hash; safe factual excerpts and not-submitted states.
- Extraction errors blocking readiness, source skips and provider failures; existing frozen-method tests additionally cover malformed/insufficient responses.
- Shared budgets, article/query/call limits, first403 stopping, interrupted claims, immutable caches and replay.
- Postgame/final-outcome gates, rescheduled/canceled fixtures, independent quote validation and primary-pair retention when v1/market are missing.

The [sanitized mock audit](mock_validation/audit.json) is **artificial**, mode `offline_mock`, with no provider calls. Its game is `offline-prospective-fixture` with fixture teams and virtual2030 clocks. It is **ineligible for live evaluation**. All three method records reproduce from the same packet hash:

`cac5bf0e4524a9fbdeb12e4a3d2ea4ec96691382fd499ba9f875faea77bde197`

Direct and both variants of each LEAP method produce mock probability0.5; these are engineering test outputs, not real Claude forecasts or accuracy evidence. A separate source fixture exercises deterministic statistics, a parsed injury fixture with an unsubmitted opponent, a verbatim-supported news claim and all three methods. Its PDF parsing/search/extraction are mocked; no synthetic finding is presented as current NBA news.

Private mock replay checks evidence/capture and cache-record hashes, group/request identities, structured observation validity and aggregation. Public replay reconstructs the frozen requests and aggregation without private captures or credentials. It does not independently authenticate provider inference or publisher history. The real403 audit and [no-cost dry run](dry_run.json) explicitly retain no selected game/target rather than reusing an expired ID.

## Independent benchmark and postgame evaluation

[prospective_evaluate.py](../../scripts/prospective_evaluate.py) is separate from inference. Its live benchmark command captures home-YES market metadata and a unique agreeing basketball milestone in a separate process/directory. It requires an open mapped market and valid two-sided dollar bid/ask, retaining raw sources, midpoint/spread, clocks and hashes. Quote retrieval must finish in **[target−300s,target]**; late quotes or missing benchmark captures are never backfilled. Quote-refresh age stays unknown. This live procedure leaves the historical 20-minute candle rule unchanged. No benchmark request was executed here.

Outcome capture requires an existing sealed live forecast and time after tipoff. Scoring additionally requires final, timestamped, team-matched outcome sources and unchanged scheduled fixture; ongoing, postponed, canceled, rescheduled or unverified results remain blocked/excluded. Model-facing packets never receive outcomes or prices. All benchmark/outcome behavior was tested with fixtures only; there is no live scored result.

## Reproduction and remaining validation

```sh
.venv/bin/python scripts/prospective_study.py --dry-run
.venv/bin/python scripts/prospective_study.py --replay reports/prospective_phase1/mock_validation
.venv/bin/python -m unittest discover -s tests -q

# Fresh artificial run; no network or credentials.
.venv/bin/python scripts/prospective_study.py --mock --output captures/prospective_phase1/mock
.venv/bin/python scripts/prospective_study.py --replay captures/prospective_phase1/mock
```

See [operating instructions](../prospective_phase1_operations.md) for explicit opt-in live commands, independent cutoff quote capture, offline partial sealing and postgame evaluation. No live command was attempted after the recorded403. Fresh authorization is required before checking source access again; do not delete the stop journal or force an off-window paid test.

**Still unvalidated live:** successful current schedule discovery, actual within-window source capture/readiness, current injury/news coverage, integrated paid research plus all three forecasts, independent Kalshi capture/mapping, and later final-outcome scoring. The workflow has offline engineering validation; Phase1 has not demonstrated a real eligible capture. The future 100-game study remains unstarted, with no method tuning or additional historical enrichment.
