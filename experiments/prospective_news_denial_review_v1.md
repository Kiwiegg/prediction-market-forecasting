# Publisher browser-challenge recognition — review v1

This is a deterministic refinement of the **unadopted** prospective news-denial
proposal. It changes no frozen forecasting method, information cutoff, existing
packet, campaign authorization or source-denial record. Adoption remains a separate
explicit operator action; automatic collection stays disabled during this task.

The preserved public-article response was read from its hash-verified private R2
capture, not requested again. It has HTTP403, `Content-Type: text/html`, the header
`cf-mitigated: challenge`, a browser-challenge HTML document, inline
`_cf_chl_opt` options and a `/cdn-cgi/challenge-platform/` script path. Cookie and
challenge values, request identifiers and raw response bytes stay private.

Cloudflare documents the exact `cf-mitigated: challenge` response marker and
`text/html` content type for Challenge Pages:
https://developers.cloudflare.com/cloudflare-challenges/challenge-types/challenge-pages/detect-response/

The classifier retains all prior gates and additionally recognizes a challenge
only when this documented header/type pair and both HTML script markers agree
in a complete response from an already-allowlisted third-party article URL.
It does not match one AP URL, body hash, team, game or vendor token. It does not
execute JavaScript, solve a challenge, follow redirects or try another endpoint.
The denied host remains permanently blocked and the response remains unusable
news, with no factual claims extracted.

Credential/proxy challenges, JSON/API errors, account/payment/login restrictions,
password forms, provider contexts, core/official source URLs, wrong status codes,
integrity mismatches and truncation still fail closed before the new branch.
Other ambiguous response shapes remain unclassified. Timing/publication/support
validation and no-retry rules are unchanged. A source browser challenge does not
establish an account-wide API restriction or prove whether an article exists.

The public fixture is a synthetic reconstruction of the observed HTML structure
and safe vendor markers. It is not the private response: its unique values and
script contents are deliberately synthetic. Private replay verifies the actual
original response separately. Tests include feature-removal controls, other
approved publishers, account/provider errors and denied-host aliases.

The final report records actual private-byte verification, GO/NO-GO for separate
operator-approved adoption, invariant checks and the full reviewed commit SHA.
No policy adoption, circuit supersession, owner recovery, paid inference, source
collection, historical backfill or campaign activation is part of this review.
