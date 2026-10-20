# Shared pregame evidence collection

The same 200 games, T−24-hour cutoffs, statistical feature definitions, evaluation files and **20-minute quote candle-end threshold** are retained. Historical packets now include a separate `injury_news` section. There is no forecasting, probability estimation, LEAP implementation, trading, or paid inference in the historical build.

## What the official archive establishes

The [NBA 2025–26 injury-report page](https://official.nba.com/nba-injury-report-2025-26-season/) was captured during this investigation. Despite its season title, the retrieved page contained a rolling day's links, not a complete historical index. Official PDFs can still be retrieved directly from `https://ak-static.cms.nba.com/referee/injury/`. Some historical candidates return 200; many early-season candidates return 403. A forbidden URL is not evidence that a report never existed.

The collector is restricted to that exact page and official PDF filename pattern. For each of 186 distinct cutoffs it probes a documented grid of 15-minute issue times, newest first, at most 17 candidates over four hours, stopping at the first timestamp-supported candidate. The scope is bounded independently of injury contents. Earlier exploratory requests are retained in the immutable raw cache but do not expand this selection rule. Reports outside the grid, or inaccessible candidates within it, may be more recent than the chosen report. **We cannot certify the globally latest eligible report.** No broader historical search or silent current-news backfill is permitted.

Three clocks must agree before a PDF can contribute player rows:

1. The PDF's Eastern Time issue header must match its filename, with DST ambiguity resolved using its timezone-aware creation clock.
2. Creation must be at or after issue and within 30 minutes of it.
3. The official object's HTTP `Last-Modified` timestamp must be at or after creation. Issue, creation and object modification must all be at or before the game's cutoff.

The object clock is stored as `published_at_utc` **with** `publication_verification=official_origin_object_timestamp`; it is an issuer-origin availability bound, not an independently observed first-publication time. For example, an issue stamped exactly at a cutoff can be uploaded seconds later and is rejected. Retrieval timestamps are recorded separately and never establish historical publication.

These checks support prior existence of the issuer's object version. They do **not** prove that it was publicly accessible at that instant, establish first dissemination, or verify an unchanged publicly archived payload. Consequently `independent_historical_public_capture_verified`, `latest_report_globally_verified`, and packet `point_in_time_verified` remain false. Reports with absent/conflicting clocks do not contribute statuses. Independently verified publication coverage is **0/200**; the separate origin-supported coverage and monthly missingness are in [injury_coverage_report.md](../data/nba_2025_26/injury_coverage_report.md). Do not describe the origin-supported count as point-in-time verified coverage.

## Deterministic extraction and missingness

The only added dependency is pinned `pypdf==6.21.1`. Coordinates define the date, matchup, team, player, status and reason columns. Exact normalized official/ESPN team names, target game date and `AWAY@HOME` matchup are required. The extractor preserves literal names and statuses; `Out`, `Doubtful`, `Questionable`, `Probable` and `Available` are the recognized labels. Other labels remain `ambiguous` with their original text.

Team state distinguishes `reported`, `not_yet_submitted`, `unavailable`, and `ambiguous`. A report can be accessible while a target team has not submitted its report. An absent target section is unavailable, never an empty healthy roster. Unlisted players receive no inferred status. Reasons wrapped above/below player baselines are assigned only when nearest-row geometry is unambiguous. Unresolved page-boundary fragments stay in the audit, and affected player reasons have uncertainty flags; partial text must not be read as a complete medical description. No extraction model is called. Model/prompt/response fields in historical lineage are null.

## Files and freezing

| Artifact in `data/nba_2025_26/` | Contract |
| --- | --- |
| `injury_raw/<URL-SHA>.json`, `.body.gz` | Original PDF/HTML/error bytes, URL, retrieval/attempt clocks, HTTP headers, status and body SHA-256. Immutable captures, including failures. |
| `injury_extractions.json` | Regenerated parsing results, issue/creation clocks, unresolved fragments, extraction method, source references and candidate acceptance/rejection decisions. |
| `injury_lineage.jsonl` | Per-game audit: candidates, selected source, hash, retrieval clock, method, uncertainty and null model fields. |
| `injury_coverage*.csv`, `injury_summary.json`, `injury_coverage_report.md` | Per-game/month coverage, team states, player counts, uncertainty, HTTP failures and publication limitations. |
| `evidence_packets.jsonl` | Model-facing statistics plus `injury_news.official_injury` and `injury_news.news`. Historical news is explicitly `not_collected_historical`. |
| `evidence_snapshot_manifest.json`, `evidence_captures/<SHA>.json` | One active game/cutoff binding to immutable, content-addressed packet captures. The hash covers canonical UTF-8 JSON excluding its own hash field. |

Derived exports are overwritten in place; original document captures are hash-checked and never overwritten. Frozen packet captures are immutable too; regenerated packets must match an existing capture or get their content hash. The manifest is the authoritative binding; unreferenced captures are not alternative dataset selections. This is capture lineage, not a new dataset version or directory.

Future direct-LLM and LEAP-inspired consumers must both call `shared_evidence.load_game_snapshot(dataset_directory, game_id)` and use its **same manifest-bound hash**. They must not independently collect evidence or attach audit/evaluation files. `load_frozen_packet` supports the same contract for prospective captures. No consumer-specific packet generation is implemented. Market prices, outcomes, future information and Kalshi identifiers remain outside all model-facing packets. Only selected evidence URLs/page references enter the injury/news section; raw PDFs, schedules, full articles and search results stay audit-only.

## Bounded prospective research

**Integrated collector:** new live CLI runs (including the `prospective_research.py` entrypoint) now delegate to `collect_prospective.py`. Read [prospective_pipeline.md](prospective_pipeline.md) for real Brave/Anthropic adapters, authoritative schedule discovery with explicit fallback, complete statistics/official-injury inputs, actual snapshot timing and the saved public-source validation. The module-level news helpers and legacy gateway/replay functions described below remain available for reuse and old captured-component tests; the older standalone `--game` CLI is superseded by the integrated CLI's `--game-id`/discovery commands.

`scripts/prospective_research.py` composes a configurable JSON search/model gateway, allowlisted page capture, deterministic validation, optional one-shot extraction and shared freezing. It accepts schedule-only game identity JSON. Before constructing providers, it requires the game to be upcoming and the live cutoff to be within the preceding five minutes. Historical mode/dates are rejected before any provider call. Historical collection is a different official-only code path with no search capability. Offline replay only revalidates saved prospective captures and never searches.

The four categories are injury updates, lineup availability, roster transactions and significant team developments. Search queries are deterministic, interleaving the two teams across categories. Defaults cap a run at **4 queries, 4 pages, 64,000 reserved tokens, 1,000 output tokens and $0.10 estimated cost**. Budgets are checked before each call; query/page/token reservations and conservative operator-supplied cost estimates are recorded. Search responses are capped at 8 KB, pages at 5 MB, and model responses at an explicit bounded size. Byte-based input reservations conservatively bound tokenizer use for the JSON context. These are estimates and local request bounds, not a guarantee about a provider's billing or honesty. Paid POSTs are not retried automatically; failed responses are retained.

Page domains initially allow `nba.com` (including team sites), `espn.com`, `apnews.com`, and `reuters.com`, rejecting scoreboard/game/betting/result endpoints and redirects. Official sources rank before credible reporting when repeated claims are deduplicated. This deliberately conservative parser supports explicit timezone-aware HTML publication metadata and article/main paragraphs; unsupported JSON-LD-only, JS-rendered, paywalled or undated pages are unusable. Conflicting dates or a publication/modification clock after cutoff are rejected. Current retrieval is not historical proof; accepted sources remain flagged `unversioned_source_payload`.

The model receives only filtered injury/availability/transaction/development excerpts with source IDs, the two team names, categories and cutoff. It receives no raw search snippets, full pages, statistical histories, tools, file access, outcomes, market prices or evaluation files. Score/result/betting/probability paragraphs are filtered before this boundary. This is an extraction call with no autonomous browser loop. A model cannot request extra tools. Every proposed finding is validated against a retrieved source reference, allowed category/team, publication cutoff and **verbatim supporting claim** (up to 400 characters). Unsupported names/claims are rejected. Repeated normalized factual claims are combined while retaining the different source excerpts and preserving negation, injury reasons and time qualifiers; potentially conflicting updates remain flagged. Deduplication is conservative and may leave paraphrases separate. Empty results never imply a player is available.

Prospective packets use the same schema; absent statistical-history inputs and official PDFs are explicitly omitted, not replaced by 0–0 records or invented statuses. This news component does not yet collect a prospective statistical history or official PDF under its news budget. Publication metadata checks cannot establish that a subsequently retrieved article was unchanged at cutoff. Both prospective packet verification flags therefore also remain false.

## Reproduction and explicit opt-in

From the repository root:

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/build_dataset.py --offline
.venv/bin/python -m unittest discover -s tests -v

# Safe: no network, model, game-data read, or output-directory creation.
.venv/bin/python scripts/prospective_research.py --dry-run

# Revalidate a previously saved prospective capture; no provider is constructed.
.venv/bin/python scripts/prospective_research.py --replay /path/to/capture
```

The committed raw cache is sufficient for a complete offline rebuild, including PDF extraction. `.venv/bin/python scripts/historical_injuries.py` explicitly permits free official GETs for **absent** cached requests; existing failures are preserved. Do not delete failures or silently replace captures to improve reported coverage.

For a complete prospective run, use [prospective_pipeline.md](prospective_pipeline.md) and [prospective_config.example.json](../examples/prospective_config.example.json). The unified CLI discovers one upcoming game and requires separate public-network, search and inference opt-ins. It records the actual snapshot instead of using a supplied historical game/cutoff.

The earlier [research_config.example.json](../examples/research_config.example.json) remains documentation for the library-level `JsonGatewayProvider` contract, not the integrated CLI configuration:

* Search POST: `{query, before_utc, categories, max_results}`; response `{results: [{url, ...}]}`.
* Model POST: `{model, max_output_tokens, tools: [], task, context}`; response `{findings: [{category, team, player, claim, source_ref}], usage: {input_tokens, output_tokens}}`.

The same optional model-gateway contract is supported by the integrated adapter alongside its real Anthropic default. Old `--game`/`--allow-model` standalone commands have been replaced by schedule discovery, `--game-id` and the integrated opt-ins. Library functions for original captured-news tests remain available. No paid search or inference was run during either implementation; the new actual public-source validation is documented separately.
