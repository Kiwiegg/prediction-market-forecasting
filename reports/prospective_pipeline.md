# One-game prospective evidence pipeline

`scripts/collect_prospective.py` integrates schedule discovery, structured team history, official injury PDFs and bounded factual news extraction. It reuses `team_evidence.extract_history/team_facts`, the official coordinate parser, news validators and shared packet hashing. It never reads the historical evaluation files or collects market prices. The 200-game dataset and 20-minute historical quote threshold are unchanged.

## Safe planning and explicit opt-ins

Install the existing pinned dependency using the README's virtual environment instructions. No new third-party dependency is added. Defaults use [prospective_config.example.json](../examples/prospective_config.example.json).

```sh
# No network, output directory, search or inference; configuration only.
.venv/bin/python scripts/collect_prospective.py --dry-run

# No-cost offline plan with a real captured game, two queries and all budgets.
# The saved games will eventually cease to be upcoming; then discover afresh.
.venv/bin/python scripts/collect_prospective.py --dry-run \
  --schedule-capture reports/prospective_validation/one_game_public_capture_complete

# Free public GETs only. Captures are never overwritten; choose a new output path.
.venv/bin/python scripts/collect_prospective.py --discover --allow-network \
  --output captures/prospective/discovery

.venv/bin/python scripts/collect_prospective.py --dry-run \
  --schedule-capture captures/prospective/discovery --game-id AN_UPCOMING_ESPN_ID
```

Dry runs verify saved source-body hashes rather than trusting an arbitrary game JSON. They show the selected identity/tipoff, nominal cutoff, deterministic team/category queries, query/page/token/cost limits, credential **presence only**, public-source request limit and output filenames. Without a saved discovery capture the configuration-only plan explicitly has no selected game. No fictitious game is supplied.

Copy the example configuration to an operator-controlled file. Configure credentials in the calling environment or secret manager; do not put them in JSON or commit them:

```sh
# Supply your own real values; these placeholders are documentation only.
export BRAVE_SEARCH_API_KEY='YOUR_SEARCH_KEY'
export ANTHROPIC_API_KEY='YOUR_EXTRACTION_KEY'

# Public components only, one discovered upcoming regular-season game.
.venv/bin/python scripts/collect_prospective.py --live --allow-network \
  --game-id AN_UPCOMING_ESPN_ID --output captures/prospective/public_one_game

# Additionally authorize bounded paid search and one extraction call.
.venv/bin/python scripts/collect_prospective.py --live --allow-network \
  --allow-search --allow-inference --config /path/to/operator_config.json \
  --game-id AN_UPCOMING_ESPN_ID --output captures/prospective/researched_one_game
```

The CLI reads environment variables, not `.env` automatically. If you maintain a trusted local shell-compatible `.env`, load it in the same shell before invoking the collector (`set -a; . ./.env; set +a`), with shell tracing disabled. Never display the file or enable tracing around credentials. `.env` and `captures/` are Git-ignored; keep private provider responses in those ignored capture directories and commit sanitized validation summaries separately.

`--allow-search` alone collects/validates pages but does not infer findings; the packet says `not_extracted`. No search opt-in yields `not_collected`. Missing credentials fail before paid calls. `--live` operates on exactly one game, chosen by ID or closest nominal T−24h target with game-ID tie breaking. Historical, final, postponed, preseason, postseason and Cup-championship games cannot be selected. There is no batch mode, background scheduler or recurring Action. Existing output directories are refused; retries use a new capture directory. `.env*` and `captures/` are ignored by Git.

## Real providers and budgets

The default adapter calls [Brave Web Search](https://api-dashboard.search.brave.com/api-reference/web/search/get) using its documented GET endpoint and header authentication. It requests four web results per query, disables spell correction, restricts freshness to the preceding week and retains raw responses. Search snippets/titles are not evidence and never enter model context. Article retrieval and timestamp validation happen independently of search metadata.

New captures enable `dated_article_research`. Two deterministic queries cover both team names: one for injury/lineup/availability, one for signings/waivers/trades/coaching developments. Both scope search to the approved publisher domains with documented [Brave operators](https://api-dashboard.search.brave.com/documentation/resources/search-operators) and exclude tracker/standings terms. Operators influence retrieval, not eligibility: dynamic URLs are also blocked locally. Under a four-page budget, the first topic gets at most two article requests; the second can use the remaining allowance. A larger query budget does not cause extra automatic queries. An empty or unhelpful search never triggers an unbudgeted fallback.

Extraction uses the documented [Anthropic Messages API](https://platform.claude.com/docs/en/api/messages/create), with a configurable `model`, fixed extraction instructions, bounded output, and **no tools**. The example pins `claude-haiku-4-5-20251001`; check its [current availability](https://platform.claude.com/docs/en/models/haiku-4-5/overview) before enabling inference. Truncation, invalid usage, unexpected tools/cache billing and malformed JSON are rejected. The provider/model name, prompt, context, original response, reported usage and validation errors are captured. Auth headers are never persisted. No vendor SDK is necessary for these documented JSON APIs.

For an operator's existing gateway, set `llm_provider` to `json_gateway`, `model_endpoint` to a credential-free HTTPS URL, and `llm_key_env` to the credential's environment-variable name. The same captured transport accepts the repository's existing `{model, max_output_tokens, tools: [], task, context}` contract and requires `{findings, usage: {input_tokens, output_tokens}}`. This is an optional compatible gateway, not a bundled adapter to another commercial API. Search remains Brave. Models/providers remain explicit settings in each frozen capture.

Configured ceilings remain eight queries, eight pages, 320,000 reserved tokens, 2,000 maximum output tokens and **$0.35 maximum estimated cost**; the new planner actually issues at most two queries across the four categories and both teams. Search responses are capped at 32,768 bytes and conservatively charged against that many reserved tokens. Model input reserves UTF-8 JSON bytes plus a 2,048-token overhead allowance; output is reserved at its configured maximum. A reservation exceeding any limit prevents the call. Reported inference usage must fit its reservation. Public GETs have a separate default limit of 190 logical source requests (hard configuration ceiling 220); each existing document-store GET can make at most three bounded attempts. Each article is capped at 5 MB. Paid requests are not automatically retried, including failed or malformed responses.

For one deliberately authorized provider validation, add **`--live-test`** to the full paid opt-in command. This now caps a run to **two searches, four article URLs, at most one extraction and $0.35 estimated cost**, retaining stricter configured limits. Credentials alone never trigger a test. Run local tests and the dry-run first. Missing usable dated content can yield no extraction and no findings; it is not a reason to loosen validation. The [first paid test](prospective_paid_validation.md) skipped extraction; the [retrieval follow-up](prospective_retrieval_validation.md) reached Anthropic and recovered one supported finding offline from its saved response. No further paid test is authorized by either report.

New captures write `research_diagnostics.json` and a matching human-readable audit section: attempted queries, discovered result entries/unique URLs, retrieved/rejected pages, validated and duplicate claims, reasons, per-query URLs/source references and attribution. The audit separately states whether extraction was enabled, how many inference requests actually occurred, and why extraction was skipped. An attempted model request does not prove successful extraction. Per-query credit overlaps when searches find the same source. Provider latency is measured and saved separately from reported input/output token usage and estimated cost. Costs distinguish reservations, request-count estimates and reported-inference estimates; unknown inference usage remains null. Failed requests/pages stay auditable, including pages retrieved before a subsequent provider failure.

The example's price estimates are conservative operator settings, **not vendor price quotations or guaranteed invoices**. Set rates for the chosen model/account. Reservation totals and actual reported token usage are separate audit fields. A gateway or provider can violate its billing/usage contract; local checks cannot guarantee external billing. A run retains all attempts and errors even when no usable finding results.

## Sources and completeness

The collector tries both NBA CDN schedule feeds and captures their failures. ESPN daily NBA scoreboards supply the existing repository's schedule/team-ID format; when the NBA feed is usable, team codes and tipoff must corroborate. NBA/ESPN disagreement is rejected. If the NBA feeds are unavailable, the packet uses the **explicitly recorded ESPN fallback**, not falsely claimed NBA verification. ESPN's public feed is undocumented and can change. Discovery is capped at 1–7 UTC dates, default three. The default selection rule does not inspect results, prices or injury/news availability.

For the two selected teams, fetch the relevant season schedules, require the target identity/tipoff to be present, and fetch only earlier game summaries. Existing completion/recap/update checks reconstruct records, last-five W/L and rest at the **actual snapshot**. Summary retrieval time additionally bounds availability. Target and future summaries never contribute. An unavailable/inconsistent season schedule omits statistics rather than inventing 0–0; a complete season feed showing no previous regular-season games permits a genuine 0–0. Cup-final/rest semantics are preserved. Missing completion/publication clocks omit affected aggregates. Historical aggregate standings and retrospective widgets are not used.

The shared constructor now also adds completed-game point differentials and their full-season mean when **all** exact scores are verified, plus records split by home/away designation. It reuses those same summaries and timestamps. Score discrepancies omit scoring without discarding otherwise reliable W/L; empty seasons omit an undefined mean instead of supplying zero. Details and omission rules match the [historical methodology](dataset_methodology.md).

Official injury collection fetches the target season's page and preceding season's rolling page, then at most eight newest eligible linked reports from the preceding 24 hours. The full 30-team ESPN name catalog is captured for deterministic row mapping, including rows belonging to other teams. PDF issue/header/creation clocks, source URL, retrieval, original bytes and body hashes are preserved. A live successful capture bounds public availability by its own retrieval time; `published_at_utc` is explicitly labeled `observed_public_capture_upper_bound`, **not first publication**. A future issue/creation clock is rejected. Select the newest eligible issue among retrieved links, not a globally certified latest report. Missing catalog/pages/reports remain unavailable. Exact target date/matchup/team matching and existing reported/not-submitted/ambiguous states are retained. Unlisted players are never inferred healthy.

News sources are restricted to NBA/team news, ESPN NBA story URLs, AP articles, Reuters sports stories, and narrowly admitted SI NBA team-article / dated Orlando Sentinel paths. SI and the Sentinel were added only after their public HTML passed date and text extraction checks; minimal attributed fixtures and original-body hashes are in `tests/fixtures/articles/`. This is not a guarantee about every article on those domains. The Sentinel can declare subscription content; only content actually returned by the unauthenticated page request is eligible, without bypassing access controls. Team/index/roster/standings/injury-tracker URLs, PDFs, scoreboard/game/result/betting endpoints and every redirect remain rejected.

The parser accepts explicit timezone-aware publication fields in HTML metadata (`article:published_time`, `datepublished`, `pubdate`, `parsely-pub-date`, DC/DCTerms issued fields), labeled `itemprop=datePublished`, or JSON-LD `Article`/`NewsArticle`/related article types. JSON-LD arrays and `@graph` are supported; article URL/main-entity identities must agree with the fetched page when supplied. Related-story objects cannot lend publication dates. Multiple unbound articles, conflicting/naive/malformed dates and `LiveBlogPosting` are rejected. All recognized publication clocks must agree in UTC. Explicit modification clocks must fall between publication and both retrieval/snapshot. See [the article metadata specification](https://developers.google.com/search/docs/appearance/structured-data/article). JSON-LD article text is never a fallback for captured HTML paragraphs.

Retrieval clocks, HTTP headers, bare dates, arbitrary JavaScript fields and search-result dates cannot establish publication. Undated, unverifiable or JS-only bodies stay unusable. Score/result/market/probability paragraphs are excluded before extraction; full pages/search results/history files are never given to the model. These lexical filters are conservative, not a proof of semantic purity for arbitrary prose. Publisher timestamps remain publisher assertions, not independent version/publication verification. The tool-free extractor cannot read files, fetch pages, or extend the budget.

Each accepted claim requires an exact allowed category/team, supported player name, an actual captured source reference and verbatim factual support. Duplicates retain source excerpts, and potentially conflicting updates retain uncertainty flags. Raw interpretation/candidates, rejected assertions and validation decisions remain audit-only. No probability forecasting or availability inference from missing evidence is implemented.

`extraction_format_recovery` accepts a single whole-response JSON code fence, never prose or arbitrary JSON repair. A claim differing only in ASCII capitalization can bind to exactly one original cited text span; the exported claim is that literal original span, with the model's original wording and normalization decision retained separately. Missing words, punctuation changes, paraphrases, ambiguous matches and unsupported names remain rejected. Day-to-day/soreness are recognized as explicit injury vocabulary. Older captures whose settings omit the new flags keep their original strict response parsing, queries and source decisions.

## Timing, shared schema and immutable bundles

`cutoff_utc` means the **actual** snapshot bound. The additive, prospective-only `snapshot_timing` section records nominal tipoff minus exactly 86,400 seconds, collection start, actual snapshot, packet creation, signed deviation, timing status, and strict eligibility. Historical packets remain unchanged. All public/page/provider retrievals must finish by the actual snapshot. A game that starts during collection is rejected. Evidence retrieved after the snapshot is never accepted or backdated to nominal T−24h.

Both early and late captures are explicitly identified and **ineligible for exact T−24h evaluation**; only zero deviation qualifies. No rounding tolerance silently converts a late capture to on-time. Ordinary sequential collection takes time: invoke around a future target and inspect measured deviation rather than assuming invocation at T−24h yields an on-time packet. Exact deadline synchronization has not been demonstrated. This CLI is a one-shot collector, not an exact-time scheduling service; any deployment requiring strict instantaneous capture must substantiate that timing separately. The saved live examples are late, not strict T−24h successes.

For eventual practical evaluation, `timing_tolerance_seconds` defines a separate symmetric window. The example uses **300 seconds**; zero is the fallback default. `within_timing_tolerance` reports `abs(actual_snapshot − target) <= tolerance`, inclusively. It never changes actual timestamps, `late`/`early` status, exact `strict_t24h_eligible`, source eligibility, or historical cutoffs. This policy and its result are frozen in each new packet. Older captures keep their original timing fields.

Retries require a new `--output` directory. Existing completed bundles are validated and returned unchanged on an identical save; different packet/audit inputs are refused before any write, including before creating a new packet file. The CLI refuses an existing directory before collection/provider calls. Retry with a fresh directory to obtain new timestamps and reevaluate timing; a successful earlier bundle is never overwritten.

`injury_news`, statistical fields and hash use the shared historical schema, extended only by explicit timing metadata. Prices, target outcomes, market identifiers, full documents and rejected agent interpretations are excluded. Existing point-in-time and schedule-verification flags remain false; original live captures establish captured bytes at recorded retrieval times, not independent first publication of all upstream facts.

A completed directory contains:

| File | Role |
| --- | --- |
| `raw/`, `news_raw/` | Immutable public documents, hashes, URLs, headers, retrieval/attempt times, including failures |
| `provider_captures/` | Auth-free request records, original response bytes, timestamps, usage and failures |
| `run.json`, `discovery.json`, `lineage.json` | Frozen settings/clocks, schedule decision rule, source lineage, statistical omissions, parser warnings, research decisions |
| `evidence_packet.json`, `evidence_captures/`, `evidence_snapshot_manifest.json` | One manifest-bound immutable shared packet/hash |
| `evidence_audit.md` | Accepted evidence, citations, timestamps, extraction method, uncertainty and rejection reasons |
| `bundle_manifest.json` | SHA-256 of all original capture/audit files plus the packet content hash |

`load_for_consumer(directory, "direct_llm")` and `load_for_consumer(directory, "leap")` verify the same bundle and load exactly the same manifest-bound packet. Neither implements a forecasting method or adds evidence. Consumers must not append audit/evaluation files. Any captured-file mutation fails integrity checks. A new attempt never overwrites an existing successful bundle.

```sh
# No keys, search or inference needed. Recomputes schedule selection, statistics,
# injury extraction, news validation and packet from saved source/provider bytes.
.venv/bin/python scripts/collect_prospective.py --replay /path/to/completed_capture

.venv/bin/python -m unittest discover -s tests -v
```

Replay uses the original clocks/settings and read-only provider responses. A missing response fails closed instead of querying a service. It compares both packet and lineage and writes no capture files. The bundle manifest is an integrity reference, not an independently notarized timestamp/signature.

The same collector can reprocess a saved bundle after the deterministic format fix, entirely offline:

```sh
.venv/bin/python scripts/collect_prospective.py --reprocess /path/to/original_capture \
  --output captures/prospective/new_offline_derived_bundle
.venv/bin/python scripts/collect_prospective.py --replay \
  captures/prospective/new_offline_derived_bundle
```

Reprocessing verifies the original bundle, copies its captured bytes to a separate new directory and enables only extraction-format recovery. It never constructs a network-enabled provider or changes queries, source retrieval times, model responses or the original actual snapshot. Packet creation records the new derivation time, and `run.json` binds the original packet/manifest hashes. Each derivation has its own creation time/hash; offline replay of the resulting frozen bundle reproduces it exactly. The successful original bundle is never overwritten or relabeled as a recovered success.

See the [actual validation report](prospective_validation/README.md) for observed public-source behavior, hashes and outstanding paid/exact-cutoff tests.
