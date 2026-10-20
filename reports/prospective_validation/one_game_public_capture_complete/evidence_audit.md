# Prospective evidence audit

Game: 401909090; Oklahoma City Thunder at San Antonio Spurs.
Recorded tipoff: 2026-10-21T01:30:00Z. Target T−24h: 2026-10-20T01:30:00Z.
Actual snapshot: 2026-10-20T03:14:02.076933Z; packet created: 2026-10-20T03:14:02.076933Z.
Timing: **late**, deviation 6242.076933 seconds; strict T−24h eligible: **False**.

## Structured statistics

* San Antonio Spurs: {"omitted_features": [{"feature": "recent_regular_season", "reason": "no_completed_games"}, {"feature": "rest_at_cutoff", "reason": "no_reliable_latest_completed_game"}], "regular_season_record": {"games_completed": 0, "losses": 0, "wins": 0}}
* Oklahoma City Thunder: {"omitted_features": [{"feature": "recent_regular_season", "reason": "no_completed_games"}, {"feature": "rest_at_cutoff", "reason": "no_reliable_latest_completed_game"}], "regular_season_record": {"games_completed": 0, "losses": 0, "wins": 0}}

## Official injuries

Verification: observed_public_capture_upper_bound; issue: 2026-10-20T03:00:00Z; availability bound: 2026-10-20T03:14:01.973824Z.
Source: https://ak-static.cms.nba.com/referee/injury/Injury-Report_2026-10-19_11_00PM.pdf. Method: deterministic pypdf coordinates; no healthy-player inference.
* home: reported; flags: []
  * Harris, Tobias: Out; Injury/Illness - Left Calf Strain; reference cd76fc133d449325fef642e7ea0ade26ad83e01a0b5813a8c478388ccb86b0e6:page:1; flags []
  * Quaintance, Jayden: Out; Injury/Illness - Right Knee Surgery; reference cd76fc133d449325fef642e7ea0ade26ad83e01a0b5813a8c478388ccb86b0e6:page:2; flags []
* away: reported; flags: []
  * Oweh, Otega: Out; Injury/Illness - Right Achilles Tendon Repair / Surgery; reference cd76fc133d449325fef642e7ea0ade26ad83e01a0b5813a8c478388ccb86b0e6:page:1; flags []
  * Sorber, Thomas: Out; Injury/Illness - Right Knee Surgery; reference cd76fc133d449325fef642e7ea0ade26ad83e01a0b5813a8c478388ccb86b0e6:page:1; flags []
  * Topic, Nikola: Out; Injury/Illness - Low Back Surgery; reference cd76fc133d449325fef642e7ea0ade26ad83e01a0b5813a8c478388ccb86b0e6:page:1; flags []

## News findings

Method: bounded model extraction followed by deterministic citation, timestamp, team and verbatim-support checks.
No validated findings; paid_search_not_enabled. This does not imply availability.

## Rejections and limitations

* {"reason": "paid_search_not_enabled"}
* Schedule source and all raw bodies/clocks/hashes are in lineage.json; raw documents are audit-only.
* Source publication metadata is not independent first-publication/version proof. Global latest-report coverage is not certified.
* Early/late snapshots do not qualify as exact T−24h captures. No probabilities or market prices are included.
