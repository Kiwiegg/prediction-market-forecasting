# Official injury evidence coverage

Games: 200. Official-origin-timestamp-supported pre-cutoff reports: 130. Player/status records: 1047. Independently archived publication verification: **0**. Globally verified latest report selection: **0**.

Origin support requires matching PDF issue/creation clocks and an official object Last-Modified timestamp at or before the cutoff. This substantiates the issuer's object-version timestamp, not independently proven public visibility at that time. No report lacking that support contributes player statuses. Retrieval time never substitutes for publication time.

| Month | Games | Origin-supported report | Player/status rows | Reported team-games | Not submitted | Unavailable | Ambiguous |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2025-10 | 13 | 0 | 0 | 0 | 0 | 26 | 0 |
| 2025-11 | 36 | 0 | 0 | 0 | 0 | 72 | 0 |
| 2025-12 | 32 | 11 | 98 | 17 | 5 | 42 | 0 |
| 2026-01 | 38 | 38 | 336 | 62 | 14 | 0 | 0 |
| 2026-02 | 27 | 27 | 195 | 38 | 16 | 0 | 0 |
| 2026-03 | 39 | 39 | 248 | 45 | 33 | 0 | 0 |
| 2026-04 | 15 | 15 | 170 | 25 | 5 | 0 | 0 |

## Limits

* The season page currently lists a rolling day's links; direct collection returned HTTP 200. The HTML request and each PDF attempt are retained, including 403/404 responses.
* Approved official PDF URLs are probed at 15-minute issue intervals, newest first, at most 17 candidates/four hours per distinct cutoff. Missing or forbidden URLs do not prove absence. A complete historical publication index was not recovered; report selection is latest only among this explicit bounded candidate set, never asserted globally complete.
* Raw captures also retain the initial longer-window investigation, including failed requests. Those extra exploratory captures do not expand the four-hour selection rule.
* A report issued at the cutoff but uploaded seconds later is rejected. No target-game final pregame report is backfilled.
* Target date, matchup and exact team mapping are required. Absent target sections are unavailable, not healthy. NOT YET SUBMITTED is distinct from reported, and ambiguous rows stay explicit. No inference is made for unlisted players.
* Extraction is deterministic, uses pypdf 6.21.1 coordinates, and records page references and warnings. 12 player rows have uncertainty flags, including incomplete page-boundary reasons. Unassigned fragments remain in the extraction audit; they are not guessed. No inference model or paid research was run.
* Historical collection has no live search/provider path. The entire dataset remains retrospectively reconstructed, not point-in-time verified.
