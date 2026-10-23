# LEAP-NBA v2: full 50-game development experiment

**All 50 v2 forecasts completed.** The existing five-game pilot and 13 qualitative observations were reused exactly; **114 new Anthropic requests all succeeded**, with no denial, retry, abstention or malformed response. Additional estimated token cost was **$0.266344**; conservative pre-call reservations totaled **$1.833528**, below the authorized 180 calls/$5. No new direct/v1 calls, searches or evidence collection occurred.

On the identical **50-game** direct/v2/market intersection, raw v2 has lower observed Brier/log loss than direct, while Kalshi has lower losses than both. On the identical **40-game** seven-method intersection, v2 has lower losses than v1. These are descriptive development-informed historical results, not evidence of independent predictive skill or a causal benefit from qualitative elicitation.

## Frozen assets, scope and preflight

The [forecast protocol](../../experiments/leap_nba_v2_phase2/protocol.md), prompts, mapping, settings, projections and original runners were verified against pre-inference commit **`8520406`**, with frozen registry SHA-256 `76bcb80ec46b452d33610ac10eb9dee1606c18b3723cfa9c25780b5c9f1ff114`. The [analysis plan](../../experiments/leap_nba_v2_development_50_analysis_plan.json) and tested execution/diagnostic code were committed at **`8c08d52e2e1aed61a54ce023cfe4a822b83aee95` before any new inference**. Analysis-plan file SHA-256: `253470447bd94787b5fafd2a4dceeee82bba0ca0f6a0b0e21b02ef981407942a`.

Preflight verified all five paid pilot forecasts/cache records, 50 direct records, 40 complete v1 records and all matching cache identities. All 168 tests passed before inference; a full mock and replay passed without network calls. The unchanged split remains 50 development / 150 reserved, canonical SHA-256 `300d87a9dbd8165934e1571453eb15a03f93616841c4a450514d42cc75a94043`. No reserved packet was loaded by the experiment, forecast, scored or diagnosed. Global integrity checks hash original bytes without using held-out evidence in analysis.

Requested and returned model: `claude-haiku-4-5-20251001`; temperature 0, max 128 output tokens, no tools. A uses the unchanged seeded X/Y projection; B/C/D use their original isolated groups. Ratios remain heuristic qualitative mappings (1, 1.25, 1.75, 2.5, 4, with reciprocals). Neutral prior, alpha 1 and 0.5, missingness and failure semantics remain unchanged. Both variants reuse the same observations; no fitted hyperparameters or post-result corrections.

Actual new request interval: **2026-10-23T04:52:37.998554Z–04:56:20.816510Z**; sealed at **04:56:20.896057Z**. These are retrospective inference clocks, not historical source clocks. Source verification and schedule limitations remain in the original evidence.

## Exact paired comparisons

All outcomes and preferred quotes are present for these 50 development games. Kalshi remains the valid two-sided YES midpoint with candle end at/before cutoff and lag <=1200 seconds. Candle end does not establish actual quote freshness. No trades or missing prices were substituted. Log loss uses natural logs and the original epsilon 1e-15 clipping; Brier uses unmodified probabilities. Extremes mean p<=0.10 or p>=0.90. Classification predicts home iff p>=0.50.


### A: direct/v2/market, n=50

| Method | n | Brier | Log loss | Mean home p | Extremes | Accuracy |
| --- | --- | --- | --- | --- | --- | --- |
| Constant 50% | 50 | 0.250000 | 0.693147 | 0.500000 | 0/50 | 0.420000 |
| Direct LLM | 50 | 0.220756 | 0.639271 | 0.508500 | 3/50 | 0.660000 |
| Kalshi | 50 | 0.192294 | 0.561299 | 0.525200 | 2/50 | 0.660000 |
| V2 conservative | 50 | 0.215781 | 0.622442 | 0.499122 | 0/50 | 0.620000 |
| V2 raw | 50 | 0.209781 | 0.608310 | 0.499226 | 1/50 | 0.640000 |

### B: all seven methods, n=40

| Method | n | Brier | Log loss | Mean home p | Extremes | Accuracy |
| --- | --- | --- | --- | --- | --- | --- |
| Constant 50% | 40 | 0.250000 | 0.693147 | 0.500000 | 0/40 | 0.375000 |
| Direct LLM | 40 | 0.218020 | 0.635184 | 0.510000 | 3/40 | 0.675000 |
| Kalshi | 40 | 0.197027 | 0.571403 | 0.518250 | 2/40 | 0.650000 |
| V1 conservative | 40 | 0.243513 | 0.680649 | 0.547272 | 0/40 | 0.575000 |
| V1 raw | 40 | 0.257588 | 0.725746 | 0.583926 | 3/40 | 0.575000 |
| V2 conservative | 40 | 0.216202 | 0.623112 | 0.496222 | 0/40 | 0.600000 |
| V2 raw | 40 | 0.213317 | 0.615922 | 0.494837 | 1/40 | 0.625000 |

A excludes no games. B excludes only the ten unchanged incomplete v1 forecasts below; no v1 request was retried. Aggregate A and B scores have different denominators and must not be compared as matched estimates. Observed home-win frequency is 21/50=0.42 in A and 15/40=0.375 in B. Coverage out of the original 50 is direct 50, v1 raw/conservative 40, v2 raw/conservative 50, Kalshi 50, constant 50. V1's selected observations retain 25 failed group requests, separate from the 73 legitimate source skips. Per-group error objects remain in [per_game.json](per_game.json), with original attempt lineage in the unchanged [v1 report](../development_50/merged/report.md).


| Game excluded from B | Failed original v1 groups |
| --- | --- |
| 401810309 | A, B, C |
| 401810143 | A, B |
| 401809954 | A, B |
| 401810609 | A, B, C |
| 401810685 | A, B, C |
| 401810958 | A, B |
| 401810517 | A, B, C |
| 401811016 | A, B, C |
| 401810569 | A, B, C |
| 401810762 | A |

## Descriptive paired uncertainty

The precommitted procedure uses 10,000 game-row resamples with replacement, seed **20261023**, jointly preserving method pairs and sharing indices within each cohort. The 95% percentile endpoints use linear interpolation at (B−1)q. The first four comparisons use A's identical 50 games; the v1 comparisons use B's identical 40 games. Negative differences favor the first method. No significance claim or winner selection follows from these development intervals.


| Mean Brier difference | n | Difference | 95% interval |
| --- | --- | --- | --- |
| leap_v2_conservative minus direct | 50 | -0.004975 | [-0.038530, +0.024993] |
| leap_v2_conservative minus kalshi | 50 | 0.023487 | [-0.004169, +0.050720] |
| leap_v2_raw minus direct | 50 | -0.010975 | [-0.040927, +0.017961] |
| leap_v2_raw minus kalshi | 50 | 0.017487 | [-0.011090, +0.047356] |
| leap_v2_conservative minus leap_v1_conservative | 40 | -0.027311 | [-0.053059, -0.002390] |
| leap_v2_raw minus leap_v1_raw | 40 | -0.044271 | [-0.088775, -0.000704] |

All paired mean Brier **and log-loss** differences are in [summary.json](summary.json); all per-game differences and exact IDs are in [per_game.json](per_game.json). [bootstrap.json](bootstrap.json) retains the seed, resampling count, cohort IDs and full-precision intervals. Games can be dependent; historical outcome memory and prior development inspection remain plausible. The negative v2–v1 intervals do not establish out-of-sample superiority.

## Strength directionality and home favoritism

The original criterion calls a side weaker only when **both** its season win fraction and average point differential are strictly lower. Seventeen games are statistically assessable; 30 have missing/zero-game statistics and three have tied/discordant indicators. Three of the 17 lack a successful v1 strength response, leaving **14 common assessable games**. V1 favors the weaker side in **5/14**, v2 in **0/14**; v1 favors home in **12/14**, v2 in **7/14**. No output was flipped or excluded for this diagnostic.

On all common successful strength observations (n=40), v1 favors home/away/neutral **31/9/0**, versus v2 **18/21/1**. Common venue observations (n=41) are **39/1/1** versus **29/11/1**; common availability observations (n=21) are **12/9/0** versus **4/16/1**. Each comparison uses its own named common group intersection, rather than silently equating unequal source coverage. Direction consistency improved in these assessable cases, but blinding, prompts, group boundaries and discrete mapping changed together; this is not an isolated causal test of elicitation format.

## Qualitative observations, source absence and mapped magnitude

The table counts usable assessments only. Skips are source absence, not model neutral judgments. All groups have zero failed, insufficient or unattempted observations; no unsupported neutralization occurred.


| Group | Success / skip | Home / away / neutral | Neutral / slight / moderate / strong / very strong | Adequate / limited |
| --- | --- | --- | --- | --- |
| A: strength | 50 / 0 | 22 / 27 / 1 | 1 / 17 / 15 / 17 / 0 | 23 / 27 |
| B: schedule/venue | 50 / 0 | 38 / 11 / 1 | 1 / 16 / 30 / 3 / 0 | 32 / 18 |
| C: availability | 27 / 23 | 4 / 22 / 1 | 1 / 2 / 23 / 1 / 0 | 22 / 5 |
| D: news | 0 / 50 | 0 / 0 / 0 | 0 / 0 / 0 / 0 / 0 | 0 / 0 |

| Group | Usable n | LR min / median / max | Mean log LR | Mean |log LR| | |log LR| p25 / p75 / max |
| --- | --- | --- | --- | --- | --- |
| A: strength | 50 | 0.400000 / 0.800000 / 2.500000 | -0.056366 | 0.555292 | 0.223144 / 0.916291 / 0.916291 |
| B: schedule/venue | 50 | 0.400000 / 1.750000 / 2.500000 | 0.255490 | 0.462153 | 0.223144 / 0.559616 / 0.916291 |
| C: availability | 27 | 0.400000 / 0.571429 / 1.750000 | -0.386287 | 0.527176 | 0.559616 / 0.559616 / 0.916291 |
| D: news | 0 | — / — / — | — | — | — / — / — |

There are 127 usable estimates: 77 adequate, 50 limited, three explicitly neutral, and none insufficient or very strong. The 73 skipped groups are **23 availability groups** (18 both unavailable, five both not submitted) and **all 50 news groups** (`not_collected_historical`). Skipped groups contribute LR=1 solely under frozen absence rules; absence does not mean healthy players or no developments. Sufficiency is an elicited label, not a validated completeness measure.

For comparison, successful v1 strength LRs span **0.08–8.5** (n=40), while v2 spans **0.4–2.5** (n=50). V1 mean absolute log-LR is 0.651793 for A, 0.205436 for B and 0.345025 for C (n=40/41/21); v2 is 0.555292/0.462153/0.527176 (n=50/50/27). Those unmatched distributions are labeled descriptively; v2 is less extreme for strength but **not uniformly weaker** for venue or injury contributions. Full counts, population deviations and quantiles are in [diagnostics.json](diagnostics.json).

## Injury coverage, uncertainty and removal

Submission states across 50 games: **19 both reported**, **seven home reported/away not submitted**, **one home not submitted/away reported**, **18 both unavailable**, and **five both not submitted**. The 27 source-usable groups yield **22 adequate / five limited** judgments, favoring **away in 22**, home in four and neither in one. Their mean log-LR is −0.386287 conditional on availability, or −0.208595 across all 50 including source-zero contributions.

The eight one-sided reports favor away six times, home once and neither once; **three are labeled adequate despite an unsubmitted opponent report**. All 19 both-reported cases are adequate. This is a concern about sufficiency and directional availability bias; terse responses cannot prove how Claude treated an unlisted player. Input uncertainty stays explicit and missing reports are never filled with current sources.


| One-sided report game | Home / away state | Assessment | Sufficiency | Home LR |
| --- | --- | --- | --- | --- |
| 401810544 | reported / not_yet_submitted | away / moderate | adequate | 0.571429 |
| 401810737 | reported / not_yet_submitted | away / strong | adequate | 0.400000 |
| 401810840 | reported / not_yet_submitted | away / moderate | limited | 0.571429 |
| 401810766 | not_yet_submitted / reported | home / slight | limited | 1.250000 |
| 401810706 | reported / not_yet_submitted | neither / neutral | limited | 1.000000 |
| 401810749 | reported / not_yet_submitted | away / moderate | limited | 0.571429 |
| 401810517 | reported / not_yet_submitted | away / slight | limited | 0.800000 |
| 401810855 | reported / not_yet_submitted | away / moderate | adequate | 0.571429 |

These official report records retain their original publication-verification qualifiers. In particular, independent historical public capture and globally latest-report verification are false; issue timestamps are not independent proof of historical publication. Existing incomplete team histories and unverified historical schedule revisions also limit strict point-in-time claims. No source was upgraded to verified by this experiment.

| A injury stratum | n | V2 raw Brier / log loss | V2 cons. Brier / log loss |
| --- | --- | --- | --- |
| adequate | 22 | 0.177606 / 0.545325 | 0.197764 / 0.586002 |
| limited | 5 | 0.205387 / 0.580770 | 0.204205 / 0.595930 |
| source_missing | 23 | 0.241513 / 0.674543 | 0.235531 / 0.663060 |
| source_usable | 27 | 0.182751 / 0.551889 | 0.198957 / 0.587841 |

These are different game strata, not randomized estimates of injury evidence value. For paired removal on **the same 50 games**, omitting C worsens raw Brier/log loss by **+0.010303/+0.020649**, and conservative by **+0.006275/+0.012850**. This differs from the small pilot and does not justify changing the frozen group. B-specific strata and all-method stratum scores retain their explicit sample sizes in [diagnostics.json](diagnostics.json).

## Dependence and offline contributions

On the **40 common games** with successful A/B in both versions, strength and venue reinforce each other with nonzero same-sign contributions in **29/40 v1** and **28/40 v2**. Across all v2 games the count is **32/50**. Zero contributions are excluded from reinforcement counts. Venue split records can reconstruct season totals and remain correlated with strength; group LRs are neither independent nor statistically calibrated.

The following mean raw log-LR contributions use all 50 A games, retaining source-zero contributions. Conservative contributions are exactly half. Standard deviations and quantiles, including zero source mass, are preserved in the cohort removal records.


| Group | Mean raw contribution | Population SD | p25 / median / p75 | Raw omission Brier / log loss | Cons. omission Brier / log loss |
| --- | --- | --- | --- | --- | --- |
| A: strength | -0.056366 | 0.627028 | -0.559616 / -0.223144 / 0.559616 | 0.223502 / 0.637351 | 0.231500 / 0.655496 |
| B: schedule/venue | 0.255490 | 0.434667 | 0.223144 / 0.559616 / 0.559616 | 0.214107 / 0.621769 | 0.223835 / 0.640308 |
| C: availability | -0.208595 | 0.345441 | -0.559616 / 0.000000 / 0.000000 | 0.220084 / 0.628959 | 0.222056 / 0.635292 |
| D: news | 0.000000 | 0.000000 | 0.000000 / 0.000000 / 0.000000 | 0.209781 / 0.608310 | 0.215781 / 0.622442 |

All omission probabilities were recomputed offline from the same cached assessments, without inference or refitting. On A, removing A/B/C each worsens both proper scores; removing the entirely missing D changes nothing. On B's **same 40 games**, removing venue slightly improves raw v2 Brier/log loss (0.211368/0.613868 versus 0.213317/0.615922), while on A's 50 it worsens them. This cohort sensitivity and small sample prevent causal conclusions. All v1 and v2 removal metrics, IDs, deltas and per-game contributions remain in [summary.json](summary.json) and [per_game.json](per_game.json).

## Conservative aggregation and calibration

Alpha 0.5 moves **48/50** forecasts closer to 50%; two are numerically neutral within the precommitted diagnostic tolerance. Mean absolute distance from 0.5 falls **0.190577→0.104192**; mean confidence falls **0.690577→0.604192**. Raw-to-conservative Brier/log loss **worsens by +0.006000/+0.014132** on A, and **+0.002885/+0.007190** on B. No alpha was optimized. Fewer extremes are a mechanical shrinkage effect, not proof of better calibration.

The ten fixed calibration buckets below show count / mean probability / observed home-win frequency for v2 on A (n=50). Empty buckets stay empty. All methods and both intersections have complete ten-bin tables in [summary.json](summary.json); bucket counts sum to each method's explicit cohort size. Small or singleton buckets cannot establish calibration.


| Bucket | V2 raw n / p / frequency | V2 conservative n / p / frequency |
| --- | --- | --- |
| [0.0, 0.1) | 1 / 0.083770 / 0.000000 | 0 / — / — |
| [0.1, 0.2) | 3 / 0.162539 / 0.000000 | 0 / — / — |
| [0.2, 0.3) | 9 / 0.247531 / 0.111111 | 2 / 0.248817 / 0.000000 |
| [0.3, 0.4) | 5 / 0.367832 / 0.200000 | 11 / 0.356769 / 0.090909 |
| [0.4, 0.5) | 7 / 0.439701 / 0.714286 | 11 / 0.450104 / 0.545455 |
| [0.5, 0.6) | 5 / 0.555556 / 0.200000 | 14 / 0.548638 / 0.428571 |
| [0.6, 0.7) | 8 / 0.632625 / 0.625000 | 11 / 0.651582 / 0.727273 |
| [0.7, 0.8) | 6 / 0.733978 / 0.666667 | 1 / 0.734536 / 0.000000 |
| [0.8, 0.9) | 6 / 0.833737 / 0.666667 | 0 / — / — |
| [0.9, 1.0] | 0 / — / — | 0 / — / — |

**Numerical boundary concern:** game `401810776` has reciprocal strength/venue LRs whose floating-point log sum is −1.1102230246251565e−16. Stored raw probability is **0.49999999999999994**, conservative **0.5**. The frozen p>=0.5 classification tie rule therefore predicts opposite sides, accounting for the entire one-game accuracy gap (64% vs 62% on A; 62.5% vs 60% on B) and a bin-boundary shift. Proper-score differences from this boundary are negligible. Stored probabilities, aggregation and thresholds were **not rounded or changed**; a regression test documents the artifact. Classification differences here should not be interpreted as forecast improvements.

## Execution, resources and failure audit

The offline plan required **114** new usable-group requests plus 13 pilot hits; the plan's full additional reservation was **$1.833528**. All 114 were reserved before claims, attempted once, returned HTTP200, passed the frozen schema and mapped to usable estimates. **Zero failed, denied, uncertain, insufficient, truncated or unattempted requests** remain. Stop reason: `completed` / `All planned group slots processed`. No successful cache entry or claim marker was replaced. Original five forecasts match their published pilot records exactly.


| V2 source | Requests | Input / output tokens | Configured token estimate | Unknown-usage reserve | Sum HTTP latency, s |
| --- | --- | --- | --- | --- | --- |
| additional | 114 | 120632 / 2508 | $0.266344 | $0.000000 | 219.124588 |
| reused | 13 | 14286 / 286 | $0.031432 | $0.000000 | 39.457498 |

Total selected v2 usage, including the prior pilot, is **134,918 input / 2,794 output tokens**, estimated **$0.297776**, with **258.582086 seconds summed HTTP latency**. The new batch's sum is 219.124588 seconds; latency sums are not wall-clock runtimes. Cost is computed from provider-reported tokens at frozen conservative **$2/$10 per million**, not an invoice or provider-reported dollar charge. Unknown-usage reserve is zero; the larger pre-call reservation is an authorization bound, not actual spend.

Reused direct records retain **114,863 input / 750 output tokens**, **$0.355839** selected estimate, **114.695358 seconds** summed latency (50 successes). Selected v1 records retain **153,661 / 1,938 tokens**, **$0.490053 reported-token estimate plus $0.732543 unknown-usage reserves = $1.222596**, **332.686180 seconds** summed latency (102 successes, 25 failed requests and 73 source skips). Their estimates use the original $3/$15 rates, so raw dollar totals are not normalized model-efficiency comparisons. Both alpha variants share cost; they do not double it. Kalshi and constant require no new inference. No additional spend was incurred by evaluating direct/v1; superseded original v1 failures and retry costs remain separately preserved in its [attempt audit](../development_50_retry_audit.json), not erased by selected-record totals.

The sanitized [execution audit](execution_audit.json) includes every game's group status, original/new/source-missing origin, request identity, HTTP status, response hash, categorized error, reported usage and estimated cost. [observations.json](observations.json) preserves reservations, claim clocks, signed records, provider settings and private completion hash. Raw HTTP bodies, headers, credentials and local absolute cache paths are excluded from public observations.

## Full development forecast table

Every row remains in the export, including ten missing v1 predictions. Probabilities below are rounded for display only; full precision, outcomes, losses, LR/categories and exact exclusions are in [results.csv](results.csv). Constant is 0.5 for every row. All paired per-game Brier/log-loss differences remain in [per_game.json](per_game.json).


| Game | Home vs away | Home won | Direct | V1 raw / cons. | V2 raw / cons. | Kalshi | In B |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 401810544 | Boston Celtics / Sacramento Kings | 1 | 0.720000 | 0.503096 / 0.501548 | 0.471698 / 0.485838 | 0.810000 | yes |
| 401810485 | Dallas Mavericks / Golden State Warriors | 1 | 0.380000 | 0.632033 / 0.567209 | 0.363636 / 0.430501 | 0.375000 | yes |
| 401810279 | Orlando Magic / Charlotte Hornets | 0 | 0.680000 | 0.710098 / 0.610147 | 0.636364 / 0.569499 | 0.710000 | yes |
| 401836746 | Houston Rockets / LA Clippers | 1 | 0.780000 | 0.765478 / 0.643704 | 0.813953 / 0.676548 | 0.775000 | yes |
| 401809808 | Golden State Warriors / Houston Rockets | 0 | 0.350000 | 0.653620 / 0.578713 | 0.242424 / 0.361302 | 0.525000 | yes |
| 401810737 | Golden State Warriors / LA Clippers | 0 | 0.620000 | 0.394691 / 0.446748 | 0.384615 / 0.441518 | 0.490000 | yes |
| 401810840 | Brooklyn Nets / Portland Trail Blazers | 0 | 0.320000 | 0.258028 / 0.370955 | 0.222222 / 0.348331 | 0.235000 | yes |
| 401810476 | Boston Celtics / Indiana Pacers | 1 | 0.720000 | 0.862547 / 0.714696 | 0.714286 / 0.612574 | 0.820000 | yes |
| 401810061 | LA Clippers / Atlanta Hawks | 0 | 0.420000 | 0.608227 / 0.554763 | 0.555556 / 0.527864 | 0.615000 | yes |
| 401810766 | Denver Nuggets / New York Knicks | 0 | 0.520000 | 0.696758 / 0.602515 | 0.636364 / 0.569499 | 0.500000 | yes |
| 401810475 | Charlotte Hornets / Cleveland Cavaliers | 0 | 0.420000 | 0.555247 / 0.527708 | 0.207120 / 0.338231 | 0.415000 | yes |
| 401809237 | Golden State Warriors / Denver Nuggets | 1 | 0.720000 | 0.674267 / 0.589954 | 0.609756 / 0.555556 | 0.555000 | yes |
| 401810504 | Utah Jazz / Miami Heat | 0 | 0.380000 | 0.502705 / 0.501353 | 0.363636 / 0.430501 | 0.335000 | yes |
| 401810498 | Philadelphia 76ers / New York Knicks | 0 | 0.520000 | 0.593165 / 0.546994 | 0.583333 / 0.541960 | 0.500000 | yes |
| 401810064 | Philadelphia 76ers / Boston Celtics | 1 | 0.550000 | 0.553970 / 0.527064 | 0.555556 / 0.527864 | 0.565000 | yes |
| 401810189 | Washington Wizards / Boston Celtics | 0 | 0.180000 | 0.310059 / 0.401331 | 0.246154 / 0.363636 | 0.195000 | yes |
| 401810928 | Golden State Warriors / Washington Wizards | 1 | 0.720000 | 0.483183 / 0.491589 | 0.636364 / 0.569499 | 0.865000 | yes |
| 401810437 | San Antonio Spurs / Milwaukee Bucks | 1 | 0.720000 | 0.766595 / 0.644418 | 0.842752 / 0.698344 | 0.725000 | yes |
| 401810178 | Golden State Warriors / Oklahoma City Thunder | 0 | 0.250000 | 0.274100 / 0.380610 | 0.186047 / 0.323452 | 0.170000 | yes |
| 401810094 | Phoenix Suns / Atlanta Hawks | 0 | 0.550000 | 0.539807 / 0.519935 | 0.686275 / 0.596615 | 0.510000 | yes |
| 401810161 | Minnesota Timberwolves / San Antonio Spurs | 1 | 0.420000 | 0.534884 / 0.517463 | 0.416667 / 0.458040 | 0.570000 | yes |
| 401810573 | Washington Wizards / New York Knicks | 0 | 0.250000 | 0.373178 / 0.435535 | 0.115523 / 0.265464 | 0.160000 | yes |
| 401810706 | Brooklyn Nets / San Antonio Spurs | 0 | 0.150000 | 0.157043 / 0.301493 | 0.186047 / 0.323452 | 0.150000 | yes |
| 401811000 | Memphis Grizzlies / Cleveland Cavaliers | 0 | 0.280000 | 0.478624 / 0.489307 | 0.242424 / 0.361302 | 0.080000 | yes |
| 401811008 | New Orleans Pelicans / Utah Jazz | 1 | 0.580000 | 0.636479 / 0.569560 | 0.792880 / 0.661769 | 0.810000 | yes |
| 401810509 | San Antonio Spurs / New Orleans Pelicans | 0 | 0.780000 | 0.945786 / 0.806830 | 0.884477 / 0.734536 | 0.830000 | yes |
| 401810032 | Dallas Mavericks / New Orleans Pelicans | 0 | 0.920000 | 0.786325 / 0.657339 | 0.753846 / 0.636364 | 0.735000 | yes |
| 401810749 | Boston Celtics / Charlotte Hornets | 0 | 0.720000 | 0.634877 / 0.568712 | 0.714286 / 0.612574 | 0.690000 | yes |
| 401810078 | Sacramento Kings / Atlanta Hawks | 0 | 0.420000 | 0.658936 / 0.581584 | 0.583333 / 0.541960 | 0.395000 | yes |
| 401810309 | New Orleans Pelicans / New York Knicks | 0 | 0.250000 | — / — | 0.363636 / 0.430501 | 0.215000 | no |
| 401810143 | Milwaukee Bucks / Portland Trail Blazers | 0 | 0.550000 | — / — | 0.500000 / 0.500000 | 0.525000 | no |
| 401809954 | LA Clippers / Phoenix Suns | 1 | 0.250000 | — / — | 0.416667 / 0.458040 | 0.785000 | no |
| 401810609 | Phoenix Suns / Philadelphia 76ers | 0 | 0.580000 | — / — | 0.444444 / 0.472136 | 0.520000 | no |
| 401810685 | Houston Rockets / Utah Jazz | 1 | 0.720000 | — / — | 0.636364 / 0.569499 | 0.875000 | no |
| 401810958 | Los Angeles Lakers / Cleveland Cavaliers | 1 | 0.545000 | — / — | 0.609756 / 0.555556 | 0.540000 | no |
| 401810517 | Houston Rockets / Memphis Grizzlies | 1 | 0.720000 | — / — | 0.833333 / 0.690983 | 0.805000 | no |
| 401811016 | San Antonio Spurs / Portland Trail Blazers | 1 | 0.780000 | — / — | 0.714286 / 0.612574 | 0.605000 | no |
| 401810569 | Memphis Grizzlies / Minnesota Timberwolves | 1 | 0.280000 | — / — | 0.285714 / 0.387426 | 0.275000 | no |
| 401810762 | Sacramento Kings / New Orleans Pelicans | 0 | 0.350000 | — / — | 0.363636 / 0.430501 | 0.385000 | no |
| 401810776 | Cleveland Cavaliers / Boston Celtics | 0 | 0.380000 | 0.767658 / 0.645099 | 0.500000 / 0.500000 | 0.510000 | yes |
| 401810652 | Chicago Bulls / Toronto Raptors | 0 | 0.450000 | 0.571867 / 0.536121 | 0.267782 / 0.376847 | 0.355000 | yes |
| 401810855 | Brooklyn Nets / Oklahoma City Thunder | 0 | 0.080000 | 0.078035 / 0.225364 | 0.083770 / 0.232170 | 0.085000 | yes |
| 401811050 | Minnesota Timberwolves / New Orleans Pelicans | 1 | 0.720000 | 0.813126 / 0.675951 | 0.714286 / 0.612574 | 0.710000 | yes |
| 401810047 | New York Knicks / Brooklyn Nets | 1 | 0.920000 | 0.959677 / 0.829889 | 0.813953 / 0.676548 | 0.890000 | yes |
| 401810833 | Toronto Raptors / Detroit Pistons | 1 | 0.280000 | 0.653620 / 0.578713 | 0.411765 / 0.455533 | 0.395000 | yes |
| 401809980 | Milwaukee Bucks / New York Knicks | 1 | 0.520000 | 0.533234 / 0.516635 | 0.609756 / 0.555556 | 0.445000 | yes |
| 401810262 | Golden State Warriors / Orlando Magic | 1 | 0.450000 | 0.546999 / 0.523552 | 0.416667 / 0.458040 | 0.645000 | yes |
| 401810243 | Toronto Raptors / Boston Celtics | 0 | 0.420000 | 0.459343 / 0.479638 | 0.246154 / 0.363636 | 0.490000 | yes |
| 401810708 | Chicago Bulls / Portland Trail Blazers | 0 | 0.420000 | 0.646513 / 0.574901 | 0.267782 / 0.376847 | 0.375000 | yes |
| 401810223 | Minnesota Timberwolves / Memphis Grizzlies | 0 | 0.720000 | 0.783174 / 0.655235 | 0.813953 / 0.676548 | 0.720000 | yes |

## Reproduction, integrity and remaining limitations

All **170 tests pass** after completion, including offline mocks, strict schemas, source/group isolation, reproducible split, partial/denied/interrupted execution, uncertain claims, budget controls, immutable caches, numeric boundaries, bootstrap arithmetic, paired missingness, removal diagnostics and public result replay. HTTP error tests are local doubles, not additional live requests. Private verification checks raw capture bytes/wire identities and reparses responses; public replay verifies sanitized hashes and reproduces projections, aggregations, comparisons, calibration, diagnostics and bootstrap without credentials or private captures. Public replay does not independently authenticate provider inference.

All 170 tests and public replay also pass in a clean repository snapshot containing neither `.env` nor private captures, with no skipped tests. A secret-value scan of candidate public files found no configured credentials. Additional post-inference changes are report links and offline test fixtures; the precommitted forecasting/execution/diagnostic implementation is unchanged.

The [preservation check](../leap_nba_v2_development_50_preservation.json) found **zero changes among 11,032 protected original files**, including **7,608 historical data files**, all earlier direct/v1/v2-pilot/Phase 1 records, source snapshots and original cache entries. Only new v2 cache entries were appended; the existing README gained new report links. Frozen forecasting assets and split remain unchanged. The preserved-original manifest hash is `5c3d16f7062c2cd848a7f1f91408da0a94141525302f161c60dae4bb30798b40`.

```sh
# Public, no network, no credentials, no private cache required.
.venv/bin/python -m unittest discover -s tests -q
.venv/bin/python scripts/analyze_v2_development.py --replay reports/leap_nba_v2_development_50
.venv/bin/python scripts/analyze_development.py --replay reports/development_50/merged

# Operator's existing private captures; read-only and no inference.
.venv/bin/python scripts/run_v2_development.py --verify captures/leap_nba_v2_phase2_development_50/run
.venv/bin/python scripts/leap_v2_forecast.py --verify captures/leap_nba_v2_phase2/paid
.venv/bin/python scripts/direct_forecast.py --verify captures/direct_baseline_v1/development_all
.venv/bin/python scripts/leap_forecast.py --verify captures/leap_nba_v1/development_merged
```

The [execution guide](../../experiments/leap_nba_v2_development_50.md) records the original no-cost planning and explicit paid opt-in commands. Planning now reports no remaining matching paid requests because the same immutable cache is complete. Do not change directories or delete claims to repeat the experiment.

These real paid outputs support a reproducible, complete development comparison. They do **not** establish calibrated likelihood ratios or independent predictive skill. Outcome contamination, previously inspected development outcomes, incomplete historical statistical evidence, uncertain historical publication/schedule verification, correlated evidence and small calibration strata remain. V1's ten failures make the seven-method cohort selective; A/B comparisons explicitly retain different IDs. The 150 reserved games remain unforecast and unscored. A later separately authorized prospective evaluation using identical frozen packets is needed to assess generalization. No protocol change, v3 method, new evidence collection or further inference was implemented.
