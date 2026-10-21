# Full 50-game development experiment: execution and descriptive analysis

**All 50 development games were attempted and both runs are sealed, but LEAP probability coverage is 34/50.** Direct produced 50/50 valid forecasts. Forty required LEAP group attempts failed (37 HTTP 403, three connection failures); no failed request was retried or replaced with neutral evidence. Five-method scores below use **the same 34 games**, with all 16 excluded games retained in the full table and exports. This is not a complete 50-game five-method accuracy comparison.

## Protocol, preflight and scope

Forecasting methods, prompts, generation settings, group definitions, aggregation, evidence packets, 20-minute Kalshi quote rule and the 50/150 split were unchanged. Both methods used `claude-haiku-4-5-20251001`, temperature 0, maximum 128 output tokens, their original structured schemas, and no tools/search. Raw alpha=1 and conservative alpha=0.5 use the same LR observations. No reserved-subset forecast, outcome inspection or score was performed.

The repository was current at `624ff1f`. Preflight verified all 7,608 historical data files against committed Git blob identities, frozen direct assets against `f1e7258`, frozen LEAP assets against their registered hashes, both paid pilot runs/caches by read-only replay, and the split SHA-256 `300d87a9dbd8165934e1571453eb15a03f93616841c4a450514d42cc75a94043`. All 123 existing tests passed before paid inference. The diagnostic/bootstrap plan was committed as `14d0e8a` before additional inference.

No-cost planning found 45 missing direct requests and 114 missing LEAP requests, reusing five direct forecasts and 13 pilot LRs. Additional reservation bounds were $1.638345 direct and $3.323850 LEAP, **$4.962195 combined**. Run ceilings were 45 new direct calls/$2 and 180 new LEAP calls/$4, inside the operator’s 45/180/$10 authorization. No budget was exhausted.

## Coverage and provider failures

| Component | Planned | Usable evidence | Successful observations | Source-missing skips | Request failures |
| --- | ---: | ---: | ---: | ---: | ---: |
| Direct | 50 | 50 packets | 50 | 0 | 0 |
| A_team_strength | 50 | 50 | 34 | 0 | 16 |
| B_schedule_venue | 50 | 50 | 35 | 0 | 15 |
| C_player_availability | 50 | 27 | 18 | 23 | 9 |
| D_additional_news | 50 | 0 | 0 | 50 | 0 |

LEAP made **114 new one-time request attempts: 74 successful, 40 failed**. With 13 reused successes, there are 87 successful group estimates, 40 failed groups and 73 legitimate missing-evidence skips. A required failure makes both variants missing: **34 complete / 16 failed game forecasts**, zero budget-blocked groups. No malformed LR, insufficient response or out-of-bounds value was observed among successful model responses. One B and one C observation survive in otherwise failed games; LR-distribution counts therefore differ from the paired-scoring count.

The failures are concentrated in fixed run-order positions 24–39. All 37 HTTP 403 bodies were JSON without a recognized Anthropic error type; the saved text indicates a forbidden response. The three other failures have no HTTP status (recorded as 0). This does not establish whether the denials originated at Anthropic, an intermediary, or the execution network. Raw bodies remain private; no additional provider probe or paid retry was made. Cache identities and failed attempts remain preserved. Future retries require separate authorization and an auditable procedure preserving original records; changing cache directories or deleting claim markers would bypass safeguards.

Injury evidence was usable before inference for 27 games; 18 C estimates succeeded and nine requests failed. Source-missing C groups comprise 18 games with unavailable reports and five with both reports not yet submitted. All 50 D groups were not collected historically, and were skipped without backfilling. Missing reports/news never establish health.

## Paired results: n=34 for every method

| Method | n | Brier | Natural-log loss |
| --- | ---: | ---: | ---: |
| direct | 34 | 0.185776 | 0.549312 |
| leap_raw | 34 | 0.223300 | 0.628984 |
| leap_conservative | 34 | 0.222678 | 0.634225 |
| kalshi | 34 | 0.175804 | 0.523186 |
| constant_50 | 34 | 0.250000 | 0.693147 |

Brier is primary; log loss is natural logarithm with the existing epsilon=1e-15 clipping for log loss only. On these 34 games, direct and Kalshi have lower losses than either LEAP variant. Conservative-minus-raw changes are **−0.000622 Brier and +0.005241 log loss**: a small Brier improvement and worse log loss. These are descriptive development observations, not a selected winner or proof of comparative forecasting skill.

**Different-denominator result, reported separately:** the original direct-vs-market evaluator can score all 50 games: direct Brier **0.220757**, log loss **0.639271**; Kalshi **0.192294 / 0.561299**; constant 50% **0.250000 / 0.693147**. These n=50 numbers must not be compared to LEAP’s n=34 numbers. Provider-failure exclusions materially change the direct/market scores; complete-case selection uncertainty is not captured by the bootstrap.

## Descriptive paired bootstrap intervals

Each replicate samples 34 paired game rows with replacement, preserving all methods/outcomes within each row. The same sampled indices are used across the five comparisons. `random.Random(20261021)`, 10,000 replicates, two-sided 95% percentile intervals, linear interpolation at (B−1)q. No models or parameters are refit. Positive differences mean the first method has larger Brier loss.

| Comparison | n | Mean Brier difference | 95% percentile interval |
| --- | ---: | ---: | --- |
| direct_minus_kalshi | 34 | +0.009972 | [-0.017485, +0.036615] |
| leap_conservative_minus_direct | 34 | +0.036902 | [-0.004302, +0.075815] |
| leap_conservative_minus_kalshi | 34 | +0.046874 | [+0.011089, +0.081512] |
| leap_raw_minus_direct | 34 | +0.037524 | [-0.013240, +0.091002] |
| leap_raw_minus_kalshi | 34 | +0.047496 | [+0.004177, +0.092453] |

These intervals are descriptive: this is a development sample, pilot results were already inspected, games share teams and season context, missing forecasts are not accounted for by independent row resampling, and historical outcomes may be in model knowledge. Do not turn interval endpoints into significance-based model selection.

## LR distributions and sufficiency

Only successful elicited LRs enter this table. Missing-group LR=1 values are excluded from inferred-neutral counts. Quantiles use linear (n−1)q interpolation. Complete quantiles and population standard deviations are in `diagnostics.json`.

| Group | n | LR<1 | LR=1 | LR>1 | Mean LR | Min / median / p90 / max | Mean log-LR / SD |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| A_team_strength | 34 | 8 | 0 | 26 | 1.551765 | 0.080000 / 1.165000 / 2.605000 / 8.500000 | 0.124823 / 0.860001 |
| B_schedule_venue | 35 | 1 | 1 | 33 | 1.239143 | 0.720000 / 1.080000 / 1.680000 / 2.800000 | 0.171528 / 0.268610 |
| C_player_availability | 18 | 8 | 0 | 10 | 1.068333 | 0.420000 / 1.150000 / 1.549000 / 1.850000 | -0.018051 / 0.427759 |
| D_additional_news | 0 | 0 | 0 | 0 | — | — / — / — / — | — / — |

The prespecified extreme flag (LR<=0.1 or LR>=10) fired once: **401810855, Brooklyn–Oklahoma City, strength LR=0.08, adequate**. Raw home probability was 0.078035 and conservative 0.225364; the home team lost. That single realization neither validates nor disproves calibration. The largest A LR was 8.5, below the high-side flag but still substantial support. All accepted LRs satisfied [0.05,20] without clipping.

| Group / label | Successful observations | Mean abs(log LR) | Paired full-forecast n | Raw Brier / log loss | Conservative Brier / log loss |
| --- | ---: | ---: | ---: | ---: | ---: |
| A_team_strength / adequate | 17 | 0.823734 | 17 | 0.216244 / 0.615683 | 0.215772 / 0.620575 |
| A_team_strength / limited | 17 | 0.434932 | 17 | 0.230356 / 0.642284 | 0.229585 / 0.647875 |
| B_schedule_venue / adequate | 7 | 0.620089 | 7 | 0.294402 / 0.781030 | 0.249387 / 0.684134 |
| B_schedule_venue / limited | 28 | 0.082852 | 27 | 0.204866 / 0.589564 | 0.215754 / 0.621286 |
| C_player_availability / adequate | 12 | 0.473324 | 11 | 0.203617 / 0.588376 | 0.214698 / 0.619579 |
| C_player_availability / limited | 6 | 0.120968 | 6 | 0.201006 / 0.561611 | 0.199509 / 0.582411 |

Adequate observations have larger mean absolute log-LRs than limited observations in A, B and C. This is a model-assigned sufficiency label, not independent source verification or measured quality. Different label strata contain different games and evidence; their scores do not establish a causal benefit of sufficiency.

## Team-strength directionality

The diagnostic was fixed before additional inference: compare season wins/completed games and average point differential. A team is “weaker” only if **both** are strictly lower. Flag A LR>1 for a weaker home team or LR<1 for a weaker away team. Ties, discordant indicators and missing/zero-game statistics are unassessable. Recent form and home/away splits are intentionally not used by this narrow diagnostic; the model did receive them when available. No forecast was changed or discarded.

Across 50 games, 30 lack the statistics required for this check, three have ties/discordant indicators, and 17 meet strict dominance. Of those 17, 12 have successful A estimates; **five of 12 favor the weaker team**. The other five dominance cases have failed A requests. Season records exist for 93/100 team-games, scoring summaries for 61/100; their absence was preserved.

| Flagged game | Home / away win fraction | Home / away avg differential | A LR | Weaker team favored |
| --- | --- | --- | ---: | --- |
| 401810485 Dallas Mavericks vs Golden State Warriors | 0.409091 / 0.555556 | -2.409091 / 2.933333 | 1.42 | home |
| 401809808 Golden State Warriors vs Houston Rockets | 0.526316 / 0.733333 | 0.842105 / 11.133333 | 1.85 | home |
| 401810161 Minnesota Timberwolves vs San Antonio Spurs | 0.555556 / 0.722222 | 4.666667 / 6.277778 | 1.15 | home |
| 401810833 Toronto Raptors vs Detroit Pistons | 0.560606 / 0.727273 | 1.606061 / 7.742424 | 1.85 | home |
| 401810262 Golden State Warriors vs Orlando Magic | 0.482759 / 0.571429 | 1.172414 / 3.178571 | 1.15 | home |

These flags identify tension with two supplied statistics, not a proof the LLM’s full strength assessment is wrong: recent form, split records and missingness also appear in A. All five flagged estimates favor home; A favored home in 26/34 successful observations, while B did so in 33/35. This warrants a future blinded directionality study rather than automatic sign reversal.

## Injury availability strata

C availability is defined before inference, separately from request success. In the usable-source stratum, 17/27 games have complete five-method forecasts; in the unavailable-source stratum, 17/23 do. Each table row below uses the same 17 games for all five methods within that stratum. Different strata contain different games.

| Source stratum | Paired n | Direct Brier / log loss | Raw | Conservative | Kalshi | 50% |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| unavailable | 17 | 0.207606 / 0.596525 | 0.243905 / 0.679038 | 0.236020 / 0.661989 | 0.216731 / 0.614039 | 0.250000 / 0.693147 |
| usable | 17 | 0.163947 / 0.502098 | 0.202695 / 0.578929 | 0.209337 / 0.606461 | 0.134878 / 0.432334 | 0.250000 / 0.693147 |

LEAP scores are lower in the injury-usable stratum, but direct and market scores also differ substantially. This is observational composition, not evidence that injury inclusion caused improvement. Source availability, source submission state, model-request failure and full-forecast eligibility remain distinct in the exports.

## Contributions and leave-one-group-out recomputation

The following contributions include legitimate missing-group zeros on the identical 34-game intersection. Inferred-only distributions above have different observation counts. Raw contributions are log(LR); conservative contributions are exactly half. `Extreme push` is abs(full p−0.5)−abs(omission p−0.5), positive when a group moves the forecast further from 50%.

| Group | Raw log contribution mean / SD / median | Conservative mean | Mean raw extreme push | Raw push / pull / unchanged counts |
| --- | --- | ---: | ---: | --- |
| A_team_strength | 0.124823 / 0.860001 / 0.152638 | 0.062412 | 0.089417 | 28 / 6 / 0 |
| B_schedule_venue | 0.175990 / 0.271250 / 0.095145 | 0.087995 | 0.022320 | 22 / 11 / 1 |
| C_player_availability | 0.000105 / 0.306381 / 0.000000 | 0.000053 | 0.001744 | 11 / 6 / 17 |
| D_additional_news | 0.000000 / 0.000000 / 0.000000 | 0.000000 | 0.000000 | 0 / 0 / 34 |

A has the largest average move toward extremes. B adds home support in most observations; on this sample its inclusion worsens aggregate losses. C sometimes reinforces and sometimes offsets other evidence. Dependence among records, differential, splits, venue and long-running injuries prevents interpreting these additive factors as calibrated independent likelihoods.

All removal metrics below use the same n=34 games, no additional calls. Parentheses show **omission minus full** loss: positive means removal worsened the score.

| Removed | Raw Brier / log loss (changes) | Conservative Brier / log loss (changes) |
| --- | --- | --- |
| A_team_strength | 0.275663 / 0.746455 (+0.052363 / +0.117471) | 0.260442 / 0.714190 (+0.037764 / +0.079965) |
| B_schedule_venue | 0.204809 / 0.586078 (-0.018491 / -0.042906) | 0.214183 / 0.617154 (-0.008495 / -0.017071) |
| C_player_availability | 0.211967 / 0.607335 (-0.011333 / -0.021649) | 0.218340 / 0.626129 (-0.004338 / -0.008096) |
| D_additional_news | 0.223300 / 0.628984 (+0.000000 / +0.000000) | 0.222678 / 0.634225 (+0.000000 / +0.000000) |

Removal of B or C reduces loss on these complete cases, while removal of A increases it. This is an offline diagnostic, not a basis for changing v1 or choosing a variant. D is unavailable throughout; removal necessarily changes nothing.

## Calibration and shrinkage

| Method | n | Mean confidence | Classification accuracy | Confidence − accuracy | Mean abs(p−0.5) | p<=0.1 or >=0.9 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| direct | 34 | 0.667647 | 0.705882 | -0.038235 | 0.167647 | 2 |
| leap_raw | 34 | 0.665903 | 0.617647 | +0.048256 | 0.165903 | 2 |
| leap_conservative | 34 | 0.592677 | 0.617647 | -0.024970 | 0.092677 | 0 |
| kalshi | 34 | 0.672059 | 0.676471 | -0.004412 | 0.172059 | 1 |
| constant_50 | 34 | 0.500000 | 0.411765 | +0.088235 | 0.000000 | 0 |

Confidence is max(p,1−p), with p>=0.5 classified as home (including the constant baseline’s ties). Raw and conservative have the same classifications; positive alpha shrinkage necessarily moves probabilities toward 50%. Raw confidence exceeds observed accuracy here; conservative confidence falls below it. These aggregate gaps are not full calibration measures. The mixed proper-score changes do not establish better calibration from shrinkage.

Fixed ten-bin calibration is shown as **count / mean p / home-win frequency**; `0 / — / —` denotes empty. Upper endpoints are exclusive except the final bin including 1. Small buckets remain descriptive.

| Probability bucket | Direct | Raw | Conservative | Kalshi | 50% |
| --- | --- | --- | --- | --- | --- |
| [0.0, 0.1) | 1 / 0.080000 / 0.000000 | 1 / 0.078035 / 0.000000 | 0 / — / — | 1 / 0.085000 / 0.000000 | 0 / — / — |
| [0.1, 0.2) | 2 / 0.165000 / 0.000000 | 1 / 0.157043 / 0.000000 | 0 / — / — | 4 / 0.168750 / 0.000000 | 0 / — / — |
| [0.2, 0.3) | 3 / 0.260000 / 0.333333 | 2 / 0.266064 / 0.000000 | 1 / 0.225364 / 0.000000 | 1 / 0.235000 / 0.000000 | 0 / — / — |
| [0.3, 0.4) | 5 / 0.362000 / 0.200000 | 3 / 0.359310 / 0.000000 | 3 / 0.351019 / 0.000000 | 5 / 0.367000 / 0.400000 | 0 / — / — |
| [0.4, 0.5) | 7 / 0.428571 / 0.285714 | 2 / 0.471263 / 0.500000 | 5 / 0.450968 / 0.200000 | 4 / 0.460000 / 0.250000 | 0 / — / — |
| [0.5, 0.6) | 5 / 0.532000 / 0.400000 | 10 / 0.543497 / 0.500000 | 16 / 0.541414 / 0.500000 | 8 / 0.529375 / 0.375000 | 34 / 0.500000 / 0.411765 |
| [0.6, 0.7) | 2 / 0.650000 / 0.000000 | 7 / 0.652148 / 0.428571 | 7 / 0.639581 / 0.428571 | 2 / 0.630000 / 0.500000 | 0 / — / — |
| [0.7, 0.8) | 8 / 0.727500 / 0.875000 | 5 / 0.758601 / 0.400000 | 1 / 0.714696 / 1.000000 | 5 / 0.728000 / 0.600000 | 0 / — / — |
| [0.8, 0.9) | 0 / — / — | 2 / 0.837836 / 1.000000 | 1 / 0.829889 / 1.000000 | 4 / 0.846250 / 1.000000 | 0 / — / — |
| [0.9, 1.0] | 1 / 0.920000 / 1.000000 | 1 / 0.959677 / 1.000000 | 0 / — / — | 0 / — / — | 0 / — / — |

## Usage, costs and latency

All costs use the original conservative $3/$15 per million input/output token estimates, not invoices. Forty failed LEAP requests returned no token usage; their records conservatively retain their reserved upper bounds. Those reserves must not be described as observed token charges.

| Scope | New/reused request count | Input / output tokens reported | Reported-token estimate | Unknown-usage reserve | Recorded estimate including reserve | Summed latency (s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| direct additional | 45 | 102097 / 675 | $0.316416 | $0.000000 | $0.316416 | 104.951338 |
| direct reused | 5 | 12766 / 75 | $0.039423 | $0.000000 | $0.039423 | 9.744020 |
| direct all_saved | 50 | 114863 / 750 | $0.355839 | $0.000000 | $0.355839 | 114.695358 |
| leap additional | 114 | 112075 / 1406 | $0.357315 | $1.154553 | $1.511868 | 291.371586 |
| leap reused | 13 | 20769 / 247 | $0.066012 | $0.000000 | $0.066012 | 32.399851 |
| leap all_saved | 127 | 132844 / 1653 | $0.423327 | $1.154553 | $1.577880 | 323.771437 |

**Additional total:** 159 request attempts (45 direct, 114 LEAP), 214,172 input and 2,081 output tokens reported; **$0.673731 reported-token estimate + $1.154553 unknown-usage reserve = $1.828284 recorded conservative estimate**. The original reservation bound was $4.962195; the independent run ceilings totaled $6, below the authorized $10. No paid retries or new evidence calls occurred. Including reused pilot observations, the recorded estimate is $1.933719 ($0.779166 reported-token estimate plus the same failure reserve).

New direct request clocks span **2026-10-21T09:58:04.462574Z–09:59:50.583993Z**; new LEAP clocks span **2026-10-21T10:04:04.102956Z–12:07:54.733275Z**. These are actual captured clocks, not historical evidence times. Summed request latency is measured separately by the transport’s monotonic clock (104.951338s direct, 291.371586s LEAP); the wider UTC span includes gaps and is not represented as provider processing time. The cause of those gaps is not established by saved captures.

## Full 50-game results table

All rows are evaluation-only development results. `—` means a failed LEAP game forecast, never an imputed probability. Exact per-game scores, every paired score difference, group LRs/statuses, submission/missingness reasons and hashes are in [results.csv](results.csv), [per_game.json](per_game.json), and [observations.json](observations.json). Raw-minus-direct Brier differences below exist only for matched rows.

| Game / recorded date (home vs away) | Home won | Direct p | Raw p | Conservative p | Kalshi p | Paired? | Raw − direct Brier |
| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: |
| 401810544 2026-01-31 Boston Celtics vs Sacramento Kings | 1 | 0.720000 | 0.503096 | 0.501548 | 0.810000 | yes | 0.168514 |
| 401810485 2026-01-23 Dallas Mavericks vs Golden State Warriors | 1 | 0.380000 | 0.632033 | 0.567209 | 0.375000 | yes | -0.249000 |
| 401810279 2025-12-27 Orlando Magic vs Charlotte Hornets | 0 | 0.680000 | 0.710098 | 0.610147 | 0.710000 | yes | 0.041839 |
| 401836746 2025-12-12 Houston Rockets vs LA Clippers | 1 | 0.780000 | 0.765478 | 0.643704 | 0.775000 | yes | 0.006600 |
| 401809808 2025-11-27 Golden State Warriors vs Houston Rockets | 0 | 0.350000 | 0.653620 | 0.578713 | 0.525000 | yes | 0.304719 |
| 401810737 2026-03-03 Golden State Warriors vs LA Clippers | 0 | 0.620000 | 0.394691 | 0.446748 | 0.490000 | yes | -0.228619 |
| 401810840 2026-03-16 Brooklyn Nets vs Portland Trail Blazers | 0 | 0.320000 | 0.258028 | 0.370955 | 0.235000 | yes | -0.035821 |
| 401810476 2026-01-22 Boston Celtics vs Indiana Pacers | 1 | 0.720000 | 0.862547 | 0.714696 | 0.820000 | yes | -0.059507 |
| 401810061 2025-11-11 LA Clippers vs Atlanta Hawks | 0 | 0.420000 | 0.608227 | 0.554763 | 0.615000 | yes | 0.193540 |
| 401810766 2026-03-07 Denver Nuggets vs New York Knicks | 0 | 0.520000 | 0.696758 | 0.602515 | 0.500000 | yes | 0.215072 |
| 401810475 2026-01-22 Charlotte Hornets vs Cleveland Cavaliers | 0 | 0.420000 | 0.555247 | 0.527708 | 0.415000 | yes | 0.131899 |
| 401809237 2025-10-24 Golden State Warriors vs Denver Nuggets | 1 | 0.720000 | 0.674267 | 0.589954 | 0.555000 | yes | 0.027702 |
| 401810504 2026-01-25 Utah Jazz vs Miami Heat | 0 | 0.380000 | 0.502705 | 0.501353 | 0.335000 | yes | 0.108313 |
| 401810498 2026-01-24 Philadelphia 76ers vs New York Knicks | 0 | 0.520000 | 0.593165 | 0.546994 | 0.500000 | yes | 0.081445 |
| 401810064 2025-11-12 Philadelphia 76ers vs Boston Celtics | 1 | 0.550000 | 0.553970 | 0.527064 | 0.565000 | yes | -0.003557 |
| 401810189 2025-12-05 Washington Wizards vs Boston Celtics | 0 | 0.180000 | 0.310059 | 0.401331 | 0.195000 | yes | 0.063737 |
| 401810928 2026-03-28 Golden State Warriors vs Washington Wizards | 1 | 0.720000 | 0.483183 | 0.491589 | 0.865000 | yes | 0.188700 |
| 401810437 2026-01-16 San Antonio Spurs vs Milwaukee Bucks | 1 | 0.720000 | 0.766595 | 0.644418 | 0.725000 | yes | -0.023922 |
| 401810178 2025-12-03 Golden State Warriors vs Oklahoma City Thunder | 0 | 0.250000 | 0.274100 | 0.380610 | 0.170000 | yes | 0.012631 |
| 401810094 2025-11-17 Phoenix Suns vs Atlanta Hawks | 0 | 0.550000 | 0.539807 | 0.519935 | 0.510000 | yes | -0.011109 |
| 401810161 2025-12-01 Minnesota Timberwolves vs San Antonio Spurs | 1 | 0.420000 | 0.534884 | 0.517463 | 0.570000 | yes | -0.120067 |
| 401810573 2026-02-04 Washington Wizards vs New York Knicks | 0 | 0.250000 | 0.373178 | 0.435535 | 0.160000 | yes | 0.076762 |
| 401810706 2026-02-27 Brooklyn Nets vs San Antonio Spurs | 0 | 0.150000 | 0.157043 | 0.301493 | 0.150000 | yes | 0.002162 |
| 401811000 2026-04-07 Memphis Grizzlies vs Cleveland Cavaliers | 0 | 0.280000 | — | — | 0.080000 | no: LEAP failed | — |
| 401811008 2026-04-08 New Orleans Pelicans vs Utah Jazz | 1 | 0.580000 | — | — | 0.810000 | no: LEAP failed | — |
| 401810509 2026-01-26 San Antonio Spurs vs New Orleans Pelicans | 0 | 0.780000 | — | — | 0.830000 | no: LEAP failed | — |
| 401810032 2025-11-06 Dallas Mavericks vs New Orleans Pelicans | 0 | 0.920000 | — | — | 0.735000 | no: LEAP failed | — |
| 401810749 2026-03-05 Boston Celtics vs Charlotte Hornets | 0 | 0.720000 | — | — | 0.690000 | no: LEAP failed | — |
| 401810078 2025-11-13 Sacramento Kings vs Atlanta Hawks | 0 | 0.420000 | — | — | 0.395000 | no: LEAP failed | — |
| 401810309 2025-12-30 New Orleans Pelicans vs New York Knicks | 0 | 0.250000 | — | — | 0.215000 | no: LEAP failed | — |
| 401810143 2025-11-25 Milwaukee Bucks vs Portland Trail Blazers | 0 | 0.550000 | — | — | 0.525000 | no: LEAP failed | — |
| 401809954 2025-10-25 LA Clippers vs Phoenix Suns | 1 | 0.250000 | — | — | 0.785000 | no: LEAP failed | — |
| 401810609 2026-02-08 Phoenix Suns vs Philadelphia 76ers | 0 | 0.580000 | — | — | 0.520000 | no: LEAP failed | — |
| 401810685 2026-02-24 Houston Rockets vs Utah Jazz | 1 | 0.720000 | — | — | 0.875000 | no: LEAP failed | — |
| 401810958 2026-04-01 Los Angeles Lakers vs Cleveland Cavaliers | 1 | 0.545000 | — | — | 0.540000 | no: LEAP failed | — |
| 401810517 2026-01-27 Houston Rockets vs Memphis Grizzlies | 1 | 0.720000 | — | — | 0.805000 | no: LEAP failed | — |
| 401811016 2026-04-09 San Antonio Spurs vs Portland Trail Blazers | 1 | 0.780000 | — | — | 0.605000 | no: LEAP failed | — |
| 401810569 2026-02-03 Memphis Grizzlies vs Minnesota Timberwolves | 1 | 0.280000 | — | — | 0.275000 | no: LEAP failed | — |
| 401810762 2026-03-06 Sacramento Kings vs New Orleans Pelicans | 0 | 0.350000 | — | — | 0.385000 | no: LEAP failed | — |
| 401810776 2026-03-08 Cleveland Cavaliers vs Boston Celtics | 0 | 0.380000 | 0.767658 | 0.645099 | 0.510000 | yes | 0.444899 |
| 401810652 2026-02-20 Chicago Bulls vs Toronto Raptors | 0 | 0.450000 | 0.571867 | 0.536121 | 0.355000 | yes | 0.124532 |
| 401810855 2026-03-18 Brooklyn Nets vs Oklahoma City Thunder | 0 | 0.080000 | 0.078035 | 0.225364 | 0.085000 | yes | -0.000311 |
| 401811050 2026-04-13 Minnesota Timberwolves vs New Orleans Pelicans | 1 | 0.720000 | 0.813126 | 0.675951 | 0.710000 | yes | -0.043478 |
| 401810047 2025-11-09 New York Knicks vs Brooklyn Nets | 1 | 0.920000 | 0.959677 | 0.829889 | 0.890000 | yes | -0.004774 |
| 401810833 2026-03-15 Toronto Raptors vs Detroit Pistons | 1 | 0.280000 | 0.653620 | 0.578713 | 0.395000 | yes | -0.398421 |
| 401809980 2025-10-29 Milwaukee Bucks vs New York Knicks | 1 | 0.520000 | 0.533234 | 0.516635 | 0.445000 | yes | -0.012529 |
| 401810262 2025-12-23 Golden State Warriors vs Orlando Magic | 1 | 0.450000 | 0.546999 | 0.523552 | 0.645000 | yes | -0.097290 |
| 401810243 2025-12-21 Toronto Raptors vs Boston Celtics | 0 | 0.420000 | 0.459343 | 0.479638 | 0.490000 | yes | 0.034596 |
| 401810708 2026-02-27 Chicago Bulls vs Portland Trail Blazers | 0 | 0.420000 | 0.646513 | 0.574901 | 0.375000 | yes | 0.241579 |
| 401810223 2025-12-18 Minnesota Timberwolves vs Memphis Grizzlies | 0 | 0.720000 | 0.783174 | 0.655235 | 0.720000 | yes | 0.094962 |

## Limitations and recommendations for a future v2

- **Operational completeness:** 16 LEAP forecasts remain unavailable because of provider/transport failures. Resolve the source of HTTP 403/connection failures before any separately authorized retry plan. Preserve original captures and uncertain attempt markers; do not change cache identity to force repeats. Consider auditable rate limits/circuit breakers for future experiments, not changes to this frozen run.
- **Elicitation quality:** investigate home/away directionality using blinded synthetic dominance cases and explicit group isolation checks before freezing a v2 prompt. This diagnostic does not justify automatically flipping signs. Player impact is not quantified in the packet; sufficiency labels may be too permissive for incomplete reports.
- **Dependence and prior:** records, recent form, margins and splits overlap; splits and venue can double count home support, and past injuries can already affect records. Future grouping/dependence corrections and prior choices need a precommitted development-only study. Do not fit alpha to these results or tune against reserved outcomes.
- **Source limitations:** season/scoring histories are incomplete, 23 injury groups are unusable and no historical news is collected. Packet and schedule point-in-time verification remains false. Official origin timestamps do not independently establish historical public visibility; missing players are never inferred healthy. No missing source was backfilled.
- **Scientific scope:** all results are exploratory historical development observations, vulnerable to model memory and source revision. The 34 complete cases are not all 50 development games, and independent game bootstrap intervals ignore shared-team/time dependence and failure selection. LEAP also uses more calls than direct. Prospective frozen packets remain the primary eventual out-of-sample evaluation. No winner, alpha choice or claim of calibrated likelihood ratios follows this run.
- **No v2 implementation:** no prompts, model settings, alpha, evidence features or evaluation rules were changed. The reserved 150 games remain unforecast and unscored.

## Validation and reproduction

The complete suite passes **132 tests**. Both full paid runs and both pilots pass read-only private-cache verification. Public sanitized replay regenerates request/group identities, probabilities, scoring, diagnostics, bootstrap intervals, usage totals and CSV from the unchanged data, without credentials/network. All **7,827 protected pre-existing files** retain their original SHA-256 hashes, including historical data, original caches, pilots and forecasting code. New cache entries preserve all successful and failed raw replies privately. No credentials or raw provider bodies are included in Git.

```sh
# No network, inference or credentials required:
.venv/bin/python scripts/direct_forecast.py --verify captures/direct_baseline_v1/development_all
.venv/bin/python scripts/leap_forecast.py --verify captures/leap_nba_v1/development_all
.venv/bin/python scripts/analyze_development.py --replay reports/development_50
.venv/bin/python -m unittest discover -s tests -q

# Re-run the unchanged separate evaluator from the original private captures:
.venv/bin/python scripts/compare_forecasts.py \
  --direct-run captures/direct_baseline_v1/development_all \
  --leap-run captures/leap_nba_v1/development_all \
  --output captures/development_50/comparison
```

The full live invocations used the existing local credential-only launchers and original CLIs: direct `--live --allow-network --allow-inference --subset development --limit 50 --max-paid-calls 45 --max-estimated-cost-usd 2.00 --output captures/direct_baseline_v1/development_all`; LEAP used the same live flags with `--max-paid-calls 180 --max-estimated-cost-usd 4.00 --output captures/leap_nba_v1/development_all`. These are a record of execution, not authorization for retries. Do not initiate new paid attempts to fill gaps.

[Preflight](preflight.json), [analysis plan](analysis_plan.json), [paired evaluator summary](summary.json), [diagnostics/bootstrap](diagnostics.json), [sanitized observations](observations.json), [resource/provenance metadata](reproduction.json), and [content-hash manifest](manifest.json) are retained for audit. Private-cache replay authenticates saved response bytes by their recorded hashes; public arithmetic replay cannot independently authenticate private provider replies.
