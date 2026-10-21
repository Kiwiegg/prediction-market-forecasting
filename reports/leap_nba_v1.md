# LEAP-NBA v1: use and reproduction

The [frozen protocol](../experiments/leap_nba_v1_protocol.md), [group definitions](../experiments/leap_nba_v1_groups.json), [prompt](../prompts/leap_nba_lr_v1.txt), [LR schema](../experiments/leap_nba_v1_response_schema.json) and [default configuration](../examples/leap_forecast_config.json) were committed at `26500dd` before paid inference. This is a LEAP-inspired NBA adaptation. The original direct baseline and historical evidence are unchanged.

`leap_evidence.py` projects the same shared frozen packet into four isolated groups. `leap_forecast.py` elicits bounded LRs once per available group through the existing captured Anthropic HTTP transport. It caches success, failure and uncertain attempts; it never automatically retries. Empty/unavailable groups skip with LR=1 and a reason. Required group failures make both posterior variants missing. `compare_forecasts.py` is the only new module permitted to join outcomes and prices, after both experiments seal.

Raw alpha=1 and conservative alpha=0.5 share identical saved LR records. The prior is 0.5. Each group contributes alpha*log(LR), and a stable sigmoid converts total log odds to probability. Leave-one-group-out posteriors are arithmetic only. Numeric bounds [0.05,20] reject rather than clip; `insufficient` is failure, not neutrality. LR estimation is not proof of statistical calibration. Common-source and overlapping-statistic dependence remains unresolved.

## Five-game commands

Run from the repository root. Existing Python dependencies suffice. Default behavior is a no-network plan. Mock runs use LR=1 for every available group and are plumbing tests, not model evidence.

```sh
.venv/bin/python scripts/forecast_split.py --check
.venv/bin/python -m unittest discover -s tests -q
.venv/bin/python scripts/leap_forecast.py --plan
.venv/bin/python scripts/leap_forecast.py --mock \
  --output captures/leap_nba_v1/mock_development_five
.venv/bin/python scripts/leap_forecast.py --verify \
  captures/leap_nba_v1/mock_development_five

# Explicitly authorized five-development-game pilot only.
# Export ANTHROPIC_API_KEY into the process; never print it or enable tracing.
.venv/bin/python scripts/leap_forecast.py --live --allow-network --allow-inference \
  --subset development --limit 5 --max-paid-calls 20 --max-estimated-cost-usd 1.00 \
  --output captures/leap_nba_v1/paid_development_five

# Read-only reparse/reaggregation from saved responses, no credential required.
.venv/bin/python scripts/leap_forecast.py --verify \
  captures/leap_nba_v1/paid_development_five
.venv/bin/python scripts/direct_forecast.py --verify \
  captures/direct_baseline_v1/paid_development_five
.venv/bin/python scripts/compare_forecasts.py \
  --direct-run captures/direct_baseline_v1/paid_development_five \
  --leap-run captures/leap_nba_v1/paid_development_five \
  --output captures/leap_nba_v1/paid_development_comparison

# Original direct-vs-market evaluator, separate from the five-method intersection.
.venv/bin/python scripts/evaluate_forecasts.py \
  --forecast-run captures/direct_baseline_v1/paid_development_five \
  --output captures/direct_baseline_v1/paid_development_five_scores
```

The pilot uses exactly 401810544, 401810485, 401810279, 401836746 and 401809808, in that order. Its no-cost plan requires 13 available-group requests, reserving at most $0.392790 at configured conservative $3/$15 per million tokens. Actual reported-token estimates are distinct from reservations and invoices. Both variants cost the same 13 observations; comparison and removal diagnostics make no provider calls. Prices are assumptions in the committed configuration, not fetched billing information.

`.env` is ignored and is not automatically executed or loaded by the CLI. Supply an exported credential to the invoking process. Provider requests, replies, attempt markers and experiments stay in ignored `captures/`. No keys or auth headers are serialized. Preserve the original private cache to reproduce extraction; public sanitized summaries alone cannot reproduce private HTTP bodies. Securely copied caches can be relocated with `--cache`. Read-only verification cannot repair a missing cache or make network requests.

## Larger experiments require future operator authorization

These commands are examples only; they were not executed in this pilot. Plan first. Do not delete attempt markers or change cache directories to force a paid retry. Use a new run directory with the same shared cache for an expanded experiment; existing pilot requests will be reused. Interrupted locks require operator investigation rather than automatic resubmission.

```sh
# All 50 development games: up to 200 groups, operator-specified ceilings.
.venv/bin/python scripts/leap_forecast.py --limit 50 --plan
.venv/bin/python scripts/leap_forecast.py --live --allow-network --allow-inference \
  --limit 50 --max-paid-calls 200 --max-estimated-cost-usd 10 \
  --output captures/leap_nba_v1/development_all

# Reserved 150: separately authorized later; never run as part of this task.
.venv/bin/python scripts/leap_forecast.py --live --allow-network --allow-inference \
  --subset evaluation --authorize-evaluation --limit 150 \
  --max-paid-calls 600 --max-estimated-cost-usd 30 \
  --output captures/leap_nba_v1/evaluation_reserved
.venv/bin/python scripts/compare_forecasts.py --authorize-evaluation \
  --direct-run captures/direct_baseline_v1/evaluation_reserved \
  --leap-run captures/leap_nba_v1/evaluation_reserved \
  --output captures/leap_nba_v1/evaluation_reserved_comparison
```

The provider/model is configurable in an explicitly supplied config, while v1 prompt and generation settings remain frozen. An explicit HTTPS `json_gateway` can accept the same Messages-shaped payload and return `{model,stop_reason:"end_turn",response:{likelihood_ratio,evidence_sufficiency},usage:{input_tokens,output_tokens}}`. This adapter path is tested offline; only Anthropic is authorized for the pilot. Real direct/LEAP comparisons require the same underlying model. Model changes define a separate experiment directory and must not be selected against reserved outcomes.

## Audit outputs and interpretation

Each `run.json` pins game IDs, split, source packet hash, isolated group hash, exact request hash, settings, asset hashes and budgets before calls. `forecasts/<game>.json` includes immutable group records, raw/cost/timing references, both posteriors, group log-LRs, weighted contributions and removal diagnostics. `completion.json` seals files, coverage, usage, reservation ledger and costs. Cache identity includes the parent packet hash, even if the changed parent field is outside the isolated group's own projection. This prevents silently reusing an observation against a different frozen snapshot.

Comparison `summary.json` reports identical eligible game IDs, five-method Brier/log loss, ten-bin calibration with counts, paired score differences, missingness and resources. `per_game.json` preserves group statuses/LRs, errors, evidence/request hashes, contributions and per-game scores/differences as **evaluation-only** information. Removal scores use the same full-method intersection, avoiding denominator changes. Original direct-only results can use a larger intersection if LEAP fails; they are not interchangeable with the shared comparison.

The [pilot report](leap_nba_v1_pilot.md) distinguishes paid observations from mock tests. Historical source and schedule flags remain unverified, official reports cover a bounded retrieval scope, unlisted players are never inferred healthy, and no historical news is backfilled. Five completed games cannot establish accuracy or calibration gains. No trading or new evidence collection is implemented.
