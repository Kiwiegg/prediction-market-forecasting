# Prospective schedule fallback: live validation

**Discovery succeeded.** The official NBA CDN again returned HTTP403; the
authorized ESPN fallback returned **24 upcoming regular-season fixtures**, each
corroborated against both teams' season schedules. **No fixture was inside the
T−24h ±5-minute window**, so no injury/news evidence collection, paid calls,
frozen game packet or forecasts were produced. This validates live discovery,
not an eligible prospective forecast or integrated paid forecasting.

## Precommitted change

The [operational amendment v1](../../experiments/prospective_schedule_amendment_v1.md),
[asset registry](../../experiments/prospective_schedule_amendment_v1_assets.json),
[implementation](../../scripts/prospective_discovery.py), tests and
[operating instructions](../prospective_schedule_amendment_v1_operations.md) were
committed at **`275b50823d7164889304db6eff6093d946020760`** before additional live
requests. All 200 tests and original private/public mock replay passed first.

Only the primary NBA schedule's403 permits a denied-source fallback. It does not
permit another NBA endpoint, a retry, or continuation after ESPN/other-source or
paid-provider access denial. Other non-denial NBA unavailability can also fall
back. The original Phase1 protocol, self-hashed orchestration, prompts, models,
evidence schemas, priors, aggregation/mappings, evaluation rules, historical data
and caches remain unchanged. A separate entry point preserves previous replay.

The new immutable authorization binds the original journal's hash at
`captures/prospective_phase1/access_denial.json`; the journal and original403 raw
capture remain intact. New captures are under
`captures/prospective_discovery_v1/attempt`. That fixed attempt is consumed and
cannot be rerun or moved to another directory to obtain a second authorization.

## Actual live activity

Discovery started **2026-10-24T11:21:11.332318Z** and completed
**2026-10-24T11:21:43.983335Z** (20:21:43.983335 in Asia/Seoul).

| Item | Actual result |
| --- | --- |
| Primary NBA schedule | One GET, HTTP403 |
| ESPN daily scoreboards | Three GETs, all HTTP200; UTC dates October24–26 |
| ESPN team season schedules | 29 distinct GETs, all HTTP200; season2027/type2 |
| Source requests / automatic retries | 33 / 0 |
| Verified fixtures / both-team checks | 24 / 48; shared schedules reused |
| NBA game IDs | Missing; no IDs fabricated while NBA unavailable |
| Schedule conflicts / rejected candidate fixtures | 0 / 0 in this capture |
| Eligible capture-window fixtures | 0 |
| Injury/news/article/Brave/Anthropic calls | All zero |
| Provider tokens / conservative reservations / paid cost | 0 / $0 / $0 |
| Frozen evidence packets / model forecasts | 0 / 0 |

Every accepted game agrees on ESPN game ID, home/away identities, explicit
timezone-normalized tipoff, neutral-site flag, season/type, scheduled status and
valid-time flag across the scoreboard and both team schedules. Raw scores,
records, odds and target outcomes are not used in schedule projections. Each
validated field has provider/source references in the [sanitized audit](audit/audit.json).
The [source table](sources.csv) preserves all URLs, retrieval times, HTTP statuses,
raw body hashes and attempt counts; original bodies/headers remain private.

The NBA403 is a visible preferred-source failure, not hidden by the ESPN success.
No field discrepancies occurred live. Conflicting, canceled, postponed,
rescheduled-status, completed, missing, duplicate and ambiguous-time fixtures are
rejected in tests. ESPN disagreement is never resolved by choosing a convenient
time or team. Both team schedules are one provider, not independent publishers.

## Timing and next opportunity

All [24 games and timing offsets](games.csv) are retained. The nearest target was:

| Field | Recorded value |
| --- | --- |
| Game | Golden State Warriors at Phoenix Suns, `401909860` |
| Scheduled tipoff | 2026-10-25T02:00:00Z |
| T−24h target | 2026-10-24T02:00:00Z |
| Discovery completion minus target | +33,703.983335 seconds |
| Timing classification | Late outside tolerance; ineligible |

At collection time the next future target was Lakers at Jazz, `401909861`,
target **2026-10-24T21:00:00Z**, scheduled tipoff **2026-10-25T21:00:00Z**. Its
operational window would be 20:55–21:05Z, subject to fresh schedule verification;
the original source cap still rejects material published/retrieved after21:00Z.
This is a recorded scheduling observation, not a current availability promise.
No waiting job, scheduler or additional request was launched. Another capture
requires fresh operator authorization; the single permitted attempt is complete.

## Verification and remaining limits

The complete suite passes **200 tests**, including nine new discovery tests, both locally (83.207s) and in a clean Git checkout (79.830s) without `.env`, private captures or provider credentials. Clean-checkout public mock replay and discovery-audit verification also pass. Hash checks preserve **23,012 original files**, including **7,608 historical data files**, with no differences. See [validation metadata](validation.json), [preservation checks](preservation.json) and the [original403 audit](../prospective_phase1/discovery_audit.json).
The saved real discovery reproduces all 24 fixtures and all decisions offline
from hashed private sources. Original private mock replay and sanitized shared
packet replay still pass without modifying either mock or cache. The public
audit verifies immutable hashes and source references; it cannot re-extract or
authenticate raw publisher documents that were intentionally not committed.

Tests cover successful NBA preference,403 fallback, both-source unavailability,
NBA/ESPN and team-schedule conflicts, status exclusions, timezone/window boundaries,
immutable parent/attempt records, denial stopping, no off-time paid collection,
tamper detection and public/private audit verification. Existing tests continue
to cover source cutoffs, identical method parent hashes, forecast caches,
postgame isolation, budgets and first paid-provider403 stopping.

**Still unvalidated live:** within-window statistical/injury/news capture, shared
packet freezing with current sources, integrated paid Direct/v1/v2 forecasts,
independent Kalshi capture and later final-outcome evaluation. No eligibility,
source-timestamp, leakage or missingness rule was relaxed. One successful ESPN
capture does not guarantee future API availability or schedule-version history.

```sh
# No network or costs.
.venv/bin/python scripts/prospective_discovery.py
.venv/bin/python scripts/prospective_discovery.py --replay captures/prospective_discovery_v1/attempt
.venv/bin/python scripts/prospective_discovery.py --verify-audit reports/prospective_schedule_discovery_v1/audit
.venv/bin/python scripts/prospective_study.py --replay reports/prospective_phase1/mock_validation
.venv/bin/python -m unittest discover -s tests -q
```
