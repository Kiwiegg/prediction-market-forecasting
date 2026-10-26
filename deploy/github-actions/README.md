# GitHub Actions + private object storage (not activated)

Use the committed `prospective-nba.yml` workflow with a private **R2 Standard**
bucket. No Mac, VM, database service or per-game workflow is required. This is
best-effort scheduling with strict eligibility, not a guarantee of captures.
The original VM deployment remains available and unchanged.

## Feasibility and costs

GitHub says scheduled workflows may be delayed/dropped and public schedules can
disable after 60 days of inactivity. Standard hosted runners in public repos are
free; private repositories have plan quotas. Hosted jobs have a six-hour limit.
Our off-hour 20-minute dispatch, 90-minute lookahead and already-running wait
provide startup margin. The worker stops after 165 minutes (job timeout190).
Queued dispatches do not cancel a running capture. Runner readiness after T−30
means missed, never backfilled. No guaranteed startup bound exists. If measured
miss rates are unacceptable, the existing ~$8/month persistent VM/storage plan
is the smallest implemented alternative; no research rule needs to change.
[Scheduling](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule),
[billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions),
[limits](https://docs.github.com/en/actions/reference/limits).

An active runner checks its saved catalog every minute and can add later games
whose forecast deadlines fit its remaining165-minute lifetime. Others are labeled
for handoff to a later dispatch. Runner-boundary delays can still cause misses;
neither overlap support nor early launch eliminates GitHub scheduling uncertainty.

| State option | Assessment |
| --- | --- |
| Actions artifacts/cache | Optional exports only: retention/eviction and no authoritative atomic cross-run claims |
| Private Git repository | CAS refs possible, but frequent binary/raw snapshots create large history; no advantage here |
| Transactional DB + blob store | Strong option for more workers; another service/schema unnecessary for one owner |
| Private R2/S3 conditional objects | Selected: one persistent owner, immutable checkpoint chain, SQLite budgets reused |

R2 Standard includes10GB-month,1million ClassA and10million ClassB operations;
overages are$0.015/GB-month,$4.50/millionA,$0.36/millionB, rounded by billing unit,
with no egress fee. This can be **$0/month infrastructure within allowances**;
it is not a promise of zero cost. Restore downloads all current blobs on each
dispatch; growing datasets increase operations and startup latency. For example,
10,000blobs ×72dispatches/day ×30days is21.6million reads before other traffic
(about$4.32 for12million rounded billable reads), even with free egress. Immutable
SQLite backups/manifests accumulate; monitor storage and use safe retention and
backup policies. Initial restore refuses state above256MiB pending a reviewed
scaling configuration. Do not assume100games fit that bound. The tiny synthetic
operation counts in the validation report are not production capacity estimates.
[R2 pricing](https://developers.cloudflare.com/r2/pricing/).

Amazon S3 is also supported (omit endpoint, set AWS region); it adds region-specific
storage, request and Internet-egress charges. For repeated full runner restores,
R2 avoids that transfer bill. Do not use arbitrary S3-compatible endpoints without
validating their CAS semantics. R2 and S3 document atomic conditional writes.
[R2 consistency](https://developers.cloudflare.com/r2/reference/consistency/),
[S3 conditional writes](https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes.html),
[S3 pricing](https://aws.amazon.com/s3/pricing/).

Provider ceilings remain **$1.35/game and $50 cumulative campaign**; observed
reported-token costs, query reservations and unknown usage are tracked separately.
20–30fully reserved games cost at most$27–$40.50;100fully reserved games could
require$135, so$50 cannot guarantee100games. No automatic budget increase. These
are provider limits; storage/account billing alerts are separate. Actual new paid
provider spend in implementation validation is$0.

## Setup after explicit deployment authorization

1. Create one private R2 Standard bucket, no public URL/custom domain, no public
   access. Configure bucket-lock retention on `nba-news-initial-v1/blobs/`,
   `.../snapshots/` and `.../recoveries/`, **not root.json**. Configure independent
   backups and billing alerts. Do not expire the authoritative checkpoint chain
   or lost/uncertain claims. Retention configuration is an operator prerequisite,
   not something these scripts provision. R2 encrypts objects at rest; access is
   TLS/SigV4. Do not place tokens in Git or command-line arguments.
   [Bucket locks](https://developers.cloudflare.com/r2/buckets/bucket-locks/).
2. Create a bucket-scoped read/write R2 API token; store the generated S3 access
   key/secret in the GitHub environment `nba-prospective-live`. Restrict environment
   deployments to protected main; require operator review for the first pilot.
   Protect workflow/code changes and never grant secrets to forks/PR code. Use
   a separately scoped backup credential. For AWS, use tightly scoped IAM/OIDC
   instead of broad account credentials; the supplied workflow's R2 credential
   step needs an explicit OIDC setup before using that alternative.
3. Configure environment secrets:
   `NBA_ACTIONS_BUCKET`, `NBA_ACTIONS_ENDPOINT` (HTTPS account R2 endpoint),
   `NBA_STORAGE_ACCESS_KEY_ID`, `NBA_STORAGE_SECRET_ACCESS_KEY`,
   `BRAVE_SEARCH_API_KEY`, `ANTHROPIC_API_KEY`.
   Set `NBA_ACTIONS_STORE_UUID` only after bootstrap. R2 region defaults to `auto`;
   AWS uses `NBA_STORAGE_REGION` repository variable. Provider secrets are passed
   only to live mode, not bootstrap/discovery/replay or the offline workflow.
4. Set repository variable `NBA_ACTIONS_REVIEWED_SHA` to the **full reviewed final
   commit**. This pins cron to reviewed code: a later unrelated main commit stops
   private jobs until reviewed/pinned again. Set `NBA_ACTIONS_ADMIN_ENABLED=true`.
   Leave `NBA_ACTIONS_LIVE_ENABLED` unset/false. Nothing in this task sets these.
5. Run the manual offline workflow first (no credentials/network provider calls).
   Run storage-only bootstrap, record its UUID as the environment secret, then
   `discover`. Inspect published fixture timings and private catalog. Verify
   storage conditional-write/restore behavior on the chosen account before
   approving paid work. All storage writes may incur account charges; setup
   requires separate authorization even without model calls.

```sh
# Exact GitHub CLI dispatches; equivalent inputs exist in Actions UI.
# These are FUTURE operator instructions, not commands run by this task.
gh workflow run prospective-nba.yml --ref main -f mode=dry-run
gh workflow run prospective-nba.yml --ref main -f mode=bootstrap
# Set NBA_ACTIONS_STORE_UUID from bootstrap, then:
gh workflow run prospective-nba.yml --ref main -f mode=discover
gh workflow run prospective-nba.yml --ref main -f mode=status
```

No secret value needs to appear in a CLI argument or public log. The status command
requires an approval once created; initial discovery does not. An interrupted
bootstrap/command leaves a durable owner and needs the recovery procedure below.
If a clock check does not return NTP-synchronized, stop and investigate the runner;
do not bypass it to force a forecast.

### Dispatch troubleshooting

The secret-free `gates` job reports boolean branch, exact/full SHA, mode and
enable-flag decisions even when `private-worker` is skipped. Enable flags accept
surrounding whitespace (including pasted CRLF); only `true` enables a flag. The
reviewed SHA is never trimmed or abbreviated. Keep these three gate variables at
repository scope; environment secrets are unavailable to job-level conditions.
Both execution jobs pin Python3.13.2. The full offline suite runs on GitHub's
hosted macOS14/arm64 runner to match the historical byte-exact replay platform;
the original derived-float comparisons also fail on Linux with Python3.13.2.
No historical records, numeric tolerances, formulas or frozen evaluators are
changed. The private collector remains Ubuntu24.04; this needs no operator Mac.

After **every new commit**, set `NBA_ACTIONS_REVIEWED_SHA` to its full40-character
SHA, keep admin enabled and live disabled, then dispatch a **new** run from main
with `mode=bootstrap` (or `discover` after a successful bootstrap/UUID setup).
Do not use “Re-run jobs” on an old run: GitHub reuses that run's original SHA.
An `offline` job means `mode=dry-run`; it never bootstraps storage or uses secrets.

## First real game: separate explicit paid approval required

Choose the earliest regular-season game from the verified catalog whose T−30
collection start is still safely ahead (prefer discovery at least90minutes early).
Do not reuse legacy ID401909861 or any expired ID. Record a UTC expiry under31days.
The authorization permits exactly one ID, regardless of the$50 global ceiling.

```sh
gh workflow run prospective-nba.yml --ref main -f mode=authorize \
  -f game_id=VERIFIED_FUTURE_ID -f expires=YYYY-MM-DDTHH:MM:SSZ
# Only after explicit paid activation approval:
gh variable set NBA_ACTIONS_LIVE_ENABLED --body true
gh workflow run prospective-nba.yml --ref main -f mode=live
```

The periodic workflow can then wait on an already-running runner for this one
authorized game. Actual evidence starts at T−30, refreshes nearT−2, must be
retrieved byT, frozen byT+5 and sealed byT+15. The model context and native methods
remain unchanged. Kalshi capture runs independently and cannot change the packet.
No postgame outcome evaluation is launched. Check the job, private sources, shared
hash, eligibility, timestamps, costs and private replay before calling it success.

After the first **genuine live primary pair** passes replay, further **explicit**
authorization may use manual `expand`, expiry, `game_limit=30` and
`automatic_enrollment=true`. This writes an immutable amendment, preserves prior
attempts/reservations, and chronologically enrolls due games within the horizon.
It cannot enable multi-game collection from a mock result. Future100-game approval
must respect the unchanged cumulative$50 cap or require a new committed budget
protocol. This does not restart or pool the original no-news100-game study.

## Monitoring, recovery and replay

Live logs contain aggregate enrolled/attempted/captured/primary-eligible counts
and reserved cost only. Raw requests, publications, extracts, model responses,
credentials and quotes stay in the private bucket; no upload-artifact/cache step.
GitHub failure notifications, private circuit records and missed-window events
provide monitoring. Configure account notifications and a human review of absent
runs; Actions cannot detect its own complete scheduling outage. Keep the repo
active or re-enable scheduling if GitHub disables it after inactivity.

Disable `NBA_ACTIONS_LIVE_ENABLED` to prevent future dispatch. **Do not cancel a
healthy capture to save minutes.** If stopped/killed, the durable owner remains
until the old run is confirmed terminated. A later workflow cannot steal it.
Missing/uncertain paid requests never resend. Recovery on a trusted temporary
runner with privately injected storage credentials:

```sh
python3 scripts/actions_prospective.py --state FRESH_PRIVATE_DIR --allow-network \
  --recover-owner 'EXACT_OWNER_JSON_FROM_PRIVATE_ROOT' \
  --confirm-old-runner-terminated CONFIRMED_OLD_RUNNER_TERMINATED
```

This CAS-clears only that exact owner and records recovery; it preserves the
snapshot, failed claims, access denials and all budgets. Never delete/reset the
root or use an older root/UUID. Ownership is deliberately not time-expiring.
Successful status/replay sessions release ownership. Native stage/cache failures
are still nonretryable after recovery. A missing store/DB needs incident review,
not reinitialization. First denial/expired approval/storage failure halts paid work.

```sh
# Offline, no credentials/network required:
.venv/bin/python scripts/actions_prospective.py
.venv/bin/python scripts/actions_prospective.py --validate-assets
.venv/bin/python scripts/cloud_prospective.py --replay-public reports/prospective_github_actions_v1/simulation
.venv/bin/python -m unittest discover -s tests -q
# Native private replay after explicit storage access (no provider calls):
gh workflow run prospective-nba.yml --ref main -f mode=replay
```

R2/S3 CAS latency, real hosted clock/startup behavior, service access, concurrent
game throughput and one eligible live game remain **unvalidated** by offline
fixtures. This deployment offers valid observations when deadlines are met, not
guaranteed observation coverage. No VM, bucket, secrets, activation variable or
paid game was provisioned/configured by the implementation task.
