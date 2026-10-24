# Operational amendment v1: NBA schedule fallback

This versioned amendment changes **schedule discovery only** under a new explicit
one-attempt authorization. Commit the amendment, implementation, asset registry
and passing offline tests before further live requests. The original Phase1
protocol, frozen forecasting assets, packet schema, timing/evaluation rules and
historical data remain unchanged. This is not a methodology revision.

## Narrow exception and independent authorization

Prefer one GET to the original primary official NBA schedule endpoint
`https://cdn.nba.com/static/json/staticData/scheduleLeagueV2_1.json`.
Its HTTP403, non-denial unavailability (including transport/server errors), or
unusable schedule document permits the existing ESPN schedule fallback. Preserve
the original response, URL, clocks, hash and failure decision. Do not retry the
same endpoint, try another NBA host, change headers or credentials, or hide errors.
An NBA HTTP401/407/451 is not covered. ESPN and every other source's access denial
still stops immediately, as does the first paid-provider HTTP403/access denial.
No paid retries; original caps of 20 Anthropic requests, two Brave queries, four
article retrievals and $1 conservative combined reservations apply only after
an eligible fixture has been confirmed.

The new immutable authorization lives at
`captures/prospective_discovery_v1/attempt/authorization.json` and binds the new
asset registry and the SHA-256 of the original blocked journal. Never remove or
modify `captures/prospective_phase1/access_denial.json`, original raw responses,
or successful/failed caches. This amendment supersedes only that journal's
specific official-schedule403 for this explicitly authorized attempt. It cannot
supersede a paid-provider or other denial. A new denial creates a distinct
permanent journal and blocks further requests. The attempt directory cannot be
changed to retry. No campaign or recurring scheduler is authorized.

## Schedule validation and provenance

Bound discovery to three UTC scoreboard dates. ESPN supplies the existing game ID
and a mapping for the NBA schedule; this ID mapping is necessary even on official
NBA success and is labeled NBA-corroborated ESPN, not a fallback. NBA fixtures must
have the regular-season NBA game-ID prefix and scheduled status. When usable NBA
rows exist, teams and exact UTC tipoff must match uniquely; conflicts are rejected,
never replaced by ESPN. When NBA is unavailable, leave its game ID missing.

For every candidate require corroboration from **both teams' ESPN regular-season
schedules**: exactly one matching game ID, correct team identity, home/away teams,
season, regular-season designation, scheduled status, valid explicit timezone,
neutral-site designation and exact normalized UTC tipoff. Reject canceled,
postponed, completed, rescheduled-status, missing, duplicate, ambiguous and
conflicting fixtures. A conflict between daily scoreboards is also fatal for that
fixture. Both ESPN team schedules are separate responses from the same provider;
they are not independent publication authorities. Preserve disagreements rather
than treating agreement as proof of historical schedule versions.

Store provider/source IDs for every validated identity/timing/status field in the
discovery audit. Display names come from the scoreboard; Eastern game date and
T−24h are explicit deterministic derivations. Never put raw schedule scores,
records, odds or audit-only fields into model-facing evidence. No target summaries
are fetched by discovery. The amendment does not change evidence schemas.

## Original point-in-time and forecasting rules

The target remains tipoff minus 86,400 elapsed UTC seconds. Only original ±300s
collection-start/snapshot/packet-creation eligibility can trigger collection and
forecasting. Preserve actual clocks, early/late/exact labels and the original
source cap `min(actual snapshot,target)`. No post-cutoff publications/retrieval,
backfill, historical reconstruction or off-time paid test is permitted. Reuse
original collection, injury missingness, shared loader, native request caches,
unchanged Direct/v1/v2 methods, per-method groups and alpha variants. They consume
one identical frozen parent hash; failures and abstentions are not neutralized.
All three methods must seal before tipoff. Outcomes and Kalshi remain isolated
under the existing prospective evaluation protocol.

## Validation and stopping

Run the complete test suite, previous sanitized replay and private mock replay.
Then make exactly one live discovery attempt linked to the original403. If no
verified game is inside the window, stop at discovery/dry-run, with no paid calls.
If the ESPN fallback is denied, preserve both sources' errors and stop. A fixture
outside the window is a discovery success only, never a prospective forecast.
Publish sanitized source/timing/cost decisions and replay commands; keep raw
provider documents and credentials outside Git. Report live and mocked behavior
separately without claiming reliable future provider availability from one test.
