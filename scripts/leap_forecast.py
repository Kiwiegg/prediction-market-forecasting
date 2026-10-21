#!/usr/bin/env python3
"""Bounded, immutable LEAP-NBA inference; no labels, markets, tools or retrieval."""
import argparse
import gzip
import json
import math
import os
import time
from pathlib import Path

from direct_forecast import signed_record, verify_raw
from evidence_documents import canonical, digest
from forecast_split import ROOT, DEFAULT_DATA, DEFAULT_SPLIT, immutable_json, load_split
from investigate_kalshi import iso
from leap_evidence import (VERSION, GROUPS, FROZEN, aggregate, build_groups, checked_config,
    frozen_assets, load_evidence, lr_object, strict_lr_json)
from research_providers import CapturedHTTP, ProviderError

DEFAULT_CONFIG = ROOT / "examples/leap_forecast_config.json"
DEFAULT_CACHE = ROOT / "captures/leap_nba_v1_cache"
PILOT = ["401810544", "401810485", "401810279", "401836746", "401809808"]


def group_spec(group, config):
    checked_config(config)
    if group["group"] not in GROUPS or group["group_evidence_sha256"] != digest(canonical(group["content"])):
        raise ValueError("Unbound group projection")
    content = group["content"]
    identity = {"game_id": content["game_id"], "group": group["group"],
        "evidence_sha256": group["evidence_sha256"], "group_evidence_sha256": group["group_evidence_sha256"],
        "usable": group["usable"], "missing_reason": group["missing_reason"],
        "deduplication_decisions": group["deduplication_decisions"]}
    envelope = {"evidence_sha256": identity["evidence_sha256"],
        "group_evidence_sha256": identity["group_evidence_sha256"], "group_packet": content}
    prompt = (ROOT / "prompts/leap_nba_lr_v1.txt").read_text()
    payload = {"model": config["model"], "system": prompt,
        "messages": [{"role": "user", "content": canonical(envelope).decode()}],
        "temperature": config["generation"]["temperature"], "max_tokens": config["generation"]["max_tokens"],
        "output_config": {"format": {"type": "json_schema", "schema": json.loads(
            (ROOT / "experiments/leap_nba_v1_response_schema.json").read_text())}}}
    wire = {"provider": config["provider"], "method": "POST",
        "url": config.get("endpoint", "https://api.anthropic.com/v1/messages"), "payload": payload}
    bound = len(canonical(payload)) + config["input_overhead_token_bound"]
    cost = (bound * config["prices"]["input_usd_per_million"] + 128 * config["prices"]["output_usd_per_million"]) / 1e6
    return {**identity, "key": digest(canonical(wire)), "wire": wire, "input_token_bound": bound,
        "reserved_cost_usd": cost if group["usable"] and config["provider"] != "mock" else 0.0}


def brief(spec):
    return {k: v for k, v in spec.items() if k != "wire"}


def plan_experiment(dataset, split_path, config, subset="development", limit=5, authorize_evaluation=False):
    if subset not in ("development", "evaluation") or subset == "evaluation" and not authorize_evaluation:
        raise ValueError("Reserved evaluation requires separate --authorize-evaluation")
    checked_config(config); assets = frozen_assets()
    split = load_split(split_path, dataset)
    if split["run_order"]["development"][:5] != PILOT:
        raise ValueError("Pilot IDs differ from the frozen direct baseline")
    if type(limit) is not int or not 1 <= limit <= len(split["run_order"][subset]):
        raise ValueError("Limit outside fixed subset")
    games, specs = [], []
    for gid in split["run_order"][subset][:limit]:
        packet = load_evidence(dataset, gid)
        groups = [group_spec(g, config) for g in build_groups(packet)]
        specs.extend(groups)
        games.append({"game_id": gid, "evidence_sha256": packet["evidence_snapshot_sha256"], "groups": [brief(g) for g in groups]})
    return {"schema_version": 1, "method": "leap_nba_v1_mock" if config["provider"] == "mock" else "leap_nba_v1",
        "subset": subset, "split_sha256": digest(canonical(split)), "config": config, "frozen_assets": assets,
        "historical_interpretation": "exploratory_completed_games_possible_memorization", "games": games}, specs


def validate_response(response, spec, config):
    usage = response.get("usage")
    if (not isinstance(usage, dict) or any(type(usage.get(k)) is not int or usage[k] < 0 for k in ("input_tokens", "output_tokens"))
            or usage["input_tokens"] > spec["input_token_bound"] or usage["output_tokens"] > 128
            or usage.get("cache_creation_input_tokens", 0) or usage.get("cache_read_input_tokens", 0)
            or not isinstance(usage.get("server_tool_use", {}), dict) or any(usage.get("server_tool_use", {}).values())):
        raise ValueError("Missing/excess usage or unexpected tool/cache billing")
    if response.get("stop_reason") != "end_turn" or response.get("model") != config["model"]:
        raise ValueError("Incomplete response or returned model differs from requested model")
    if config["provider"] == "anthropic":
        blocks = response.get("content")
        if (response.get("role") != "assistant" or not isinstance(blocks, list) or len(blocks) != 1
                or not isinstance(blocks[0], dict) or set(blocks[0]) - {"type", "text", "citations"}
                or blocks[0].get("type") != "text" or not isinstance(blocks[0].get("text"), str) or blocks[0].get("citations")):
            raise ValueError("Unapproved tools, citations or response blocks")
        return strict_lr_json(blocks[0]["text"])
    if response.get("tool_calls"):
        raise ValueError("Gateway returned forbidden tools")
    return lr_object(response.get("response"))


def verify_record(record):
    body = {k: v for k, v in record.items() if k != "record_sha256"}
    if record.get("record_sha256") != digest(canonical(body)) or record.get("group") not in GROUPS:
        raise ValueError("Group record integrity failure")
    if record["status"] == "success":
        lr_object({k: record[k] for k in ("likelihood_ratio", "evidence_sufficiency")})
    elif record["status"] == "skipped_missing":
        if record["likelihood_ratio"] != 1 or not record["missing_reason"] or record["usable"]:
            raise ValueError("Invalid neutral missing group")
    elif record["status"] not in ("failed", "not_attempted_budget") or record["likelihood_ratio"] is not None:
        raise ValueError("Invalid failed group")
    return record


def base_record(spec, config, status):
    return {**brief(spec), "request_sha256": spec["key"], "schema_version": 1, "status": status,
        "method": "leap_nba_v1_mock" if config["provider"] == "mock" else "leap_nba_v1",
        "provider": config["provider"], "requested_model": config["model"], "returned_model": None,
        "prompt_version": VERSION, "prompt_sha256": FROZEN["prompts/leap_nba_lr_v1.txt"],
        "generation_settings": config["generation"], "likelihood_ratio": None, "evidence_sufficiency": None,
        "extreme_lr": None, "request_started_at_utc": None, "response_retrieved_at_utc": None,
        "usage": None, "latency_seconds": None, "estimated_cost_usd": 0.0, "estimated_cost_kind": "not_requested",
        "prices": config["prices"], "raw_response": None, "error": None}


def load_cached(spec, cache):
    folder = Path(cache) / spec["key"]
    r = verify_record(json.loads((folder / "group.json").read_text()))
    for key in ("game_id", "group", "evidence_sha256", "group_evidence_sha256", "key", "usable", "missing_reason"):
        if r[key] != spec[key]:
            raise ValueError("Cache identity mismatch")
    verify_raw(r, folder)
    if r["raw_response"] and (folder / "raw" / (spec["key"] + ".request.json")).read_bytes() != canonical(spec["wire"]) + b"\n":
        raise ValueError("Cached wire request changed")
    return r


def cached_group(spec, config, cache, allow_paid=False, transport_factory=CapturedHTTP):
    folder = Path(cache) / spec["key"]
    final = folder / "group.json"
    if final.exists():
        return load_cached(spec, cache)
    folder.mkdir(parents=True, exist_ok=True)
    if not spec["usable"]:
        r = base_record(spec, config, "skipped_missing")
        r.update(likelihood_ratio=1.0, evidence_sufficiency="not_applicable_missing")
        return immutable_json(final, signed_record(r))
    attempt = folder / "attempt.json"
    new = not attempt.exists()
    if new:
        if config["provider"] != "mock" and (not allow_paid or not os.environ.get(config["key_env"])):
            raise ValueError("Live inference requires authorization and credential")
        with attempt.open("xb") as f:
            f.write(canonical({"request_sha256": spec["key"], "claimed_at_utc": iso(time.time())}) + b"\n")
    r = base_record(spec, config, "failed")
    r.update(estimated_cost_usd=spec["reserved_cost_usd"], estimated_cost_kind="reserved_upper_bound_usage_unavailable")
    transport = transport_factory(folder / "raw", allow_network=allow_paid and new)
    try:
        if config["provider"] == "mock":
            response = {"response": {"likelihood_ratio": 1.0, "evidence_sufficiency": "limited"},
                "usage": {"input_tokens": 0, "output_tokens": 0}, "model": config["model"], "stop_reason": "end_turn"}
            immutable_json(folder / "mock_response.json", response)
        else:
            if not new and not (folder / "raw" / (spec["key"] + ".json")).is_file():
                raise ValueError("Previous attempt outcome uncertain; automatic resend forbidden")
            key = os.environ.get(config["key_env"], "")
            headers = {"x-api-key": key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"}
            if config["provider"] == "json_gateway":
                headers = {"Authorization": "Bearer " + key, "Content-Type": "application/json"}
            wire = spec["wire"]
            response = transport.request(wire["provider"], "POST", wire["url"], wire["payload"], headers, 128 * 16 + 8192)
        r.update(returned_model=response.get("model"), usage=response.get("usage"))
        u = response.get("usage")
        if isinstance(u, dict) and all(type(u.get(k)) is int and u[k] >= 0 for k in ("input_tokens", "output_tokens")):
            r.update(estimated_cost_usd=(u["input_tokens"] * config["prices"]["input_usd_per_million"] +
                u["output_tokens"] * config["prices"]["output_usd_per_million"]) / 1e6,
                estimated_cost_kind="mock_no_provider_calls" if config["provider"] == "mock" else "reported_tokens_at_configured_rates")
        result = validate_response(response, spec, config)
        r.update(status="success", **result, extreme_lr=result["likelihood_ratio"] <= .1 or result["likelihood_ratio"] >= 10)
        if config["provider"] == "mock":
            r["latency_seconds"] = 0.0
    except (ProviderError, ValueError, TypeError, KeyError, OSError) as exc:
        r["error"] = {"type": type(exc).__name__, "message": str(exc) if isinstance(exc, ValueError) else "Provider/response failure; inspect private capture"}
    if transport.calls:
        m = transport.calls[-1]
        r.update(request_started_at_utc=m["started_at_utc"], response_retrieved_at_utc=m["retrieved_at_utc"],
            latency_seconds=m["latency_seconds"], raw_response={"body_file": "raw/" + m["source_id"] + ".body.gz",
            "body_sha256": m["body_sha256"], "http_status": m["http_status"], "truncated": m["truncated"]})
    r["record_created_at_utc"] = iso(time.time())
    return immutable_json(final, signed_record(r))


def game_record(gid, evidence_hash, records):
    return signed_record({"game_id": gid, "evidence_sha256": evidence_hash, "groups": records, **aggregate(records)})


def counters(games):
    records = [r for g in games for r in g["groups"]]
    return {"planned_games": len(games), "successful_forecasts": sum(g["status"] == "success" for g in games),
        "failed_forecasts": sum(g["status"] != "success" for g in games),
        "group_status_counts": {s: sum(r["status"] == s for r in records) for s in ("success", "skipped_missing", "failed", "not_attempted_budget")},
        "reported_usage": {k: sum(r.get("usage", {}).get(k, 0) for r in records if isinstance(r.get("usage"), dict)) for k in ("input_tokens", "output_tokens")},
        "usage_unavailable_groups": sum(r["status"] == "failed" and r.get("usage") is None for r in records),
        "estimated_response_cost_usd": sum(r["estimated_cost_usd"] for r in records),
        "summed_observation_latency_seconds": sum(r["latency_seconds"] or 0 for r in records)}


def load_experiment(folder):
    folder = Path(folder)
    complete = json.loads((folder / "completion.json").read_text())
    run = json.loads((folder / "run.json").read_text())
    required = {"run.json"} | {"forecasts/" + g["game_id"] + ".json" for g in run["games"]}
    if not required <= set(complete["files"]) or len({g["game_id"] for g in run["games"]}) != len(run["games"]):
        raise ValueError("Incomplete or duplicate experiment manifest")
    for name, sha in complete["files"].items():
        path = (folder / name).resolve()
        if folder.resolve() not in path.parents or digest(path.read_bytes()) != sha:
            raise ValueError("Completed experiment file hash mismatch")
    games = []
    for planned in run["games"]:
        record = json.loads((folder / "forecasts" / (planned["game_id"] + ".json")).read_text())
        if len(planned["groups"]) != 4 or len(record["groups"]) != 4:
            raise ValueError("Four group records required")
        for r, s in zip(record["groups"], planned["groups"]):
            verify_record(r)
            if any(r[k] != s[k] for k in ("key", "game_id", "group", "evidence_sha256", "group_evidence_sha256", "usable", "missing_reason")):
                raise ValueError("Manifest/group identity mismatch")
        expected = game_record(planned["game_id"], planned["evidence_sha256"], record["groups"])
        if record != expected:
            raise ValueError("Game aggregation does not reproduce")
        games.append(record)
    if any(complete.get(k) != v for k, v in counters(games).items()):
        raise ValueError("Completion counters do not reconcile")
    reservations = [json.loads(p.read_text()) for p in (folder / "reservations").glob("*.json")]
    reserved_cost = math.fsum(r["cost_usd"] for r in reservations)
    if (complete["paid_call_reservations"] != len(reservations) or complete["reserved_cost_usd"] != reserved_cost
            or len(reservations) > run["max_paid_calls"] or reserved_cost > run["max_estimated_cost_usd"] + 1e-12):
        raise ValueError("Saved request reservations exceed or disagree with run budgets")
    return run, games, complete


def protect_paths(output, cache, dataset):
    paths = [Path(p).resolve() for p in (output, cache, dataset)]
    for i, a in enumerate(paths):
        for b in paths[i + 1:]:
            if a == b or a in b.parents or b in a.parents:
                raise ValueError("Run, cache and historical dataset must be separate directories")


def run_experiment(plan, specs, output, cache, max_paid_calls=20, max_cost=1.0, allow_paid=False, transport_factory=CapturedHTTP):
    if type(max_paid_calls) is not int or max_paid_calls < 0 or type(max_cost) not in (int, float) or not math.isfinite(max_cost) or max_cost < 0:
        raise ValueError("Explicit finite nonnegative call/cost budgets required")
    checked_config(plan["config"]); frozen_assets()
    if [brief(s) for s in specs] != [g for game in plan["games"] for g in game["groups"]]:
        raise ValueError("Request specifications differ from the frozen run plan")
    if any(digest(canonical(s["wire"])) != s["key"] for s in specs):
        raise ValueError("Wire request cache identity differs")
    output, cache = Path(output), Path(cache)
    protect_paths(output, cache, DEFAULT_DATA)
    config = plan["config"]
    if config["provider"] != "mock" and (not allow_paid or not os.environ.get(config["key_env"])):
        raise ValueError("Live run requires explicit paid opt-ins and credential")
    identity = {**plan, "cache_directory": str(cache.resolve()), "max_paid_calls": max_paid_calls, "max_estimated_cost_usd": max_cost}
    output.mkdir(parents=True, exist_ok=True)
    immutable_json(output / "run.json", identity)
    if (output / "completion.json").exists():
        return load_experiment(output)[2]
    lock = output / ".running"
    with lock.open("xb") as f:
        f.write(b"Active or interrupted run; no automatic concurrent paid retry.\n")
    try:
        for game in plan["games"]:
            target = output / "forecasts" / (game["game_id"] + ".json")
            if target.exists():
                continue
            records = []
            for spec in [s for s in specs if s["game_id"] == game["game_id"]]:
                needs_call = spec["usable"] and config["provider"] != "mock" and not any(
                    (cache / spec["key"] / name).exists() for name in ("group.json", "attempt.json"))
                reservations = [json.loads(p.read_text()) for p in (output / "reservations").glob("*.json")]
                if needs_call:
                    if len(reservations) >= max_paid_calls or math.fsum(r["cost_usd"] for r in reservations) + spec["reserved_cost_usd"] > max_cost + 1e-12:
                        r = base_record(spec, config, "not_attempted_budget")
                        r["error"] = {"type": "BudgetExceeded", "message": "Call/cost limit reached before request"}
                        records.append(signed_record(r)); continue
                    immutable_json(output / "reservations" / (spec["key"] + ".json"), {"request_sha256": spec["key"],
                        "cost_usd": spec["reserved_cost_usd"], "reserved_at_utc": iso(time.time())})
                records.append(cached_group(spec, config, cache, allow_paid, transport_factory))
            immutable_json(target, game_record(game["game_id"], game["evidence_sha256"], records))
        games = [json.loads((output / "forecasts" / (g["game_id"] + ".json")).read_text()) for g in plan["games"]]
        reservations = [json.loads(p.read_text()) for p in (output / "reservations").glob("*.json")]
        files = {str(p.relative_to(output)): digest(p.read_bytes()) for p in sorted(output.rglob("*")) if p.is_file() and p.name != ".running"}
        complete = {**counters(games), "paid_call_reservations": len(reservations),
            "reserved_cost_usd": math.fsum(r["cost_usd"] for r in reservations),
            "reused_observations": sum(r["usable"] and r["key"] not in {s["request_sha256"] for s in reservations}
                and config["provider"] != "mock" and r["status"] != "not_attempted_budget" for g in games for r in g["groups"]),
            "completed_at_utc": iso(time.time()), "files": files}
        immutable_json(output / "completion.json", complete)
        load_experiment(output)
        return complete
    finally:
        lock.unlink()


def verify_experiment(folder, dataset=DEFAULT_DATA, split_path=DEFAULT_SPLIT, authorize_evaluation=False, cache_override=None):
    initial = json.loads((Path(folder) / "run.json").read_text())
    if initial["subset"] == "evaluation" and not authorize_evaluation:
        raise ValueError("Reserved evaluation verification requires authorization")
    run, games, complete = load_experiment(folder)
    plan, specs = plan_experiment(dataset, split_path, run["config"], run["subset"], len(games), authorize_evaluation)
    if any(run[k] != v for k, v in plan.items()):
        raise ValueError("Frozen experiment settings/evidence changed")
    cache = Path(cache_override or run["cache_directory"])
    for spec, r in zip(specs, [r for g in games for r in g["groups"]]):
        if r["status"] == "not_attempted_budget":
            continue
        if load_cached(spec, cache) != r:
            raise ValueError("Cached and experiment observations differ")
        if r["status"] == "success":
            folder = cache / spec["key"]
            if r["raw_response"]:
                response = json.loads(gzip.decompress((folder / r["raw_response"]["body_file"]).read_bytes()))
            else:
                if run["config"]["provider"] != "mock":
                    raise ValueError("Paid success is missing raw capture")
                response = json.loads((folder / "mock_response.json").read_text())
            parsed = validate_response(response, spec, run["config"])
            if any(r[k] != v for k, v in parsed.items()):
                raise ValueError("Raw LR response does not reproduce")
    return complete


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dataset", type=Path, default=DEFAULT_DATA)
    p.add_argument("--split", type=Path, default=DEFAULT_SPLIT)
    p.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    p.add_argument("--subset", choices=("development", "evaluation"), default="development")
    p.add_argument("--authorize-evaluation", action="store_true")
    p.add_argument("--limit", type=int, default=5)
    p.add_argument("--output", type=Path)
    p.add_argument("--cache", type=Path, help="Shared LR cache; defaults to captures/leap_nba_v1_cache, or original run cache for --verify")
    p.add_argument("--max-paid-calls", type=int, default=20)
    p.add_argument("--max-estimated-cost-usd", type=float, default=1.0)
    for flag in ("mock", "live", "allow-network", "allow-inference", "plan"):
        p.add_argument("--" + flag, action="store_true")
    p.add_argument("--verify", type=Path)
    args = p.parse_args()
    if args.verify:
        if args.live or args.mock or args.allow_network or args.allow_inference:
            p.error("Read-only verification cannot enable inference/network")
        result = verify_experiment(args.verify, args.dataset, args.split, args.authorize_evaluation, args.cache)
        print(json.dumps({"verified": True, "games": result["planned_games"], "network_calls": 0})); return
    if args.mock and (args.live or args.allow_network or args.allow_inference):
        p.error("Mock cannot enable paid/network flags")
    config = json.loads(args.config.read_text())
    if args.mock:
        config = dict(config, provider="mock", model="offline-lr-one")
    plan, specs = plan_experiment(args.dataset, args.split, config, args.subset, args.limit, args.authorize_evaluation)
    if args.plan or not (args.mock or args.live):
        print(json.dumps({"plan": plan, "maximum_new_requests": sum(s["usable"] for s in specs) if config["provider"] != "mock" else 0,
            "estimated_uncached_upper_bound_usd": math.fsum(s["reserved_cost_usd"] for s in specs),
            "max_paid_calls": args.max_paid_calls, "max_estimated_cost_usd": args.max_estimated_cost_usd,
            "credential_present": bool(os.environ.get(config["key_env"])), "network_calls": 0}, indent=2)); return
    if not args.output or args.live and not (args.allow_network and args.allow_inference):
        p.error("Specify --output and all live opt-ins")
    cache = args.cache or DEFAULT_CACHE
    protect_paths(args.output, cache, args.dataset)
    result = run_experiment(plan, specs, args.output, cache, args.max_paid_calls, args.max_estimated_cost_usd,
        args.live and args.allow_network and args.allow_inference)
    print(json.dumps({k: v for k, v in result.items() if k != "files"}, indent=2))


if __name__ == "__main__":
    main()
