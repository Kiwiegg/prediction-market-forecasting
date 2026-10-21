# LEAP-NBA v1 five-game paid pilot

The implementation completed one authorized paid development pilot: **13 new Anthropic requests, all HTTP 200 and valid**, seven legitimate missing-evidence skips, zero failed/budget-blocked groups, and zero paid retries. No searches or new evidence collection occurred. Both variants produced five forecasts from the same cached LR observations. The reserved 150 games were not forecast or scored.

Protocol/prompt/groups/schema/config were frozen in `26500dd`; the tested inference implementation was committed in `95e4eab` before these calls. Neither prompts, bounds, alpha values nor sample membership were changed after observing results. The [methodology](../experiments/leap_nba_v1_protocol.md) describes the paper review and adaptations; [commands](leap_nba_v1.md) document reproduction.

## Actual inference and resource use

- Model: `claude-haiku-4-5-20251001`, Anthropic Messages, temperature 0, maximum 128 output tokens, structured JSON, no tools. Requested and returned model IDs matched in all 13 calls.
- Actual request interval: **2026-10-21T09:19:17.152142Z–2026-10-21T09:19:49.856457Z**. Run sealed at **2026-10-21T09:19:49.893189Z**. These are retrospective inference times, not historical source/snapshot times.
- Reported usage: **20,769 input + 247 output tokens**; cache creation/read input tokens were zero. Summed provider latency **32.399851 seconds**. No billed usage was unavailable.
- Estimated inference cost **$0.066012**, using the frozen conservative $3/$15 per million input/output token rates; not an invoice. No-cost reservation upper bound **$0.392790**. Authorized ceilings: 20 new calls / $1.00. Direct forecasts were reused without new calls (their earlier estimated cost was $0.039423; combined saved observation cost $0.105435).
- All five paired labels and preferred market quotes were available. Kalshi selection remains the existing <=20-minute candle-end rule; quote-refresh age is unknown.

## Selected games and posterior probabilities

All times below are UTC. A/B/C/D denote strength, schedule/venue, player availability and additional news. `1*` denotes a skipped missing group, not a model-estimated neutral LR. These are exactly the existing five direct development pilot IDs, in frozen order.

| Game (home vs away) | Recorded tipoff / T−24h cutoff | A LR | B LR | C LR | D LR | Raw p | Conservative p | Direct p | Kalshi p | Home won |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 401810544 Boston Celtics vs Sacramento Kings | 2026-01-31T00:30:00Z / 2026-01-30T00:30:00Z | 1.42 | 1.15 | 0.62 | 1* | 0.503096 | 0.501548 | 0.72 | 0.810 | 1 |
| 401810485 Dallas Mavericks vs Golden State Warriors | 2026-01-23T00:30:00Z / 2026-01-22T00:30:00Z | 1.42 | 1.68 | 0.72 | 1* | 0.632033 | 0.567209 | 0.38 | 0.375 | 1 |
| 401810279 Orlando Magic vs Charlotte Hornets | 2025-12-27T00:00:00Z / 2025-12-26T00:00:00Z | 1.68 | 1.08 | 1.35 | 1* | 0.710098 | 0.610147 | 0.68 | 0.710 | 0 |
| 401836746 Houston Rockets vs LA Clippers | 2025-12-12T01:00:00Z / 2025-12-11T01:00:00Z | 3.20 | 1.02 | 1* | 1* | 0.765478 | 0.643704 | 0.78 | 0.775 | 1 |
| 401809808 Golden State Warriors vs Houston Rockets | 2025-11-27T03:00:00Z / 2025-11-26T03:00:00Z | 1.85 | 1.02 | 1* | 1* | 0.653620 | 0.578713 | 0.35 | 0.525 | 0 |

Player availability was usable for Boston–Sacramento, Dallas–Golden State and Orlando–Charlotte. Boston was reported; Sacramento was **not yet submitted**, with no inferred health. Dallas/Golden State and Orlando/Charlotte were reported on both sides. Houston–Clippers and Golden State–Houston had **unavailable** reports on both sides, so C skipped. D skipped for all five because historical news was **not collected**, with live historical search disabled. No missing reports/news were backfilled. Report origin timestamps and bounded retrieval scope remain distinct from independently verified historical public visibility; dataset/schedule point-in-time flags remain false.

Eight accepted responses were labeled adequate and five limited. The model’s sufficiency label is not a source verification or quality guarantee. Missing-group sufficiency is `not_applicable_missing`, an audit value never accepted from the model.

## Paired scores: identical five-game intersection

Lower is better. Brier is primary; natural-log loss uses epsilon 1e-15 clipping for log loss only. Every row has **n=5 and exactly the same IDs above**.

| Method | Brier | Natural-log loss |
| --- | ---: | ---: |
| direct | 0.219220 | 0.622953 |
| leap_raw | 0.273754 | 0.742295 |
| leap_conservative | 0.253980 | 0.700805 |
| kalshi | 0.251415 | 0.685751 |
| constant_50 | 0.250000 | 0.693147 |

Raw and conservative LEAP scored worse than direct on this pilot. Raw-minus-direct mean differences: **+0.054534 Brier / +0.119341 log loss**; conservative-minus-direct: **+0.034760 / +0.077852**. These observations validate the implementation and expose qualitative problems; five historical games do not establish comparative skill. No alpha fitting, prompt optimization or exclusions followed these results.

Per-game cells below show **Brier / log loss**. Full-precision probabilities, scores and every paired method difference are in the evaluation-only JSON exports.

| Game | Direct | Raw | Conservative | Kalshi | 50% |
| --- | ---: | ---: | ---: | ---: | ---: |
| 401810544 | 0.078400 / 0.328504 | 0.246914 / 0.686975 | 0.248455 / 0.690056 | 0.036100 / 0.210721 | 0.250000 / 0.693147 |
| 401810485 | 0.384400 / 0.967584 | 0.135400 / 0.458814 | 0.187308 / 0.567027 | 0.390625 / 0.980829 | 0.250000 / 0.693147 |
| 401810279 | 0.462400 / 1.139434 | 0.504239 / 1.238212 | 0.372279 / 0.941985 | 0.504100 / 1.237874 | 0.250000 / 0.693147 |
| 401836746 | 0.048400 / 0.248461 | 0.055000 / 0.267254 | 0.126947 / 0.440516 | 0.050625 / 0.254892 | 0.250000 / 0.693147 |
| 401809808 | 0.122500 / 0.430783 | 0.427219 / 1.060218 | 0.334909 / 0.864442 | 0.275625 / 0.744440 | 0.250000 / 0.693147 |

## Group contributions and offline removal diagnostics

Raw log-odds contributions are log(LR); conservative contributions are exactly half these values. Absent groups contribute zero. Posterior differences after omission are conditional diagnostics, not independent causal effects.

| Game | A log-LR | B log-LR | C log-LR | D log-LR | Raw p minus p without A / B / C / D |
| --- | ---: | ---: | ---: | ---: | --- |
| 401810544 | +0.350657 | +0.139762 | -0.478036 | +0.000000 | +0.086867 / +0.034897 / -0.117109 / +0.000000 |
| 401810485 | +0.350657 | +0.518794 | -0.328504 | +0.000000 | +0.084603 / +0.126495 / -0.072599 / +0.000000 |
| 401810279 | +0.518794 | +0.076961 | +0.300105 | +0.000000 | +0.116933 / +0.016095 / +0.065413 / +0.000000 |
| 401836746 | +1.163151 | +0.019803 | +0.000000 | +0.000000 | +0.260528 / +0.003574 / +0.000000 / +0.000000 |
| 401809808 | +0.615186 | +0.019803 | +0.000000 | +0.000000 | +0.148669 / +0.004497 / +0.000000 / +0.000000 |

Removal scores below also use the same five-game intersection. They were recomputed without model calls, and are diagnostics rather than a basis for selecting/removing groups.

| Removed group | Raw Brier / log loss | Conservative Brier / log loss |
| --- | ---: | ---: |
| A_team_strength | 0.279501 / 0.752956 | 0.263995 / 0.721232 |
| B_schedule_venue | 0.297399 / 0.788885 | 0.267050 / 0.726917 |
| C_player_availability | 0.225865 / 0.638001 | 0.227683 / 0.647072 |
| D_additional_news | 0.273754 / 0.742295 | 0.253980 / 0.700805 |

Calibration uses ten fixed equal-width bins, with the final bin including 1. The following lists populated bins as `range: count, mean probability, observed home-win frequency`; all unlisted bins have count zero. Counts are too small to assess calibration.

- direct: [0.3,0.4): 2, 0.365000, 0.500000; [0.6,0.7): 1, 0.680000, 0.000000; [0.7,0.8): 2, 0.750000, 1.000000.
- leap_raw: [0.5,0.6): 1, 0.503096, 1.000000; [0.6,0.7): 2, 0.642826, 0.500000; [0.7,0.8): 2, 0.737788, 0.500000.
- leap_conservative: [0.5,0.6): 3, 0.549157, 0.666667; [0.6,0.7): 2, 0.626925, 0.500000.
- kalshi: [0.3,0.4): 1, 0.375000, 1.000000; [0.5,0.6): 1, 0.525000, 0.000000; [0.7,0.8): 2, 0.742500, 0.500000; [0.8,0.9): 1, 0.810000, 1.000000.
- constant_50: [0.5,0.6): 5, 0.500000, 0.600000.

## Qualitative problems retained unchanged

- All five A estimates favored home, ranging from 1.42 to 3.20. Golden State–Houston A=1.85 is counterintuitive relative to Golden State’s supplied 10–9 record, +0.842105 average differential and 2–3 recent form versus Houston’s 11–4, +11.133333 and 4–1. Golden State did have a 6–1 home split, so the output is not an arithmetic contradiction, but its direction warrants scrutiny. Dallas A=1.42 also favored home despite its 18–26 record and −2.409091 differential versus Golden State’s 25–20 and +2.933333 (recent form 4–1 for both). No sign was reversed or output replaced.
- Boston C=0.62 is plausible in direction given the listed home absences, but it was labeled **adequate** despite Sacramento’s unsubmitted report. The instruction against treating missingness as health cannot establish what the model internally assumed. Boston’s strength, schedule and injury factors nearly canceled, yielding raw p=0.503096 versus direct p=0.72.
- No LR hit the prespecified extreme flag (<=0.1 or >=10); the accepted range was **0.62–3.20**. Passing numeric validation does not establish reasonable magnitude, direction or calibration. Every accepted response contained only the two required JSON fields; no explanations were requested, so internal reasoning cannot be diagnosed.
- Strength statistics overlap, and strength home/away splits overlap venue evidence. Long-running absences may already affect records. Fixed alpha=0.5 is a sensitivity variant, not a proven correction for dependence. The neutral prior and group-wise home designation can invite venue effects outside B despite instructions.
- Player impact is not quantified by the supplied packet. Mapping names/statuses to impact may draw on remembered knowledge despite the external-knowledge restriction; this cannot be verified from two-field outputs. Completed games and identities may also be memorized. Source/schedule historical revisions remain unresolved.
- LEAP used 13 inference calls versus five for direct; both received the same parent snapshot hashes, but this is not an equal inference-budget comparison. News isolation/deduplication, error handling and gateway support were tested with offline fixtures; **no live D/news inference or live JSON-gateway inference was validated**.

## Reproduction and integrity

Both paid experiments passed read-only private-cache replay: original request hashes, parent/group bindings, raw response hashes, strict parsing and deterministic aggregation. Both consumers use exactly the same five parent evidence hashes. The original direct-vs-Kalshi evaluator reproduced its saved results. The complete test suite passed **123 tests** after adding sanitized replay validation; pre-inference suite passed 122. Offline mocks returned LR=1 and p=0.5 and are kept separate from these actual paid observations.

All **7,665 protected files** retained their original SHA-256 hashes, including every file under `data/`, the direct paid run/cache and frozen direct/split assets. All **7,608 historical data files** remain unchanged. No historical rebuild or evidence refresh was run. Credentials, auth headers and raw provider replies are outside Git.

Public derived exports: [summary](leap_nba_v1_pilot/summary.json), [per-game evaluation](leap_nba_v1_pilot/per_game.json), [sanitized observations/settings](leap_nba_v1_pilot/observations.json), and [content-hash manifest](leap_nba_v1_pilot/manifest.json). These preserve paid derived results and audit metadata; they are not raw provider responses. Fresh clones can verify group/request bindings, reaggregate both variants and reproduce scores from them:

```sh
.venv/bin/python scripts/compare_forecasts.py --replay-sanitized reports/leap_nba_v1_pilot
.venv/bin/python -m unittest discover -s tests -q
```

Private-cache replay additionally validates original HTTP response bytes and reparses model output; it requires the securely retained ignored cache. Public arithmetic replay does not independently authenticate those private HTTP bytes. See the [guide](leap_nba_v1.md) for both commands and separately authorized future runs. No further paid calls are authorized or needed for this report.
