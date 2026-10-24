# One-game scheduled prospective pilot — scheduled/pending

**The real one-game job is installed and pending. No eligible evidence packet,
Kalshi quote or forecasts have been produced yet.** This report records setup and
offline validation, not a completed prospective forecasting success.

| Item | Registered value |
| --- | --- |
| Game | Los Angeles Lakers at Utah Jazz, `401909861` |
| Scheduled tipoff | 2026-10-25 21:00 UTC / October26 06:00 Seoul |
| T−24h target | **2026-10-24 21:00 UTC / October25 06:00 Seoul** |
| Operational window | 20:55–21:05 UTC / 05:55–06:05 Seoul |
| Evidence launch | **20:58 UTC / October25 05:58 Seoul** |
| Independent market launch | **20:59 UTC / October25 05:59 Seoul** |
| Planned quote request | 20:59:55 UTC; actual response must finish by21:00 |
| Source retrieval deadline | 21:00 UTC; no post-cutoff publication/retrieval |
| Job identity | `c9abaa9022d931c6e1c1922da24ac60e1175ec7c59d1c5aba3057670e160a405` |

## What actually happened

The scheduling [protocol](../../experiments/prospective_scheduled_pilot_v1.md),
[configuration](../../examples/prospective_scheduled_pilot_v1.json), workers and
tests were committed at **`bdc7bce`**, after all216 tests passed and before live
enrollment/installation. The login-persistence [deployment note](../../experiments/prospective_scheduled_pilot_login_v1.md)
and helper were committed at **`0722d57`** after the full218-test suite passed,
before installing identical persistent timer files. The frozen worker/config/job
assets were not modified by the persistence step.

Fresh enrollment discovered24 upcoming regular-season games. The official NBA
endpoint returned403; the authorized ESPN fallback supplied three daily
scoreboards and29 team season schedules, all HTTP200: **33 source requests,
zero retries**. Both team schedules corroborated the enrolled fixture. The
selection rule chose the first future cutoff with at least300s preparation before
the target−120s launch, using scheduled times/game IDs only. Raw sources remain
private; the [sanitized discovery audit](discovery_audit.json) preserves sources,
retrieval clocks, hashes, field provenance, all decisions and source failure.

Both launchd calendar tasks registered successfully at
**2026-10-24T14:06:20.207023Z**. Real no-cost RunAtLoad probes verified frozen assets
and returned `pending`, exiting0. OS inspection recorded each agent loaded,
not running, one startup invocation and last exit0. There was no capture or paid
claim. Identical plists were installed in the user's `~/Library/LaunchAgents`
directory at **2026-10-24T15:07:30.016880Z**, preserving the current loaded jobs and
enabling future login loading. A real logout/reboot was not performed.

The saved [job](job.json), [timer installation](installation.json),
[login persistence](login_persistence.json), both startup proofs and sanitized OS
status are included. Private execution state stays under
`captures/prospective_scheduled_pilot/`. All original access-denial journals,
source captures and successful/failed native cache records remain intact.

At report time: **zero Anthropic/Brave/article calls, zero provider tokens,
zero conservative paid reservations, $0 paid cost**, zero frozen packets and
zero forecasts. The Anthropic credential is locally readable; its API validity
and future paid inference remain untested. No additional historical forecasts,
outcome collection, market requests, tuning or campaign were launched.

## Scheduled behavior and protections

Evidence and benchmark run as separate OS processes/output directories. Each
performs one new targeted schedule corroboration; a cancellation, changed
tipoff/teams/venue, incomplete mapping or denied fallback stops the registered
fixture rather than shifting the cutoff or selecting another game.

Phase A reuses deterministic statistics/official-injury extraction, strict packet
construction and source clocks. Packet creation retains the ±300s rule and
min(snapshot,target) source cap. Missing/incomplete reports stay explicit; unlisted
players never mean healthy. **Paid news research is not collected in this pilot**,
because paid calls are gated on a valid frozen packet first. This omission is
recorded as not collected, not no news found. No feature, schema or forecast
projection was changed.

Only an eligible frozen packet unlocks Phase B. Direct, LEAP v1 and LEAP v2 load
the same parent hash through native loaders/caches, with unchanged prompts,
Haiku4.5, settings, priors, mappings and alpha variants. No source retrieval is
allowed during inference. All requests/seals must precede tipoff; a late seal is
explicitly ineligible. The job shares the original **20 Anthropic / $1 conservative
reservation** caps; no paid retries. Brave/article maxima are two/four but actual
planned usage is zero.

The market worker reuses original home-YES milestone/quote validation, preserving
bid/ask/spread/midpoint and actual response clocks. A request near target−5s is a
practical capture, not a claim of exact-cutoff timing or quote refresh age. Late,
invalid or missing quotes are never backfilled. Market data never enters evidence
or model context and its absence does not invalidate a valid Direct/v2 pair.
Historical20-minute candle selection is unchanged.

Persistent locks and immutable claims protect restarts. An interrupted capture is
not retrieved again. Existing inference claims permit offline sealing, never a
paid resend. The original schedule403 exception is narrow; other source/paid
access denial stops future requests with a new permanent journal. Each completed
worker requests its own launchd unload. After completion, remove the two exact
LaunchAgent files if desired; if login reloads them first, completion/year/UTC
guards make them no-ops and they unload again. No second game is enrolled.

## Validation and remaining limits

All **218 unit tests pass**, including18 new scheduling/deployment tests, both locally (83.347s) and in a clean checkout (78.419s) without `.env`, provider credentials or private captures. Clean-checkout public plan replay and original shared mock replay also pass. Hash checks preserve **23,102 original files**, including **7,608 historical data files**, without differences. See [validation metadata](validation.json) and [preservation results](preservation.json). These
cover UTC/DST/windows, fixture changes, duplicate locks, restart claims, delayed
collection/seals, incomplete sources, no paid calls before freeze, explicit news
and injury missingness, shared native method hashes, market isolation and quote
replay, cost/denial guards, and exact immutable login-file copying.

Private replay reproduced the fresh enrollment and original shared mock; original
public mock replay still passes. Public plan replay checks the sanitized job,
timer hashes, UTC/local schedule and frozen assets without private captures,
credentials, source requests or model calls. It does not authenticate publisher
history or prove future capture/forecast execution.

**Still unvalidated:** actual wake/time-window execution, live injuries/statistics,
valid packet freezing, paid native inference, cutoff benchmark mapping/latency,
and later final-outcome evaluation. Keep this Mac **awake, connected and logged
in** around05:58–06:00 Seoul. Timers/login persistence cannot guarantee uptime,
network access or an on-time packet. A missed window remains missed. No one-time
pilot accuracy or method-superiority claim can follow from setup or mocks.

## Reproduction and monitoring

```sh
# No network or costs; prints the enrolled game/target/plan.
.venv/bin/python scripts/scheduled_prospective.py
.venv/bin/python scripts/scheduled_prospective.py --replay
.venv/bin/python scripts/scheduled_market.py --replay
.venv/bin/python reports/prospective_scheduled_pilot/replay.py
.venv/bin/python scripts/prospective_study.py --replay reports/prospective_phase1/mock_validation
.venv/bin/python -m unittest discover -s tests -q
```

Do not re-enroll, delete claims, kickstart off-time work or resend failed paid
requests. See [operations](../prospective_scheduled_pilot_operations.md) for
deployment and cancellation. Actual future results will remain private until
reviewed and explicitly exported; no automatic Git publication is installed.
