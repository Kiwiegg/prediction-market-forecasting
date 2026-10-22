# LEAP-NBA v2 Phase 2: five-game historical pilot

The authorized pilot completed **13 real Anthropic calls**, producing **five complete forecasts** with seven legitimate missing-source skips, no insufficient/invalid responses, no provider failures, and no retries. On the **identical five-game intersection**, v2 improved on v1 but remained worse than direct LLM on Brier and log loss. This is a development-informed integration result; improved evidence-level consistency has not established improved out-of-sample probability accuracy.

## Frozen protocol and actual inference

The [historical v2 protocol](../experiments/leap_nba_v2_phase2/protocol.md), group definitions, all four prompts, schemas, mapping, model settings, selected parent hashes and tested implementation were committed in **`8520406` before any paid call**. Registered asset SHA-256: `76bcb80ec46b452d33610ac10eb9dee1606c18b3723cfa9c25780b5c9f1ff114`. No prompt, mapping, category, orientation, alpha, evidence or evaluation rule changed after observing results. The same direct/v1 pilot IDs were fixed in advance; prior outcomes and forecasts were already known, so this is not an independent historical test.

Both variants reuse the same 13 qualitative observations: neutral prior, sum of mapped home-oriented log-LRs, alpha 1 or 0.5, and stable sigmoid. The mapping remains neutral1, slight1.25, moderate1.75, strong2.5, very_strong4, with reciprocals for the opposite side. These are heuristic mapped ratios, not calibrated likelihood ratios. Missing sources contribute explicit skipped LR1, while failed/insufficient required inference would make the final forecast missing.

Actual request interval: **2026-10-22T12:13:55.310428Z–12:14:35.079613Z**; sealed at **12:14:35.086618Z**. These are retrospective inference clocks, not historical publication/snapshot clocks. Requested/returned model was `claude-haiku-4-5-20251001`, temperature0, max128 output tokens, strict structured JSON, no tools, search or retrieval. All 13 requests returned HTTP200 and coherent schema-valid responses; 11 were adequate and two limited. No model response was insufficient or usable neutral. There were no HTTP403s, malformed responses, blocked groups or paid retries.

Reported usage: **14,286 input + 286 output tokens**. Summed captured HTTP latency: **39.457498 seconds**. Estimated additional cost: **$0.031432**, using precommitted conservative $2/$10 per million input/output tokens, not an invoice. All calls had pre-call reservations; the whole-plan reservation was **$0.212498**, within 20 requests/$1. No qualitative cache hit was available; all 13 paid observations are new. Direct and v1 used their original saved outputs with **zero new calls**. Their prior saved usage/costs remain separately identified in [summary.json](leap_nba_v2_pilot/summary.json): direct 12,766/75 tokens, $0.039423; v1 20,769/247 tokens, $0.066012. Those older estimates used $3/$15 rates, so dollar totals are not a normalized efficiency comparison.

## Inputs, source absence and qualitative observations

A reuses Phase 1's deterministic X/Y projection and removes identities, dates, home/away labels/splits and unrelated groups. Its X/Y assignment stays outside model context and is inverted afterward where necessary. B receives the existing venue splits, cutoff rest and venue designation; C/D reuse validated v1 partitioning and deduplication. All seven methods retain identical parent snapshot bindings. No historical news was backfilled, and source/schedule point-in-time verification flags remain false.

The table shows original model labels, category and sufficiency, followed by **home-oriented LR**. `L` means limited, `A` adequate, and `1*` a source-missing skip rather than a model-assessed neutral. D skipped for every game because historical news was not collected.

| Game, home vs away | X denotes | A: side/category/sufficiency → LR | B: side/category/sufficiency → LR | C: side/category/sufficiency → LR | D |
| --- | --- | --- | --- | --- | --- |
| 401810544 Boston–Sacramento | away | Y/slight/L → 1.25 | home/slight/L → 1.25 | away/moderate/A → 0.571429 | 1* |
| 401810485 Dallas–Golden State | away | X/moderate/A → 0.571429 | home/moderate/A → 1.75 | away/moderate/A → 0.571429 | 1* |
| 401810279 Orlando–Charlotte | home | X/moderate/A → 1.75 | home/moderate/A → 1.75 | away/moderate/A → 0.571429 | 1* |
| 401836746 Houston–LA Clippers | home | X/strong/A → 2.50 | home/moderate/A → 1.75 | 1* | 1* |
| 401809808 Golden State–Houston | home | Y/strong/A → 0.40 | away/slight/A → 0.80 | 1* | 1* |

Boston's opponent statistical history/splits were unavailable; A and B retain that omission and returned limited judgments. Boston's injury report was submitted, but Sacramento's was **not yet submitted**. C still returned adequate away/moderate support. This repeats the v1 concern that an adequate label does not establish sound treatment of missing opponent availability; the terse response cannot reveal internal assumptions. Dallas/Golden State and Orlando/Charlotte had reports for both sides. Both sides' official reports were unavailable for the last two games, so C skipped; no healthy-player inference or current-news replacement was added. All five news groups explicitly record `not_collected_historical`.

## Exact paired comparison

Every aggregate score, calibration table and removal score below uses **n=5**, with exactly the IDs above and no exclusions. All finalized outcomes and preferred market quotes were available. Kalshi retains the original two-sided YES quote candle-end lag <=1200 seconds at/before cutoff; actual quote-update age remains unknown. Lower scores are better. Log loss uses natural logs and epsilon1e-15 clipping only for log loss.

| Method | n | Brier | Log loss |
| --- | ---: | ---: | ---: |
| Direct LLM | 5 | 0.219220 | 0.622953 |
| V1 raw | 5 | 0.273754 | 0.742295 |
| V1 conservative | 5 | 0.253980 | 0.700805 |
| V2 raw | 5 | 0.236481 | 0.651620 |
| V2 conservative | 5 | 0.229636 | 0.649314 |
| Kalshi | 5 | 0.251415 | 0.685751 |
| Constant50% | 5 | 0.250000 | 0.693147 |

V2 raw minus v1 raw is **−0.037274 Brier / −0.090674 log loss**; conservative minus v1 conservative is **−0.024343 / −0.051492**. V2 remains worse than direct: raw-minus-direct **+0.017261 / +0.028667**, conservative-minus-direct **+0.010416 / +0.026360**. Both v2 variants score below Kalshi and constant50% in this tiny selected historical pilot; no predictive-skill or statistical-significance conclusion follows.

| Game | Direct | V1 raw | V1 cons. | V2 raw | V2 cons. | Kalshi | Home won |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 401810544 | 0.720000 | 0.503096 | 0.501548 | 0.471698 | 0.485838 | 0.810000 | 1 |
| 401810485 | 0.380000 | 0.632033 | 0.567209 | 0.363636 | 0.430501 | 0.375000 | 1 |
| 401810279 | 0.680000 | 0.710098 | 0.610147 | 0.636364 | 0.569499 | 0.710000 | 0 |
| 401836746 | 0.780000 | 0.765478 | 0.643704 | 0.813953 | 0.676548 | 0.775000 | 1 |
| 401809808 | 0.350000 | 0.653620 | 0.578713 | 0.242424 | 0.361302 | 0.525000 | 0 |

Constant50% is 0.5 for every game. Per-game v2 losses follow; [per_game.json](leap_nba_v2_pilot/per_game.json) contains full-precision probabilities/losses for **all seven methods and every paired score difference**.

| Game | V2 raw Brier / log loss | V2 cons. Brier / log loss | Raw minus v1 raw Brier | Cons. minus direct Brier |
| --- | ---: | ---: | ---: | ---: |
| 401810544 | 0.279103 / 0.751416 | 0.264363 / 0.721881 | +0.032189 | +0.185963 |
| 401810485 | 0.404959 / 1.011601 | 0.324329 / 0.842806 | +0.269559 | −0.060071 |
| 401810279 | 0.404959 / 1.011601 | 0.324329 / 0.842806 | −0.099280 | −0.138071 |
| 401836746 | 0.034613 / 0.205852 | 0.104621 / 0.390752 | −0.020387 | +0.056221 |
| 401809808 | 0.058770 / 0.277632 | 0.130539 / 0.448324 | −0.368449 | +0.008039 |

## Direction, magnitude and dependence diagnostics

The preregistered strength diagnostic calls a side weaker only when both its completed-season win fraction and average differential are strictly lower. Ties/discordant/missing statistics are unassessable. Boston–Sacramento is unassessable because Sacramento's history is missing. Across the **same four assessable games**, v1 favors the weaker side twice, v2 zero times:

| Game | Home win fraction / differential | Away win fraction / differential | V1 A favors | V2 A favors |
| --- | ---: | ---: | --- | --- |
| 401810485 | 0.409091 / −2.409091 | 0.555556 / +2.933333 | home | away |
| 401810279 | 0.566667 / +2.333333 | 0.333333 / −3.400000 | home | home |
| 401836746 | 0.714286 / +10.619048 | 0.250000 / −5.166667 | home | home |
| 401809808 | 0.526316 / +0.842105 | 0.733333 / +11.133333 | home | away |

This diagnostic is not forecast correctness: Dallas actually won, so its more statistically aligned v2 strength assessment coincides with a worse raw forecast loss. No sign was corrected using this result. V1 A also included venue splits, so its disagreement is not a simple arithmetic contradiction.

| Group | V1 successful home / away / neutral | V2 successful home / away / neutral | V2 categories |
| --- | --- | --- | --- |
| A, n=5 | 5 / 0 / 0 | 3 / 2 / 0 | slight1, moderate2, strong2 |
| B, n=5 | 5 / 0 / 0 | 4 / 1 / 0 | slight2, moderate3 |
| C, n=3 | 1 / 2 / 0 | 0 / 3 / 0 | moderate3 |
| D, n=0 | 0 / 0 / 0 | 0 / 0 / 0 | all five source-missing |

V2 has three slight, eight moderate and two strong assessments; no neutral or very-strong outputs. Successful v2 home-oriented LRs span **0.40–2.50**, versus **0.62–3.20** in v1. A's reduced home-favoring count is consistent with the intended change, but blinding, categorical elicitation, group prompts and relocated splits all changed together. Five games cannot identify a causal effect. V2 C flips Orlando's v1 home-favoring judgment to away support; both remain uncalibrated assessments without quantified player-impact evidence.

A/B reinforce the same nonzero direction in **4/5 v2 games** (all except Dallas), versus 5/5 in v1. Their contributions remain dependent: venue split records can reconstruct season totals and overlap A's statistics, and long-running injuries may already affect both. The new partition and shrinkage do not establish independent calibrated LRs.

## Contributions and offline removal

Raw contributions are log(LR_home); conservative contributions are exactly half. Source skips contribute zero, distinct from an accepted usable neutral assessment. Full records preserve both weighted variants, omission probabilities and full-minus-omission probability deltas.

| Game | A log-LR | B log-LR | C log-LR | D log-LR |
| --- | ---: | ---: | ---: | ---: |
| 401810544 | +0.223144 | +0.223144 | −0.559616 | 0 |
| 401810485 | −0.559616 | +0.559616 | −0.559616 | 0 |
| 401810279 | +0.559616 | +0.559616 | −0.559616 | 0 |
| 401836746 | +0.916291 | +0.559616 | 0 | 0 |
| 401809808 | −0.916291 | −0.223144 | 0 | 0 |

Leave-one-group-out scores use the **same n=5** and no extra calls. Full v1/v2 omission results and omission-minus-full deltas are in the summary.

| Removed group | V2 raw Brier / log loss | V2 cons. Brier / log loss |
| --- | ---: | ---: |
| A | 0.234008 / 0.660307 | 0.240393 / 0.673802 |
| B | 0.264365 / 0.728672 | 0.249775 / 0.693144 |
| C | 0.212791 / 0.614625 | 0.217530 / 0.626322 |
| D | 0.236481 / 0.651620 | 0.229636 / 0.649314 |

Removing C improves both scores here, as in the earlier v1 pilot, but this is an outcome-informed diagnostic rather than grounds to drop injuries or tune the method. Removing A slightly improves raw Brier while worsening raw log loss; removing B worsens both variants. No group, alpha or observation was changed based on these results.

## Calibration

Ten precommitted equal-width bins are preserved, including zero-count bins in JSON. Below, each populated bin is `range: count, mean probability, observed home-win frequency`. Every method totals **n=5**.

- Direct: [0.3,0.4): 2, 0.365000, 0.500000; [0.6,0.7): 1, 0.680000, 0; [0.7,0.8): 2, 0.750000, 1.
- V1 raw: [0.5,0.6): 1, 0.503096, 1; [0.6,0.7): 2, 0.642826, 0.5; [0.7,0.8): 2, 0.737788, 0.5.
- V1 conservative: [0.5,0.6): 3, 0.549157, 0.666667; [0.6,0.7): 2, 0.626925, 0.5.
- V2 raw: [0.2,0.3): 1, 0.242424, 0; [0.3,0.4): 1, 0.363636, 1; [0.4,0.5): 1, 0.471698, 1; [0.6,0.7): 1, 0.636364, 0; [0.8,0.9): 1, 0.813953, 1.
- V2 conservative: [0.3,0.4): 1, 0.361302, 0; [0.4,0.5): 2, 0.458169, 1; [0.5,0.6): 1, 0.569499, 0; [0.6,0.7): 1, 0.676548, 1.
- Kalshi: [0.3,0.4): 1, 0.375000, 1; [0.5,0.6): 1, 0.525000, 0; [0.7,0.8): 2, 0.742500, 0.5; [0.8,0.9): 1, 0.810000, 1.
- Constant50%: [0.5,0.6): 5, 0.500000, 0.6.

Shrinkage reduces confidence in both correct and incorrect v2 predictions and improves the two aggregate losses on this sample. V2's populated buckets contain only one or two observations; this cannot establish better calibration. Both alpha variants remain frozen for future separately authorized comparisons.

## Reproduction, preservation and remaining limitations

The pre-inference full suite passed **159 tests**; adding saved paid public replay brings the post-inference suite to **160 passing tests**. Tests cover projection isolation, deterministic inversion, strict coherence/mapping, source skips vs abstention, provider/malformed failures, first-403 stopping, budget preflight, uncertain-attempt protection, immutable caches/seals, stable aggregation/removal, exact paired scoring with incomplete/empty intersections and data/split preservation. Mocks and failure fixtures validate controls; no live 403, live abstention, full-development execution or live D/news inference was observed in this pilot. The mock forecast is 0.5 and is never substituted into paid results.

Private response verification and sanitized public replay pass offline. [Observations/settings](leap_nba_v2_pilot/observations.json), [per-game evaluation](leap_nba_v2_pilot/per_game.json), [summary/calibration/removal scores](leap_nba_v2_pilot/summary.json), [diagnostics](leap_nba_v2_pilot/diagnostics.json), and the [content-hash manifest](leap_nba_v2_pilot/manifest.json) reproduce the results. Public replay verifies original frozen projections, request identities, assignments, mapped ratios, all seven-method scores and accounting; private verification additionally reparses captured HTTP bodies. Public arithmetic replay does not independently authenticate those private bytes or recreate inference. Credentials, auth headers and original raw bodies remain outside Git.

The [preservation audit](leap_nba_v2_pilot_preservation.json) confirms **10,792 original files byte-identical**, including all **7,608 historical data files**, direct/v1 prompts/code/results/caches, Phase 1 assets/results/captures and the unchanged 50/150 split. No reserved-game inference or analysis, new evidence collection, Brave search or historical rebuild occurred. README only adds Phase 2 links.

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/compare_leap_v2.py --replay reports/leap_nba_v2_pilot
# Original private captures required; no credential/network needed:
.venv/bin/python scripts/leap_v2_forecast.py --verify captures/leap_nba_v2_phase2/paid
```

The [run guide](../experiments/leap_nba_v2_phase2/README.md) includes no-cost planning, mock commands and separately gated future development execution. No additional paid inference is needed to reproduce saved results.

The integration succeeds, and two v1 strength-direction concerns disappear under the fixed diagnostic, but direct remains better on these five games. These development-informed historical results are vulnerable to model memory, selection/diagnostic feedback, unverified historical source/schedule versions, correlated evidence and uncalibrated player-impact judgments. Thirteen group calls versus five direct calls also make this an unequal inference-budget comparison. Preserve both variants and treat injury sufficiency/magnitude and residual dependence as unresolved methodological issues. Any expansion needs separate authorization; prospective frozen packets remain the eventual primary out-of-sample test. No further historical run or method revision was performed.
