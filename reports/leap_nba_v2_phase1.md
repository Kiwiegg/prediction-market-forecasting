# LEAP-NBA v2 Phase 1 — synthetic elicitation validation

The single authorized paid batch completed on **2026-10-22**, with **54 successful Anthropic requests**, no failures or retries, and **$0.090438 conservative estimated cost**. Qualitative elicitation passed the prespecified engineering criteria. Numeric elicitation matched its dominance directionality but failed populated-identical neutrality and the swap threshold. This supports a separately authorized five-game v2 pilot; it does not establish forecasting accuracy or calibrated likelihood ratios.

## Frozen design and execution

The [protocol, generator, cases, mapping, schemas and configuration](../experiments/leap_nba_v2_phase1/protocol.md) and [two prompts](../prompts/leap_nba_v2_phase1_qualitative_v1.txt) were committed in **`3d10364`** before inference. The tested runner/evaluator implementation was committed in **`6dc9aa5`** before inference. Registered asset SHA-256: `e6087d3663076f02da358ab0268b8236b6bb3c8b28c8444ec3fd5df15aee5b88`. Neither prompts, cases, mappings, thresholds nor generation settings changed after observing responses.

Ten fictional families each have base, swapped and field-order/format variants: clear X advantage, modest X advantage, clear Y advantage, populated-identical statistics, conflicting indicators, missing scoring, small samples, extreme consistent differences, wholly unavailable features and zero completed games. There are **30 cases × 2 methods = 60 slots**. Identical base/swap requests in three families reuse six observations, giving **27 unique requests per method**, not 60 independent observations. Both methods receive identical blinded input strings per case; expected properties and case labels stay outside model context. No historical evidence or evaluation subset enters Phase 1 inference or diagnostics.

The numeric arm is **v1-style blinded elicitation**, not a rerun of unblinded v1. Both arms use `claude-haiku-4-5-20251001`, temperature 0, max 128 output tokens, strict structured JSON and no tools/retrieval. Insufficient responses are valid abstentions with usable LR/direction **null**. Numeric placeholder 1 and qualitative neither/neutral do not silently become usable neutral estimates when sufficiency is insufficient.

Actual first request: **08:56:25.287923 UTC**; last response: **08:58:30.054367 UTC**; completion sealed at **08:58:30.065833 UTC**. All 54 responses returned HTTP 200 and passed strict JSON and schema/coherence validation. There were no invalid responses, provider errors, uncertain attempts, unattempted cases or access denials. No historical inference, Brave searches or new evidence collection occurred.

## Prespecified metrics

All planned cases were observed: 30 cases have valid structured responses in both arms, and 21 have usable LRs in both. Percentages below use the full planned denominator, including abstentions as failures for dominance/swap/neutrality where appropriate. JSON/coherence rates are 30/30 per arm both among returned slots and among planned slots.

| Criterion or diagnostic | Numeric | Qualitative |
| --- | ---: | ---: |
| Strict JSON / coherent schema | 30/30 / 30/30 | 30/30 / 30/30 |
| Usable assessments / valid abstentions | 21 / 9 | 24 / 6 |
| Dominance direction, minimum 90% | **15/15, pass** | **15/15, pass** |
| Swap direction, minimum 90% | **7/8, fail** | **8/8, pass** |
| Populated-identical evidence usable neutral, all required | **0/3, fail** | **3/3, pass** |
| Unavailable/zero-game evidence abstention, all required | **6/6, pass** | **6/6, pass** |
| Observable unsupported fields / confident uninformative assessments | **0 / 0, pass** | **0 / 0, pass** |
| Exact parsed assessment under formatting changes | 7/10 | 9/10 |
| Formatting magnitude stability or paired abstention | 8/10 | 10/10 |
| Usable LR range | 0.05–18.5 | 0.25–4.0 |
| Usable LR median | 2.8 | 1.375 |

The numeric swap failure is an **abstention on the populated-identical family**, not a preference for the wrong swapped side. Its seven usable swap pairs all reverse direction correctly. Qualitative treats that family as usable neutral. Hypothesis H1 (better dominance directionality) is **not supported**: both methods score 100%. The swap/formatting observations favor qualitative under this fixed suite, but this small dependent fixture set supports engineering diagnosis only.

Reciprocity has seven usable pairs for numeric and eight for qualitative. Numeric has exact reciprocal consistency on **2/7**, and consistency within a factor of 1.25 on **6/7**; mean absolute log-product error is **0.223119**, maximum **1.139434**. Qualitative has **8/8** exact reciprocals within numerical tolerance (maximum floating-point error `1.11e-16`). On the **same seven jointly usable pairs**, qualitative is 7/7 exact versus numeric 2/7. Both methods consistently abstain across base/swap for both uninformative families. No missing or unusable pair is silently removed from a planned denominator.

The fixed mapping constrains magnitudes to a small set: qualitative has 12 moderate, 6 strong and 3 very-strong usable assessments; 3 usable neutral assessments; and 6 neutral-placeholder abstentions. There are no slight assessments. Mean usable LR is 1.460714 for qualitative and 4.724286 for numeric, but these means depend on X/Y orientation and are not calibration statistics. Full distributions, sufficiency labels, pair diagnostics and all case-level outputs are in the [replayable observations](leap_nba_v2_phase1/observations.json) and [metrics](leap_nba_v2_phase1/metrics.json).

## Counterintuitive and inconsistent examples

| Family | Numeric observation | Qualitative observation |
| --- | --- | --- |
| Identical populated statistics (`f04`) | All three slots return insufficient with LR placeholder 1, producing no usable estimate | All three are adequate, neither/neutral, mapped LR 1 |
| Two-game samples (`f07`) | Base LR 4, swapped LR 0.08; product **0.32**, a factor **3.125** from reciprocity; both limited | Moderate in each direction, 1.75 and 0.571429; both limited |
| Modest advantage (`f02`) | Formatting alone changes LR **2.8 → 3.8**, exceeding the fixed 1.25 factor tolerance | Moderate/X/adequate in both, LR 1.75 |
| Conflicting record/differential (`f05`) | Formatting changes LR **0.35 → 0.15** and adequate → limited | Y/moderate remains LR 0.571429, but adequate → limited; exact output stability fails |
| Missing scoring (`f06`) | Base is adequate while its format variant is limited, both LR 2.8 | Base/format both limited, but the swapped case becomes adequate despite the same missing scoring |
| Extreme consistent difference (`f08`) | Base 18.5, swapped **0.05**, exactly the permitted lower bound; no clipping was performed | Very-strong in each direction, 4 and 0.25 |

Conflict cases have no prescribed correct direction. The missing-scoring and small-sample cases do not expose invented statistics because only the restricted response fields are returned. Their sufficiency and magnitude judgments can still be inconsistent. The identical numeric abstentions are schema-valid but violate the precommitted neutrality property; they were not repaired or reclassified.

## Usage and cost

| Method | New requests | Input tokens | Output tokens | Summed provider latency | Estimated cost |
| --- | ---: | ---: | ---: | ---: | ---: |
| Numeric | 27 | 19,317 | 501 | 65.878542 s | $0.043644 |
| Qualitative | 27 | 20,397 | 600 | 57.392206 s | $0.046794 |
| Total | **54** | **39,714** | **1,101** | **123.270748 s** | **$0.090438** |

Usage is provider-reported, counted once per unique request. Estimates use the **precommitted conservative $2/$10 per million input/output tokens**, twice the documented base rates checked before the run; these are estimates, not an invoice. The full-plan pre-call reservation was **$0.768512**, within the $1/120-request ceiling. All attempts were reserved before submission. No retries or additional paid validation were run. Detailed timestamps, usage, request/evidence/prompt hashes and raw-response hashes are in the [sanitized bundle](leap_nba_v2_phase1/manifest.json); original wire requests and provider bodies remain in Git-ignored private captures.

## Validation and preservation

The pre-inference complete suite passed **145 tests**. Post-inference verification adds a saved-public-results replay test; the full suite passes **146 tests**. Tests cover field-level blinding, outcome-independent assignments, missingness/source qualifiers, mapping/reciprocals, coherent abstention, malformed JSON/values/envelopes, budget rejection before network, first-403 stop, uncertain-attempt protection, immutable cache reuse, metrics arithmetic and private-data/network isolation. The neutral-only mock completed all slots at zero cost and correctly failed dominance; its results are not counted as paid empirical observations.

Private raw-response verification, saved mock replay and public sanitized replay all pass offline. Public replay reconstructs request identities and remaps observations/recomputes diagnostics and cost totals without credentials, private bodies or historical files. It does not recreate provider inference. The [preservation audit](leap_nba_v2_phase1_preservation.json) confirms byte-identical hashes for **10,154 existing files**, including all **7,608 data files**, previous v1/direct code, prompts, protocols, reports and private captures. The 50/150 split SHA-256 remains `f8e456dbe1b53b5957bf469755b59b94afe621b89e78814c92ca3a3720b97e77`. Existing README changes only add this experiment's links.

Reproduce from the repository root:

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/run_synthetic_elicitation.py --plan
.venv/bin/python scripts/evaluate_synthetic_elicitation.py --replay reports/leap_nba_v2_phase1
# With the original private captures present; no network or key needed:
.venv/bin/python scripts/run_synthetic_elicitation.py --verify captures/leap_nba_v2_phase1/paid
```

The [run guide](../experiments/leap_nba_v2_phase1/README.md) also documents mocks and the explicit live controls. Reproduction of saved observations requires no paid calls. Do not delete private authorization/cache records to rerun the paid batch.

## Limitations and recommendation

All qualitative engineering criteria pass with complete paired-arm coverage, satisfying the precommitted condition to recommend a **separately authorized and precommitted five-game v2 pilot**. No historical v2 pilot was implemented or run here. The pilot should retain these observations as diagnostics rather than treat them as evidence of predictive skill.

Coarse categories and the reciprocal mapping mechanically limit asymmetry once category choices agree. They may improve repeatability by reducing expressiveness, without improving probability accuracy. Neither mapped ratios nor numeric elicited ratios are established statistical likelihood ratios. There are no outcomes, Brier scores, probability forecasts or calibration-of-win-probability results in this phase. Artificial fixtures cover only ten families, repeated formats and cached identical cases are dependent, and temperature 0 does not guarantee deterministic provider inference. Field blinding cannot prove protection against statistical reidentification in a future historical pilot. Finally, zero unsupported output fields does **not** establish zero unspoken invented reasoning: the intentionally terse schema cannot expose that reasoning. Sufficiency instability remains a methodological concern despite better qualitative direction/magnitude consistency.
