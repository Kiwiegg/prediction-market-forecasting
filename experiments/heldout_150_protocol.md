# One-time historical held-out evaluation

This protocol, its [machine-readable rules](heldout_150_rules.json), the exact identity/request/evidence plan and tested execution/evaluation code must be committed **before paid inference**. The final report references that commit. Forecasting is frozen at the existing direct/v1 definitions and v2 pre-inference commit `8520406`; development diagnostics do not change prompts, models, settings, schema, prior, likelihood mapping, groups or alpha.

## Question and fixed sample

The **primary comparison** is LEAP-NBA v2 raw minus direct LLM **mean paired Brier score**. Lower is better. The primary cohort requires both complete forecasts and a finalized verified home-win outcome; neither a v1 forecast nor a market quote is required. Secondary measures are natural-log loss, calibration and coverage. Secondary methods are v2 conservative, v1 raw/conservative, the original Kalshi preferred midpoint and constant 50%.

Use all and only the existing **150 evaluation IDs** in `nba_2025_26_split.json`, in the pre-existing hash run order. The original monthly 50/150 split and all 200 evidence packets remain unchanged. `heldout_150_plan.json` freezes each evaluation ID, parent hash, request identities, model settings, source availability and frozen dependency hashes. These values depend on identity and existing evidence, never held-out outcomes or prices. No alternate sample, backfill, additional source, prompt tuning, mapping fitting or model selection is permitted after the evaluation starts.

All methods receive the same hash-verified frozen parent snapshot via the shared loader. Direct receives the original full packet; v1/v2 receive exactly their original deterministic projections. V2's existing development runner intentionally does not support held-out scope. The small held-out wrapper adds explicit scope permission and global execution controls; it calls the unchanged group/request/cache/parser/aggregation functions without changing evidence or wire identity. This is scope plumbing, not a new elicitation method. The original direct/v1 planners are invoked with `subset=evaluation`, `limit=150`, and `authorize_evaluation=True`.

## Inference and stopping

All methods use their original Claude Haiku 4.5 model, temperature0 and fixed generation settings. No outcomes, prices, evaluation-only files, source audits, tools, browsing or independent retrieval enter inference. Hashing original files for integrity is not a semantic outcome join. No held-out outcomes or market prices are parsed for analysis until **all method runs are sealed**, including any partial stop.

Execution follows the existing evaluation game order, then **direct → v2 A/B/C/D → v1 A/B/C/D per game**. This fixed order is independent of outcomes, prices, source availability and responses; source-missing groups skip under unchanged rules. A single shared budget/authorization applies to the entire experiment: **at most 1,200 new Anthropic requests and $40 cumulative conservative pre-call reservations**, also accounting for known response cost. All original matching cache records are verified and reused, including terminal failures. No successful call is repeated. An uncertain original attempt blocks a new paid run. New claim markers precede network calls; no automatic retry or new cache directory may bypass them.

Stop new paid inference globally on the **first HTTP403** or other access-denial response. Conservatively stop on HTTP401/407/451 and explicit top-level provider authentication/permission or HTML denial errors too. A non-access transport/provider/schema failure is preserved and not retried; other planned requests may continue. A budget stop happens before the next reservation/request. Keyboard interruption seals completed records, marks claimed/unknown requests separately and leaves unattempted requests missing. A killed process can be sealed explicitly offline; unknown claims are never resent. A single immutable authorization registry prevents relaunch in another directory. Completed bundles are never overwritten.

Method-specific cached records keep their native status schemas. A global-stop slot uses native `not_attempted_budget` with an explicit execution-stop reason; this serialization does **not** mean a budget was exhausted. The audit categorizes actual stop reasons separately. Legitimate source absence stays `skipped_missing`/LR1; provider failure, invalid/insufficient required assessment and unknown/unattempted requests make the final group method forecast missing. Failed or insufficient observations never silently become neutral LRs. No-request statuses incur no cost. Claimed requests without usage retain their conservative reserve, not zero cost.

## Locked evaluation and intersections

Once inference is sealed, join evaluation outcomes/quotes for the 150 selected IDs using the existing finalized/home-mapping and quote validator. Preserve the **20-minute candle-end** rule: valid two-sided YES prices `0<bid<=ask<1`, candle end at/before cutoff, lag<=1200 seconds, midpoint=(bid+ask)/2. Quote end does not establish quote-update age. Missing quotes are never replaced by trades.

Publish three explicitly named cohorts, each with exact IDs and every exclusion:

1. **Primary pair:** v2 raw and direct, regardless of v1 or market availability.
2. **A, five methods:** direct, v2 raw/conservative, Kalshi and constant 50% on the identical complete intersection.
3. **B, seven methods:** A plus v1 raw/conservative on their identical complete intersection.

Every row stays in the 150-game export. Missing outcomes, quotes, failed and unattempted forecasts have separate reasons. Never compare differently sized aggregates as matched estimates. Retain each method's overall coverage and the inferential success/source-skip/failure breakdown. Additional per-game pairwise differences may exist only when both scores are available and must not be confused with A/B aggregate cohorts.

Brier is primary. Natural-log loss uses the existing epsilon=1e-15 clipping only for log loss. Calibration uses the existing ten equal-width buckets with counts, mean probability and observed frequency, retaining empty buckets. Mean home probability, confidence, extreme frequency (p<=0.1 or p>=0.9) and classification accuracy (home iff p>=0.5) are secondary diagnostics. Preserve stored probabilities without rounding; known reciprocal-LR floating-point boundary artifacts remain documented.

Use **10,000 paired game-row bootstrap resamples, seed 20261023**, jointly preserving methods within each resampled row, and the same indices across pairs within a cohort. Report mean Brier differences and 95% percentile intervals using linear (B−1)q endpoint interpolation. Primary interval is v2 raw minus direct on the primary pair. Secondary A comparisons are v2 raw/conservative minus direct/Kalshi and direct minus Kalshi; B compares v2 against corresponding v1 and v1 against direct. Empty intersections produce null metrics/intervals, not fabricated scores. No significance-based winner selection or adjustment of methods follows. These are descriptive intervals: repeated teams/games and source effects violate simple independent sampling assumptions, and historical memory remains possible.

## Prespecified diagnostics and interpretation

Reuse the original strength-direction diagnostic: a team is weaker only if both season win fraction and average point differential are strictly lower. Compare v1/v2 on common successful, statistically assessable strength observations. List missing/zero-game, tied/discordant and inference exclusions separately. Report group LR/log-LR distributions, home/away/neutral/category/sufficiency counts, missingness, injury submission states, A/B reinforcement and offline group removal. No output is flipped and no group is removed based on diagnosis. Uncalibrated mapped ratios and dependent groups remain methodological limitations.

Compare already published development A n50/B n40 against the corresponding held-out cohorts, with different denominators and game sets explicit. This is a locked historical hold-out with respect to this repository's development cycle, **not** a truly prospective or contamination-free test. The model may remember completed games; historical source issue clocks and reconstructed schedules are not universally publication/as-of verified. Evidence groups are correlated. Direct uses one call while each group method can use up to four; v1/v2 token counts and frozen cost-rate assumptions differ. Report unequal inference resources rather than interpreting all methods as equally funded.

## Reproduction and audit

Save raw HTTP captures, immutable requests/claims/reservations, model responses and detailed errors outside Git. Commit only structured sanitized observations, response hashes, clocks, usage, settings, aggregate resources, scores and reproducibility metadata. No keys, auth headers or private raw bodies belong in Git. Distinguish provider-reported tokens from configured-rate dollar estimates, unknown-usage reserves from known-usage costs, prior-cache use from new calls, summed latency from wall-clock time, and actual success from mocks.

Run all tests and an offline mock before paid inference, private-cache verification after sealing, sanitized public replay, original-file/hash preservation checks and a clean-checkout test/replay without `.env` or private captures. The evaluator refuses an unsealed run. Its public replay validates frozen request/evidence identities and deterministic derived results; private verification additionally checks raw response bytes and parsers. Public hashes are consistency checks, not independent proof of provider authenticity.

```sh
# No network; requires explicit permission to load reserved evidence.
.venv/bin/python scripts/heldout_forecast.py --authorize-evaluation --freeze-plan
.venv/bin/python -m unittest discover -s tests -q
.venv/bin/python scripts/heldout_forecast.py --authorize-evaluation --mock

# Commit frozen protocol/plan/tested code first, then save the preflight.
.venv/bin/python scripts/heldout_forecast.py --authorize-evaluation --plan --save-preflight
# ANTHROPIC_API_KEY must be available; do not echo credentials or enable tracing.
.venv/bin/python scripts/heldout_forecast.py --authorize-evaluation --live --allow-network --allow-inference

# Offline only, after global completion or partial-stop seal.
.venv/bin/python scripts/heldout_forecast.py --authorize-evaluation --verify captures/heldout_150/run
.venv/bin/python scripts/analyze_heldout.py --authorize-evaluation --run captures/heldout_150/run --output reports/heldout_150
.venv/bin/python scripts/analyze_heldout.py --authorize-evaluation --replay reports/heldout_150
```

This is a **one-time final historical evaluation**, not a new development cycle. Report all results regardless of favorability. No evaluation-driven tuning, paid retries, evidence changes or new methods are authorized by this protocol.
