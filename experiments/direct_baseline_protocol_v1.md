# Direct baseline protocol v1

Freeze this protocol, `nba_2025_26_split.json`, `prompts/direct_home_win_v1.txt` and `examples/direct_forecast_config.json` before forecasting or joining outcomes. Do not use the reserved evaluation subset to select prompts, models, settings or exclusions.

The unchanged 200-game sample is split into exactly 50 development and 150 evaluation games with proportional monthly largest-remainder quotas. Within each month, rank SHA-256 of the fixed split seed, assignment purpose and game ID. A separate seed/purpose/game-ID ranking fixes run order; the first five development games are the paid pilot. No labels, market prices, statistical features or evidence availability enter assignment or pilot selection.

Use one complete, hash-verified frozen packet per model request and no other game context. The fixed v1 prompt requests only `home_win_probability`. Default provider/model: Anthropic `claude-haiku-4-5-20251001`, temperature 0, 128 output tokens, structured JSON; validate finite probability in [0,1] locally. No search, tools, reasoning trace or score prediction. Malformed responses fail without retries or imputation. Cache exact requests and preserve raw replies and immutable result records.

The current operator authorization permits at most five paid development forecasts, at most $0.25 estimated cost, no paid retries. Complete development runs and all evaluation runs require future explicit operator invocation; evaluation additionally requires a dedicated authorization flag. No automatic all-sample run.

After an experiment is sealed, a separate evaluator may join only its selected IDs to outcomes and the existing preferred quote midpoint. Score Brier loss and natural-log loss clipped at epsilon 1e-15 for log loss only. Compare direct, Kalshi and constant 0.5 on exactly the same eligible paired games; retain exclusions, sample sizes, failures, ten probability buckets and per-game evaluation-only exports. Keep the existing 20-minute candle-end rule; do not interpret it as quote-refresh age.

All historical findings are exploratory: completed games may have appeared in model training or other knowledge, and source/schedule versions remain unverified. Prompt instructions cannot eliminate memorization. Prospective frozen captures remain the eventual primary out-of-sample evaluation. Do not tune this protocol using evaluation outcomes.
