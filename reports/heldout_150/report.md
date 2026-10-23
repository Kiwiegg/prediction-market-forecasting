# One-time 150-game historical held-out evaluation

**All planned requests finished; incomplete forecasts remain missing.** Coverage: direct **148/150**, v1 **144/150**, v2 **144/150**. The primary paired comparison uses **n=143**; v2 raw minus direct Brier is **0.011819**, with a descriptive 95% paired bootstrap interval **[-0.007015, 0.030833]**. Negative differences favor v2. No method was tuned after held-out results were opened.

**The observed primary result does not demonstrate an improvement over direct LLM.** V2 raw has higher Brier and log loss than direct on the same 143 games; the primary interval includes zero. V2's strength judgments are more directionally consistent than v1's (0 versus 16 weaker-team judgments among 47 common assessable games), but this consistency did not translate into a lower primary forecasting loss. On the separate 139-game seven-method intersection, v2 has lower observed losses than v1, while Kalshi has the lowest observed Brier/log loss. These are descriptive comparisons, not causal or contamination-free skill claims.

The experiment made **914 new Anthropic requests**, with **$3.790550** estimated from reported tokens plus **$0.225613** unknown-usage reserves. Cumulative pre-call reservations were **$22.943654**, within 1,200 requests/$40. Stop reason: **`completed`** (All frozen requests processed). No paid retries, searches or evidence collection occurred.

## Precommitted protocol and inference isolation

The [protocol](../../experiments/heldout_150_protocol.md), [machine-readable rules](../../experiments/heldout_150_rules.json), exact [150-game request/evidence plan](../../experiments/heldout_150_plan.json) and tested execution/evaluation code were committed before paid inference. The primary outcome was fixed as paired mean Brier difference, **v2 raw minus direct**. Secondary analyses and all exclusions were also fixed in advance. This is a one-time final historical evaluation, not another development cycle.

Protocol commit: **`3c420aff25a23f51afe823cc07b261fcddc4a7dc`**. Plan file SHA-256: `107802faa795986bec5c536eff29d58ddcb7491637b3d7c5c9d58d5c56838c81`. The original split remains 50 development / 150 evaluation; canonical split hash `300d87a9dbd8165934e1571453eb15a03f93616841c4a450514d42cc75a94043`. The exact 150 IDs, model/request/group/evidence hashes and settings are saved in the committed plan; all inference methods bind to the same frozen parent packet for each game.

No forecasting method changed. Direct uses its original full packet and fixed probability prompt. V1 retains direct numerical LR elicitation, group boundaries, strict bounds and aggregation. V2 retains the original deterministic X/Y strength blinding, four qualitative prompts, schemas and mapped ratios (neutral1, slight1.25, moderate1.75, strong2.5, very_strong4, with reciprocals). All use `claude-haiku-4-5-20251001`, temperature0 and their original generation settings. Both LEAP variants use the same observations: neutral 50% prior and alpha1 or0.5. No weights, prompts, priors, cutoffs or data were adjusted.

The small wrapper adds explicit held-out scope and a shared budget/access-denial stop. It reuses unchanged native request builders, caches, parsers and aggregation; v2's development runner remains unchanged. Original direct/v1 planners receive explicit evaluation authorization. Order is the existing evaluation hash order, **direct → v2 A–D → v1 A–D per game**, independent of outcomes and model outputs. The primary methods therefore get within-game priority if a later denial interrupts the experiment.

Inference reads only shared frozen snapshots. It has no evaluation-file join, search or tools. All three methods are sealed under one global completion manifest before the separate evaluator accesses outcomes or Kalshi probabilities. Opaque preflight byte hashing for integrity is not outcome parsing.

Actual retrospective inference interval: **2026-10-23T13:41:22.601007Z–2026-10-23T14:37:45.880982Z**; global seal **2026-10-23T14:37:46.366181Z**. These are API collection clocks, not historical publication or prediction clocks. Public observations bind to private completion SHA-256 `7d6c3023d145af4306713ae753cf780cc85183e0d8067b205b8f269acd662d65`.

Evaluation was initiated at **2026-10-23T14:38:16.417036Z**, after private verification and the global seal, before the separate evaluator joined outcomes/quotes. This records phase initiation, not an instrumented CSV-open timestamp; [reproduction.json](reproduction.json) preserves the event and validation metadata.

## Offline cost plan and execution audit

| Method | Planned new calls | Reservation bound | Original cache hits | Source-missing groups |
| --- | --- | --- | --- | --- |
| direct | 150 | $5.547066 | 0 | 0 |
| v2 | 382 | $6.179540 | 0 | 218 |
| v1 | 382 | $11.217048 | 0 | 218 |

The full offline plan required **914 calls / $22.943654 reservations**, within the authorization. All 179 tests passed before inference; a 150-game mock passed with zero provider calls. Mock fixtures use artificial labels and quotes and did not parse actual held-out outcomes. The Anthropic credential was loaded from the ignored trusted local `.env` without printing it. No provider health check or additional paid call was made outside this run.

| Method | Attempted | Successful game forecasts | Observation statuses | HTTP statuses | Input / output tokens | Known-token estimate | Unknown reserve | Sum HTTP latency, s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| direct | 150 | 148/150 | failed:2, success:148 | 0:2, 200:148 | 345032 / 2220 | $1.068396 | $0.065886 | 589.737920 |
| v1 | 382 | 144/150 | failed:6, skipped_missing:218, success:376 | 0:3, 200:379 | 572491 / 7195 | $1.825398 | $0.110853 | 1374.705416 |
| v2 | 382 | 144/150 | failed:3, insufficient:3, skipped_missing:218, success:376 | 0:3, 200:379 | 406678 / 8340 | $0.896756 | $0.048874 | 1297.377378 |

Total reported usage: **1,324,201 input / 17,755 output tokens**. Recorded estimate: **$4.016163**. Summed captured HTTP latency is **3261.820714 seconds**; it is not wall-clock runtime. Reservations: **914**; claimed attempts: **914**; unattempted new requests: **0**. Original-cache observations reused: **0**. Every reservation precedes its claim. The single authorization/output binding prevents relaunching in another directory; no failed or uncertain attempt was resent.

Costs use provider-reported **tokens** at frozen conservative rates: direct/v1 $3/$15 per million input/output, v2 $2/$10. Dollar estimates are not provider invoices, and unequal configured rates are not a normalized efficiency comparison. One direct call versus several group calls is an unequal inference budget. Raw/conservative variants share the same calls and do not double cost. Kalshi and constant require no model inference. Unknown usage retains a reserve rather than being recorded as zero.

The [execution audit](execution_audit.json) retains every planned observation, request identity, source/cached/new/unattempted origin, HTTP status, category, error, response hash, usage and latency. Source skips are separate from failed/insufficient/unknown or unattempted inference. The native `not_attempted_budget` serialization can represent a global denial/interruption stop too; the actual stopping reason is explicit and is never mislabeled as cost exhaustion.

| Failed/insufficient game | Method / group | HTTP | Category | Reason |
| --- | --- | --- | --- | --- |
| 401809936 | direct / None | 0 | transport_failure | No HTTP response; usage unknown |
| 401810527 | direct / None | 0 | transport_failure | No HTTP response; usage unknown |
| 401809234 | v2 / B_schedule_venue | 200 | model_abstention | Insufficient required evidence |
| 401809936 | v2 / B_schedule_venue | 0 | transport_failure | No HTTP response; usage unknown |
| 401810278 | v2 / B_schedule_venue | 0 | transport_failure | No HTTP response; usage unknown |
| 401810954 | v2 / C_player_availability | 0 | transport_failure | No HTTP response; usage unknown |
| 401810996 | v2 / B_schedule_venue | 200 | model_abstention | Insufficient required evidence |
| 401809933 | v2 / B_schedule_venue | 200 | model_abstention | Insufficient required evidence |
| 401809234 | v1 / B_schedule_venue | 200 | invalid_response | Model reports insufficient evidence; required group inference failed |
| 401809936 | v1 / B_schedule_venue | 200 | invalid_response | Model reports insufficient evidence; required group inference failed |
| 401810585 | v1 / A_team_strength | 0 | transport_failure | No HTTP response; usage unknown |
| 401809504 | v1 / B_schedule_venue | 200 | invalid_response | Model reports insufficient evidence; required group inference failed |
| 401810370 | v1 / A_team_strength | 0 | transport_failure | No HTTP response; usage unknown |
| 401810728 | v1 / A_team_strength | 0 | transport_failure | No HTTP response; usage unknown |

There were **eight transport failures with HTTP status0**, **three explicit v2 abstentions**, and **three v1 insufficient-evidence responses**. V1's frozen numeric parser records its insufficient responses as `failed`/`invalid_response`; they are not HTTP failures or usable neutral judgments. All six insufficiency responses concern schedule/venue. No HTTP403 or other access-denial response was observed, and no request was retried. All response hashes and detailed errors remain in the audit.

The eight private transport metadata records identify seven `URLError`s and one `TimeoutError`. They provide no valid HTTP response or usage and do not establish a provider-side denial or a confirmed network root cause. Their $0.225613 aggregate reserve remains in the recorded estimate.

## Paired evaluation and missingness

The primary pair is not conditioned on v1 or market availability. A additionally requires v2 conservative, Kalshi and constant on exactly the same eligible games; B additionally requires v1 raw/conservative. Every cohort requires finalized, verified home outcomes. All 150 rows remain in the exports, including failures, missing quotes and exclusions. No imputation, retry, trade substitution or outcome-dependent selection occurred.

Brier is primary; log loss uses natural logs and the original epsilon1e-15 clipping for log loss only. Calibration uses ten original equal-width buckets. Classification predicts home iff p>=0.5; extremes are p<=0.1 or p>=0.9. Stored probabilities remain unrounded. Kalshi retains the original valid two-sided YES midpoint with candle end at/before cutoff and lag<=1200 seconds. Candle end does not prove actual quote freshness.

### Primary: v2 raw versus direct (n=143)

| Method | n | Brier | Natural-log loss | Mean home p | Extremes | Accuracy |
| --- | --- | --- | --- | --- | --- | --- |
| Direct LLM | 143 | 0.209123 | 0.607207 | 0.525035 | 8/143 | 0.692308 |
| V2 raw | 143 | 0.220942 | 0.635951 | 0.529767 | 2/143 | 0.643357 |

### A: five-method complete intersection (n=143)

| Method | n | Brier | Natural-log loss | Mean home p | Extremes | Accuracy |
| --- | --- | --- | --- | --- | --- | --- |
| Direct LLM | 143 | 0.209123 | 0.607207 | 0.525035 | 8/143 | 0.692308 |
| V2 raw | 143 | 0.220942 | 0.635951 | 0.529767 | 2/143 | 0.643357 |
| V2 conservative | 143 | 0.222770 | 0.637299 | 0.516043 | 0/143 | 0.650350 |
| Kalshi | 143 | 0.184988 | 0.547454 | 0.566678 | 6/143 | 0.692308 |
| Constant 50% | 143 | 0.250000 | 0.693147 | 0.500000 | 0/143 | 0.573427 |

### B: seven-method complete intersection (n=139)

| Method | n | Brier | Natural-log loss | Mean home p | Extremes | Accuracy |
| --- | --- | --- | --- | --- | --- | --- |
| Direct LLM | 139 | 0.206424 | 0.601494 | 0.521583 | 8/139 | 0.697842 |
| V1 raw | 139 | 0.229428 | 0.660946 | 0.626500 | 9/139 | 0.640288 |
| V1 conservative | 139 | 0.227086 | 0.646618 | 0.571481 | 0/139 | 0.640288 |
| V2 raw | 139 | 0.218404 | 0.630439 | 0.528839 | 2/139 | 0.647482 |
| V2 conservative | 139 | 0.221310 | 0.634291 | 0.515516 | 0/139 | 0.654676 |
| Kalshi | 139 | 0.182469 | 0.541683 | 0.567482 | 6/139 | 0.697842 |
| Constant 50% | 139 | 0.250000 | 0.693147 | 0.500000 | 0/139 | 0.575540 |

Available probabilities out of 150: **Direct LLM 148, V1 raw 144, V1 conservative 144, V2 raw 144, V2 conservative 144, Kalshi 150, Constant 50% 150**. Missing finalized outcomes: **0**; missing/ineligible market quotes: **0**. These coverage counts are not substituted as denominators for paired scores. All comparison rows, exact IDs, exclusions and paired mean Brier/log-loss differences are in [summary.json](summary.json); all individual differences are in [per_game.json](per_game.json).

| Cohort | Eligible n | Excluded n | Missing-method reason counts |
| --- | --- | --- | --- |
| A_v2_market | 143 | 7 | {'leap_v2_raw': 6, 'leap_v2_conservative': 6, 'direct': 2} |
| B_seven_method | 139 | 11 | {'leap_v1_raw': 6, 'leap_v1_conservative': 6, 'leap_v2_raw': 6, 'leap_v2_conservative': 6, 'direct': 2} |
| primary | 143 | 7 | {'leap_v2_raw': 6, 'direct': 2} |

If A and B have different denominators, their method scores describe different game sets. B excludes any missing v1 forecasts explicitly; A/primary retain eligible games regardless of v1 failure. This is distinct from development, where v1 has 40 complete forecasts; no old development failure was retried here.

Here primary and A have exactly the same 143 IDs because all 150 market quotes pass the existing rule. B excludes four additional games solely for unavailable v1 forecasts: `401810585`, `401809504`, `401810370`, `401810728`. Two other missing v1 forecasts already fall among primary/A's seven exclusions. The n=139 B scores must not be compared to n=143 A scores as if only the forecasting method changed.

## Prespecified paired bootstrap

Seed **20261023**, **10,000 resamples**, game rows sampled jointly with replacement, shared row indices across comparisons within each named cohort. The 95% percentile interval uses linear (B−1)q interpolation. Differences below are first-method minus second-method Brier; negative favors the first. Primary P, market A and seven-method B have explicitly separate denominators. Intervals are descriptive because games/teams and evidence are dependent and historical outcome contamination remains possible. No significance claim or winner-based tuning follows.

| Cohort | Pair | n | Mean Brier difference | 95% interval |
| --- | --- | --- | --- | --- |
| A_v2_market | direct minus kalshi | 143 | 0.024135 | [0.002368, 0.046142] |
| A_v2_market | leap_v2_conservative minus direct | 143 | 0.013647 | [-0.004677, 0.031590] |
| A_v2_market | leap_v2_conservative minus kalshi | 143 | 0.037782 | [0.017250, 0.058576] |
| A_v2_market | leap_v2_raw minus direct | 143 | 0.011819 | [-0.007015, 0.030833] |
| A_v2_market | leap_v2_raw minus kalshi | 143 | 0.035953 | [0.012675, 0.060366] |
| B_seven_method | leap_v1_conservative minus direct | 139 | 0.020662 | [-0.006315, 0.046345] |
| B_seven_method | leap_v1_raw minus direct | 139 | 0.023004 | [-0.009286, 0.055573] |
| B_seven_method | leap_v2_conservative minus leap_v1_conservative | 139 | -0.005776 | [-0.024739, 0.012188] |
| B_seven_method | leap_v2_raw minus leap_v1_raw | 139 | -0.011024 | [-0.044601, 0.021219] |
| primary | leap_v2_raw minus direct | 143 | 0.011819 | [-0.007015, 0.030833] |

## Group LR distributions, directionality and source uncertainty

Ratios are LLM-elicited numeric estimates (v1) or fixed heuristic category mappings (v2), not independently calibrated likelihood ratios. Success-only distributions below exclude source-missing LR1 and failed/insufficient requests; neutral model judgments remain included. All source skips, categories, sufficiency labels, quantiles and raw log contributions are retained in [diagnostics.json](diagnostics.json).

| Version / group | Usable success n | Source skip / other | Home / away / neutral | LR min / median / max | Mean absolute log LR | Sufficiency |
| --- | --- | --- | --- | --- | --- | --- |
| v1 A: strength | 143 | 4 / 3 | 117 / 26 / 0 | 0.080000 / 1.350000 / 18.500000 | 0.635735 | {'adequate': 71, 'limited': 72, 'not_applicable_missing': 4, 'not_returned': 3} |
| v1 B: schedule/venue | 147 | 0 / 3 | 128 / 5 / 14 | 0.720000 / 1.150000 / 3.200000 | 0.209561 | {'adequate': 52, 'limited': 95, 'not_returned': 3} |
| v1 C: availability | 86 | 64 / 0 | 56 / 30 / 0 | 0.350000 / 1.150000 / 2.100000 | 0.338112 | {'adequate': 55, 'limited': 31, 'not_applicable_missing': 64} |
| v1 D: news | 0 | 150 / 0 | 0 / 0 / 0 | — / — / — | — | {'not_applicable_missing': 150} |
| v2 A: strength | 146 | 4 / 0 | 72 / 68 / 6 | 0.250000 / 1.000000 / 2.500000 | 0.520160 | {'adequate': 73, 'limited': 73, 'not_applicable_missing': 4} |
| v2 B: schedule/venue | 145 | 0 / 5 | 112 / 30 / 3 | 0.571429 / 1.250000 / 2.500000 | 0.428068 | {'adequate': 87, 'insufficient': 3, 'limited': 58, 'not_returned': 2} |
| v2 C: availability | 85 | 64 / 1 | 25 / 60 / 0 | 0.400000 / 0.571429 / 1.750000 | 0.536340 | {'adequate': 59, 'limited': 26, 'not_applicable_missing': 64, 'not_returned': 1} |
| v2 D: news | 0 | 150 / 0 | 0 / 0 / 0 | — / — / — | — | {'not_applicable_missing': 150} |

| V2 group | Neutral / slight / moderate / strong / very strong | Insufficient |
| --- | --- | --- |
| A: strength | 6 / 52 / 47 / 40 / 1 | 0 |
| B: schedule/venue | 3 / 57 / 80 / 5 / 0 | 3 |
| C: availability | 0 / 8 / 75 / 2 / 0 | 0 |
| D: news | 0 / 0 / 0 / 0 / 0 | 0 |

The predefined weaker-team rule requires **strictly lower season win fraction and average point differential**. On **47 common assessable successful strength observations**, v1 favors the weaker side **16** times and v2 **0**. Home-favoring counts on this same set are **36 v1 / 20 v2**. Statistical exclusions: `{'missing_or_zero_game_statistics': 94, 'ties_or_discordant_indicators': 8}`; any additional inference exclusions are listed by ID. No judgment was corrected. Improvements in this diagnostic cannot isolate blinding versus prompt format, category mapping or group boundaries.

| Home report state | Away report state | Games |
| --- | --- | --- |
| not_yet_submitted | not_yet_submitted | 12 |
| not_yet_submitted | reported | 16 |
| reported | not_yet_submitted | 15 |
| reported | reported | 55 |
| unavailable | unavailable | 52 |

There are **31 one-sided submitted report cases**. Their assessments and sufficiency labels remain in the diagnostic JSON. Missing or unsubmitted reports never imply health. Injury source publication/issue clocks retain original qualifiers: no independent historical public-capture verification or global latest-report verification is manufactured. Historical news remains uncollected and is not backfilled. Existing incomplete team histories and unverified schedule revisions limit point-in-time claims.

Source-usable availability exists for 86 games; v1 completes all 86 availability requests, v2 completes 85 and loses one to transport failure. The 64 source-missing injury groups and four strength groups without completed historical games are legitimate source skips. Terse LR/category responses cannot prove how Claude internally interpreted missing opponent availability; no unlisted player is labeled healthy by the pipeline.

The diagnostic helper retains the legacy key `A_v2_development` for its injury/shrinkage subtrees; `cohort_name_mapping` explicitly identifies it as **held-out A_v2_market**, not development observations.

## Evidence dependence, group removal and conservative aggregation

Leave-one-group-out values are recomputed offline from the same immutable LR observations without new model calls or fitting. They diagnose associations, not causal effects. Venue splits can reconstruct season totals and duplicate strength information; correlated groups can reinforce or cancel each other.

On **141 common successful A/B group observations**, same-direction nonzero reinforcement occurs **102 times for v1** and **87 for v2**. Zero contributions do not count as reinforcement. Exact group-eligible IDs and version-specific denominators are preserved separately.

### Group removal: A_v2_market (n=143)

| Method / omitted group | Mean log-odds contribution | Omission Brier | Omission log loss | Omission−full Brier / log loss |
| --- | --- | --- | --- | --- |
| V2 conservative / A: strength | 0.007176 | 0.237650 | 0.668113 | 0.014880 / 0.030813 |
| V2 conservative / B: schedule/venue | 0.123948 | 0.229483 | 0.651289 | 0.006713 / 0.013989 |
| V2 conservative / C: availability | -0.065109 | 0.224634 | 0.640935 | 0.001864 / 0.003635 |
| V2 conservative / D: news | 0.000000 | 0.222770 | 0.637299 | 0.000000 / 0.000000 |
| V2 raw / A: strength | 0.014351 | 0.235497 | 0.663490 | 0.014556 / 0.027539 |
| V2 raw / B: schedule/venue | 0.247895 | 0.225390 | 0.642063 | 0.004448 / 0.006112 |
| V2 raw / C: availability | -0.130217 | 0.222431 | 0.636111 | 0.001489 / 0.000160 |
| V2 raw / D: news | 0.000000 | 0.220942 | 0.635951 | 0.000000 / 0.000000 |

### Group removal: B_seven_method (n=139)

| Method / omitted group | Mean log-odds contribution | Omission Brier | Omission log loss | Omission−full Brier / log loss |
| --- | --- | --- | --- | --- |
| V1 conservative / A: strength | 0.179872 | 0.246927 | 0.686931 | 0.019841 / 0.040313 |
| V1 conservative / B: schedule/venue | 0.095469 | 0.224169 | 0.640357 | -0.002917 / -0.006260 |
| V1 conservative / C: availability | 0.028045 | 0.229912 | 0.652227 | 0.002826 / 0.005610 |
| V1 conservative / D: news | 0.000000 | 0.227086 | 0.646618 | 0.000000 / 0.000000 |
| V1 raw / A: strength | 0.359744 | 0.249862 | 0.693452 | 0.020434 / 0.032506 |
| V1 raw / B: schedule/venue | 0.190938 | 0.219826 | 0.636632 | -0.009603 / -0.024314 |
| V1 raw / C: availability | 0.056089 | 0.231404 | 0.663305 | 0.001975 / 0.002359 |
| V1 raw / D: news | 0.000000 | 0.229428 | 0.660946 | 0.000000 / 0.000000 |
| V2 conservative / A: strength | 0.002876 | 0.237353 | 0.667509 | 0.016043 / 0.033218 |
| V2 conservative / B: schedule/venue | 0.123094 | 0.227984 | 0.648220 | 0.006674 / 0.013930 |
| V2 conservative / C: availability | -0.062154 | 0.223409 | 0.638417 | 0.002099 / 0.004127 |
| V2 conservative / D: news | 0.000000 | 0.221310 | 0.634291 | 0.000000 / 0.000000 |
| V2 raw / A: strength | 0.005751 | 0.235108 | 0.662695 | 0.016704 / 0.032256 |
| V2 raw / B: schedule/venue | 0.246187 | 0.222617 | 0.636058 | 0.004213 / 0.005619 |
| V2 raw / C: availability | -0.124307 | 0.220248 | 0.631368 | 0.001844 / 0.000929 |
| V2 raw / D: news | 0.000000 | 0.218404 | 0.630439 | 0.000000 / 0.000000 |

No diagnosed group is removed from the official forecasts. Contribution distributions and injury-source/adequate/limited strata retain their explicit IDs and n. Raw and conservative variants share all observations; alpha0.5 mechanically moves nonneutral forecasts toward 50%, which alone does not establish better calibration.

**A_v2_market, n=143:** conservative-minus-raw Brier **0.001828**, log loss **0.001348**; forecasts closer to 50% **132**, unchanged within the fixed diagnostic tolerance **11**. Mean distance from 50%: **0.181947 raw → 0.099574 conservative**.

**B_seven_method, n=139:** conservative-minus-raw Brier **0.002906**, log loss **0.003851**; forecasts closer to 50% **128**, unchanged within the fixed diagnostic tolerance **11**. Mean distance from 50%: **0.182237 raw → 0.099847 conservative**.

Removing A/B/C each worsens both v2 proper scores on A's same 143 games; removing the absent news group changes nothing. On B's 139 games, removing v1 venue improves its raw Brier by 0.009603, whereas removing v2 venue worsens raw Brier by 0.004213. No group was removed from the official results. The reduced reinforcement and balanced strength direction in v2 did not establish independence or calibrated LRs.

## Calibration

All named cohorts and methods have complete ten-bucket tables with counts in [summary.json](summary.json). Below are A's buckets for direct and both v2 variants, as **count / mean p / observed frequency**. Empty or small buckets are retained; no bins were optimized. Stored floating-point probabilities and the original bucket/tie rules are unchanged, including any reciprocal-LR near-50% boundary artifacts.

| Bucket | Direct n / p / frequency | V2 raw n / p / frequency | V2 cons. n / p / frequency |
| --- | --- | --- | --- |
| [0.0, 0.1) | 1 / 0.040000 / 0.000000 | 0 / — / — | 0 / — / — |
| [0.1, 0.2) | 7 / 0.162857 / 0.285714 | 14 / 0.153058 / 0.285714 | 0 / — / — |
| [0.2, 0.3) | 18 / 0.253333 / 0.388889 | 13 / 0.276446 / 0.384615 | 6 / 0.266935 / 0.166667 |
| [0.3, 0.4) | 17 / 0.358824 / 0.235294 | 15 / 0.350080 / 0.533333 | 21 / 0.357896 / 0.380952 |
| [0.4, 0.5) | 22 / 0.429545 / 0.500000 | 22 / 0.460517 / 0.454545 | 30 / 0.447006 / 0.466667 |
| [0.5, 0.6) | 16 / 0.552500 / 0.687500 | 20 / 0.550000 / 0.500000 | 45 / 0.541031 / 0.555556 |
| [0.6, 0.7) | 22 / 0.633636 / 0.681818 | 18 / 0.645705 / 0.611111 | 37 / 0.647459 / 0.837838 |
| [0.7, 0.8) | 31 / 0.737419 / 0.774194 | 26 / 0.745752 / 0.846154 | 4 / 0.741058 / 0.750000 |
| [0.8, 0.9) | 2 / 0.845000 / 1.000000 | 13 / 0.830217 / 0.846154 | 0 / — / — |
| [0.9, 1.0] | 7 / 0.922857 / 0.857143 | 2 / 0.916230 / 0.500000 | 0 / — / — |

Conservative v2 concentrates 112/143 forecasts in the 0.4–0.7 range; in its 0.6–0.7 bucket, mean p=0.647459 versus observed frequency=0.837838 (n=37). Shrinkage therefore does not uniformly correct the visible calibration errors. Raw v2's top bucket has only two cases and cannot support a reliable extreme-probability claim. Mean home probabilities are 0.525035 direct, 0.529767 raw v2 and 0.566678 Kalshi, versus observed home wins 82/143=0.573427; agreement of pooled means alone is not full calibration.

## Development versus held-out results

These are **different game sets**, with separately labeled denominators and possible source/provider coverage differences. Held-out minus development is an **unpaired descriptive change**, not an estimate from matching the same games. No score from either cohort was used to revise a method. The seven-method development sample retains v1's ten prior incomplete games; the held-out sample has its own independently reported exclusions.

The development A sample favored v2 raw over direct by 0.010975 Brier (n=50), whereas the locked held-out primary/A pair favors direct by 0.011819 (n=143). This descriptive reversal is evidence against treating the development result as established predictive improvement; the distinct samples, failures, source coverage and possible model memory prevent a causal overfitting diagnosis.

### A_v2_market: development n=50 / held-out n=143

| Method | Development Brier / log loss | Held-out Brier / log loss | Held-out−development Brier / log loss |
| --- | --- | --- | --- |
| Constant 50% | 0.250000 / 0.693147 | 0.250000 / 0.693147 | 0.000000 / 0.000000 |
| Direct LLM | 0.220756 / 0.639271 | 0.209123 / 0.607207 | -0.011633 / -0.032064 |
| Kalshi | 0.192294 / 0.561299 | 0.184988 / 0.547454 | -0.007306 / -0.013845 |
| V2 conservative | 0.215781 / 0.622442 | 0.222770 / 0.637299 | 0.006989 / 0.014858 |
| V2 raw | 0.209781 / 0.608310 | 0.220942 / 0.635951 | 0.011160 / 0.027641 |

### B_seven_method: development n=40 / held-out n=139

| Method | Development Brier / log loss | Held-out Brier / log loss | Held-out−development Brier / log loss |
| --- | --- | --- | --- |
| Constant 50% | 0.250000 / 0.693147 | 0.250000 / 0.693147 | 0.000000 / 0.000000 |
| Direct LLM | 0.218020 / 0.635184 | 0.206424 / 0.601494 | -0.011596 / -0.033691 |
| Kalshi | 0.197027 / 0.571403 | 0.182469 / 0.541683 | -0.014558 / -0.029720 |
| V1 conservative | 0.243513 / 0.680649 | 0.227086 / 0.646618 | -0.016427 / -0.034032 |
| V1 raw | 0.257588 / 0.725746 | 0.229428 / 0.660946 | -0.028160 / -0.064801 |
| V2 conservative | 0.216202 / 0.623112 | 0.221310 / 0.634291 | 0.005108 / 0.011179 |
| V2 raw | 0.213317 / 0.615922 | 0.218404 / 0.630439 | 0.005088 / 0.014517 |

## Full outputs and reproduction

[results.csv](results.csv) retains all **150 games**, all seven probabilities, outcomes, statuses, cohort membership, per-method Brier/log loss and group LR/category/missingness. [per_game.json](per_game.json) additionally retains individual group assessments/contributions, offline omission probabilities and every available pairwise score difference. [bootstrap.json](bootstrap.json) binds each interval to its exact IDs, seed and resampling count. [labels.json](labels.json) is evaluation-only and binds selected source rows to the original evaluation-file hash; it is never model context.

[observations.json](observations.json) contains sanitized structured records, model/settings, parent/prompt/request hashes, clocks, claim markers and reservations. It excludes raw HTTP bodies, auth headers and local cache paths. [manifest.json](manifest.json) hashes the complete replayable artifact set. Public replay checks plan/evidence/labels, recomputes aggregation, scoring, calibration, uncertainty, group diagnostics and development comparisons. Private verification additionally checks raw captured bytes and response parsers. Public hashes prove consistency, not independent authenticity of model inference.

```sh
# Public: no network, credentials or private captures.
.venv/bin/python -m unittest discover -s tests -q
.venv/bin/python scripts/analyze_heldout.py --authorize-evaluation --replay reports/heldout_150

# Operator's existing sealed captures; no new paid requests.
.venv/bin/python scripts/heldout_forecast.py --authorize-evaluation --verify captures/heldout_150/run

# Original execution and opt-in commands are preserved in the committed protocol.
# Do not delete claim markers, change cache paths or relaunch paid inference.
```

## Validation and preservation

All **179 tests passed before inference**, **179 after inference**, and **179 in a clean repository snapshot without `.env` or private captures**, with no skipped tests. Private-cache verification, local sanitized replay and clean-snapshot public replay passed. Native CSV coverage and all calibration bucket totals reconcile with the exported exact intersections (primary/A143, B139); all 150 rows remain. Every forecasting/execution/evaluation source file, test, frozen protocol and request plan remains byte-identical to the pre-inference commit. After inference, the only Git publication changes are README and new sanitized reports.

The [preservation audit](preservation.json) confirms **zero changes among 12,372 protected original files**, including **7,608 historical data files**, the split, all original prompts/settings/projections and every previous direct/v1/v2/synthetic record or cache file. New held-out keys were appended to the original shared caches. The private original-file manifest SHA-256 is `038dd69b0c552bdeae606fa6a62c19bf0e99dd0fb95ed1987a4d7a736cbf7528`. A configured-secret-value scan found no credentials or private raw HTTP files among publication candidates. Reproduction metadata records the phase clock, checks and artifact hashes.

## Limitations and locked conclusion

This held-out subset was unused for repository development inference/scoring until this authorization, but all games are historical. Claude may remember game identities/results; frozen evidence and prompts cannot rule out memorization or pretraining contamination. Historical sources and scheduled tipoff revisions are not universally independently as-of verified. Missing statistical histories, unsubmitted injury reports and absent historical news constrain evidence quality. Uncalibrated LR estimates, correlated groups and unequal per-method call/token budgets prevent interpreting this as a clean causal test of qualitative elicitation alone.

Paired bootstrap intervals remain descriptive because NBA games share teams, schedules, sources and possibly model errors. Failure-driven complete intersections can be selective. Small calibration buckets cannot establish reliable calibration. The prospective dataset remains the eventual primary out-of-sample evaluation. This report records the locked historical result without tuning any method or initiating a new development cycle.
