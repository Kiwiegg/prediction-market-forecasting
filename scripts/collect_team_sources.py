#!/usr/bin/env python3
"""Collect independent schedule/history sources; resumable by response URL."""

import argparse
from concurrent.futures import ThreadPoolExecutor

from dataset_sources import SPORT, Sources


def collect(api, workers):
    def team(team_id):
        params = {"season": 2026, "seasontype": 2}
        result = api.get(f"{SPORT}/teams/{team_id}/schedule", params)
        if not result or "events" not in result:
            raise RuntimeError(f"Missing full team schedule: {team_id}")
        return result
    with ThreadPoolExecutor(max_workers=workers) as pool:
        boards = list(pool.map(team, range(1, 31)))
    # Fetch every event summary before filtering on its content or availability.
    ids = sorted({e["id"] for b in boards for e in b["events"]
                  if e.get("season", {}).get("year") == 2026})
    def summary(game_id):
        api.get(f"{SPORT}/summary", {"event": game_id})
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for i, _ in enumerate(pool.map(summary, ids), 1):
            if i % 100 == 0:
                print(f"PROGRESS team history {i}/{len(ids)}", flush=True)
    return boards


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="data/nba_2025_26")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    collect(Sources(args.output, args.offline), args.workers)
