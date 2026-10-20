# Prospective evidence audit

Game: 401909090; Oklahoma City Thunder at San Antonio Spurs.
Recorded tipoff: 2026-10-21T01:30:00Z. Target T−24h: 2026-10-20T01:30:00Z.
Actual snapshot: 2026-10-20T02:50:58.121238Z; packet created: 2026-10-20T02:50:58.121238Z.
Timing: **late**, deviation 4858.121238 seconds; strict T−24h eligible: **False**.

## Structured statistics

* San Antonio Spurs: {"omitted_features": [{"feature": "recent_regular_season", "reason": "no_completed_games"}, {"feature": "rest_at_cutoff", "reason": "no_reliable_latest_completed_game"}], "regular_season_record": {"games_completed": 0, "losses": 0, "wins": 0}}
* Oklahoma City Thunder: {"omitted_features": [{"feature": "recent_regular_season", "reason": "no_completed_games"}, {"feature": "rest_at_cutoff", "reason": "no_reliable_latest_completed_game"}], "regular_season_record": {"games_completed": 0, "losses": 0, "wins": 0}}

## Official injuries

Verification: observed_public_capture_upper_bound; issue: 2026-10-20T02:45:00Z; availability bound: 2026-10-20T02:50:58.021831Z.
Source: https://ak-static.cms.nba.com/referee/injury/Injury-Report_2026-10-19_10_45PM.pdf. Method: deterministic pypdf coordinates; no healthy-player inference.
* home: reported; flags: []
  * Harris, Tobias: Out; Injury/Illness - Left Calf Strain; reference a4060b6acc56b0d3f1716d871201d29c27650b3c4f6eb69f17e7eec949ac1732:page:1; flags []
  * Quaintance, Jayden: Out; Injury/Illness - Right Knee Surgery; reference a4060b6acc56b0d3f1716d871201d29c27650b3c4f6eb69f17e7eec949ac1732:page:2; flags []
* away: reported; flags: []
  * Oweh, Otega: Out; Injury/Illness - Right Achilles Tendon Repair / Surgery; reference a4060b6acc56b0d3f1716d871201d29c27650b3c4f6eb69f17e7eec949ac1732:page:1; flags ['reason_extraction_ambiguous', 'reason_extraction_ambiguous', 'reason_extraction_ambiguous', 'reason_extraction_ambiguous', 'reason_extraction_ambiguous', 'reason_extraction_ambiguous', 'reason_extraction_ambiguous', 'reason_extraction_ambiguous', 'reason_extraction_ambiguous', 'reason_extraction_ambiguous', 'reason_extraction_ambiguous', 'reason_extraction_ambiguous', 'reason_extraction_ambiguous', 'reason_extraction_ambiguous']
  * Sorber, Thomas: Out; Injury/Illness - Right Knee Surgery; reference a4060b6acc56b0d3f1716d871201d29c27650b3c4f6eb69f17e7eec949ac1732:page:1; flags []
  * Topic, Nikola: Out; Injury/Illness - Low Back Surgery; reference a4060b6acc56b0d3f1716d871201d29c27650b3c4f6eb69f17e7eec949ac1732:page:1; flags []

## News findings

Method: bounded model extraction followed by deterministic citation, timestamp, team and verbatim-support checks.
No validated findings; paid_search_not_enabled. This does not imply availability.

## Rejections and limitations

* {"reason": "paid_search_not_enabled"}
* Schedule source and all raw bodies/clocks/hashes are in lineage.json; raw documents are audit-only.
* Source publication metadata is not independent first-publication/version proof. Global latest-report coverage is not certified.
* Early/late snapshots do not qualify as exact T−24h captures. No probabilities or market prices are included.
