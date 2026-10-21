#!/usr/bin/env python3
"""Frozen-packet direct probability baseline. Default: offline cost plan only.

This module never reads labels, prices, evaluation exports, source audit files,
or research tools. Evaluation is a separate CLI after a run is sealed.
"""
import argparse
import gzip
import json
import math
import os
import re
import time
import urllib.parse
from pathlib import Path

from evidence_documents import canonical, digest
from forecast_split import DEFAULT_DATA, DEFAULT_SPLIT, ROOT, immutable_json, load_split
from investigate_kalshi import iso
from research_providers import CapturedHTTP, ProviderError
from shared_evidence import load_game_snapshot, validate_packet

PROMPT_VERSION = "direct_home_win_v1"
PROMPT_HASH = "e073236a57b397456d14ee003838162019af97f36d905a4a1b77cb57b176174c"
DEFAULT_CONFIG = ROOT / "examples/direct_forecast_config.json"
RESPONSE_SCHEMA = {"type": "object", "properties": {"home_win_probability": {
    "type": "number", "description": "Probability that the home team wins, between 0 and 1 inclusive."}},
    "required": ["home_win_probability"], "additionalProperties": False}


def checked_config(config):
    required = {"provider", "model", "key_env", "prompt_version", "generation", "prices", "input_overhead_token_bound"}
    if set(config) - (required | {"endpoint"}) or required - set(config):
        raise ValueError("Unapproved forecasting configuration fields")
    if config["provider"] not in {"anthropic", "json_gateway", "mock"}:
        raise ValueError("Supported providers: anthropic, json_gateway, mock")
    if not re.fullmatch(r"[A-Z_][A-Z0-9_]*", config["key_env"]):
        raise ValueError("Credential configuration must name an environment variable")
    if not isinstance(config["model"], str) or not re.fullmatch(r"[\w.:/-]{1,200}", config["model"]):
        raise ValueError("Invalid model identifier")
    if config["prompt_version"] != PROMPT_VERSION:
        raise ValueError("Only the frozen v1 baseline prompt is registered")
    generation = config["generation"]
    if (set(generation) != {"temperature", "max_tokens", "structured_json"}
            or type(generation["temperature"]) not in (int, float)
            or not math.isfinite(generation["temperature"]) or not 0 <= generation["temperature"] <= .2
            or type(generation["max_tokens"]) is not int or not 32 <= generation["max_tokens"] <= 256
            or type(generation["structured_json"]) is not bool):
        raise ValueError("Require fixed low temperature, 32–256 output tokens and an explicit JSON-mode choice")
    if type(config["input_overhead_token_bound"]) is not int or not 4096 <= config["input_overhead_token_bound"] <= 16384:
        raise ValueError("Conservative input overhead must be 4096–16384 tokens")
    if (set(config["prices"]) != {"input_usd_per_million", "output_usd_per_million"}
            or any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v in config["prices"].values())):
        raise ValueError("Explicit positive finite conservative token price estimates required")
    if "endpoint" in config and config["provider"] != "json_gateway":
        raise ValueError("Custom endpoint is allowed only for an explicitly selected JSON gateway")
    if config["provider"] == "json_gateway":
        parsed = urllib.parse.urlsplit(config.get("endpoint", ""))
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                or parsed.query or parsed.fragment or parsed.port not in (None, 443)):
            raise ValueError("Gateway must be credential-free HTTPS with no query or fragment")
    return config


def probability(value):
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError("Probability must be a finite JSON number in [0,1]")
    return float(value)


def probability_object(value):
    if not isinstance(value, dict) or set(value) != {"home_win_probability"}:
        raise ValueError("Response must contain only home_win_probability")
    return probability(value["home_win_probability"])


def strict_probability_json(text):
    def pairs(items):
        if len({k for k, _ in items}) != len(items):
            raise ValueError("Duplicate JSON keys")
        return dict(items)
    def invalid_constant(_):
        raise ValueError("Nonstandard JSON numeric constant")
    return probability_object(json.loads(text, object_pairs_hook=pairs, parse_constant=invalid_constant))


def load_evidence(dataset, game_id):
    """Exactly the same consumer-neutral frozen packet used by future methods."""
    packet = load_game_snapshot(dataset, game_id)
    if packet["game_id"] != game_id:
        raise ValueError("Manifest-bound evidence game mismatch")
    return packet


def request_spec(packet, config):
    checked_config(config)
    validate_packet(packet)
    if packet.get("evidence_snapshot_sha256") != digest(canonical({k: v for k, v in packet.items() if k != "evidence_snapshot_sha256"})):
        raise ValueError("Evidence hash differs from its supplied frozen content")
    prompt = (ROOT / "prompts" / (PROMPT_VERSION + ".txt")).read_bytes()
    if digest(prompt) != PROMPT_HASH:
        raise ValueError("Frozen prompt changed; register a new version before a new experiment")
    generation = config["generation"]
    payload = {"model": config["model"], "system": prompt.decode(),
        "messages": [{"role": "user", "content": canonical(packet).decode()}],
        "temperature": generation["temperature"], "max_tokens": generation["max_tokens"]}
    if generation["structured_json"]:
        # Anthropic does not support minimum/maximum in the wire schema; the
        # range is enforced locally, even when constrained decoding is enabled.
        payload["output_config"] = {"format": {"type": "json_schema", "schema": RESPONSE_SCHEMA}}
    endpoint = config["endpoint"] if config["provider"] == "json_gateway" else "https://api.anthropic.com/v1/messages"
    wire = {"provider": config["provider"], "method": "POST", "url": endpoint, "payload": payload}
    bound = len(canonical(payload)) + config["input_overhead_token_bound"]
    cost = (bound * config["prices"]["input_usd_per_million"] + generation["max_tokens"] * config["prices"]["output_usd_per_million"]) / 1e6
    return {"key": digest(canonical(wire)), "wire": wire, "input_token_bound": bound,
            "reserved_cost_usd": cost if config["provider"] != "mock" else 0.0,
            "game_id": packet["game_id"], "evidence_sha256": packet["evidence_snapshot_sha256"]}


def plan_experiment(dataset, split_path, config, subset="development", limit=5, authorize_evaluation=False):
    if subset not in {"development", "evaluation"} or subset == "evaluation" and not authorize_evaluation:
        raise ValueError("Reserved evaluation forecasts require --authorize-evaluation")
    manifest = load_split(split_path, dataset)
    order = manifest["run_order"][subset]
    if type(limit) is not int or not 1 <= limit <= len(order):
        raise ValueError("Limit must be within the requested fixed subset")
    specs = [request_spec(load_evidence(dataset, gid), config) for gid in order[:limit]]
    return {"schema_version": 1, "method": "mock_constant" if config["provider"] == "mock" else "direct_llm",
        "historical_interpretation": "exploratory_completed_games_possible_model_memorization",
        "subset": subset, "split_sha256": digest(canonical(manifest)), "config": config,
        "prompt_sha256": PROMPT_HASH, "games": [{k: s[k] for k in ("game_id", "evidence_sha256", "key", "input_token_bound", "reserved_cost_usd")} for s in specs]}, specs


def signed_record(record):
    return dict(record, record_sha256=digest(canonical(record)))


def verify_record(record):
    body = {k: v for k, v in record.items() if k != "record_sha256"}
    if record.get("record_sha256") != digest(canonical(body)):
        raise ValueError("Forecast record hash mismatch")
    if record["status"] not in {"success", "failed", "not_attempted_budget"}:
        raise ValueError("Unknown forecast status")
    if record["status"] == "success":
        probability(record["home_win_probability"])
    elif record["home_win_probability"] is not None:
        raise ValueError("Failed/missing forecast must not contain an imputed probability")
    return record


def validated_response(response, spec, config):
    usage = response.get("usage")
    if (not isinstance(usage, dict) or any(type(usage.get(k)) is not int or usage[k] < 0 for k in ("input_tokens", "output_tokens"))
            or usage["input_tokens"] > spec["input_token_bound"] or usage["output_tokens"] > config["generation"]["max_tokens"]
            or usage.get("cache_creation_input_tokens", 0) or usage.get("cache_read_input_tokens", 0)
            or not isinstance(usage.get("server_tool_use", {}), dict) or any(usage.get("server_tool_use", {}).values())):
        raise ValueError("Missing/excess usage or unexpected cache/tool billing")
    if response.get("stop_reason") != "end_turn" or not isinstance(response.get("model"), str):
        raise ValueError("Provider did not return a completed model response")
    if config["provider"] == "anthropic":
        blocks = response.get("content")
        if (response.get("role") != "assistant" or not isinstance(blocks, list) or len(blocks) != 1
                or not isinstance(blocks[0], dict) or set(blocks[0]) - {"type", "text", "citations"}
                or blocks[0].get("type") != "text" or not isinstance(blocks[0].get("text"), str) or blocks[0].get("citations")):
            raise ValueError("Unapproved response blocks, tools or citations")
        return strict_probability_json(blocks[0]["text"])
    if response.get("tool_calls"):
        raise ValueError("Gateway returned forbidden tool calls")
    return probability_object(response.get("response"))


def verify_raw(record, folder):
    raw = record.get("raw_response")
    if raw:
        path = (Path(folder) / raw["body_file"]).resolve()
        if Path(folder).resolve() not in path.parents or digest(gzip.decompress(path.read_bytes())) != raw["body_sha256"]:
            raise ValueError("Raw forecast response hash mismatch")


def cached_forecast(spec, config, cache, allow_paid=False, transport_factory=CapturedHTTP):
    """One immutable attempt per exact request, including errors and crashes."""
    folder = Path(cache) / spec["key"]
    final = folder / "forecast.json"
    if final.exists():
        record = verify_record(json.loads(final.read_text()))
        if (record["request_sha256"], record["evidence_sha256"], record["game_id"]) != (spec["key"], spec["evidence_sha256"], spec["game_id"]):
            raise ValueError("Cache identity mismatch")
        verify_raw(record, folder)
        if record.get("raw_response") and (folder / "raw" / (spec["key"] + ".request.json")).read_bytes() != canonical(spec["wire"]) + b"\n":
            raise ValueError("Cached request body differs from the evidence-only request")
        return record
    folder.mkdir(parents=True, exist_ok=True)
    attempt = folder / "attempt.json"
    new_attempt = not attempt.exists()
    if new_attempt:
        if config["provider"] != "mock" and not allow_paid:
            raise ValueError("Paid forecasting requires explicit network/inference authorization")
        # Claim *before* the network call. An interrupted/uncertain attempt is
        # never sent again, even in a new experiment directory or process.
        with attempt.open("xb") as f:
            f.write(canonical({"request_sha256": spec["key"], "claimed_at_utc": iso(time.time())}) + b"\n")
    record = {"schema_version": 1, "method": "mock_constant" if config["provider"] == "mock" else "direct_llm",
        "game_id": spec["game_id"], "evidence_sha256": spec["evidence_sha256"], "request_sha256": spec["key"],
        "provider": config["provider"], "requested_model": config["model"], "returned_model": None,
        "prompt_version": config["prompt_version"], "prompt_sha256": PROMPT_HASH, "generation_settings": config["generation"],
        "status": "failed", "home_win_probability": None, "request_started_at_utc": None, "response_retrieved_at_utc": None,
        "usage": None, "latency_seconds": None, "estimated_cost_usd": spec["reserved_cost_usd"],
        "estimated_cost_kind": "reserved_upper_bound_usage_unavailable", "reservation_upper_bound_usd": spec["reserved_cost_usd"],
        "input_token_bound": spec["input_token_bound"], "prices": config["prices"], "raw_response": None, "error": None}
    transport = transport_factory(folder / "raw", allow_network=allow_paid and new_attempt)
    response = None
    try:
        if config["provider"] == "mock":
            response = {"response": {"home_win_probability": .5}, "usage": {"input_tokens": 0, "output_tokens": 0}, "model": "offline-constant-0.5"}
            immutable_json(folder / "mock_response.json", response)
            result = .5
            record.update(usage=response["usage"], returned_model=response["model"], estimated_cost_usd=0.0,
                          estimated_cost_kind="mock_no_provider_calls", latency_seconds=0.0)
        else:
            if not new_attempt and not (folder / "raw" / (spec["key"] + ".json")).exists():
                raise ValueError("Previous request outcome is uncertain; automatic resend is forbidden")
            key = os.environ.get(config["key_env"], "")
            headers = {"x-api-key": key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"}
            if config["provider"] == "json_gateway":
                headers = {"Authorization": "Bearer " + key, "Content-Type": "application/json"}
            wire = spec["wire"]
            response = transport.request(wire["provider"], "POST", wire["url"], wire["payload"], headers,
                                         config["generation"]["max_tokens"] * 16 + 8192)
            record.update(returned_model=response.get("model"), usage=response.get("usage"))
            usage = response.get("usage")
            if isinstance(usage, dict) and all(type(usage.get(k)) is int and usage[k] >= 0 for k in ("input_tokens", "output_tokens")):
                record.update(estimated_cost_usd=(usage["input_tokens"] * config["prices"]["input_usd_per_million"]
                    + usage["output_tokens"] * config["prices"]["output_usd_per_million"]) / 1e6, estimated_cost_kind="reported_tokens_at_configured_rates")
            result = validated_response(response, spec, config)
        record.update(status="success", home_win_probability=result)
    except (ProviderError, ValueError, TypeError, KeyError, OSError) as exc:
        record["error"] = {"type": type(exc).__name__, "message": str(exc) if isinstance(exc, (ValueError, ProviderError)) else "Provider/response failure; inspect private raw capture"}
    if transport.calls:
        meta = transport.calls[-1]
        record.update(request_started_at_utc=meta["started_at_utc"], response_retrieved_at_utc=meta["retrieved_at_utc"],
                      latency_seconds=meta["latency_seconds"], raw_response={"body_file": "raw/" + meta["source_id"] + ".body.gz",
                      "body_sha256": meta["body_sha256"], "http_status": meta["http_status"], "truncated": meta["truncated"]})
    record["record_created_at_utc"] = iso(time.time())
    return immutable_json(final, signed_record(record))


def load_experiment(folder):
    """Read only sealed, internally consistent experiments (no provider calls)."""
    folder = Path(folder)
    completion = json.loads((folder / "completion.json").read_text())
    for name, sha in completion["files"].items():
        target = (folder / name).resolve()
        if folder.resolve() not in target.parents or digest(target.read_bytes()) != sha:
            raise ValueError("Completed experiment file hash mismatch")
    run = json.loads((folder / "run.json").read_text())
    required = {"run.json"} | {"forecasts/" + g["game_id"] + ".json" for g in run["games"]}
    if not required <= set(completion["files"]) or len({g["game_id"] for g in run["games"]}) != len(run["games"]):
        raise ValueError("Completion manifest omits required files or duplicates games")
    records = [verify_record(json.loads((folder / "forecasts" / (g["game_id"] + ".json")).read_text())) for g in run["games"]]
    for g, r in zip(run["games"], records):
        if (g["game_id"], g["evidence_sha256"], g["key"]) != (r["game_id"], r["evidence_sha256"], r["request_sha256"]):
            raise ValueError("Forecast identity differs from experiment manifest")
    if completion["planned_games"] != len(records):
        raise ValueError("Incomplete sealed experiment")
    for key, status in (("successful_forecasts", "success"), ("failed_responses", "failed"), ("not_attempted", "not_attempted_budget")):
        if completion[key] != sum(r["status"] == status for r in records):
            raise ValueError("Completion counters differ from saved forecasts")
    return run, records, completion


def run_experiment(plan, specs, output, cache, max_paid_calls=5, max_cost=.25, allow_paid=False, transport_factory=CapturedHTTP):
    if type(max_paid_calls) is not int or max_paid_calls < 0 or type(max_cost) not in (int, float) or not math.isfinite(max_cost) or max_cost < 0:
        raise ValueError("Explicit nonnegative finite run budgets required")
    output, cache = Path(output), Path(cache)
    if output.resolve() == cache.resolve() or output.resolve() in cache.resolve().parents or cache.resolve() in output.resolve().parents:
        raise ValueError("Experiment output and shared cache must be separate")
    config = plan["config"]
    if config["provider"] != "mock" and (not allow_paid or not os.environ.get(config["key_env"])):
        raise ValueError("Live forecasts require explicit paid opt-ins and an accessible provider credential")
    identity = {**plan, "cache_directory": str(cache.resolve()), "max_paid_calls": max_paid_calls, "max_estimated_cost_usd": max_cost}
    output.mkdir(parents=True, exist_ok=True)
    immutable_json(output / "run.json", identity)  # fixed before the first inference
    if (output / "completion.json").exists():
        return load_experiment(output)[2]
    lock = output / ".running"
    with lock.open("xb") as f:
        f.write(b"A run is active or was interrupted; no automatic concurrent paid retry.\n")
    try:
        for spec in specs:
            target = output / "forecasts" / (spec["game_id"] + ".json")
            if target.exists():
                verify_record(json.loads(target.read_text()))
                continue
            cached = cache / spec["key"] / "forecast.json"
            attempt = cache / spec["key"] / "attempt.json"
            needs_call = config["provider"] != "mock" and not cached.exists() and not attempt.exists()
            reservations = [json.loads(f.read_text()) for f in (output / "reservations").glob("*.json")]
            if needs_call:
                if len(reservations) >= max_paid_calls or sum(r["cost_usd"] for r in reservations) + spec["reserved_cost_usd"] > max_cost + 1e-12:
                    record = signed_record({"schema_version": 1, "game_id": spec["game_id"], "evidence_sha256": spec["evidence_sha256"],
                        "request_sha256": spec["key"], "status": "not_attempted_budget", "home_win_probability": None,
                        "error": {"type": "BudgetExceeded", "message": "Call/cost limit reached before provider request"}, "estimated_cost_usd": 0.0})
                    immutable_json(target, record)
                    continue
                immutable_json(output / "reservations" / (spec["key"] + ".json"), {"request_sha256": spec["key"],
                    "cost_usd": spec["reserved_cost_usd"], "reserved_at_utc": iso(time.time())})
            record = cached_forecast(spec, config, cache, allow_paid, transport_factory)
            immutable_json(target, record)
        records = [verify_record(json.loads((output / "forecasts" / (s["game_id"] + ".json")).read_text())) for s in specs]
        files = {str(p.relative_to(output)): digest(p.read_bytes()) for p in sorted(output.rglob("*")) if p.is_file() and p.name != ".running"}
        reservations = list((output / "reservations").glob("*.json"))
        complete = {"planned_games": len(specs), "successful_forecasts": sum(r["status"] == "success" for r in records),
            "failed_responses": sum(r["status"] == "failed" for r in records), "not_attempted": sum(r["status"].startswith("not_attempted") for r in records),
            "paid_call_reservations": len(reservations), "reserved_cost_usd": sum(json.loads(p.read_text())["cost_usd"] for p in reservations),
            "estimated_response_cost_usd": sum(r["estimated_cost_usd"] for r in records),
            "completed_at_utc": iso(time.time()), "files": files}
        immutable_json(output / "completion.json", complete)
        load_experiment(output)
        return complete
    finally:
        lock.unlink()


def verify_experiment(folder, dataset=DEFAULT_DATA, split=DEFAULT_SPLIT, authorize_evaluation=False, cache_override=None):
    initial = json.loads((Path(folder) / "run.json").read_text())
    if initial["subset"] == "evaluation" and not authorize_evaluation:
        raise ValueError("Reserved evaluation artifacts require explicit authorization")
    run, records, completion = load_experiment(folder)
    plan, specs = plan_experiment(dataset, split, run["config"], run["subset"], len(run["games"]), authorize_evaluation)
    if any(plan[k] != run[k] for k in plan):
        raise ValueError("Completed run differs from the split, prompt, settings or frozen packets")
    for record, spec in zip(records, specs):
        if record["status"] == "not_attempted_budget":
            continue
        cache = Path(cache_override or run["cache_directory"])
        if not (cache / spec["key"] / "forecast.json").is_file():
            raise ValueError("Offline verification requires the original immutable cache record")
        if cached_forecast(spec, run["config"], cache, allow_paid=False) != record:
            raise ValueError("Forecast cache and saved record differ")
        if record["status"] == "success" and record.get("raw_response"):
            response = json.loads(gzip.decompress((cache / spec["key"] / record["raw_response"]["body_file"]).read_bytes()))
            if validated_response(response, spec, run["config"]) != record["home_win_probability"]:
                raise ValueError("Saved probability does not reproduce from raw response")
    return completion


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dataset", type=Path, default=DEFAULT_DATA)
    p.add_argument("--split", type=Path, default=DEFAULT_SPLIT)
    p.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    p.add_argument("--subset", choices=("development", "evaluation"), default="development")
    p.add_argument("--authorize-evaluation", action="store_true")
    p.add_argument("--limit", type=int, default=5)
    p.add_argument("--output", type=Path)
    p.add_argument("--cache", type=Path, help="Shared immutable cache; default captures/forecast_cache; may relocate it for --verify")
    p.add_argument("--max-paid-calls", type=int, default=5)
    p.add_argument("--max-estimated-cost-usd", type=float, default=.25)
    p.add_argument("--mock", action="store_true")
    p.add_argument("--live", action="store_true")
    p.add_argument("--allow-network", action="store_true")
    p.add_argument("--allow-inference", action="store_true")
    p.add_argument("--plan", action="store_true")
    p.add_argument("--verify", type=Path, help="Offline replay of a sealed experiment and its private cache")
    args = p.parse_args()
    if args.verify:
        if args.live or args.mock or args.allow_network or args.allow_inference:
            p.error("Verification cannot enable model/network calls")
        completion = verify_experiment(args.verify, args.dataset, args.split, args.authorize_evaluation, args.cache)
        print(json.dumps({"verified": True, "games": completion["planned_games"], "network_calls": 0}))
        return
    if args.mock and (args.live or args.allow_network or args.allow_inference):
        p.error("Mock mode cannot enable network or inference")
    config = json.loads(args.config.read_text())
    if args.mock:
        config = dict(config, provider="mock", model="offline-constant-0.5")
    plan, specs = plan_experiment(args.dataset, args.split, config, args.subset, args.limit, args.authorize_evaluation)
    total = sum(s["reserved_cost_usd"] for s in specs)
    if args.plan or not (args.mock or args.live):
        print(json.dumps({"subset": args.subset, "games": plan["games"], "estimated_uncached_upper_bound_usd": total,
            "max_paid_calls": args.max_paid_calls, "max_estimated_cost_usd": args.max_estimated_cost_usd,
            "credential_present": bool(os.environ.get(config["key_env"])), "provider": config["provider"], "network_calls": 0}, indent=2))
        return
    if not args.output or args.live and not (args.allow_network and args.allow_inference):
        p.error("Specify --output and all paid opt-ins for live forecasting")
    cache = args.cache or ROOT / "captures/forecast_cache"
    for target in (args.output, cache):
        if (target.resolve() == args.dataset.resolve() or args.dataset.resolve() in target.resolve().parents
                or target.resolve() in args.dataset.resolve().parents):
            p.error("Forecast outputs/cache cannot modify the historical dataset")
    result = run_experiment(plan, specs, args.output, cache, args.max_paid_calls, args.max_estimated_cost_usd,
                            args.live and args.allow_network and args.allow_inference)
    print(json.dumps({k: v for k, v in result.items() if k != "files"}, indent=2))


if __name__ == "__main__":
    main()
