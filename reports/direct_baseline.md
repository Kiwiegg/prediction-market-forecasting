# Direct-LLM probability baseline v1

The baseline sends exactly one existing frozen packet to a model and requests one JSON number, `home_win_probability`. It does not search, retrieve evidence, call tools, predict scores or request explanations. The historical sample, packet contents and 20-minute market-price rule are unchanged. This baseline is separate from news extraction.

The [frozen protocol](../experiments/direct_baseline_protocol_v1.md), [split manifest](../experiments/nba_2025_26_split.json), [prompt](../prompts/direct_home_win_v1.txt) and [configuration](../examples/direct_forecast_config.json) were committed before inference. Exactly **50 development / 150 reserved evaluation** games are assigned proportionally by month. Largest-remainder quotas break ties by month; SHA-256 of a fixed seed, assignment purpose and game ID ranks games within each month. A separate deterministic game-ID ranking fixes run order. The first five development IDs define the pilot, independently of labels, prices, features and source availability.

Historical results are **exploratory**. Models may recognize completed games despite instructions; this code cannot establish absence of memorization. Source/schedule version verification flags remain unchanged. Prospective captures are the eventual primary out-of-sample evaluation. Do not use the evaluation subset to choose prompts/models or settings.

## Commands and authorization

Run from the repository root with the existing virtual environment. No new dependencies are needed. `--plan` is the default and makes no network calls or output directories.

```sh
# Reproduce/check the existing immutable split; never overwrites a changed file.
.venv/bin/python scripts/forecast_split.py --check

# Offline cost plan and mock plumbing run, development only.
.venv/bin/python scripts/direct_forecast.py --plan
.venv/bin/python scripts/direct_forecast.py --mock \
  --output captures/direct_baseline_v1/mock_development_five
.venv/bin/python scripts/direct_forecast.py --verify \
  captures/direct_baseline_v1/mock_development_five

# Real paid five-game development run, only with operator authorization.
# Set ANTHROPIC_API_KEY in this process; credential values never enter JSON.
.venv/bin/python scripts/direct_forecast.py --live --allow-network --allow-inference \
  --subset development --limit 5 --max-paid-calls 5 --max-estimated-cost-usd 0.25 \
  --output captures/direct_baseline_v1/paid_development_five

# Score ONLY after inference is complete. This output is evaluation-only.
.venv/bin/python scripts/evaluate_forecasts.py \
  --forecast-run captures/direct_baseline_v1/paid_development_five \
  --output captures/direct_baseline_v1/paid_development_five_scores
```

`.env` is Git-ignored but is not loaded automatically. Export the key into the invoking process or load your trusted shell-compatible local `.env` with shell tracing disabled. Do not print credential values. Raw provider bodies, request contexts, caches and experiments belong under the Git-ignored `captures/` directory. Commit sanitized development summaries separately.

The following commands are documented for **future explicit operator authorization**, not automatically executed as part of this implementation. Plan costs first; the shown ceilings are upper limits, not prepaid spend. The same shared cache avoids paying twice for the pilot when completing development.

```sh
# Full development subset, a new experiment directory.
.venv/bin/python scripts/direct_forecast.py --subset development --limit 50 --plan
.venv/bin/python scripts/direct_forecast.py --live --allow-network --allow-inference \
  --subset development --limit 50 --max-paid-calls 50 --max-estimated-cost-usd 5.00 \
  --output captures/direct_baseline_v1/development_all

# Reserved evaluation is separately gated, including offline verification/scoring.
# Do not run until the comparison protocol and future methods are frozen.
.venv/bin/python scripts/direct_forecast.py --live --allow-network --allow-inference \
  --subset evaluation --authorize-evaluation --limit 150 \
  --max-paid-calls 150 --max-estimated-cost-usd 15.00 \
  --output captures/direct_baseline_v1/evaluation_reserved
.venv/bin/python scripts/evaluate_forecasts.py --authorize-evaluation \
  --forecast-run captures/direct_baseline_v1/evaluation_reserved \
  --output captures/direct_baseline_v1/evaluation_reserved_scores
```

## Input, provider and immutable records

`load_evidence` delegates exclusively to `shared_evidence.load_game_snapshot`. Its returned object, including its content hash, is the complete user-message JSON. A registered fixed system prompt and JSON response schema are the only additional context. Source/audit/evaluation files and cross-game messages are absent. Direct and future methods can use the same neutral loader and hash; no LEAP method is implemented.

The default uses Anthropic `claude-haiku-4-5-20251001`, temperature **0**, **128 output tokens**, and documented [structured JSON output](https://platform.claude.com/docs/en/build-with-claude/structured-outputs). The wire schema excludes unsupported numeric range constraints; local validation enforces [0,1]. No tools, thinking settings or agent loop are provided. [Temperature zero is not guaranteed deterministic](https://platform.claude.com/docs/en/api/messages/create); caching makes the saved experiment reproducible. Changing the prompt requires a new registered version/hash; no prompts were optimized against held-out games.

Provider/model and fixed generation settings are explicit JSON configuration. A credential-free HTTPS `json_gateway` endpoint can alternatively accept the same `model/system/messages/max_tokens/temperature/output_config` request and return `{model, stop_reason: "end_turn", response: {home_win_probability: NUMBER}, usage: {input_tokens, output_tokens}}`. Gateway inference is tested with mocks only. Mock mode is labeled `mock_constant`, returns 0.5 for plumbing tests and never represents an LLM forecast.

Each exact provider/endpoint/prompt/model/settings/evidence request gets a SHA-256 cache key. The shared `CapturedHTTP` transport preserves auth-free request JSON, compressed raw response bytes, source hashes, request/retrieval clocks, status and latency. Per-game immutable records add parsed probability, provider/returned model, prompt version/hash, generation settings, usage, estimated cost and errors. Strict validation rejects malformed/fenced/duplicate-key JSON, extra keys, strings, booleans, NaN/infinity, values outside [0,1], truncated replies, tool output and invalid usage. Failed forecasts remain missing; there is no recovery inference or probability imputation.

The cache claims an attempt on disk **before** sending it. A crash with uncertain delivery is never automatically resent. Successful and failed cache records are reused across experiment directories. A run-level exclusive lock prevents concurrent writes. An interrupted lock requires operator investigation; do not delete claim markers or change cache directories to force a paid retry without authorization. No automatic retry occurs for provider errors or malformed replies.

`run.json` pins the split, selected IDs, packet/request hashes, settings and budgets before the first inference. Cost reservations precede requests; exhausted budgets create explicit `not_attempted_budget` records. An immutable `completion.json` seals all run/record/reservation hashes and counts. The evaluator refuses unsealed runs. Repeating a completed experiment verifies and returns its original records without overwriting them; changing its identity is refused. Use a new directory for a new experiment, keeping the shared cache.

```sh
# Read-only replay: verify original request bytes, current frozen packet binding,
# raw response hashes and parsed probabilities, without credentials/network.
.venv/bin/python scripts/direct_forecast.py --verify \
  captures/direct_baseline_v1/paid_development_five
# A securely copied cache can be relocated with --cache /path/to/copied_cache.
.venv/bin/python -m unittest discover -s tests -q
```

The cache must accompany an experiment for full raw-response replay; sealed forecast records alone suffice for deterministic scoring. Content hashes detect changes relative to saved manifests, not independent notarization. New live model calls may differ; reproducing saved results does not require them.

## Cost accounting and evaluation

The default **conservative estimates** are $3/M input and $15/M output tokens, above the model's documented [base pricing](https://platform.claude.com/docs/en/about-claude/pricing) at implementation time. Reserve serialized request UTF-8 bytes plus 4,096 overhead tokens, and the full output-token maximum, before every new request. The five-game pilot reservation is **$0.196896**, within the authorized **$0.25 / five-call** ceiling. Report actual provider token counts separately from estimates. External invoices are not verified. Cached responses retain their original usage/cost estimates; their reuse creates no new provider charge.

Only `evaluate_forecasts.py` reads `evaluation.csv`, after verifying the sealed experiment. It filters to its fixed selected IDs before parsing labels/prices and does not summarize the reserved remainder. Evaluation uses finalized 0/1 home-market outcomes with verified home mapping. Missing labels or forecasts remain missing. Preferred quote checks retain the exported midpoint, bid/ask validity, cutoff identity, candle end <= cutoff and lag <= **1,200 seconds**. They never substitute trades or treat candle end as actual quote-update time.

Report un-clipped Brier loss `(p-y)^2` and natural-log loss with probability clipped to `[1e-15, 1-1e-15]` for log loss only. Predictions 0 and 1 remain valid. Calibration uses ten [0.0,0.1), …, [0.9,1.0] buckets, including counts and empty buckets. The evaluator emits `summary.json` and `per_game.csv` with outcomes, prices, eligibility, missingness, scores and direct-minus-market differences; these files are **evaluation-only**, never model context.

Forecast-available scores compare direct and constant 0.5 on the same labeled successful forecasts. The market comparison uses the intersection of valid forecasts, outcomes and preferred quotes for **all three methods**. Every paired metric/calibration table shares exactly those IDs and N. Coverage, failures, budget skips and excluded markets/outcomes remain explicit; do not compare metrics from different denominators. Mock scoring requires `--allow-mock` and is labeled accordingly.
