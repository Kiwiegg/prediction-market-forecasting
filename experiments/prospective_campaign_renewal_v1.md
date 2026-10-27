# Prospective campaign renewal v1 — operational amendment

This amendment changes authorization administration only. Freeze it, its migration
policy and operational assets before a renewal. It changes no forecasting method,
evidence cohort, cutoff, metric, market rule, budget ceiling or paid retry rule.
The original cloud-news pilot and historical/missed attempts remain immutable.

## Separate inspection, renewal, expansion and activation

`renewal-plan` is a GET-only restore of the original idle R2 checkpoint, followed
by read-only authorization-chain/ledger validation and private source/forecast
replay. It acquires no owner, writes no remote objects, enrolls no game and grants
no authorization. It reports the exact predecessor digest, current scope, expiry,
ledger digest/reserved total, denial digest/count, source/target asset hashes and
replay result. Captured files and the remote root must remain unchanged. An
unknown registry, broken chain, active owner or inconsistent snapshot fails closed.

`renew` requires an explicit authorized-campaign confirmation, exact latest
predecessor SHA-256 and a new future expiry no more than 31 days from execution
and later than the previous expiry. It appends a numbered immutable amendment
under the existing exclusive R2 owner and lock. Original `campaign.json`, prior
amendments, store UUID, jobs, caches, requests, reservations and circuits are not
edited or reset. Renewal preserves max_games, allowlist, automatic enrollment,
mode and budget ceilings exactly. It does not authorize additional games. A stale
predecessor or uncertain persistence must not trigger automatic renewal retry.

Expired records are readable for audit/renewal, never usable for paid execution.
Every paid reservation and post-checkpoint gate continues to require a current,
unexpired, registry-matching campaign. Renewal does not clear provider denials or
make uncertain claims reusable. There is no grace period for expired paid sends.

`expand` remains a separate explicit approval after successful genuine live
primary-pair replay and current renewed authorization. A proposed cumulative cap
of 30 includes the original pilot; chronological automatic enrollment requires
its own explicit flag. Caps remain $50 cumulative/$1.35 per game, including the
original $0.178331 reservation, without refunds. Enrolled attempts are not the
same as primary-eligible pairs. Live activation remains a separate repository
flag/manual-live decision. No activation is authorized by this amendment.

## Narrow operational registry transition

The preserved predecessor registry is
`prospective_github_actions_before_renewal_v1_assets.json`, SHA-256
`d0ddb612029c3435f0037f7eeeedf2bd6e06fb16246cb5abe98cf45b383b865b`.
`prospective_campaign_renewal_v1.json` lists the only operational files that may
change or be added. Existing assets cannot disappear. All other entries remain
identical, especially campaign configuration and the transitive cloud-news
registry binding frozen methods/evidence. Current assets must match their
committed registry before network administration or live execution.

An old-registry approval does not automatically become current. A renewal that
migrates it requires an additional explicit operational-migration confirmation.
The amendment records the exact source/target registry hashes, policy hash,
protocol ID and predecessor approval hash. Each chain node is checked for store,
configuration, limits and transition semantics; migrations in the wrong direction
or without this proof fail closed. No alternative unknown registry is accepted.
Subsequent same-registry renewal needs no migration override. Future operational
changes need their own reviewed transition; this is not a general asset bypass.

## Validation and deployment

Offline fixtures must cover expired/renewed payment gates, stale approval hashes,
invalid expiry/confirmation, immutable chains, duplicate claims, denial retention,
unchanged native replay after restore, chronological cumulative enrollment and
unchanged global/per-game budgets. The protected Actions `renewal-plan` mode can
verify the actual private pilot without provider keys or paid/source requests.
Actual renewal/expansion remains operator-authorized and is not part of no-cost
validation. See the deployment guide for dispatch commands and recovery rules.
