# Source-session clock repair v1 — one explicit discovery rerun

The operator authorized fixing and rerunning the failed discovery. This narrowly
scoped operational amendment preserves all timing, research, forecasting and cost
rules. No historical data, frozen method, old capture or old stage is rewritten.

## Verified incident

Run40321487047, attempt1, commit a99b24a9021a833c1899041048fc12ec7636553b
failed before any source request. The GET-only audit40323099217 verified UUID and
checkpoint hash48ba34a01f6678f6b2233929f37255804ea9e50a590e1161b31c82821be6971f.
The only failed stage was catalog/2026-10-26, with exact error
`AttributeError: 'SourceBudget' object has no attribute 'clock'`. There were no
source metadata, denial circuits or paid claims. SourceBudget now exposes the
state's existing clock to the inherited StudySession constructor. No clocks,
deadlines, source rules or generation settings change.

## Explicit repair-discover mode

This mode is admin-only, main-only, reviewed-SHA pinned, without model/search
secrets. It first confirms through GitHub that the exact old run/attempt/commit
completed with failure. It then validates the original UUID, exact audited
checkpoint hash, owner run, failed stage, exact exception, zero source requests,
zero paid claims and no circuits. Any discrepancy stops recovery. This specific
repair expires after2026-10-26UTC and cannot be generalized to another failure.

Existing CAS recovery writes an immutable recovery record and releases only the
exact old owner. It does not erase claims, failed stages, budgets or old snapshot
history. The replacement stage is catalog/2026-10-26-clock-v1, linked by the
recovery's original snapshot/owner. It gets one real discovery attempt; the old
stage remains failed. This is the first source acquisition after a constructor
failure, not a retry of denied or uncertain HTTP requests. If the new stage fails,
it cannot be retried automatically. Existing access-denial/fallback rules apply.

Normal discovery may reuse a completed replacement stage on that UTC day. A
failed/claimed replacement remains blocked. No automatic owner takeover is added.
Live mode remains disabled throughout repair and discovery. New public logs contain
validated schedule projections/decisions and safe authorization summaries only,
never publisher bodies, headers, credentials, outcomes or market data.

## Immutable replay compatibility

The original cloud asset registry is archived byte-for-byte at
prospective_cloud_news_v1_initial_assets.json, SHA-256
72a6224febba31adcf752f79a8b65d110d9d2a7101b36d0938ef064a3ab035e9.
Existing public captures retain that identity and are never regenerated. Public
replay accepts that exact archived registry only when all its other original
assets remain byte-identical. The repaired cloud_prospective.py is authenticated
by the current committed registry. Native prompt/request/packet/aggregation checks
remain unchanged. Existing private capture jobs still use their original pinned
checkout; this operational repair does not migrate them. No actual game job or
campaign approval existed in the failed remote catalog checkpoint.
