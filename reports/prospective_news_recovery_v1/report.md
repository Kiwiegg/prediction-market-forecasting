# Blocked prospective campaign: audit and safe recovery

**Live collection is disabled.** The terminated worker's exact R2 owner was
conditionally released; the checkpoint, original authorizations, all reservations
and all three denial circuits were preserved. No article-policy exception was
adopted, no new game authorization was issued, and no source/search/model request
was made during this recovery task.

**Resume is still blocked:** the saved AP response does not pass the proposed
conservative ordinary-article403 classifier. Human review of the already-captured
response is required; do not fetch the denied URL again or force policy adoption.

## Root causes

1. At **2026-10-27 23:31:56 UTC (19:31:56 EDT)** an allowlisted AP article returned
   HTTP403. The original `SourceBudget.stop` treated every nonbenchmark source
   denial as globally fatal. It preserved `host:apnews.com`, then opened global
   `network` and `paid` circuits. This was a publisher response, not an Anthropic
   or Brave credential denial; every saved paid-provider response was HTTP200.
2. The failed worker retained its durable owner, as designed to prevent uncertain
   paid retries. Later scheduled workers could not acquire that owner. Recovery
   must verify termination, exact ownership and claims, not use a lease timeout
   or reset the store.
3. The separate `'SourceBudget' object has no attribute 'clock'` record is the
   **2026-10-26 12:18:49 UTC historical catalog failure**, already fixed in
   `d65a2e1` before the successful pilot. Current `SourceBudget.__init__` supplies
   `state.clock`; real session constructors and one-shot transport clock tests
   pass. The new article budget inherits the same clock. The historical failed
   row and its explicitly authorized repaired catalog remain untouched; no old
   discovery request was retried in this task.

## Exact paid-claim accounting

[All 17 claims](paid_claims.csv) reconcile to immutable receipts, exact saved
request identities, hash-verified response bytes and **HTTP200** responses.
There are **zero paid claims without a saved response**. `claimed` remains the
permanent no-resend ledger state; it does not mean those HTTP operations are
still running. Conservative reservations are retained without refund/reset.

| Kind | Claims | Reserved USD | Reported input/output tokens | Configured-rate usage estimate |
|---|---:|---:|---:|---:|
| Brave search | 9 | 0.090000 | query billing, no model tokens | 0.090000 |
| Original pilot forecasts | 7 | 0.158331 | 8,661 / 138 | 0.024619 |
| New factual extraction | 1 | 0.034170 | 624 / 433 | 0.008367 |
| Total | **17** | **0.282501** | **9,285 / 571** | **0.122986** |

The original pilot's **$0.178331** remains included. The eight later paid claims
(seven searches and one extraction) reserved **$0.104170**. No new probability
forecast was generated after the pilot. Remaining reservation headroom is
**$49.717499** under the unchanged $50 campaign ceiling and $1.35/game ceiling.
Dollar amounts are USD. Usage estimates use the frozen configured rates,
including their differing method rates; provider invoices/credits were not
inspected. They are not billed-cost claims. Zero-cost article claims are retained
separately in the sanitized audit and do not count as paid-provider requests.

## Enrolled games and unrecoverable cutoffs

[Per-game inventory](games.csv). The deeper audit found **seven** enrolled jobs:
the completed pilot, four partial collections, and two unstarted jobs that were
not visible from the earlier stage-only inspection. All six unfinished jobs have
passed both freeze and forecast deadlines. Their captured data can be replayed
for audit, but none can become an eligible prospective forecast now.

| Game ID | Away at home | Recorded T−24h cutoff UTC | Reserved USD | Disposition |
|---|---|---|---:|---|
| 401909877 | Brooklyn at Boston | Oct 26 23:30 | 0.178331 | completed original pair, preserved |
| 401909886 | New York at Chicago | Oct 28 00:00 | 0.054170 | partial, including one completed extraction; expired |
| 401909887 | Houston at Milwaukee | Oct 28 00:00 | 0.010000 | partial news acquisition failed on AP403; expired |
| 401909888 | Golden State at Minnesota | Oct 28 00:00 | 0.020000 | partial; expired |
| 401909889 | Denver at New Orleans | Oct 28 00:00 | 0.020000 | partial; expired |
| 401909890 | San Antonio at Utah | Oct 28 01:00 | 0 | enrolled, collection never started; expired |
| 401909891 | Oklahoma City at Dallas | Oct 28 01:30 | 0 | enrolled, collection never started; expired |

All cutoffs are in 2026. Four partial jobs have no frozen packet or forecast;
two jobs have no source stages. Preserve every original ID, failed/absent stage,
raw capture, claim and reserved amount. No retrospective freezing, paid replay,
request resend or market backfill is permitted. The original 30-game cap counts
all seven enrollment slots: **23 more games can be enrolled, allowing at most
24 successful pairs** without a separately approved expansion. No such expansion
was performed. The original expiry remains **2026-11-03T12:30:00Z**.

## Private verification and owner recovery

- [Initial full private audit 40701082766](https://github.com/Kiwiegg/prediction-market-forecasting/actions/runs/40701082766)
  reconciled the 17 claims and replayed all available saved stages.
- [Reviewed pre-release audit 40723506300](https://github.com/Kiwiegg/prediction-market-forecasting/actions/runs/40723506300)
  separately verified owner-release prerequisites and reported policy-adoption
  failure. [Saved pre-release audit](pre_release_audit.json).
- [Exact-owner release 40724586144](https://github.com/Kiwiegg/prediction-market-forecasting/actions/runs/40724586144)
  succeeded. [Sanitized result](owner_release.json): owner released, snapshot
  preserved, circuits not cleared, policy not adopted, paid calls zero.
- [Post-release GET-only verification 40726224030](https://github.com/Kiwiegg/prediction-market-forecasting/actions/runs/40726224030)
  checks the same private checkpoint and corrected public-capture lineage.

The failed run was definitively **completed/failure/attempt1**, at commit
`ba2507a12177811d27e469126d2e54858bca00d1`; its exact owner was
`40600612996-1`. Before any mutation the release reran the audit, matched its
canonical digest, checked the UUID, exact owner digest, checkpoint, ledger,
responses, denial origins and expired partial-game deadlines. It then called the
existing exact-owner CAS recovery with an additional expected-snapshot guard.
The canonical reviewed audit digest is
`058ca50461a068f21765c55e32551dab9203cb50367dc9ab8fce88cb6c3b150d`.
It excludes the artifact file's trailing newline; it is not a blind file hash.

Checkpoint SHA-256 remains
`1aeb0ee7d2fdec42b7d16f2af2d1df3f3afac60dc8272ad8f44258e448534abc`.
All **703 captured files** remain hash-verified and unchanged. The root's store
UUID and snapshot were preserved; only ownership was released, with immutable
R2 recovery/audit attestations appended. Global circuit rows/files remain intact,
as does the permanent denied-host record. No circuit exception is active.

The pre-release inspector initially looked for five benchmark revalidation
responses under the claim-slot name rather than their independent `market/raw`
capture directory. That audit lookup was corrected and regression-tested.
Their benchmark stage had already passed private source replay. This affected no
paid accounting or recovery gate; the original signed pre-release audit is kept
unchanged, and the post-release audit supplies corrected source-path accounting.

## Proposed policy and remaining blocker

[Protocol](../../experiments/prospective_news_denial_v1.md),
[configuration](../../experiments/prospective_news_denial_v1.json), and
`news_denial_policy.py` implement a prospective-only amendment, **default off**.
An unambiguously ordinary403 from an approved third-party article is recorded as
unusable evidence; the normalized host (including case/www/default-port aliases)
is never retried. Other eligible sources may continue within existing budgets.
Publication/retrieval clocks, redirect/domain restrictions, exact T cutoff,
verbatim support and missing-player-health safeguards remain unchanged. The
existing extractor, model prompts and three forecasting methods are reused.

Provider/credential/account errors, authentication challenges, HTTP401/407/451,
official/core-source denials, integrity failures and deadline violations retain
fatal behavior. A new denial after an approved historical exception creates a
distinct persistent fatal record; the old `INSERT OR IGNORE` circuit row cannot
mask it. There are no paid or public-request automatic retries.

The actual saved AP403 is nonempty, nontruncated, from an approved article URL,
with no authentication challenge, JSON/API error shape or recognized restriction
marker. It also lacks recognized publisher-denial text. That is **insufficient
for automatic classification**, not proof of an account restriction. No wording
rule was relaxed to make this incident pass. Policy adoption therefore remains
blocked even if its confirmation flag is supplied. Review the preserved response
privately and, if justified, commit a deterministic classification refinement
with offline fixtures/tests and explicit operator approval. Never request the
denied host again to diagnose it. All three original circuits remain fatal until
that independent policy review succeeds.

## Operator-reviewed resume procedure

**Do not enable paid collection yet.** First review the source-classification
blocker above and commit any justified policy refinement without changing frozen
forecasting methods. Set `NBA_ACTIONS_REVIEWED_SHA` to the full reviewed final
main commit provided at delivery. Keep the live flag false. Use GET-only
`audit-nba-recovery.yml -f mode=audit` for paused-state inspection; a release has
already occurred, so do not repeat the owner-release command.

After classification verification and explicit policy approval, the supported
scope-preserving adoption command is:

```sh
export GH_REPO='Kiwiegg/prediction-market-forecasting'
gh variable set NBA_ACTIONS_LIVE_ENABLED --body false
gh variable set NBA_ACTIONS_REVIEWED_SHA --body FULL_REVIEWED_40_CHARACTER_MAIN_SHA
gh workflow run audit-nba-recovery.yml --ref main -f mode=audit
# Inspect results; do not proceed while policy classification remains unverified.

gh workflow run prospective-nba.yml --ref main -f mode=adopt-news-policy \
  -f recovery_audit_sha256=058ca50461a068f21765c55e32551dab9203cb50367dc9ab8fce88cb6c3b150d \
  -f predecessor_sha256=52dd40964f91e29d0ae62f33b599e15d18044ec3fdc26ae7806aa7a377608257 \
  -f confirm_news_policy=true
# Only after successful adoption, one operation at a time:
gh workflow run prospective-nba.yml --ref main -f mode=status
gh workflow run prospective-nba.yml --ref main -f mode=replay

# Only after a separate explicit approval to resume paid collection:
gh variable set NBA_ACTIONS_LIVE_ENABLED --body true
gh workflow run prospective-nba.yml --ref main -f mode=live
```

Wait for and inspect each completion. Do not use a post-release audit digest in
place of the preserved released-audit attestation. If approval/ledger/circuits
changed, stop and obtain a fresh reviewed plan. If the existing expiry has passed,
separately approved renewal is required first. Adoption does not extend expiry,
reset the 30-game count, refund claims or remove any journal. Source-policy
effective time and per-game amendment lineage label only future game cutoffs.
Unknown/denied requests and expired jobs remain nonretryable.

## Validation and limitations

The complete suite passed **307 tests**. Clean-checkout replay, frozen-asset
validation, original sanitized pilot replay, source-clock tests and private replay
passed; workflow YAML passed actionlint. Tests cover exact-owner/snapshot gates,
separate policy approval, denied hosts and aliases, ambiguity/credential handling,
partial/deadline exclusions, budgets, unknown/duplicate claims, immutable restore,
operational hash migration, and a mocked real-transport provider403 after adoption
that stops the next send. Mock calls are not counted as live observations.

Historical datasets, frozen prompts/models/aggregation, earlier reports, native
request caches and original pilot records remain unchanged. The transitive cloud
evidence registry is unchanged; operational registry archives preserve earlier
authorization proofs. No forecasts, outcomes or prices were newly retrieved or
evaluated. Human AP-response classification, actual live operation under the new
amendment, multi-game reliability and future provider availability remain
unvalidated. GitHub scheduling delays can still cause missed windows; this policy
does not extend any deadline or guarantee 30 successful pairs.
