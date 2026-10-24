# Scheduled prospective pilot: operational amendment v1

Commit this protocol, scheduling configuration, tested implementation and hash
registry before live discovery or installation. This explicitly authorizes one
new prospective game and a macOS launchd job pair; it does not authorize the
100-game campaign. No forecasting prompt/model/settings, evidence schema, prior,
LR mapping, aggregation, historical data or evaluation rule changes.

## Enrollment and bounded discovery

Use the existing NBA-preferred discovery and authorized ESPN fallback. Enroll the
first upcoming regular-season fixture by T−24h then game ID whose planned T−24h
minus120s launch is at least300s in the future. The rule is independent of results,
market prices and model forecasts. Preserve both-team corroboration and all
discrepancies. Freeze game ID, teams, neutral designation, scheduled tipoff, cutoff,
job identity, asset hashes, authorization and initial discovery sources.

Exactly one new enrollment discovery is authorized. One fresh targeted schedule
revalidation is permitted for each of the evidence and benchmark tasks. These
are new contemporaneous validations, not retries of a failed request. Each URL
gets at most one HTTP attempt within its phase; no autonomous discovery retries.
Only the original primary NBA schedule403 can use the existing ESPN fallback.
Preserve every earlier journal; bind their hashes in this authorization. No other
old denial is superseded. ESPN/other-source or paid access denial stops further
network/paid work under a new permanent journal. Successful forecasts completed
before a subsequent market failure are not retroactively invalidated.

## OS timers, locks and restarts

Create two user launchd calendar agents for this single fixed game: evidence at
target−120s, independent market at target−60s. Store plist files and installation
audit in the private immutable job directory. No credentials in arguments,
plists or Git. Host-local calendar components are derived from absolute UTC
instants; save timezone/offset. launchd runs on login/wake and calendar triggers.
Absolute year/UTC/window guards prevent an annual calendar match or timezone
change from becoming another eligible run. Keep the host awake and logged in;
OS suspension, permissions, Internet loss or timezone changes can miss a window.

Persistent job IDs and advisory process locks prevent overlap. Immutable phase
claims are written before network or paid work. Early RunAtLoad invocations are
no-ops; late starts are recorded as missed. Finished tasks request removal of
their own launchd label. A repeated invocation never repeats capture or a paid
request. After interruption, preserve raw sources and mark the phase uncertain.
If a valid packet already froze and inference has not been claimed, it can start
before tipoff; if inference was claimed, only offline native-cache sealing is
permitted. Unknown claims are never resent, including after reboot. No task
changes the registered cutoff, rolls to another game or backfills evidence.

## Evidence first, then inference

Revalidate game/status/teams/venue/regular-season/tipoff immediately before
collection. A change or unavailable confirmation aborts the registered game.
Use the existing statistics and official injury extraction, strict packet
construction and shared snapshot loader. Preserve source clocks, raw hashes,
injury submission states, omissions and source-verification uncertainty. Missing
reports or unlisted players never imply health.

All source retrieval must finish at/before the target. Collection start, snapshot
and packet creation retain the original ±300s rule, including min(snapshot,target)
source cutoff. No post-cutoff retrieval/publication/revision, retrospective
reconstruction or target-game outcome endpoints. A +tolerance wake is not an
authorization for newly retrieved post-target material. Freeze incomplete packets
where possible but never forecast from them. Other failures preserve raw audit.

This pilot collects **no paid news research before freezing**: news is explicitly
not collected, not "no news found". This satisfies the user's requirement that
no paid request precede confirmation of a valid frozen packet. News omission is
visible and is not a change to statistical features or forecasting projections.
Brave/article usage is zero; authorized maxima remain two/four, not quotas.

After bundle, timing and readiness verification, run unchanged Direct/v1/v2 from
exactly the same parent hash, using original caches and no source retrieval.
Both alpha variants share native group observations. Start promptly; every
request/response and final seal must precede tipoff. Missing evidence skips,
provider failures and insufficient abstentions retain original semantics.
One persistent ledger caps this job at20 Anthropic requests and $1 conservative
pre-call reservations. No paid retry. Check journals and tipoff before every
request. Credentials may be loaded from the operator's trusted local `.env`
without logging values. No outcome/price/evaluation file enters model context.

## Independent benchmark

A separate executable/process and output directory reads only registered schedule
metadata. It revalidates that fixture, fetches the original Kalshi milestone,
and sends the home-YES market request near target−5s after a bounded wait. This
five-second lead allows response time; record the actual response clock, not an
asserted exact-cutoff timestamp. Reuse the original quote/mapping validator and
preserve sources, bid/ask/spread/midpoint/hash. Response completion must remain
in [target−300s,target]. If late, unavailable, denied or invalid, retain missing;
no later price substitution or backfill. Quote refresh age remains unknown.

No market record is read by evidence or forecasting. Market absence never removes
an otherwise valid Direct/v2 primary pair. A market403 stops future paid work
under the existing non-schedule-denial policy but does not erase sealed forecasts.
Final outcomes/evaluation are not scheduled; original postgame gating remains.

## Validation and reporting

Run full offline tests and prior private/public replay before installation.
Test UTC/DST/window arithmetic, changed/canceled fixtures, delays, restart claims,
locks, source missingness, market failure, shared parent identity, denial/budget
guards and immutable replay. Save sanitized pending job/timer configuration,
installation status and validation metadata. If execution is future, report
**scheduled/pending**, never completed or successfully forecast. Raw responses,
credentials, claims and private caches remain outside Git. No automatic Git
publishing, long-running scheduler service or recurring game enrollment.
