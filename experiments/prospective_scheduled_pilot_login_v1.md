# Scheduled pilot login persistence: deployment note v1

The original tested single-game worker/protocol/configuration remains frozen at
`bdc7bce`. Direct `launchctl bootstrap` registers jobs in the current GUI session;
for automatic login/reboot loading, also install byte-identical copies of the
two existing plists in the current user's `~/Library/LaunchAgents` directory.
Commit this deployment helper/note before writing there. This does not alter job
identity, schedule, source policy, paid limits, packet hash or any method.

Only copy files whose hashes and labels match the private immutable installation
audit. Never overwrite a different agent. Preserve the original private plists
and every source/paid claim. The already loaded jobs are not bootstrapped again.
On login, RunAtLoad checks the same absolute UTC/deadline/claims: a missed capture
is recorded missing, and uncertain paid requests are never repeated.

Completed workers unload their own labels. Persistent files can remain until the
operator removes the two exact hash-verified LaunchAgent files after completion;
if another login loads them first, completion/UTC guards make them no-ops and
they unload again. This cannot enroll another game or run an annual campaign.
Keep the host awake and logged in through the target window: login persistence
is not a guarantee of wakeup, network access or successful evidence collection.

The helper installs no secrets and makes no source or provider requests. A real
logout/reboot is not performed during deployment validation; restart safety is
tested with persistent fixtures and the OS startup probes. Record actual status
as scheduled/pending until capture and native forecast seals exist.
