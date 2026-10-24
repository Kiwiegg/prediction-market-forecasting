# Single-game scheduled pilot: operations

The [versioned operational protocol](../experiments/prospective_scheduled_pilot_v1.md)
and [configuration](../examples/prospective_scheduled_pilot_v1.json) preserve
frozen methods, schemas, cutoffs and evaluation. Two launchd agents handle one
game. They are not a campaign or a custom long-running scheduling service.

```sh
# No cost: uses saved schedule if no enrolled job exists; otherwise prints job.
.venv/bin/python scripts/scheduled_prospective.py
.venv/bin/python -m unittest discover -s tests -q
.venv/bin/python scripts/prospective_study.py --replay reports/prospective_phase1/mock_validation

# After committing and testing, enroll exactly one freshly verified game.
.venv/bin/python scripts/scheduled_prospective.py --prepare --allow-network --allow-inference

# Install the two calendar agents in the current macOS user's GUI domain.
# Explicit OS approval may be required. No source/model network requests here.
.venv/bin/python scripts/scheduled_prospective.py --install

# Persist those exact definitions across login/reboot (user OS permission needed).
.venv/bin/python scripts/install_scheduled_agents.py --install

# Inspect the saved plan and installation/startup verification.
.venv/bin/python scripts/scheduled_prospective.py
.venv/bin/python scripts/scheduled_prospective.py --replay
.venv/bin/python scripts/scheduled_market.py --replay
```

Enrollment is immutable at `captures/prospective_scheduled_pilot/job.json`, with
game ID, UTC tipoff/target, registered teams, deterministic identity, source
lineage, native asset hashes, parent journal hashes and authorized caps. It picks
the first safely schedulable cutoff, never a preferred outcome/price/forecast.
There is no output-directory switch or automatic selection of a second game.

Evidence starts at target−2min. Benchmark starts separately at target−1min,
revalidates, fetches the milestone, waits briefly and sends its quote request
near target−5s. Retain actual response timestamps: this is not proof of an exact
T−24h quote or of quote freshness. Late/invalid/absent quotes stay missing.
Forecasting never reads market output. Primary Direct/v2 eligibility does not
require the benchmark. Final results/evaluation are deliberately not scheduled.

Evidence uses existing deterministic statistics/official injuries. News is
explicitly **not collected** in this pilot: no paid call is allowed before a
valid frozen packet exists. After verification, native Direct/v1/v2 requests use
one parent hash, immutable caches, at most20 Anthropic requests and $1 in shared
pre-call reservations. Alpha variants need no extra calls. Unavailable reports
or unlisted players never mean health. Source and model failures remain distinct.
Trusted `.env` is read only before inference; only `ANTHROPIC_API_KEY` is needed
for this no-news pilot. Keys never enter arguments, plists, logs or Git.

Keep this Mac awake, connected and logged in through the window. launchd calendar
events may coalesce after wake; the UTC/source-deadline guards reject late work.
Installation requires both OS registrations and successful no-cost worker startup
proofs. It cannot guarantee future uptime or Internet access. If the host timezone
changes, inspect/reinstall the same immutable timer definitions before the window;
different definitions are refused, rather than silently shifting the cutoff.

Per-phase file locks prevent simultaneous workers. Capture/market/inference claims
survive crashes. A capture claim without a frozen bundle is not retrieved again.
A frozen bundle without an inference claim may proceed before tipoff; an existing
inference claim permits only native offline sealing of cached/uncertain work,
never more paid requests. Finished workers request removal of their own label;
even if OS cleanup fails, persisted completion/year/UTC guards prevent recurrence.

Do not delete parent journals, phase claims or caches to retry. A new paid/source
denial stops future requests, except the specifically authorized NBA schedule403
fallback during enrollment/revalidation. To cancel, use `launchctl bootout` on
each exact `gui/UID/LABEL` stored in `installation.json`. Do not kickstart workers
to force off-time evidence. Capture, inference, quote and failure records remain
under the private job directory; no automatic Git commit or push occurs later.

After actual execution, use private replay above. `scheduled_prospective.py`
never imports the evaluation/market module. `scheduled_market.py --replay`
re-extracts a saved valid quote from its own sources. If forecasts sealed,
the existing `prospective_study.py --export-audit` can publish a separate sanitized
packet/forecast audit. Never label a pending job or a mock as a real forecast.
