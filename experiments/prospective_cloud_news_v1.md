# Prospective cloud news protocol v1

Commit this protocol, configuration, extraction settings and tested implementation
before the first affected live capture. No live game or paid request is authorized
by this implementation task. The Mac Lakers–Jazz job, its files, installed timers,
journals, native caches and old protocols remain untouched. Exclude `401909861`
from this protocol even if an operator tries to enroll it explicitly.

## Fixed timing and evidence

T is recorded scheduled tipoff minus exactly86400 elapsed UTC seconds. Timing
configuration is bound into job identity; changing a material setting creates a
new precommitted protocol/configuration cohort, never rescues a running attempt.
Defaults: collection [T−30min,T], retrieval deadline T, freeze by T+5min,
forecasts sealed by T+15min and strictly before tipoff. An earlier configured
retrieval deadline is allowed; a post-T deadline or non-24h target is rejected.
No dynamic extensions or rescheduled cutoff mutation. Save actual clocks and
deadline failures. Late/incomplete stages remain ineligible, never silently dropped.

Reuse NBA-preferred/ESPN fallback and both-team schedule corroboration. Admit games
deterministically by target then game ID, only before collection start. Each job
is immutable by protocol/config hash, game identity and registered tipoff. A changed
fixture, status, venue or unavailable corroboration blocks collection. One public
baseline and one declared near-T public refresh are allowed, each a new bounded
capture slot, not a retry. There are no automatic denied/uncertain request retries.
Refresh failure is visible; previously eligible captured sources may remain usable
with explicit freshness/missingness. No guarantee of globally latest information.

An explicitly requested no-cost discovery catalog may run once per UTC date.
Each daily slot is immutable and never automatically retried. Host circuits
persist across dates. Workers never invoke discovery/enrollment automatically;
first-game paid authorization follows review of the captured catalog.

Every included publisher/source response must finish retrieval by the fixed
deadline; official issue/creation/availability and article publication/modification
clocks retain existing validation. Capture raw bytes, URLs, clocks and hashes.
Reject undated, ambiguous, modified-after-T, unsupported-domain or future evidence.
Record source age at T from publication and actual retrieval separately; retrieval
does not prove the underlying information was newly refreshed. Unversioned source
history and independent first-publication uncertainty remain explicit.

Use existing statistics, rest-at-cutoff and deterministic official injury parsing.
Missing reports/unsubmitted teams/unlisted players never mean healthy. Use existing
Brave queries, article allowlists/no redirects, safe excerpts, Anthropic factual
extraction prompt and deterministic verbatim/citation/deduplication validation.
Search snippets, outcomes, prices and source audits never enter forecasting context.

## Acquisition and extraction boundary

Search and page retrieval occur only within collection, with2 queries/4 pages by
default. Persist validated source bytes/excerpts and a hashed acquisition manifest.
Prefer extracting immediately. One bounded extraction request may finish after T
only from this sealed pre-cutoff input; it cannot fetch pages or search. This is
the narrowly specified exception to post-T deterministic processing, not an
extension of the information horizon. Freeze must still finish by T+5. Preserve
the original extraction prompt/model, complete context, response, reported usage,
latency, reservations and start/end clocks privately. Revalidate support after
extraction. No qualifying article means no model call, with explicit missingness.
Extraction failure and genuinely no usable evidence remain distinct.

After T no new external source contributes. Deterministic processing reconstructs
features from captured bytes only. Freeze one shared packet with cutoff_utc=T.
The existing schema's optional legacy snapshot_timing field is omitted: its
actual-snapshot semantics cannot honestly represent a multi-phase information
cutoff. Actual collection, extraction, freeze and inference clocks, protocol and
eligibility live in separate hashed audit files. Do not backdate a physical event.
This is a new evidence-protocol cohort, not a forecasting-method change. Explicitly
validate retrieval timestamps even without that optional legacy field.

## Native inference and independent market

Use the existing shared loader, request builders, immutable caches, parsers and
aggregation for Direct, v1 and v2 with their identical original settings. Native
alpha variants share observations. Failed/insufficient groups are not imputed;
legitimate source skips retain native LR1 semantics. All methods bind the same
parent hash. Missing/late freeze blocks inference. Recheck T+15 and tipoff before
each request and after the final seal; a delayed response makes the run ineligible.
No tools/search or audit/evaluation file is available to inference.

A separate market worker/output directory reads only registered schedule metadata,
revalidates, fetches the original milestone and sends the quote near T−5s. Reuse
original matching, status and 0<bid<=ask<1 requirements and actual response clock
in [T−300s,T]. Late/missing/stale/unmatched quotes remain missing; no trade or
post-cutoff candle substitution. Quote update age remains unknown. Historical
20-minute market rules are unchanged. Market absence does not invalidate the
Direct/v2 primary pair. Final outcomes/evaluation are not part of collection.

Benchmark access failures are isolated: preserve a persistent denied-host circuit
and a missing quote, never retry or switch hosts, but do not halt unrelated
forecasting from valid evidence. This explicitly implements benchmark independence
in this new protocol; it does not change the legacy pilot. Evidence-source and
paid-provider denials retain global pause semantics below; paid403 always pauses.

## Persistence, failures and cost

Deploy one Linux VM with persistent private local disk, SQLite WAL/FULL synchronous
transactions, filesystem process locks, fsynced immutable records, and systemd
restart supervision. No ephemeral GitHub runner, shared-NFS database, multi-VM
active/active or high-availability claim. Separate bounded evidence/market worker
pools allow overlapping games without queuing quotes behind model requests.
An explicit operator authorization binds store UUID, frozen asset registry, protocol/config, allowed
game IDs, job count and total cost. No default enrollment or unattended paid mode.
Durable global request claims and native attempt markers survive restart. Never
resend an uncertain paid request. Deterministic stages can replay; completed
artifacts are verified. A network stage interrupted without an artifact is marked
uncertain rather than retried. Intentional baseline/refresh public slots are
predeclared; they cannot retry a denied host. Paid search is once per game/query,
not once per worker restart. Forecast request identity stays native.

First paid access denial pauses paid work globally with a durable circuit record.
Other evidence-source access denials also pause new network/paid work globally, preserve
per-host circuits and affected-stage failure/missingness. Only the known NBA
schedule403 has the explicit ESPN fallback. Do not change endpoints, credentials,
cache paths or volume UUID to bypass a circuit or an uncertain claim. A missing
volume sentinel or mismatched authorization blocks startup. Backups/restore must
preserve the claim ledger, sources, caches and circuits together; restoring a
stale backup cannot prove no calls happened afterward and requires operator review.

Separate research and forecasting reservations before network calls, with default
research cap$0.35 (including search), forecast$1/9 calls and combined$1.35/game.
Global authorization budget applies atomically across overlapping games. Usage
unknown keeps its full reserve; actual reported token estimates are distinct from
reserves/invoices. Keep secrets in root-owned environment files, private captures
outside Git with restrictive permissions, and encrypted/provider-protected disks
and backups. No cloud deployment, paid call or campaign occurs in this task.

## Cohorts and analysis

The original hypothesis remains whether structured evidence-level elicitation
improves probability accuracy/calibration over Direct. Primary paired Brier is
v2 raw minus Direct; existing secondary metrics and source/outcome gates stay.
All subsequent explicitly enrolled cloud-news-v1 observations form this separate
cohort. They do not retroactively relabel the legacy no-news pilot or reset the
original planned100-game study. The legacy target remains unfulfilled/unchanged.
If a news campaign is later authorized, prespecify its own first100 eligible pairs
by T then game ID and report it separately; never silently pool incompatible
protocols, tune to outcomes, or stop on favorable scores. No such campaign is
activated here. One future authorized cloud integration game is not skill evidence.
