# Direct probability baseline implementation and validation

**Implemented and validated five development forecasts; 150 evaluation games remain reserved, unforecast and unscored.** All historical results are exploratory because completed games may be in model knowledge and historical source/schedule versions remain unverified. These five observations establish working experiment plumbing, not predictive skill. Prospective captures remain the eventual primary out-of-sample evaluation.

## Frozen design and implementation

The unchanged sample has exactly **50 development / 150 evaluation games**, stratified across all seven months using largest-remainder quotas and fixed seed/game-ID hashing. A separate deterministic ID order selected the first five development games; no outcome, price or evidence-availability filter was used. [The split and protocol](../experiments/direct_baseline_protocol_v1.md), fixed prompt and configuration were committed in **`f1e7258` before forecasts or scoring**. The tested runner/evaluator were committed as **`b4e0fe4` before paid calls**. Neither prompt nor model settings were tuned after results.

The runner loads one complete packet exclusively through the shared frozen snapshot loader. Its model context contains that packet plus the registered system prompt and response schema. No label/price exports, source audits, additional games, search, tools or retrieval are available. Direct and future methods can load the identical evidence object/hash. No LEAP implementation, Bayesian aggregation, trading, enrichment or historical dataset version was added.

The Anthropic adapter reuses the existing auth-free captured HTTP transport. It requests structured JSON from **`claude-haiku-4-5-20251001`**, temperature **0**, maximum **128 output tokens**. Responses require exactly one finite numeric `home_win_probability` in [0,1]; malformed/fenced JSON, additional fields, unexpected tools and invalid usage fail without retries or imputation. Provider/model remain configurable; the optional gateway contract has only been tested with mocks.

Experiment manifests pin the split, packet/request hashes, prompt, settings and budgets before inference. Request claims prevent automatic resend after uncertain delivery. A shared cache retains successful and failed attempts; complete runs and per-game records are immutable. The separate evaluator refuses unsealed runs and requires an additional authorization flag for the reserved subset. Default operation is a no-network cost plan; no automatic all-sample execution exists.

## Actual five-game paid pilot

Both credentials and provider responses remain private under ignored paths. The Anthropic key was accessible through the ignored local `.env`, loaded only into the invocation process without displaying it. No Brave request or evidence retrieval occurred during forecasting.

* Request window: **2026-10-21 01:27:11.310781–01:27:21.163160 UTC**; run sealed at **01:27:21.174354 UTC**.
* Exactly **5 paid requests**, all HTTP 200, all **5 valid forecasts**, **0 failed responses**, **0 budget skips**, **0 retries**.
* Provider-reported usage: **12,766 input / 75 output tokens**. Total provider latency: **9.744020 seconds**.
* Pre-call conservative reservation: **$0.196896**; reported-token cost estimate: **$0.039423**, both below the authorized **$0.25**. Estimates use configured $3/M input and $15/M output rates, not an external invoice. Cache/tool usage was zero.
* Prompt: `direct_home_win_v1`; SHA-256 `e073236a57b397456d14ee003838162019af97f36d905a4a1b77cb57b176174c`.
* [Sanitized request/result metadata](direct_baseline_v1/paid_development_validation.json) records the five probabilities, evidence/request/response hashes, fixed settings, clocks, usage, latency and errors. Original raw replies and request contexts are preserved locally in the shared ignored cache, not committed.

Only after inference sealed, the evaluator joined the five selected development IDs to labels and exported preferred market prices. All five had eligible labels and valid preferred quotes under the **20-minute candle-end** rule; actual quote age remains unknown. No trades substituted for quotes. Scores, differences and all ten calibration buckets are in the [evaluation-only JSON](direct_baseline_v1/development_scores.json) and [per-game CSV](direct_baseline_v1/development_scores.csv).

| Method, identical paired games | N | Brier score | Natural-log loss |
| --- | ---: | ---: | ---: |
| Direct LLM | 5 | 0.219220 | 0.622953 |
| Kalshi preferred midpoint | 5 | 0.251415 | 0.685751 |
| Constant 50% | 5 | 0.250000 | 0.693147 |

Mean direct-minus-market differences: **−0.032195 Brier / −0.062798 log loss**. These small-sample retrospective numbers do not substantiate superiority, calibration or profitability. Brier uses original probabilities; log loss alone clips to `[1e-15, 1-1e-15]`. Future comparisons must use the same eligible paired IDs and preserve missingness/sample sizes. No reserved-subset model results were computed or exposed.

## Offline verification and limits

**96 tests pass.** Tests cover outcome-blind split reproducibility, exact packet-only input, shared consumer hashes, strict JSON/probability boundaries, provider failures, raw-response retention, cross-experiment caching, uncertain-attempt refusal, immutable outputs, pre-call budgets, scoring arithmetic, clipping, calibration bins, quote boundaries and missing data. Synthetic held-out rows test authorization/label filtering without evaluating real reserved forecasts. A read-only verification guard was added so missing cache records cause failure instead of being regenerated; custom endpoints require explicit gateway selection. Neither fix changes the frozen model request or probabilities.

The offline five-game mock run succeeded without credentials/network; its constant outputs are plumbing fixtures, not LLM results. The paid run reproduces its probabilities from the saved raw replies and exact frozen input hashes without network or credentials. Existing prospective saved-capture replay passes. All **7,608 pre-existing historical files** have identical before/after SHA-256 fingerprints. Forecasting/evaluation outputs are outside `data/`.

Remaining work/limitations: the full 50-game development run and all 150 evaluation forecasts are **not run**; the current five-game sample is insufficient for performance conclusions; low temperature does not guarantee identical fresh API generations; cached replay does. The gateway adapter is mock-tested only. Copies of the private cache are needed for raw-response replay elsewhere. Publisher/version uncertainty and possible historical memorization persist. Do not use reserved outcomes to select prompts, model settings or exclusions.

Reproduction and explicitly bounded full-subset commands are in the [baseline guide](direct_baseline.md). The pilot can be checked offline:

```sh
.venv/bin/python scripts/forecast_split.py --check
.venv/bin/python -m unittest discover -s tests -q
.venv/bin/python scripts/direct_forecast.py --verify captures/direct_baseline_v1/mock_development_five
.venv/bin/python scripts/direct_forecast.py --verify captures/direct_baseline_v1/paid_development_five
.venv/bin/python scripts/evaluate_forecasts.py \
  --forecast-run captures/direct_baseline_v1/paid_development_five \
  --output captures/direct_baseline_v1/paid_development_five_scores
```

These replay commands reuse the ignored captures/cache from this workspace; fresh clones can reproduce the split, mock experiment and tests without credentials. Do not repeat the paid pilot with a fresh cache: the authorization of five paid forecasts has been fully used.
