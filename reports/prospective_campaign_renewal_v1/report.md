# Campaign renewal v1 validation

2026-10-27. **Implemented and tested; not activated.** Baseline `7b98f1838c6f46f1637ba6ce65306b27f35d1d0b`; implementation `19c3d0cbc680d5caa38ee06019916e40a9d0b7f6`.

The expired-authorization blocker is resolved in code. `renewal-plan` inspects an
expired approval without granting authority. `renew` appends an explicitly approved
renewal preserving scope and spending. `expand` remains a separate approval to
increase the cumulative game cap. Paid sends still reject expired or mismatched
authorization; no timing, model, evidence or scoring rules changed.

## Private R2 validation actually performed

[GET-only renewal-plan run 40501209408](https://github.com/Kiwiegg/prediction-market-forecasting/actions/runs/40501209408)
passed on the implementation commit. [Sanitized result](private_plan.json):

| Check | Actual result |
|---|---|
| Original store identity | verified, UUID not published |
| Existing approval | expired 2026-10-27 00:30 UTC |
| Authorized scope | game `401909877` only, max_games=1, automatic=false |
| Original spending | 9 claims, **$0.178331 reserved** |
| Ceilings | **$50 cumulative / $1.35 per game**, unchanged |
| Denial-circuit entries | 0; original raw error records preserved |
| Captured files checked | **296**, all unchanged |
| Private native source/forecast replay | passed; genuine live primary pair verified |
| Remote writes / new authorizations / paid calls | **0 / 0 / 0** |

The checkpoint remains
`ad640327ecee31d1c07bfdc77888cc51a83af987845da23187743617889db191`,
identical to the first pilot's saved audit. The shared packet remains
`e7b0dc9502a0f374f6805bfa0ad16a947a4ce6d1aeff09d6d3f5cb09503c27de`.
The complete source captures, native caches, prior approval and request ledger
were read/replayed, not rewritten. R2 owner acquisition was unnecessary; the
inspection required an idle root and checked it remained unchanged.

Exact current approval digest for a separately approved renewal:
`0789a7fe557a585cdfb6facfd4d42c8b38b280be17124bfe0628bed46c9c5333`.
Inspect a fresh plan before dispatch if any authorization may have changed.

## Authorization and operational migration

The original registry is preserved byte-for-byte at
`experiments/prospective_github_actions_before_renewal_v1_assets.json`:
`d0ddb612029c3435f0037f7eeeedf2bd6e06fb16246cb5abe98cf45b383b865b`.
The reviewed replacement registry is
`0092b665df1319d076d66dff9f3ecbfc023f073382d4ff0224b5d5606d9c3913`.

[Protocol](../../experiments/prospective_campaign_renewal_v1.md) and
[file allowlist](../../experiments/prospective_campaign_renewal_v1.json) constrain
the transition to operational workflow/authorization/deployment files and their
tests/documentation. No original registry entry can disappear; the campaign
configuration and transitive frozen evidence/method manifest stay identical.

Renewal requires explicit approval, a matching predecessor digest, a later future
expiry within 31 days and explicit acceptance of this operational migration. It
records the source/target registry hashes and policy digest in a new numbered
amendment. The original approval and every predecessor remain unchanged. Unknown
registries, broken/noncontiguous chains and scope changes disguised as renewals
fail closed. Same-registry future renewal requires fresh approval/expiry but no
registry override. Stale predecessor reuse fails rather than duplicating records.

Renewal retains the one-game allowlist and automatic=false. It cannot enroll a
new game, clear a denial, reuse an old request identity, or refund a reservation.
Expansion requires current authorization and the genuine primary-pair gate. A
30-game expansion is **30 cumulative attempts including the pilot**, with
chronological selection; it does not guarantee 30 primary-eligible pairs. The
initial 30-attempt conservative envelope remains $39.328331 including the pilot.
No amendment or enrollment was issued in this task.

## Tests and preservation

- Complete suite: **292 tests passed** in 82.628 seconds; 13 new renewal tests.
- Clean archive of the implementation commit: new renewal tests passed, Actions
  registry validation passed, cloud-news mock replay passed, and sanitized pilot
  summary replay passed. [Validation metadata](validation.json).
- Actual source/forecast private replay passed in the protected Actions runner;
  its Brave and Anthropic environment variables were empty.
- Workflow passed actionlint; local committed-asset validation also passed.
- The only changed original files are the Actions workflow, deployment guide,
  operational registry and three Actions administration modules. All **7,844**
  protected data/prompt/prior-report/experiment files checked remain unchanged,
  including all **7,411** historical dataset files. Previous pilot report and
  immutable records remain intact.

Tests cover explicit confirmation/migration, future expiry boundaries, expired
live sends stopping before HTTP, expiry during durable reservation, stale
predecessors, repeated same-registry renewal, retained denial/unknown claims,
duplicate request rejection, cumulative budgets, separate 30-job chronological
enrollment, hash-chain/registry corruption, read-only remote planning, and native
forecast replay after renewal plus checkpoint restore. Mock success is not used
as evidence that the real primary-pair gate passed; that was separately verified
from the private live pilot.

## Operator sequence — not executed

The full final main commit supplied with this delivery must be set as
`NBA_ACTIONS_REVIEWED_SHA` before dispatch. The validation run used the implementation
commit above; a report-only successor does not change the operational registry.
Keep live forecasting disabled while reviewing. These commands are templates for
**separate explicit approval**; choose an approved UTC expiry within 31 days.

```sh
export GH_REPO='Kiwiegg/prediction-market-forecasting'
export NBA_REVIEWED_COMMIT='FULL_FINAL_REVIEWED_40_CHARACTER_MAIN_SHA'
export NBA_AUTH_EXPIRY='APPROVED_FUTURE_UTC_TIMESTAMP'
export NBA_PREDECESSOR_SHA='0789a7fe557a585cdfb6facfd4d42c8b38b280be17124bfe0628bed46c9c5333'
gh variable set NBA_ACTIONS_REVIEWED_SHA --body "$NBA_REVIEWED_COMMIT"

# Fresh GET-only inspection, no authorization or provider calls.
gh workflow run prospective-nba.yml --ref main -f mode=renewal-plan
# Wait for success and confirm predecessor/ledger before proceeding.
gh run list --workflow prospective-nba.yml --limit 5

# 1. Only after explicit renewal/migration approval; same one-game scope.
gh workflow run prospective-nba.yml --ref main -f mode=renew \
  -f predecessor_sha256="$NBA_PREDECESSOR_SHA" -f expires="$NBA_AUTH_EXPIRY" \
  -f accept_operational_migration=true

# 2. Wait for renewal success. Only after separate 30-game expansion approval:
gh workflow run prospective-nba.yml --ref main -f mode=expand \
  -f expires="$NBA_AUTH_EXPIRY" -f game_limit=30 -f automatic_enrollment=true

# 3. After each prior workflow finishes, verify persisted state and replay.
gh workflow run prospective-nba.yml --ref main -f mode=status
gh workflow run prospective-nba.yml --ref main -f mode=replay

# 4. Only after explicit paid activation approval and successful persisted checks:
gh variable set NBA_ACTIONS_LIVE_ENABLED --body true
gh workflow run prospective-nba.yml --ref main -f mode=live
```

Do not queue the whole block blindly. Inspect each completion, approval hash,
scope, expiry, $0.178331 consumed, unchanged ceilings, denial state and replay.
Renewal/status do not require LIVE_ENABLED=true. If approval changed, obtain a
fresh predecessor; if an operation is uncertain, preserve the exact owner and
follow recovery review rather than retrying. The deployment guide contains the
full recovery instructions. No bootstrap, new store or ledger reset is needed.

## Remaining validation

Actual immutable renewal/expansion writes against R2 were **not executed**, because
this task supplies their implementation and commands without a chosen/approved
future expiry or permission to authorize more paid games. Those transitions were
tested with conditional-write/checkpoint fixtures, including restore. The real
R2 predecessor, eligibility prerequisite and preserved ledger were verified
read-only. Live forecasting remains false; no automatic enrollment or new paid
game authorization was activated. No new news research, source collection or
model inference occurred.
