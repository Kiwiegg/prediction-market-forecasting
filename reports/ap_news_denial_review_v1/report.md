# Final AP News denial review

**GO for separate, explicit operator-approved policy adoption.** The preserved
response is defensibly classified as an ordinary publisher browser-challenge
article denial. **No policy was adopted, no circuits were superseded, and live
collection remains disabled.** This is not approval to activate the campaign.

## Evidence from the original capture

The GET-only private review read the original, hash-verified R2 bytes. It did not
request AP again. The response for the saved AP basketball article was retrieved
at **2026-10-27T23:31:56.427502Z** and contains:

| Observation | Preserved evidence |
|---|---|
| HTTP status / MIME type | 403 / `text/html` |
| Body length | 5,669 bytes, not truncated |
| Body SHA-256 | `e4a0bfe2fbbd697743e644ffaf301f4e95d01497ce8265bd613383bfc710ab98` |
| Challenge header | `cf-mitigated: challenge` |
| Corroborating HTML | `_cf_chl_opt` and `/cdn-cgi/challenge-platform/` |
| Visible document | Known browser-challenge title and JavaScript/cookie instruction |
| Authentication / account indicators | No WWW/proxy authentication challenge, JSON/API body, password form or recognized account restriction marker |

Cloudflare documents the challenge header and HTML content type for Challenge
Pages. This supports identifying the response as a browser challenge rather than
an API credential error. [Official Cloudflare documentation](https://developers.cloudflare.com/cloudflare-challenges/challenge-types/challenge-pages/detect-response/)

The complete structural profile and header **names** are in
[before_profile.json](before_profile.json) and [after_profile.json](after_profile.json).
Cookie values, challenge tokens, request identifiers, security-policy values and
raw response bytes remain private. The HTML has one inline script, six metadata
elements and a short visible message; it contains no retrieved article text.

## Minimal deterministic refinement

Implementation commit: `2003d979ea2f092ff67fba9bad272757475e8471`.
The original keyword heuristic rejected this template because its body lacks
literal denial wording. The new branch requires HTTP 403, an already-allowlisted
third-party article URL, a complete integrity-checked response, the documented
header/MIME pair, and both corroborating HTML markers. There is no AP URL, article
hash or game-specific exception.

Credential/proxy challenges, account/login/payment restrictions, password forms,
provider contexts, official sources, JSON errors, other statuses, integrity
mismatches and truncation still fail closed. Unknown response shapes remain
ambiguous and fatal under the existing proposal. Host normalization preserves the
permanent denied-host block. No script execution, challenge solving, alternate
endpoint, denied-host retry or source-cutoff relaxation was introduced.

The public regression HTML is a **synthetic reconstruction of the observed
structure**, with synthetic script values. Actual private bytes were checked
separately. The response remains missing news evidence: browser-challenge
recognition does not establish article availability, a publication timestamp,
global account status, or any usable factual claim.

## Validation and preservation

- Complete suite: **315 tests passed**. New regressions cover corroboration,
  authentication/account challenges, provider and official sources, other 403
  bodies/statuses, truncation/integrity, approved publisher generalization, header
  case and normalized denied-host aliases.
- [Initial private review](https://github.com/Kiwiegg/prediction-market-forecasting/actions/runs/40739073416): original classifier rejected the captured shape.
- [Final private review](https://github.com/Kiwiegg/prediction-market-forecasting/actions/runs/40751159878): refined classifier accepted the **same** bytes; adoption preconditions and all seven available job replays passed, including the completed original pilot.
- Both reviews verified **703 unchanged private files**, idle owner, **17 unchanged
  paid claims**, **$0.282501 retained reservations**, unchanged ledger/circuit
  hashes and the identical R2 snapshot. Existing host, network and paid denial
  journals remain intact. No policy authorization exists.
- **Zero publisher requests, zero paid calls and zero remote writes** during
  inspection/replay. Storage reads were the only private network operations.
- Clean-checkout frozen-asset validation, cloud mock replay, original sanitized
  pilot replay and all eight article-denial tests passed. All 7,987 baseline file
  hashes were checked: historical data, frozen forecasting methods, prior reports,
  splits and authorizations remain unchanged. Only the classifier and its two
  operational registries changed among baseline files.

[validation.json](validation.json) records reproducible checks. The private
snapshot remains `1aeb0ee7d2fdec42b7d16f2af2d1df3f3afac60dc8272ad8f44258e448534abc`.
Hashes of the sanitized artifacts are in [manifest.json](manifest.json).

## Recommendation and remaining approval

Proceed only with a **separate reviewed adoption** of the prospective denial
policy, using the existing authorization/migration safeguards and the reviewed
commit pin. That operation must retain the AP host block, original immutable
records, reservations and denial history; any circuit supersession must be
explicitly authorized. Expired partial games remain ineligible and must not be
backfilled. Campaign activation requires its own explicit approval.

This review does not demonstrate that every publisher 403 is ordinary or that
future news retrieval will succeed. Unrecognized or account/provider/official
access failures retain their fatal treatment. No live forecasting was tested.

## Reproduction

```sh
.venv/bin/python -m unittest discover -s tests -q
.venv/bin/python scripts/actions_prospective.py --validate-assets
.venv/bin/python scripts/cloud_prospective.py --replay-public reports/prospective_cloud_news_v1/simulation
.venv/bin/python scripts/replay_live_pilot_summary.py reports/prospective_live_pilot_1
```

With protected storage credentials, an idle original R2 checkpoint, administrator
mode enabled, live mode disabled and the reviewed SHA pinned to the dispatched
commit, the read-only private review is:

```sh
gh workflow run review-nba-denial.yml --repo Kiwiegg/prediction-market-forecasting --ref main
```

It performs no policy adoption, owner acquisition, checkpoint publication, source
retrieval or inference. No Brave or Anthropic credentials are supplied to it.
