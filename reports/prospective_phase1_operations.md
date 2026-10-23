# One-game prospective operations

The [precommitted study protocol](../experiments/prospective_phase1_protocol.md) fixes timing, source restrictions, all frozen methods, a future 100-pair sample target and separate evaluation. Phase1 authorizes only one integration pilot. No scheduler or campaign is installed.

```sh
# No network, no credentials or costs.
.venv/bin/python scripts/prospective_study.py --dry-run
.venv/bin/python scripts/prospective_study.py --dry-run \
  --schedule-capture captures/prospective_phase1/discovery_initial
.venv/bin/python scripts/prospective_study.py --mock \
  --output captures/prospective_phase1/mock
.venv/bin/python scripts/prospective_study.py --replay captures/prospective_phase1/mock
.venv/bin/python scripts/prospective_study.py --export-audit captures/prospective_phase1/mock \
  --output captures/prospective_phase1/mock_public
.venv/bin/python scripts/prospective_study.py --replay captures/prospective_phase1/mock_public
# Replay the committed sanitized example independently of private captures.
.venv/bin/python scripts/prospective_study.py --replay reports/prospective_phase1/mock_validation
.venv/bin/python -m unittest discover -s tests -q
```

Live operation requires `BRAVE_SEARCH_API_KEY` and `ANTHROPIC_API_KEY` in the process environment. Existing trusted local `.env` files may be loaded by the operator with shell tracing disabled; never echo or commit values. The command is opt-in and only proceeds if fresh authoritative discovery verifies a game currently inside its fixed ±300-second cutoff window:

```sh
# Only under an active authorization, after protocol commit and passing tests.
.venv/bin/python scripts/prospective_study.py --discover --allow-network \
  --output captures/prospective_phase1/discovery
.venv/bin/python scripts/prospective_study.py --live-pilot \
  --allow-network --allow-search --allow-inference --game-id UPCOMING_ESPN_ID
```

The live output is fixed at `captures/prospective_phase1/pilot`; no alternate directory can bypass its one-pilot registry. An existing output is not overwritten. A permanent access-denial journal blocks subsequent live work under the same authorization, including free fallback requests. Do not remove it to retry. The initial discovery for this task received HTTP403; no additional live requests are authorized by the existing run. A later explicit operator authorization is needed to resolve access and approve another attempt. No code automatically changes hosts or retries denied requests.

An evidence bundle is frozen even if readiness fails, with explicit missingness; no model request follows an off-time or incomplete packet. Native successful/failed responses remain in their original shared caches. If interrupted, preserve the output/claims; do not rerun in a fresh directory or resend an uncertain request. Completed native request records are immutable. Failed methods and source skips remain distinct. The dry run shows query/provider budgets; exact forecast reservation bounds become available from frozen request specifications after collection.

After the active process has stopped, `scripts/prospective_study.py --seal-partial captures/prospective_phase1/pilot` can seal cached work offline, marking claimed-but-unknown requests separately and leaving other groups unattempted. It never resends a request; a seal made after tipoff is explicitly ineligible. A failed attempt is not a new paid retry authorization.

The separate evaluator never supplies data to model context. Run independent market capture before the cutoff, using the same recorded schedule and a distinct output. The market quote must finish in [target−300s,target]; neither late quotes nor historical candles are backfilled. Market capture is **not executed automatically** by the orchestrator.

```sh
# Separate process/directory; public GETs only, no model calls.
.venv/bin/python scripts/prospective_evaluate.py --capture-market --allow-network \
  --schedule captures/SCHEDULE_DISCOVERY --game-id UPCOMING_ESPN_ID \
  --output captures/prospective_market/GAME_ID

# After final status, with an eligible pre-tipoff seal.
.venv/bin/python scripts/prospective_evaluate.py --capture-outcome --allow-network \
  --capture captures/prospective_phase1/pilot --output captures/prospective_outcome/GAME_ID
.venv/bin/python scripts/prospective_evaluate.py \
  --capture captures/prospective_phase1/pilot \
  --outcome captures/prospective_outcome/GAME_ID \
  --market captures/prospective_market/GAME_ID \
  --output captures/prospective_scores/GAME_ID.json
```

Never call the outcome command before tipoff; it rejects nonfinal games. A rescheduled, canceled or postponed fixture remains excluded, preserving its original forecast. Market absence does not exclude the primary Direct-v2 pair. Do not tune methods on these results or launch a 100-game campaign without separate authorization.
