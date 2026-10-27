# Bounded news-v1 campaign preparation — not authorization

Prepared after successful private pilot replay. **Not activated.** Target: 30 primary-eligible Direct/v2 pairs in `news_v1_separate_from_legacy_100`, including the first eligible pilot. This is an interim news-v1 report target, not a redefinition/restart of the original 100-game study. Do not pool incompatible cohorts or tune methods against these outcomes.

## Existing safeguards reviewed

- `actions_campaign.py:first_success()` requires genuine live-mode private replay and eligible frozen/forecast records. This prerequisite passed for `401909877`; LEAP v1 was independently verified too.
- `enroll_catalog()` sorts verified fixtures by fixed target then game ID; requires a saved hashed catalog, regular-season guard, admission before collection starts, dispatch horizon, remaining session lifetime, allowlist/automatic authorization, and cumulative enrollment cap. Exclusions remain visible. Forecasts, market prices and outcomes are not selection inputs.
- Approval binds store UUID, configuration and frozen asset registry hashes, expiry, $50 cumulative ceiling and $1.35/game. `expand` must increase the cumulative game cap; it cannot reset the spend ledger or exceed those ceilings. Research/forecast caps stay $0.35/$1 respectively.
- The R2 conditional root owner serializes private workers. SQLite's transaction/unique request identity, filesystem locks, native immutable attempts, and checkpoint-before-send reservation preserve at-most-once requests. Interrupted/uncertain claims keep reservations and cannot be resent automatically. Paid sends are serialized even across overlapping games.
- Persistent provider-denial journals stop new paid sends; no automatic retry after a denial. Only the preauthorized NBA schedule-403 fallback is exempt; independent market failure stays missing and does not invalidate the primary pair.
- No-cost admin modes do not receive Brave/Anthropic keys. Main/ref, reviewed full SHA, environment secrets and explicit activation gates remain. Scheduled live work requires the live flag and unexpired private campaign approval. Source retrieval, freeze and sealing deadlines remain fixed at T, T+5 and T+15.

These are code/replay checks, not a multi-game live concurrency or crash test. No such live stress test occurred in this task.

## Staged scope and cost

Initial proposed expansion: **30 cumulative enrolled attempts**, including the pilot, with chronological automatic enrollment. That permits 29 more attempts, not a guarantee of 30 eligible pairs. Native enrollment caps count jobs, not successful forecasts. Do not label an enrollment cap as a primary-eligible stopping rule.

After all authorized attempts are terminal, review capture/primary counts and technical exclusions, without selecting on scores or market direction. If fewer than 30 pairs succeed, an additional **explicit** amendment can increase the cumulative enrollment cap by the exact shortfall, with an absolute planning cap of **37 total attempts**. Do not preauthorize 37 and assume the current worker will stop at 30 successes: it has no success-target enrollment stop. Do not extend while earlier attempts are pending if that could over-enroll the target. If failure exceeds the bounded scope/budget, report incomplete coverage rather than extending automatically.

| Scenario | Cumulative amount, including pilot | Interpretation |
|---|---:|---|
| Current reservation | $0.178331 | committed ledger consumption |
| 30 attempts, remaining 29 at full $1.35 | $39.328331 | conservative reservation envelope |
| 37 attempts, remaining 36 at full $1.35 | $48.778331 | room for at most 7 failed attempts while targeting 30 pairs |
| 38 attempts, remaining 37 at full $1.35 | $50.128331 | exceeds $50; not covered by this conservative plan |
| 30 attempts repeating pilot reservations | $5.349930 | descriptive projection, not a bound |
| 30 attempts repeating pilot configured-rate usage | $1.338570 | token/search estimate, not ledger capacity |
| 30 attempts repeating pilot published-rate usage | $0.580530 | before credits, invoice unverified |

Observed projections have **zero news extraction** and only three usable groups per LEAP method. Games with dated news and extra group calls will cost more. Do not reduce reservations based on this one cheap pilot. Native ledger enforcement remains authoritative; no budget refund/reset or permission to spend $50 is issued by this plan. Unknown usage keeps its reservation. Any future expansion must explicitly retain the already consumed $0.178331.

## Activation blocker

The persisted single-game approval expired **2026-10-27T00:30:00Z**. `CampaignState.expand()` calls `campaign()` before writing an amendment, and `campaign()` rejects an expired approval. There is currently **no supported CLI command that safely renews this expired approval**. Re-running `authorize` would conflict with the immutable original and is not a renewal procedure.

A separately reviewed fix must permit explicit authorized renewal from a hash-verified expired predecessor without allowing expired paid sends; preserve original approval, amendment chain, store, jobs, request identities, reservations and circuits. If that fix changes hash-bound operational assets, it must include an explicit approved registry/authorization migration. Do not delete/reset the store, edit private approval bytes, change cache paths or create a fresh budget to bypass this blocker. This task intentionally leaves the frozen operational assets unchanged and grants no renewal permission.

## Activation commands after review

**Do not run this block yet.** First repair/review the expired-approval renewal path as above and obtain explicit authorization for the new bounded campaign. The block below uses the existing workflow inputs; as of this audit, its `expand` step will fail on expiry. If the reviewed repair exposes a distinct renewal command, use that documented command before expansion; no such command exists today.

Substitute the full reviewed main commit and a deliberately approved future UTC expiry (within 31 days). The following shell commands are exact CLI syntax, with required operator-provided values:

```sh
export NBA_REVIEWED_COMMIT='FULL_REVIEWED_40_CHARACTER_MAIN_COMMIT'
export NBA_AUTH_EXPIRY='APPROVED_FUTURE_UTC_TIMESTAMP'
test "${#NBA_REVIEWED_COMMIT}" -eq 40

# Keep paid mode disabled while checking persisted authorization.
gh variable set NBA_ACTIONS_LIVE_ENABLED --repo Kiwiegg/prediction-market-forecasting --body false
gh variable set NBA_ACTIONS_REVIEWED_SHA --repo Kiwiegg/prediction-market-forecasting --body "$NBA_REVIEWED_COMMIT"

# Only after the expired-approval renewal blocker is resolved and approved:
gh workflow run prospective-nba.yml --repo Kiwiegg/prediction-market-forecasting --ref main \
  -f mode=expand -f expires="$NBA_AUTH_EXPIRY" -f game_limit=30 -f automatic_enrollment=true
gh run list --repo Kiwiegg/prediction-market-forecasting --workflow prospective-nba.yml --limit 5
# Wait for successful expansion; inspect its run before dispatching status.
gh workflow run prospective-nba.yml --repo Kiwiegg/prediction-market-forecasting --ref main -f mode=status
```

Verify the persisted amendment's predecessor/hash binding, expiry, cumulative max_games=30, automatic flag, unchanged $50/$1.35 ceilings, existing pilot, ledger total, no unresolved owner/denial, and no duplicate claims. A green workflow alone is insufficient; inspect its sanitized status. If anything fails, leave paid mode disabled.

**Only after explicit paid activation approval** and successful checks:

```sh
gh variable set NBA_ACTIONS_LIVE_ENABLED --repo Kiwiegg/prediction-market-forecasting --body true
gh workflow run prospective-nba.yml --repo Kiwiegg/prediction-market-forecasting --ref main -f mode=live
# Existing cron then dispatches the same bounded campaign; no per-game cron needed.
```

Monitor with `gh run list --repo Kiwiegg/prediction-market-forecasting --workflow prospective-nba.yml --limit 10` and the existing status/replay modes. Do not queue admin runs behind a healthy time-sensitive capture just to inspect it. Disable future sends with `gh variable set NBA_ACTIONS_LIVE_ENABLED --repo Kiwiegg/prediction-market-forecasting --body false`; this does not cancel or revoke an already-running authorized worker. Do not kill a healthy active worker merely for status; interruptions require the existing exact-owner recovery review and never permit resending uncertain requests.

## Operational bottlenecks and monitoring

- **Timing:** GitHub cron at UTC minutes 7/27/47 can start late or be dropped. Checkout/dependency installation/full checkpoint restore add latency. Workers run up to 165 minutes within a 190-minute job. Lookahead/session-deadline handoffs can exclude games near worker boundaries. Late admission remains missed, never backfilled. See [GitHub scheduling caveat](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).
- **Overlap:** bounded evidence/market pools overlap games, but paid sends and checkpoint writes serialize. Several identical targets may compete for the T+5/T+15 deadlines. The single pilot's 37.4-second inference orchestration does not establish peak capacity.
- **R2:** every dispatch restores the full manifest/blob set; immutable captures, checkpoint manifests and journals accumulate. The configured local snapshot ceiling is 256 MiB. This audit verified restore integrity, not 30-game storage growth or account billing. Monitor manifest bytes/object counts, restore time and storage request volume before the next stage; preserve claims/raw evidence rather than pruning to pass limits. [R2 standard pricing](https://developers.cloudflare.com/r2/pricing/) is $0.015/GB-month, $4.50/M Class A and $0.36/M Class B operations before free allowances; no new paid infrastructure is required by this plan, but zero storage cost is not guaranteed.
- **API/rates:** 29 additional games could use up to 58 Brave searches, 116 article retrievals, 29 extraction calls and 261 forecast calls (9/game). No live rate-limit stress test was run. Article eligibility was the pilot's weak point: no dated article reached extraction. Provider failure must reduce coverage rather than trigger retries or loosen sources.
- **Discovery and recovery:** daily catalog slots and source-denial circuits are durable; a failed/uncertain slot is not silently retried. A killed workflow can leave a non-expiring R2 owner, which blocks safe progress until explicit recovery. Check both Actions failures and missed expected runs; workflow success notifications alone do not detect absent cron execution.
- **Daily audit:** track attempted/captured/primary-eligible counts separately; stage failures and exclusion reasons; method-specific coverage; matching hashes; source/news/submission missingness; market missingness; cumulative reserves versus token estimates; outstanding owner and denial journals. Do not inspect outcomes to choose which games to collect. Final scoring waits for verified outcomes under the frozen evaluation protocol.

Readiness: first-pilot data integrity and all three methods **validated live**; 30-game authorization/renewal **blocked**, multi-game live capacity and successful news extraction **unvalidated**. No paid or automatic campaign activity was started by this task.
