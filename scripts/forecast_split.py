"""Outcome-blind, deterministic monthly 50/150 assignment for the locked sample."""
import argparse
import json
from collections import Counter
from pathlib import Path

from evidence_documents import canonical, digest

SEED = "nba-direct-baseline-split-2026-10-21-v1"
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT / "data/nba_2025_26"
DEFAULT_SPLIT = ROOT / "experiments/nba_2025_26_split.json"


def immutable_json(path, value):
    path = Path(path)
    data = canonical(value) + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as f:
            f.write(data)
    except FileExistsError:
        if path.read_bytes() != data:
            raise ValueError("Refusing to overwrite immutable file: " + str(path))
    return value


def split_manifest(dataset=DEFAULT_DATA):
    # Only these schedule/identity fields participate; no labels or prices.
    games = json.loads((Path(dataset) / "selection_manifest.json").read_text())["games"]
    identities = sorted(({"game_id": g["game_id"], "month": g["month"]} for g in games), key=lambda g: g["game_id"])
    if len(identities) != 200 or len({g["game_id"] for g in identities}) != 200:
        raise ValueError("The historical sample must contain exactly 200 distinct games")
    counts = Counter(g["month"] for g in identities)
    quotas = {m: n * 50 // 200 for m, n in counts.items()}
    for m in sorted(counts, key=lambda m: (-(counts[m] * 50 % 200), m))[:50 - sum(quotas.values())]:
        quotas[m] += 1
    def rank(gid, purpose):
        return digest((SEED + "|" + purpose + "|" + gid).encode())
    development = set()
    for month in sorted(counts):
        members = [g["game_id"] for g in identities if g["month"] == month]
        development.update(sorted(members, key=lambda gid: (rank(gid, "assignment"), gid))[:quotas[month]])
    members = [{**g, "subset": "development" if g["game_id"] in development else "evaluation"} for g in identities]
    order = {subset: sorted([g["game_id"] for g in members if g["subset"] == subset],
                            key=lambda gid: (rank(gid, "run-order"), gid)) for subset in ("development", "evaluation")}
    return {"schema_version": 1, "seed": SEED, "sample_size": 200,
        "assignment_rule": "Largest-remainder monthly quotas totaling 50; rank SHA256(seed|assignment|game_id) within month; remainder ties by month.",
        "run_order_rule": "SHA256(seed|run-order|game_id), then game_id; pilot is first five development IDs.",
        "identity_projection_sha256": digest(canonical(identities)),
        "monthly_counts": {m: {"total": counts[m], "development": quotas[m], "evaluation": counts[m] - quotas[m]} for m in sorted(counts)},
        "games": members, "run_order": order,
        "historical_interpretation": "Exploratory: completed games may be in model knowledge. Prospective captures are the eventual primary out-of-sample evaluation."}


def load_split(path=DEFAULT_SPLIT, dataset=DEFAULT_DATA):
    saved = json.loads(Path(path).read_text())
    if saved != split_manifest(dataset):
        raise ValueError("Split differs from the fixed seed, schedule identities or assignment rule")
    return saved


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dataset", type=Path, default=DEFAULT_DATA)
    p.add_argument("--output", type=Path, default=DEFAULT_SPLIT)
    p.add_argument("--check", action="store_true")
    args = p.parse_args()
    value = load_split(args.output, args.dataset) if args.check else immutable_json(args.output, split_manifest(args.dataset))
    print(json.dumps({"development": len(value["run_order"]["development"]), "evaluation": len(value["run_order"]["evaluation"]),
                      "manifest_sha256": digest(canonical(value)), "monthly_counts": value["monthly_counts"]}))


if __name__ == "__main__":
    main()
