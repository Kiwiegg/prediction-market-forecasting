# Authorized retries and merged development results

**15 failed LEAP group requests succeeded on retry, recovering six game forecasts. Coverage is now 40/50, up from 34/50.** The 16th retry returned HTTP 403, triggering the prespecified stop rule. Twenty-four remaining requests were not retried. No second retry or new direct forecast was made.

## Why the 403s occurred

The original saved errors contain `error.type="forbidden"` and `message="Request not allowed"`, without an error-body request ID. [Anthropic documents](https://platform.claude.com/docs/en/api/errors) its usual 403 as `permission_error`, and rate limiting as 429. The observed response therefore does not establish that the API key was invalid, the prompt was malformed, or a rate limit was hit. An access-control denial occurred, but the captures cannot identify whether Anthropic or an intermediary issued it. Fifteen identical previously failing requests later succeeded; the denial then recurred. This is consistent with intermittent access blocking, not a confirmed root-cause diagnosis. Three original failures were connection errors (two URL errors, one connection reset).

## Retry controls and immutable merging

The operator explicitly authorized retries after the original no-retry experiment. [Authorization](../../../experiments/development_50_retry_authorization.json) and tested retry/merge code were committed at `6f35d47` before new calls. The plan allowed one new attempt for each of 40 failed development requests, at most $1.20 reserved cost, stopping after the first unsuccessful attempt. Model, prompts, settings, request/group/evidence hashes, alpha values, historical packets and split remained unchanged. No successful or source-missing group was re-elicited; the reserved evaluation subset was not accessed.

The original run and shared cache remain immutable. Each retry references its original failed record hash. The merged cache selects a successful retry only for an originally failed request; it retains all other original observations. All 34 originally successful game records are exactly unchanged. The new merged run is sealed with per-group selection lineage and can be verified using the original snapshot/request validator. The merge itself makes no API calls.

| Retry disposition | Count |
| --- | ---: |
| Originally failed requests eligible | 40 |
| Retried once | 16 |
| Successful replacements | 15 |
| Retry failed with HTTP 403 | 1 |
| Not attempted after stop | 24 |
| Recovered complete game forecasts | 6 |
| Final valid LEAP game forecasts | 40 |
| Final incomplete games | 10 |

Recovered games: 401811000, 401811008, 401810509, 401810032, 401810749, 401810078. Twenty-five required group observations remain failed in the merged selection. Source-missing groups remain 73, including 23 unusable injury groups and all 50 historical-news groups; no missing observation was imputed.

## Recomputed comparison on the identical 40-game intersection

| Method | n | Brier | Natural-log loss |
| --- | ---: | ---: | ---: |
| direct | 40 | 0.218020 | 0.635184 |
| leap_raw | 40 | 0.257588 | 0.725746 |
| leap_conservative | 40 | 0.243513 | 0.680649 |
| kalshi | 40 | 0.197027 | 0.571403 |
| constant_50 | 40 | 0.250000 | 0.693147 |

These n=40 scores must not be compared directly with the original n=34 scores as if only model outputs changed. Six different games have entered the common intersection. All 50 rows, ten exclusions, per-game scores/differences and LRs are preserved in [results.csv](results.csv), [per_game.json](per_game.json), and [observations.json](observations.json). The original [34-game report](../report.md) remains unchanged.

Raw/conservative probabilities use the same merged LR observations. The [diagnostic export](diagnostics.json) recomputes the original directionality rule, group distributions, missingness, injury strata, sufficiency/contribution diagnostics and ten-bin calibration. No alpha fitting, prompt changes or outcome-dependent exclusions occurred.

## Descriptive paired bootstrap

The unchanged analysis plan uses 10,000 paired game resamples, seed 20261021, shared resampled indices across comparisons and 95% percentile intervals with linear interpolation. Here n=40. Intervals remain descriptive because these are dependent historical development observations, with possible model memory and incomplete provider coverage.

| Brier difference | Mean | 95% interval |
| --- | ---: | --- |
| direct_minus_kalshi | +0.020993 | [-0.007235, +0.049688] |
| leap_conservative_minus_direct | +0.025493 | [-0.020739, +0.066500] |
| leap_conservative_minus_kalshi | +0.046485 | [+0.010637, +0.080487] |
| leap_raw_minus_direct | +0.039568 | [-0.012490, +0.088290] |
| leap_raw_minus_kalshi | +0.060560 | [+0.018661, +0.101467] |

## Cost and attempt accounting

- Retry requests reported **20,817 input / 285 output tokens**, and summed provider latency **50.796403 seconds**.
- Estimated token cost is **$0.066726** at the unchanged conservative $3/$15 per million rates. The failed retry has no usage and retains a **$0.025584** reserve: **$0.092310 recorded estimate**, not an invoice.
- Sixteen request reservations totaled **$0.447594**, below the $1.20 retry cap. No additional provider requests were made after the repeated denial.
- Since the start of the full-development completion task, cumulative new attempts are **45 direct + 130 LEAP** (114 original plus 16 retries), still within the earlier 45/180 request ceilings. Cumulative reservation bounds are **$5.409789**, below the earlier $10 maximum.
- Cumulative full-development recorded estimate including the new retry is **$1.920594**: **$0.740457 reported-token estimate + $1.180137 unknown-usage reserves**. Including the older five-game pilots gives **$2.026029**. No unavailable usage is assumed zero.
- The merged export’s `resources` describes **selected effective observations only**; it excludes superseded failed attempts and the latest unsuccessful retry. Its zero new merge reservations mean offline copying/reaggregation, not free inference. The separate [attempt audit](../../development_50_retry_audit.json) preserves all original/retry references and retry costs, so replacement does not erase prior spend or failures.

## Validation and remaining work

All 136 tests passed before retries. Tests cover failed-only eligibility, stopping after a renewed denial, immutable original records, same-request identity, merging only successes, zero-network merge/verification, repeat execution without duplicate paid calls, budgets and prevention of a third attempt under a different output directory. Private retry/merged replay and public arithmetic replay pass; original data, caches and published initial results retain their hashes.

After merging, all **137 tests** pass, including the new public merged replay and attempt-audit reconciliation. Fingerprint verification confirms all **8,955 protected original files** remain unchanged.

```sh
.venv/bin/python scripts/retry_leap.py --source captures/leap_nba_v1/development_all --verify captures/leap_nba_v1/development_retry_once
.venv/bin/python scripts/leap_forecast.py --verify captures/leap_nba_v1/development_merged
.venv/bin/python scripts/analyze_development.py --replay reports/development_50/merged
.venv/bin/python -m unittest discover -s tests -q
```

The existing private `development_all` and `development_retry_once` bundles remain the originals; `development_merged` contains the selected observations and bound lineage. Raw responses and credentials remain outside Git. The cause of the recurring denial still needs access/network investigation before another retry authorization; this run does not establish 50/50 LEAP coverage or comparative skill.
