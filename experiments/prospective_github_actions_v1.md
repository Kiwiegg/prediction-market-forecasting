# Operational amendment: prospective GitHub Actions v1

Applies only to newly authorized `prospective_cloud_news_v1` observations. This
changes execution/storage, not evidence timing, forecasting, scoring or the
separate news-v1 cohort. The legacy Lakers–Jazz missed attempt and original
100-game plan remain untouched. Commit these assets before any affected live use.

## Timing and enrollment

One periodic workflow at UTC minutes 7, 27, 47 discovers/reuses the day's verified
NBA/ESPN catalog. The original two-team corroboration, regular-season, status,
tipoff and discrepancy checks apply. No more than one catalog acquisition per UTC
date; unsuccessful/uncertain discovery stages cannot be retried. Public schedule
NBA403 fallback remains the existing explicit exception. All other denials retain
the original circuits. No historical or missed attempt is rerun.

A runner enrolls games chronologically by target, then ID, at most 90 minutes
before collection starts; it waits in the already-running process until T−30.
Runner readiness must precede collection start. An initially late game is logged
as missed without backfill, even when T itself has not passed. Overlapping games
share bounded evidence/market pools. Paid sends remain globally serialized.
Each runner works at most 165 minutes, with a 190-minute job timeout and no
automatic job retry. Later dispatches can process newly due games. They cannot
take over a persistent owner after interruption without explicit recovery.
While active, the runner checks the saved catalog each minute for newly due
games. It enrolls only games whose forecast deadline fits its remaining lifetime;
others receive an explicit handoff reason. Job-boundary startup delays can still
miss games. No new discovery or shortened evidence window rescues such gaps.

The existing defaults remain T−30 acquisition, hard T publication/retrieval
cutoff, freeze by T+5 and seal by T+15/before tipoff. Post-T extraction sees only
pre-T captured bytes. The native packet, source validation and all five forecast
variants are unchanged. All consume one hash. Independent benchmark data stays
evaluation-only and must finish retrieval by T; missing quotes do not invalidate
the primary Direct–v2 comparison. No postgame scoring runs in this workflow.

GitHub cron and runner provisioning have no punctuality guarantee. Starting early
provides margin, not proof of reliability. Late/canceled/queued runs can reduce
coverage; they must never change eligibility. A persistent VM remains the fallback
if observed startup/storage latency makes valid coverage inadequate.

## Authoritative private state and at-most-once sends

Use a private R2 Standard bucket through the official boto3 S3 API, or private
Amazon S3. R2 provides atomic conditional writes and zero egress charges, avoiding
S3-to-runner egress when restoring checkpoints. Use an isolated, fixed prefix and
store UUID. GitHub artifacts/caches/public Git/private Git are not the ledger.

The root object is updated using If-Match (bootstrap If-None-Match). It binds a
single non-expiring owner to an immutable content-addressed checkpoint manifest.
Manifests link previous manifests. Captured bytes and SQLite consistent backups
are SHA-256 blobs created conditionally. SQL transactions, authorization, stages,
request claims, reserves and denial circuits are checkpointed before write
operations return. In particular, reserve must be remotely committed before
the native HTTP send. Raw captures/caches flush on the next commit/stage seal;
an interruption can lose a response but cannot permit its paid request to resend.

GitHub concurrency cancel-in-progress=false prevents normal duplicate workflows;
remote CAS is the independent coordination authority. One process/thread lock
serializes root changes and global budget transactions. Snapshot SQL and blob
hashes are verified on restore. SDK attempts=1; no automatic network write/send
retries. Conditional immutable-blob existence may be verified by byte equality,
which does not retry a paid request. A write/read ambiguity is fatal, poisons the
runner, and retains ownership. No time-based lease expiry or automatic takeover.

After interruption an operator must confirm the old GitHub run/runner has fully
terminated, release precisely its owner using CAS, and restore the original
snapshot. Never reset the prefix/UUID, delete failed claims, restore an old root,
or change provider identities. Claimed/failed stages and ambiguous requests remain
nonretryable. Completed work is replayed rather than elicited again. Missing
root/DB or mismatching identity fails closed. This guarantees at-most-once sends,
not exactly-once success or recovery of a lost provider response.

Enable private bucket encryption/access controls and retention/lock rules for
blobs, snapshots and recovery records. Root must remain mutable. Application
immutability is not protection against a storage administrator deleting data;
configure independent backup/retention and keep raw responses out of public logs.

## Explicit campaign authorization and budget

Campaign ID `nba-news-initial-v1`, maximum $50 across all request rows, including
unknown usage and prior runs. Per game maximum $1.35, split into at most $0.35
research and $1 forecasting using original conservative reservations. These
are ceilings, not invoices. Native query/page/call caps apply. Current prices
and actual reported usage must be reported separately; no forecast/source
adjustment to exploit observed outcomes. Storage/GitHub infrastructure charges
are outside this provider ceiling and need their own account billing alerts.

Initial approval requires one explicit game ID, UTC expiry (at most 31 days),
store/config/asset hashes and a bounded budget. No activation solely because
credentials exist. Automatic/multi-game enrollment stays disabled until a live
eligible frozen packet and primary forecast pair pass private replay. Further
explicit approval creates an immutable chained amendment with cumulative caps;
it does not reset reservations or remove earlier attempted games. The cap may
then be 20–30 games, followed only after separate approval by up to 100. All
allowlisted/automatic selection is chronological and independent of forecasts,
markets and outcomes. Budget exhausted, missed, source-failed, provider-failed
and primary-eligible counts remain distinct. Outcomes/market data never guide
enrollment. The news cohort stays separate from the original no-news cohort.

Every paid request must have a unique native identity, one owner, valid approval,
atomic local transaction under that owner, per-game/global budget checks and a
remotely durable reservation. Unknown usage is never released automatically.
First paid denial persists globally before another paid send; benchmark-only
denials remain isolated as in cloud-news-v1. No retry after uncertain requests.

## Activation and validation scope

Committed workflow defaults have no enabled live/admin repository variables and
no supplied secrets. Offline workflow is manual and has no provider/storage
credentials. Live code is main-only, pinned by an explicitly reviewed SHA and a
protected environment. Initial operator actions are bootstrap, discover, authorize
one game, live enable; none are performed by implementation/testing. No artifacts
containing captures are uploaded. Only aggregate counts/cost reservations are
printed by live runs. Failure details stay private; GitHub run status is the
minimal monitoring channel. Configure notifications and bucket billing alerts.

Offline tests use a conditional-write in-memory object-store fixture, synthetic
publisher/model captures, native frozen methods and hash replay. They establish
logic, not actual R2/S3 CAS behavior, runner startup reliability, NTP, publication
availability or real provider integration. Validate storage-only CAS/restore and
one live game before authorizing unattended multi-game collection. No paid or
cloud storage resources are provisioned by this implementation task.
