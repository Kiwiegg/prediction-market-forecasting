# GitHub Actions v1: offline validated, live collection disabled

## Decision and implementation

Use one periodic GitHub-hosted workflow with a private R2 Standard bucket instead
of a continuously running VM. The [operational amendment](../../experiments/prospective_github_actions_v1.md)
and implementation are frozen at **b843717**, with bounded in-run enrollment finalized at **9280eee**. All original files other than this
repository's README remain unchanged, including forecasting methods, historical
data, prior reports and the original cloud protocol. The Lakers–Jazz missed
attempt is excluded; its jobs, journals and captures were not executed/modified.

GitHub explicitly allows delayed/dropped schedule events; no start-time guarantee
is claimed. A dispatcher at UTC minutes7/27/47 starts a runner up to90minutes
before T−30 and waits on that runner. Readiness after T−30 is missed, not backfilled.
Already-running jobs handle overlapping games through bounded native thread pools;
paid sends serialize globally. Each worker stops at165minutes, job timeout190,
below the hosted six-hour limit. This meets **eligibility/integrity rules when
deadlines are met**, but cannot guarantee the study's coverage or punctuality.
Real startup/queue/storage latency must be measured before a campaign. The existing
persistent VM is the implemented fallback if missed-window rates are unacceptable.
[GitHub scheduling](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule),
[runner limits](https://docs.github.com/en/actions/reference/limits).

## Private durability and cost safeguards

Artifacts/caches are not an authoritative ledger. Private Git would accumulate
binary history; a database plus blob storage is unnecessary for one owner.
Selected architecture: atomic conditional root object, non-expiring run owner,
SHA-256 immutable checkpoint chain, native SQLite WAL/FULL budgets and captures.
One global owner plus local transaction/lock serializes all campaign reservations.
Every paid claim/reservation commits remotely before the native HTTP send. Failed
or ambiguous writes stop the process; paid uncertainty retains reserves/claims.
There is no automatic takeover or paid retry. Explicit recovery requires proof
the old runner terminated and CAS-clears only its exact owner, retaining history.
[R2 atomic semantics](https://developers.cloudflare.com/r2/reference/consistency/).

Original per-game research$0.35/forecast$1 caps, query/page/call bounds and
first-denial behavior remain. A separate cumulative **$50 campaign** checks all
request rows, including failed/unknown usage and previous authorizations. Approval
binds store/config/code hashes, explicit IDs, expiry and limits. Multi-game and
automatic selection cannot activate until a genuine live primary pair passes
private replay; mock success is insufficient. Later explicit amendments retain
earlier claims and the cumulative cap. Enrollment is chronological, independent
of forecasts, markets and outcomes. Budget-excluded/missed/failed/captured/eligible
records remain distinct. Reported usage/estimated cost is separate from reserves;
new actual provider spend in this task is **$0**.

Fixed source cutoff T, collection T−30, freezing T+5 and sealing T+15 remain
unchanged. News is validated/captured before T; later extraction sees only saved
bytes. Native team/injury extraction, forecast prompts, request identities,
aggregation, shared packet loader and independent Kalshi quote rules are reused.
Market/outcome information never enters packets. No new outcome evaluation ran.
The separately labeled news cohort does not restart or merge the legacy100-game
study. Initial game cap is1; future20–30/100 enrollment needs explicit expansion.

## Validation actually performed

See [machine-readable validation](validation.json), [preservation](preservation.json)
and [simulation](simulation_validation.json) for final checks and timings.
**All 261 tests pass**, including20 new Actions tests, in a final clean checkout
(119.590s) without credentials/private captures. Existing and new offline replays
pass. No live provider requests were made.
New tests cover delayed startup, overlapping chronological enrollment, duplicate
owners, interrupted stages, conditional claims, concurrent$50 reservations,
per-game budgets, absent/expired approval, missing credentials/NTP, permanent
denials, corrupted source blobs, shared native packet hashes and immutable replay.
An accepted remote claim with a lost acknowledgement remains nonretryable after
explicit recovery. Workflow syntax passes **actionlint1.7.7** (shellcheck disabled).
GitHub-hosted execution and actual R2/S3 conditional operations were **not run**.

The synthetic full pipeline produced one packet, native mock Direct/v1/v2 outputs,
then restored the private checkpoint into a fresh directory and reproduced it.
Hash: `68ba497484267bf559c6b603cf1d5c65eae35c3f8be548bc48829e21133d829d`.
This is fixture-only, with `live_evaluation_eligible=false`, one attempted mock,
zero real captures/primary-eligible observations, zero real provider requests.
Fake publisher/PDF data and LLM outputs are not live evidence. The in-memory store
recorded161reads/157writes/127objects; these are not production workload forecasts.
Public replay verifies native request/packet/aggregation hashes, not publisher or
provider authenticity. Private replay also verifies saved capture bytes.

## Infrastructure cost and activation blockers

Public-repository standard GitHub runners are free; private-repository usage is
subject to plan quotas. R2 Standard can be$0/month within its10GB storage,
1million writes and10million reads allowances; overages, retention and account
usage can add charges. R2 charges no egress. Full checkpoint restores can grow
expensive/slow; a10,000-object,72dispatch/day example reaches21.6million reads/month
before other operations. The current256MiB initial restore bound requires review
before scaling beyond it. Cost is not guaranteed zero or benchmarked live.
[Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions),
[R2 pricing](https://developers.cloudflare.com/r2/pricing/).

The existing VM alternative is approximately$8/month before backups/tax/overages.
The$50 provider ceiling covers at most37 fully reserved$1.35 games; actual costs
may be lower, but cannot guarantee100games. No cap increase is automatic.
[Existing VM cost analysis](../../deploy/cloud-news/README.md).

**Published:** workflow/code/protocol and sanitized offline results. **Not deployed
or activated:** no bucket, cloud account permissions, retention policy, environment
secrets, approval, activation variables or live game were configured by this task.
No Mac dependency remains in the proposed execution path, but real operational
behavior is unvalidated.

For the first real game, after separate permission:

1. Configure the private bucket, prefix retention/backups/billing alerts and scoped
   storage credential; protect the GitHub environment and main branch.
2. Pin the full reviewed SHA and enable admin commands only. Run manual dry-run,
   bootstrap, store the returned UUID, then discovery. Validate storage CAS/restore.
3. Authorize the earliest verified future game's one ID and UTC expiry. Leave
   automatic/multi-game disabled.
4. Only with paid activation approval, enable the live variable and dispatch.
   Verify timing, provenance, costs, shared hash and private replay afterward.

[Exact setup/activation/recovery commands](../../deploy/github-actions/README.md).
No activation or first live success is claimed. Remaining live checks include
hosted NTP/startup, R2 permissions/CAS/latency/retention, NBA/ESPN access, news
coverage/extraction, native inference, benchmark latency and overlapping capacity.

```sh
.venv/bin/python scripts/actions_prospective.py
.venv/bin/python scripts/actions_prospective.py --validate-assets
.venv/bin/python scripts/cloud_prospective.py --replay-public reports/prospective_github_actions_v1/simulation
.venv/bin/python scripts/cloud_prospective.py --replay-public reports/prospective_cloud_news_v1/simulation
.venv/bin/python scripts/prospective_study.py --replay reports/prospective_phase1/mock_validation
.venv/bin/python -m unittest discover -s tests -q
# Fresh fixture directories only; all network/provider calls are mocked:
.venv/bin/python tests/test_actions_prospective.py --export-simulation \
  captures/actions_mock_fresh /tmp/actions_mock_public
```
