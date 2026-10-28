# Final research paper

Read [paper.md](paper.md). Historical experiments are complete; prospective scores
are interim and pending verified outcomes. The report stands on its historical
results even if no further live captures succeed. No collection is activated here.

From the repository root, rebuild without API credentials or network:

```sh
.venv/bin/python -m pip install -r reports/final_research/requirements.txt
.venv/bin/python scripts/build_final_research.py
.venv/bin/python scripts/build_final_research.py --verify reports/final_research
.venv/bin/python -m unittest discover -s tests -q
```

Installing the optional plotting dependency needs package access once; rebuilding
then runs offline. For a dependency-free tables/paper check, use `--no-figures
--output /tmp/nba-paper-tables`. Figures are standard Matplotlib PNG/SVG exports
with fixed styling; byte-identical chart reproduction should use the recorded
Python/Matplotlib/font environment. CSV tables and text are deterministic and are
tested against a clean checkout. No model output is regenerated.

`source_manifest.json` pins 54 existing result/protocol artifacts at baseline
`43ea2d4125e1cfd2214249d8a97e43020ced9cb0`. The builder also checks the original
historical report manifests. `generated_manifest.json` hashes generated paper,
tables and charts; `build.json` binds the prospective input bundle. The complete
historical per-game tables retain failures and missingness; denominators are
explicit in every aggregate table. `paper_template.md` holds the prose and table
placeholders. Edit prose there and rebuild instead of changing generated numbers.

## PDF export

The deliverable is Markdown plus figures; PDF conversion is optional and no PDF
converter has been installed automatically. With Pandoc and XeLaTeX installed:

```sh
cd reports/final_research
pandoc paper.md --from=gfm+tex_math_dollars --standalone \
  --pdf-engine=xelatex -V geometry:margin=0.8in -V fontsize=10pt \
  -V mainfont='DejaVu Serif' -o paper.pdf
```

PNG images resolve relative to this directory. Install the named font or choose an
available Unicode font. Inspect page breaks and wide tables before submission.
Alternatively export HTML and print it using a browser; display mathematics needs
a math renderer. Authorship, affiliation, venue styling and independent scientific
review remain the research owner's submission steps.

## Fixed prospective publication update

[update_protocol.json](update_protocol.json) fixes the capture/reporting boundary
to **2026-11-03T05:00:00Z exclusive**: end of November 2 in US Eastern time,
after the daylight-saving transition. This does not move T−24h or any operational
deadline. Verified outcome retrieval may occur later; its actual timestamp stays
in the update. Earlier editions remain interim rather than claiming final results.

The original pilot audit is unchanged. `prospective_initial/` seeds its unscored
observation; `prospective_update_2026_10_28/` links that manifest and inventories all
seven already audited enrollments, including six unrecoverable attempts.

To append a new immutable reporting bundle from a **restored private checkpoint**
and previously captured outcome directories:

```sh
.venv/bin/python scripts/update_final_prospective.py \
  --private-state /private/path/restored-state \
  --outcomes /private/path/verified-outcomes \
  --previous reports/final_research/prospective_update_2026_10_28 \
  --output reports/final_research/update_november_2
.venv/bin/python scripts/update_final_prospective.py \
  --verify reports/final_research/update_november_2
.venv/bin/python scripts/build_final_research.py \
  --update reports/final_research/update_november_2
```

Or use `--r2` instead of `--private-state`: it requires the original storage-only
environment variables used by `review-nba-denial.yml` and the storage SDK from
`deploy/github-actions/requirements.txt`. It performs **GET-only** idle-store
restore, private replay and sanitized projection; it never acquires an owner,
publishes a checkpoint, retrieves an article/outcome or calls Brave/Anthropic.
Do not put credentials on the command line. If an active owner exists, wait for
that worker to finish; the reporting command cannot release or bypass it.

Outcome directories must be named by game ID under `--outcomes`, each with the
existing `prospective_evaluate` `outcome.json`, manifest and raw saved ESPN response.
Use the existing final-outcome capture procedure only after tipoff/final status
and required operator approval. **The reporting script never fetches a result.**
Missing directories leave outcomes pending; rejected/mismatched/unfinalized
captures fail validation. Rescheduled/canceled fixtures stay explicit exclusions.
Do not bypass existing denial journals to obtain results. No outcome was newly
retrieved for this edition.

Every enrolled game is retained; failed captures cannot be rescued or backfilled.
Updates refuse overwrites, removed prior IDs, changed prior predictions/packet
hashes and replacement of a verified outcome. A successful primary pair does not
require v1 or a market quote. Scores are stratified by the original evidence
cohort and denial-policy amendment. If no outcomes are verified, sample size is
zero and losses remain null. Use a new output directory for each append and pass
the latest bundle as `--previous`; do not delete a completed bundle to rerun it.
Fresh audit-attestation hashes may differ as campaign circuits/checkpoint metadata
change; the preceding audit is preserved in the previous immutable bundle while
all original per-game forecast fields and packet hashes remain locked.

Offline historical replay:

```sh
.venv/bin/python scripts/analyze_heldout.py --authorize-evaluation --replay reports/heldout_150
.venv/bin/python scripts/analyze_v2_development.py --replay reports/leap_nba_v2_development_50
.venv/bin/python scripts/evaluate_synthetic_elicitation.py --replay reports/leap_nba_v2_phase1
.venv/bin/python scripts/replay_live_pilot_summary.py reports/prospective_live_pilot_1
```

The evaluation flag permits reading the **already sealed** historical results; it
does not trigger inference. Private source/provider authenticity checks require
the original captures. Public replay proves arithmetic/hash consistency only.

## Collection state

The approved article-denial policy was adopted and privately verified; see
[operations/policy_adoption.md](operations/policy_adoption.md). Paid live collection
remains **disabled**. No new games were enrolled or paid calls issued. Activation
requires separate explicit approval. The USD50 campaign and USD1.35/game ceilings,
original 30-attempt cap, claims and reservations are unchanged. A 30-success sample
is not promised or required to publish this report; the original 100-game study
is neither silently restarted nor declared complete.
