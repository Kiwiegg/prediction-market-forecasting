# Focused evidence improvements: validation

Validated on **2026-10-20 UTC**. The initial no-cost checks and original 56-test suite passed before implementation/provider validation. The expanded suite now passes **63 tests**. No new network source requests, paid search, inference, forecasts or recurring workflows were run in this round.

## What changed and was checked

* New audits/`research_diagnostics.json` count queries, result entries, unique URLs, retrieved/rejected pages, validated findings, duplicate claims and rejection reasons. Per-query URL/source-reference attribution makes useful searches inspectable; overlapping attribution is explicitly non-additive. Mocked success, duplicates, undated pages, disallowed URLs, malformed responses and provider failure after a successful page fetch were tested.
* Provider request latency is captured independently of reported token usage. Cost accounting separates reserved upper bounds, estimated request/page charges and reported-inference usage. Unknown or malformed usage stays null, not invented zero. Actual bills and real provider latency remain unverified because no paid test ran.
* Shared scoring and home/away features reuse saved ESPN game summaries. End Game/header exact-score agreement, completed status and pre-cutoff source clocks are required. Future and target games are excluded. Negative, fractional and boolean scores are rejected. Source/clock/score disagreements omit the applicable feature. Both consumers load the same updated manifest-bound packet; complete mocked prospective collection and all 200 historical packets are checked.
* A configured **±300-second practical timing window** is separate from exact-time eligibility. Boundary tests include ±300 and +300.000001 seconds. Late remains late even inside the practical window. Historical cutoffs never move.
* Identical saves of completed bundles make no writes; changed saves fail before any writes. Retrying in a new capture directory is allowed. Tests compare every original bundle byte before and after identical/different save attempts.

## Historical feature coverage, same 200 games

Counts use **400 team-game sides**, including omissions; no games were replaced.

| Feature | Home available | Away available | Omitted reasons across both sides |
| --- | ---: | ---: | --- |
| Per-game point differential and full-season average | 125 | 118 | 7 no completed games; 113 unverified exact scores; 37 incomplete timestamped history |
| Home/away split records | 183 | 180 | 37 incomplete timestamped history |

A score feature is omitted entirely when any required exact score is unavailable; there is no partial-season average disguised as complete. Split records use recorded home/away designation, including neutral fixtures. A known empty split is 0–0; an undefined scoring average is omitted. The new feature lineage identifies every contributing prior game and existing source ID. These are source-clock-supported reconstructions, not a claim of independently verified historical publication/payload versions.

Offline rebuilding succeeded using existing captures only, and a second rebuild reproduced **all 7,411 dataset files byte-for-byte**. Selection, outcome/price exports, raw history, source hashes and the 20-minute market rule remain unchanged. Original team-feature projections retain their frozen hashes. Only additive evidence, feature lineage and active snapshot bindings change; older immutable packet captures are retained. No new historical dataset version/directory was created.

## Existing prospective captures

Both original public-source captures replay offline without modification:

* `one_game_public_capture_complete`: `f846b19cc98077000242ebcbc01b594f3efbd6d3d3d4ffbfe2b53058d78df931`
* `one_game_public_capture`: `23c9c72b48d9fe53862faaa097326b6e99d91074349fb9543e87287d385b4977`

Those earlier live public captures remain evidence of schedule/injury retrieval at their recorded times; neither was an exact T−24h or paid-news success. Frozen older settings preserve their original schemas on replay. New captures enable the added statistics/diagnostics and freeze their timing-window policy. No past bundle is silently upgraded or relabeled.

## Real-provider test: blocked, not claimed successful

At the no-cost credential check, **both `BRAVE_SEARCH_API_KEY` and `ANTHROPIC_API_KEY` were absent**. No operator live-test flag was executed. Consequently this round has **zero real accepted news claims**, no real rejection/usage/latency measurements, and **$0 new provider spend**. Mock metrics/claims are not substituted for live results. The existing adapters remain contract-tested, not newly validated against authenticated Brave/Anthropic services.

The saved discovery frame lists upcoming regular-season games, including **401909834** (Atlanta at Orlando), recorded tipoff **2026-10-21 23:00 UTC**, nominal target **2026-10-20 23:00 UTC**. This is a saved schedule observation, not fresh schedule verification or a current exact-cutoff opportunity. A real run rediscovers and rejects a game that is no longer upcoming. No game or timestamp was fabricated.

After configuring credentials through the documented environment variables, the operator can run **at most one explicitly authorized validation**:

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/collect_prospective.py --dry-run \
  --schedule-capture reports/prospective_validation/one_game_public_capture_complete \
  --game-id 401909834

# Explicit operator opt-in: one search, <=2 pages, <=1 extraction;
# existing 320,000 reserved-token / 2,000 output-token / $0.35 estimated cap.
.venv/bin/python scripts/collect_prospective.py --live-test --live \
  --allow-network --allow-search --allow-inference --game-id 401909834 \
  --config examples/prospective_config.example.json \
  --output captures/prospective/operator_live_test_1
```

Use a fresh output directory on retry. If the game has started, use a freshly discovered eligible game rather than changing its tipoff. The audit will show actual accepted claims, URLs, publication/retrieval clocks, verbatim support and rejected evidence, plus separate latency, reported usage and estimated costs. If no safe dated article is retrieved, no extraction is forced. Neither provider credentials nor the practical tolerance bypass cutoff/provenance/leakage checks. Exact-time capture and real extraction usefulness remain unvalidated.
