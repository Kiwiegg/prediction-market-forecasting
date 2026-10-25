# Cloud news v1 — offline validated, not deployed

**Implemented and tested; no cloud host, service, live job or paid collection was
activated.** The Lakers–Jazz pilot, installed launchd configuration, immutable job,
journals and historical dataset were not modified or executed by this task.
Only explicitly synthetic fixture jobs were processed. New real Brave/Anthropic,
NBA/ESPN/news and Kalshi requests for this pipeline: **zero**; new paid spend:$0.

## Frozen protocol and timing

The [protocol](../../experiments/prospective_cloud_news_v1.md),
[configuration](../../examples/prospective_cloud_news_v1.json), asset registry,
worker and tests were committed at **`b338133`** before any affected live capture.
Public-header redaction and its regression were committed at **`fd928f7`**, also
before any affected live capture. Original private captures retain their headers;
public exports strip headers/payloads rather than expose session material.
No affected live capture has occurred. All original Direct/v1/v2 prompts, models,
generation settings, priors, mappings, alpha variants and scoring functions remain
byte-identical. The implementation reuses original loaders, request identities,
provider adapters, parsers, response validation and aggregation.

| Phase | Default deadline/window |
| --- | --- |
| Information target T | Recorded scheduled tipoff−86400 elapsed UTC seconds |
| Source collection | T−30min through T |
| Public statistics/injury refresh | One declared slot near T−2min |
| Search/page publication and retrieval | At/before T, no undated or revised-later evidence |
| Packet validation/freezing | At/after T, finished by T+5min |
| Direct/v1/v2 inference and seal | After freeze, by T+15min and before tipoff |
| Independent benchmark | Request near T−5s; actual response must finish by T |

Timing settings are versioned JSON and part of immutable authorization/job
identity alongside the source-code registry. A pending job cannot adopt another
config/asset version to rescue a deadline. A non-24h target or post-T retrieval
deadline is rejected. UTC/date discovery includes fixtures two dates ahead when
collection crosses midnight. Missed/uncertain/failed stages remain in the audit.

The shared packet keeps cutoff_utc=T and omits the optional legacy
snapshot_timing field: its old physical-snapshot semantics cannot honestly label
multi-phase processing. Actual collection/retrieval/extraction/freeze/inference
clocks and eligibility are retained in separate hashed audit artifacts. No physical
event is backdated. Source freshness records publication/issue age and retrieval
age at T separately; underlying update age/global latest coverage may be unknown.

## Cloud execution and security

Choose one persistent Linux VM, not ephemeral Actions runners. GitHub documents
that scheduled runs can be delayed or dropped under load; scheduling alone cannot
guarantee this information boundary. The VM uses systemd supervision, separate
evidence/market pools, local-filesystem SQLite WAL/FULL transactions, process locks,
fsynced captures and durable global paid request claims.
[GitHub scheduling limitations](https://docs.github.com/en/actions/how-tos/troubleshoot-workflows).

Store UUID and database identity must match authorization; a missing database is
not silently recreated, even by reinitializing an existing volume. Native claim
markers and completed cache records remain immutable. An interrupted network
stage without a completed artifact is not retried. A completed artifact interrupted
before SQL finalization can be verified and recovered without another request.
Paid sends serialize across games, so first paid denial pauses later sends.
Unknown-usage reservations are retained. Slow queues may miss deadlines rather
than extending them.

Evidence-source denials pause new network/paid work; only the explicit NBA403
schedule fallback is exempt. Benchmark denials preserve a missing quote and a
denied-host circuit without canceling unrelated valid forecasts, as explicitly
documented in this new protocol. No denied host is retried or replaced. The old
pilot's access policy is unchanged. Its game ID401909861 and legacy data/state
paths are explicitly protected from cloud enrollment/storage.

Deployment templates require an activation marker, persistent-volume sentinel,
matching UUID, NTP synchronization, explicit allowlisted authorization and paid
flags. State/captures are private, secrets are root-readable environment files on
encrypted storage, and the benchmark process receives no model/search credentials.
No service was installed or started. Linux/systemd startup and actual cloud storage
encryption/backups remain operator deployment tasks, not validated deployments.

## News acquisition, extraction and evidence identity

Existing deterministic queries cover both teams and the four original news
categories. Two searches/four pages are the default maximum. Existing domain,
redirect, explicit-timezone publication/modification and verbatim-support checks
remain in force. Search snippets stay audit-only. Source bytes, parsed excerpts,
query results and decisions are captured and hashed before reuse.

Extraction normally follows acquisition before T. If delayed, it may process only
the immutable pre-cutoff context until the freeze deadline. The extraction transport
cannot search or retrieve pages. Original extraction instructions, model request,
response, usage and latency are saved privately. Offline replay re-parses captured
articles and revalidates source-supported candidates. No eligible article skips
the model; this is unavailable evidence, never player health or proof of no news.
Extraction failure blocks eligible freezing rather than masquerading as no findings.

One packet is frozen once and loaded through the shared loader for all methods.
No source audit, target outcome or market value enters the model context. Native
group missingness/abstention/failure handling stays intact; alpha variants share
group observations. Independent quote capture reuses original mapping, open-market,
two-sided quote and cutoff validation. Late/invalid/unmatched quotes stay missing;
quote refresh age is unknown and historical20-minute rules are unchanged.

## Offline results actually obtained

The complete suite passes **241 tests**, including23 new cloud tests, locally (126.548s) and in a clean checkout (142.310s) without `.env`, provider credentials or private captures. Clean-checkout synthetic/public native replay and the original shared mock replay also pass. Hash checks preserve **7,914 original protected files**, including **7,608 historical data files**, with no differences. See [validation metadata](validation.json) and [preservation checks](preservation.json). Tests cover
UTC/DST/midnight discovery, collection-start/cutoff/freeze/seal boundaries, late
responses, publication/retrieval conflicts, missing injuries, post-T extraction
from pre-T bytes, unknown claims, overlapping jobs and atomic global budgets,
provider403 stopping, source/benchmark denial isolation, cache/request identity,
market/outcome isolation, source hashes, monitoring and deployment activation gates.

The [sanitized simulation](simulation/audit.json) is **offline_mock** with
**live_evaluation_eligible=false**. It starts at T−30, refreshes public fixtures
near T−2, freezes at virtual T+1 and exercises all three native methods from one
packet hash:

`68ba497484267bf559c6b603cf1d5c65eae35c3f8be548bc48829e21133d829d`

It contains one grounded **synthetic** news claim, a synthetic reported home injury
and an opponent not-yet-submitted state. Publisher bytes and PDF parsing are
fixtures; LLM responses/usage are mocked. Direct and LEAP probabilities are mock
values, not Claude forecasts or accuracy evidence. Real adapters are exercised
against local mock HTTP responses, including denied and late requests. Independent
quote replay is also fixture-only; no live benchmark was captured.

Private replay checks capture hashes, article parsing, extraction support, derived
packets and native caches. Public replay verifies the packet, registered cutoff,
native request/group identity and aggregation; it does not authenticate publishers
or providers. Original shared-packet public replay still passes. No cloud observation
has entered an evaluation dataset.

## Cohorts, costs and remaining activation steps

All future explicitly enrolled cloud-news-v1 observations are a separate labeled
cohort. The original100-game prospective plan is not restarted, relabeled or pooled
with it. The legacy no-news pilot stays legacy. If a news campaign is later approved,
its own first100 eligible pairs and stopping plan must be reported separately; no
campaign is enabled now. Primary paired Brier remains v2 raw minus Direct, with
existing secondary metrics and no tuning to outcomes.

Illustrative infrastructure: $6/month for the listed1GiB VM plus$2 for20GiB encrypted
state storage, **about$8/month before backups, tax and overages**. Larger-memory
or backup choices cost more. Persistent volume and backup policy must be configured.
[VM pricing](https://www.digitalocean.com/pricing/droplets),
[volume pricing](https://docs.digitalocean.com/products/volumes/details/pricing/),
[volume encryption](https://docs.digitalocean.com/products/volumes/details/features/).

Configured conservative ceilings are **$0.35 research + $1 forecasting = $1.35/game**,
with at most2 Brave requests,4 pages,1 extraction and9 forecast calls. These are
reservations, not invoices or permission to spend in this task. The synthetic
packet's no-network forecast reservation plan is$0.156853 for7 available calls;
real packet sizes/coverage/costs remain unvalidated. See [cost plan](cost_plan.json).

**Deployed:** nothing in the cloud. **Ready for deployment review:** code, disabled
systemd units, persistent-store initialization, bounded activation commands, and
offline monitoring/replay. No VM/SSH target, encrypted mount, backup policy, cloud
secret files or live-game authorization was configured or used here.

To activate the first news-enabled game after explicit approval:

1. Provision the VM/SSH access and encrypted persistent volume; configure UTC/NTP,
   permissions, matching backups and an external health/disk alert destination.
2. Install the pinned checkout/dependencies and initialize the private store once.
3. Install secrets/UUID privately. Perform one explicitly permitted no-cost schedule
   discovery, review the earliest future collection window and authorize that game
   with a bounded total budget. Never use the protected legacy pilot ID.
4. Enroll that single game, review immutable deadlines, then explicitly install,
   activate and start both services. Do not authorize the full campaign yet.
5. After execution, inspect sources, freshness, supported claims, budgets, denials,
   shared hashes and deadline seals; retain failures. Only then assess wider rollout.

Exact commands, rollback, monitoring and recovery are in the
[deployment instructions](../../deploy/cloud-news/README.md). **Still unvalidated
live:** cloud clock/storage/service behavior, NBA/ESPN access from the chosen region,
article coverage, real extraction, integrated native inference, quote mapping/latency,
and actual deadline performance for overlapping games. No live success is claimed.

```sh
# All no-cost/offline.
.venv/bin/python scripts/cloud_prospective.py
.venv/bin/python scripts/cloud_prospective.py --replay-public reports/prospective_cloud_news_v1/simulation
.venv/bin/python scripts/prospective_study.py --replay reports/prospective_phase1/mock_validation
.venv/bin/python -m unittest discover -s tests -q

# Fresh synthetic replay; paths must be new, never a real job/cache.
.venv/bin/python tests/test_cloud_news_pipeline.py --export-simulation \
  captures/cloud_news_mock_fresh /tmp/cloud_news_mock_public
```
