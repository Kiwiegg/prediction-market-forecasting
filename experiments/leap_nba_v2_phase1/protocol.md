# LEAP-NBA v2 Phase 1: frozen synthetic elicitation protocol

This is an outcome-free methodological experiment. No historical forecasts, game outcome evaluation, historical sample/split changes, new evidence collection, or v1 changes are authorized. Synthetic validation is not a historical forecasting result or evidence of calibrated likelihood ratios.

## Objectives and hypotheses

Compare direct numeric LR elicitation with direction/strength elicitation and deterministic mapping, holding anonymous evidence and the underlying model fixed. H1: qualitative assessment has better unambiguous statistical-dominance directionality. H2: it has better team-swap/reciprocity and irrelevant-formatting stability. These hypotheses can fail; publish actual outputs and all missing/failed requests. No prompt or mapping revision after observing this phase's outputs. This is a blinded numeric comparator, not a reproduction of unblinded LEAP v1.

## Blinding and evidence isolation

The projection takes an in-memory packet in the existing schema. A fixed seed `leap-nba-v2-phase1-blinding-2026-10-22`, opaque game identifier and SHA-256 parity assign the original two sides to X/Y, independently of outcomes, prices, evidence quality or team identity. Assignment lineage stays outside model context. Copy only regular-season W/L, recent results, scoring counts/totals/average differential and optional per-game margins with every game ID removed. No names, IDs, home/away designation/splits, dates, venue, schedule, injuries, news, target outcomes/prices or audit/evaluation metadata enter the projection. Preserve omitted statistical features/reason codes and source reconstruction/point-in-time qualifiers; reject unknown free-text qualifiers rather than leak identities. Do not fill absent fields. Identifying patterns may remain in statistics; this is field-level blinding, not a proof against reidentification.

The executable Phase 1 runner accepts **only the frozen synthetic cases**, not historical packet paths, game IDs or split subsets. Projection tests use artificial in-memory packets, never repository historical data. Existing full-suite tests may perform their established development-only checks; Phase 1 inference/replay/scoring never opens any `data/` or historical evaluation/capture files. Existing data and v1 fingerprints must remain unchanged.

## Fixed fixtures

`generate_cases.py` deterministically creates `cases.json`: ten fictional NBA-scale families, each base, X/Y-swapped and formatting/field-order varied, totaling **30 cases**. Families: clear X, modest X, clear Y, identical populated statistics, conflicting record/differential indicators, missing scoring, small samples, extreme consistent differences, all features unavailable, and zero completed games. Season W/L, recent windows and scoring totals must reconcile. No actual game is copied. No simulated outcomes exist.

Expected properties and category labels remain audit-only and are not sent to the model. Unambiguous dominance comprises five families (clear X/modest X/clear Y/small sample/extreme), **15 cases**; all included win rates, differentials and recent form favor the specified side. Small samples still have direction but uncertain strength. Three populated-identical cases should be neutral. Six unavailable/zero-game cases should abstain rather than make confident neutral/directional judgments. Conflicting and missing-scoring cases have no prescribed direction/magnitude; report their behavior. Zero-game/wholly absent statistics are not populated-identical evidence.

Case run order is SHA256(fixed synthetic seed|run-order|case_id). Methods are interleaved per case, alternating numeric-first and qualitative-first by run-order position. Both get the **identical input string** for a case. Base/swap use canonical compact JSON; formatting variants reverse dictionary field order and use indentation without changing values. Metadata, IDs, expectations and the paired case are never visible in a request. Identical base/swap payloads reuse the exact-request cache; report reuse and do not call reused responses independent samples. No replicate calls are needed: 60 case/method slots, <=60 distinct requests (expected 54).

## Elicitation, schemas and mapping

Use the two separately versioned prompts in `prompts/`, and the two strict JSON schemas here. Numeric output has finite LR in [0.05,20] plus adequate/limited/insufficient; invalid/extreme-out-of-bounds outputs fail without clipping. Qualitative output has exactly favored_side (X/Y/neither), strength (neutral/slight/moderate/strong/very_strong), and sufficiency (adequate/limited/insufficient). Neither requires neutral; X/Y requires nonneutral. Insufficient must be neither+neutral for qualitative, or LR=1 placeholder for numeric. Such coherent abstention is a valid structured response, but its usable LR and direction are **null**, never neutral LR=1. Contradictory combinations fail without repair. No long explanations or additional output fields.

Fixed magnitudes: neutral1, slight1.25, moderate1.75, strong2.5, very_strong4. Favoring X maps to magnitude; Y maps to reciprocal; neither with adequate/limited maps to1. These are **heuristic mapped ratios, not calibrated likelihood ratios**. The qualitative model does not see the numeric mapping. Numeric direction uses sign(log LR), neutral tolerance abs(log LR)<=1e-9. No final probability aggregation, forecasting scores, win outcomes, or market comparison is performed.

## Fixed metrics and thresholds

Report strict JSON-object parsing rate among returned texts and all planned slots; coherent schema-valid rates separately; usable LR versus valid abstention versus malformed/provider/missing response counts. Extra fields/claims are unsupported output. Preserve raw invalid responses privately and their hashes/error categories publicly. Rates must show both full planned denominators and observed denominators; incomplete coverage is not silently dropped.

For each method:

- Dominance: correct favored side on the 15 prespecified cases; **>=90%** (at least14/15). An abstention on a dominance case is not directionally correct.
- Team swaps: eight base/swap pairs with potentially usable evidence; **>=90%** (8/8 at this sample size). X must reverse to Y, Y to X, neither remain neither. Abstention/incomplete pairs are not successes; the two uninformative families' abstention consistency is reported separately.
- Reciprocity: on the same eight planned pairs report usable-pair count, abs(log LR_base+log LR_swap) distribution, exact reciprocity <=1e-9 and a prespecified engineering tolerance <=log(1.25). No additional pass threshold or magnitude tuning.
- Identical populated statistics: **all three** must produce usable neutral assessments, not abstentions.
- Formatting: ten base/format pairs, report exact parsed-output equality, direction/sufficiency equality and magnitude stability <=log(1.25). Coherent abstention on both variants counts as stable abstention; missing pairs remain missing.
- Missingness: six uninformative cases must produce coherent insufficient abstentions. Missing-scoring/small-sample/conflict cases get descriptive direction, magnitude and sufficiency counts, not invented numeric ground truth.
- Unsupported evidence: **zero observable invented/unsupported output fields or claims**, and zero usable/confident assessments on wholly unavailable/zero-game evidence. The restricted output schema cannot reveal unspoken fabricated reasoning; passing this observable check does not prove no internal unsupported assumptions.

The four proposed criteria are engineering diagnostics, not statistical validity or LR calibration. Any incomplete required coverage yields `incomplete`, not pass or empirical failure inferred from unattempted cases. To recommend proceeding to a **separately authorized** five-game qualitative pilot, require complete paired-arm coverage and every qualitative criterion (including coherent abstention behavior) to pass. Numeric thresholds need not pass; comparative success must be assessed rather than assumed. No historical pilot is authorized in Phase 1.

## Model, costs and execution

Anthropic `claude-haiku-4-5-20251001`, temperature0, max128 output tokens, structured JSON, no tools/search. Configuration is here, independent of unchanged v1 settings. Reserve payload byte count +4096 as input-token bound and128 output tokens. Conservative Phase 1 estimates use **$2/$10 per million**, twice the [documented Haiku4.5 base $1/$5 rates](https://platform.claude.com/docs/en/about-claude/pricing) checked 2026-10-22. Prices are estimates, not invoices. If actual usage is absent retain its reservation estimate.

Hard ceilings: **120 requests / $1.00**, zero automatic retries; execute only this fixed synthetic plan once if credentials and all live flags are present. Check the full unique-request reservation sum before calls; do not remove cases to fit. If it does not fit, make no calls and report incomplete budget feasibility. Reserve before each new request. Stop after the **first HTTP403**, retaining all later slots as explicitly not attempted. Other failures remain terminal, without retry. Reuse immutable cache success/failure; uncertain prior attempts cannot be resent from a new run directory. Keep raw responses/credentials outside Git. Each cache identity binds exact wire payload, evidence bytes, prompt/schema/model/generation. Freeze run manifest first, terminal records and source hashes, then seal completion. Verification/replay is read-only and network-free.

Commit fixtures, generator, protocol, prompts, mapping, schemas, config, registered content hashes and tested implementation before paid inference. Full local suite and mock run must pass first. Report actual paid observations separately from mocks. Publish sanitized observations, source/raw-response hashes, usage/latency/errors, coverage-aware metrics, prespecified threshold statuses and honest limitations in `reports/leap_nba_v2_phase1.md`. Never modify v1 or the historical split/evidence to improve Phase 1 results.
