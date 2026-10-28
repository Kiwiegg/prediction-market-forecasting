# Approved policy adoption, collection paused

The operator explicitly approved adoption at reviewed commit
`43ea2d4125e1cfd2214249d8a97e43020ced9cb0`. Paid collection was not authorized.

1. [Fresh GET-only recovery audit 40754513428](https://github.com/Kiwiegg/prediction-market-forecasting/actions/runs/40754513428) passed: idle original store, 17 claims with known HTTP200 responses, unchanged ledger/circuits and all seven available job replays. Classification/recovery preconditions passed before mutation.
2. [Adopt-news-policy 40755133266](https://github.com/Kiwiegg/prediction-market-forecasting/actions/runs/40755133266) succeeded on the reviewed commit. It used the existing released-audit attestation `058ca50461a068f21765c55e32551dab9203cb50367dc9ab8fce88cb6c3b150d` and exact campaign predecessor `52dd40964f91e29d0ae62f33b599e15d18044ec3fdc26ae7806aa7a377608257`.
3. [Status 40757698617](https://github.com/Kiwiegg/prediction-market-forecasting/actions/runs/40757698617) passed: seven enrolled jobs, unchanged USD0.282501 reservation and new `recovery_policy` authorization linked to that predecessor.
4. [Private replay 40758625180](https://github.com/Kiwiegg/prediction-market-forecasting/actions/runs/40758625180) passed for all seven jobs. The original completed pilot reproduces its shared packet and all three forecasting methods. The six unfinished jobs remain failed/absent, not backfilled.
5. [GET-only preserved-response verification 40758918594](https://github.com/Kiwiegg/prediction-market-forecasting/actions/runs/40758918594) passed: policy authorization present, idle owner, 706 hash-verified files, unchanged request-ledger/circuit hashes, and zero paid/source calls or writes during review. Sanitized proof: [post_adoption_profile.json](post_adoption_profile.json).

New authorization hash:
`50367c8444831c6d766d8b1d15849aa20274b460624af76b5f2b0c7117435072`.
It preserves cumulative max_games=30, campaign USD50, per-game USD1.35 and expiry
`2026-11-03T12:30:00Z`. No original approval, claim, reservation, raw source,
forecast or denial journal was deleted or refunded. The new snapshot is
`03370c827eccb5ad1f000c5080677ff1200096461011f54f0ac57dedfe9f97ad`;
the original snapshots remain immutable. Adoption appends three policy/audit
files rather than rewriting original captures.

The **permanent `host:apnews.com` block remains**. Only the two exact historical
`network`/`paid` circuit bodies are superseded under the linked policy
authorization; their original records are still present. New denials, provider
credentials/account restrictions, official sources and ambiguous responses remain
fatal. No denied AP request was repeated. The existing exact-body/hash binding and
campaign authorization checks enforce the scope; the adopted policy adds no
blanket circuit-clear operation.

Ledger SHA-256:
`1b60b58b84141c6dad7d8a1d37fdd811bba7e18a55bc4bce4aa433084a39ea4e`.
Circuits SHA-256:
`c31c751dc71950a4b1b07d1db664c19f1d1876e21b01ffa9eaff945277725a84`.
These match the pre-adoption audit exactly. The operator's original approval and
retained USD0.178331 pilot reservation are included in the unchanged chain/ledger.

**Collection stays disabled (`NBA_ACTIONS_LIVE_ENABLED=false`).** No live workflow,
new paid authorization, campaign expansion, enrollment or inference was triggered.
Automatic-enrollment permission exists in the old scope, but cannot execute while
the live gate is false. Separately approved activation must use the final reviewed
main commit and still honor expiry, chronology, current budgets and missed windows.
Policy adoption does not itself demonstrate live recovery success. No activation
is necessary to complete the present research paper.
