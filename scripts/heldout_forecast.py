#!/usr/bin/env python3
"""One-time, globally bounded held-out execution of unchanged forecast methods.

No labels, market files, evaluation exports, searches or outcome joins are read
here. Only existing consumer-neutral frozen snapshots enter request builders.
"""
import argparse
import gzip
import json
import math
import os
import subprocess
import time
from collections import Counter
from pathlib import Path

import direct_forecast as direct
import leap_forecast as v1
import leap_v2_forecast as v2
import leap_v2_evidence as evidence_v2
from evidence_documents import canonical, digest
from forecast_split import ROOT, DEFAULT_DATA, DEFAULT_SPLIT, immutable_json, load_split
from investigate_kalshi import iso, timestamp
from research_providers import CapturedHTTP
from run_v2_development import response_category

BASE = ROOT / "captures/heldout_150"
PLAN_PATH = ROOT / "experiments/heldout_150_plan.json"
RULES_PATH = ROOT / "experiments/heldout_150_rules.json"
CACHES = {"direct": ROOT / "captures/forecast_cache", "v1": v1.DEFAULT_CACHE, "v2": v2.DEFAULT_CACHE}
MODULES = {"direct": direct, "v1": v1, "v2": v2}
ORDER = ("direct", "v2", "v1")


def rules():
    return json.loads(RULES_PATH.read_text())


def make_plan(authorize_evaluation=False, mock=False):
    if not authorize_evaluation:
        raise ValueError("Held-out access requires --authorize-evaluation")
    split = load_split(); assets = evidence_v2.frozen_assets()
    configs = {"direct": json.loads(direct.DEFAULT_CONFIG.read_text()),
        "v1": json.loads(v1.DEFAULT_CONFIG.read_text()), "v2": evidence_v2.config(mock)}
    if mock:
        for cfg in configs.values(): cfg["provider"] = "mock"
    plans = {}; specs = {}
    for name, module in (("direct", direct), ("v1", v1)):
        plans[name], specs[name] = module.plan_experiment(DEFAULT_DATA, DEFAULT_SPLIT, configs[name],
            subset="evaluation", limit=150, authorize_evaluation=True)
    games = []; specs["v2"] = []
    for gid in split["run_order"]["evaluation"]:
        packet = direct.load_evidence(DEFAULT_DATA, gid)
        groups = [evidence_v2.group_spec(g, configs["v2"]) for g in evidence_v2.build_groups(packet)]
        specs["v2"].extend(groups)
        games.append({"game_id": gid, "evidence_sha256": packet["evidence_snapshot_sha256"],
            "groups": [evidence_v2.brief(g) for g in groups]})
    # Scope permission only: original v2 projections, prompts, schemas, settings,
    # request identities, parsers and aggregation are used without modification.
    plans["v2"] = {"schema_version": 1, "method": "leap_nba_v2_mock" if mock else "leap_nba_v2",
        "subset": "evaluation", "evaluation_authorized": True, "scope": "heldout-150",
        "split_sha256": digest(canonical(split)), "config": configs["v2"], "frozen_assets": assets,
        "frozen_registry_sha256": evidence_v2.REGISTRY_SHA, "games": games}
    frozen = set(assets) | set(v1.FROZEN) | {"scripts/leap_forecast.py", "scripts/leap_v2_forecast.py",
        "scripts/leap_v2_evidence.py", "examples/direct_forecast_config.json",
        "prompts/direct_home_win_v1.txt", "experiments/direct_baseline_protocol_v1.md",
        "experiments/heldout_150_protocol.md", "experiments/heldout_150_rules.json",
        "scripts/heldout_forecast.py", "scripts/analyze_heldout.py", "scripts/run_v2_development.py",
        "scripts/analyze_v2_development.py", "scripts/compare_leap_v2.py",
        "reports/leap_nba_v2_development_50/manifest.json", "reports/leap_nba_v2_development_50/summary.json"}
    phase = json.loads((ROOT / "experiments/leap_nba_v2_phase1/frozen_assets.json").read_text())
    frozen.update(phase)
    result = {"schema_version": 1, "subset": "evaluation", "evaluation_authorized": True,
        "game_ids": split["run_order"]["evaluation"], "method_order_per_game": list(ORDER),
        "rules_sha256": digest(RULES_PATH.read_bytes()), "plans": plans,
        "assets": {name: digest((ROOT / name).read_bytes()) for name in sorted(frozen)}}
    if len(result["game_ids"]) != 150 or any([g["game_id"] for g in p["games"]] != result["game_ids"] for p in plans.values()):
        raise ValueError("Exact fixed evaluation subset required")
    parents = [{g["game_id"]: g["evidence_sha256"] for g in plans[n]["games"]} for n in ORDER]
    if not all(p == parents[0] for p in parents): raise ValueError("Consumers have different snapshots")
    return result, specs


def frozen_plan(authorize_evaluation=False, mock=False):
    plan, specs = make_plan(authorize_evaluation, mock)
    if not mock and json.loads(PLAN_PATH.read_text()) != plan:
        raise ValueError("Precommitted held-out plan/assets/evidence changed")
    return plan, specs


def sequence(plan, specs):
    lookup = {name: {gid: [s for s in specs[name] if s["game_id"] == gid] for gid in plan["game_ids"]} for name in ORDER}
    return [(name, s) for gid in plan["game_ids"] for name in ORDER for s in lookup[name][gid]]


def final_path(name, cache, spec):
    return Path(cache) / spec["key"] / ("forecast.json" if name == "direct" else "group.json")


def load_cached(name, spec, cfg, cache):
    if name == "direct": return direct.cached_forecast(spec, cfg, cache)
    return MODULES[name].load_cached(spec, cache)


def cache_state(plan, specs, caches):
    old = []; fresh = []
    for name, s in sequence(plan, specs):
        if final_path(name, caches[name], s).exists():
            load_cached(name, s, plan["plans"][name]["config"], caches[name]); old.append(name + ":" + s["key"])
        elif (Path(caches[name]) / s["key"] / "attempt.json").exists():
            raise ValueError("Uncertain prior attempt: do not resend or change cache directories")
        elif s.get("usable", True): fresh.append((name, s))
    return old, fresh


def cost_plan(plan, specs, caches):
    old, fresh = cache_state(plan, specs, caches)
    return {"planned_new_requests": len(fresh), "additional_reservation_usd": math.fsum(s["reserved_cost_usd"] for _, s in fresh),
        "cached_request_ids": old, "new_request_ids": [n + ":" + s["key"] for n, s in fresh],
        "by_method": {name: {"new_requests": sum(n == name for n, _ in fresh),
            "reservation_usd": math.fsum(s["reserved_cost_usd"] for n, s in fresh if n == name),
            "cached": sum(k.startswith(name + ":") for k in old),
            "source_missing_groups": sum(not s.get("usable", True) for s in specs[name])} for name in ORDER},
        "max_new_requests": 1200, "max_reserved_cost_usd": 40, "network_calls": 0}


def blank(name, spec, cfg, reason, uncertain=False, marker=None):
    status = "failed" if uncertain else "not_attempted_budget"
    if name == "direct":
        r = {"schema_version": 1, "method": "direct_llm", "game_id": spec["game_id"],
            "evidence_sha256": spec["evidence_sha256"], "request_sha256": spec["key"],
            "status": status, "home_win_probability": None, "estimated_cost_usd": 0,
            "raw_response": None, "usage": None, "latency_seconds": None,
            "request_started_at_utc": None, "response_retrieved_at_utc": None}
    else: r = MODULES[name].base_record(spec, cfg, status)
    r["error"] = {"type": "InterruptedUnknown" if uncertain else "ExecutionStopped",
        "message": "No automatic retry; inspect sealed execution reason", "stop_category": reason}
    if uncertain:
        r.update(uncertain_attempt=True, attempt_marker_sha256=digest(marker.read_bytes()),
            estimated_cost_usd=spec["reserved_cost_usd"], estimated_cost_kind="reserved_upper_bound_usage_unavailable")
    return direct.signed_record(r)


def record_category(name, r, cache):
    if not r.get("raw_response"): return "uncertain_attempt" if r.get("uncertain_attempt") else r["status"]
    return response_category(dict(r, key=r["request_sha256"]), cache)


def game_record(name, planned, records):
    if name == "direct":
        if len(records) != 1: raise ValueError("Exactly one direct observation required")
        return records[0]
    if name == "v1": return v1.game_record(planned["game_id"], planned["evidence_sha256"], records)
    return v2.game_record(planned, records)


def can_reserve(calls, reserved_or_known_cost, next_cost):
    if (type(calls) is not int or calls < 0 or any(type(x) not in (int, float) or not math.isfinite(x) or x < 0
            for x in (reserved_or_known_cost, next_cost))):
        raise ValueError("Finite nonnegative budget inputs required")
    return calls < 1200 and reserved_or_known_cost + next_cost <= 40 + 1e-12


def public_counts(plan, games, execution):
    stats = {}
    for name in ORDER:
        observations = [r for g in games[name] for r in ([g] if name == "direct" else g["groups"])]
        attempted = [r for r in observations if r.get("raw_response") or r.get("uncertain_attempt")]
        stats[name] = {"planned_games": len(games[name]), "successful_forecasts": sum(g["status"] == "success" for g in games[name]),
            "forecast_status_counts": dict(Counter(g["status"] for g in games[name])),
            "observation_status_counts": dict(Counter(r["status"] for r in observations)),
            "attempted_requests": len(attempted), "http_status_counts": dict(Counter(str(r["raw_response"]["http_status"]) if r.get("raw_response") else "uncertain" for r in attempted)),
            "usage": {k: sum((r.get("usage") or {}).get(k, 0) for r in attempted) for k in ("input_tokens", "output_tokens")},
            "reported_token_cost_usd": math.fsum(r["estimated_cost_usd"] for r in attempted if r.get("usage") is not None),
            "unknown_usage_reserve_usd": math.fsum(r["estimated_cost_usd"] for r in attempted if r.get("usage") is None),
            "summed_http_latency_seconds": math.fsum(r.get("latency_seconds") or 0 for r in attempted),
            "missing_latency_count": sum(r.get("latency_seconds") is None for r in attempted),
            "first_request_at_utc": min((r["request_started_at_utc"] for r in attempted if r.get("request_started_at_utc")), default=None),
            "last_response_at_utc": max((r["response_retrieved_at_utc"] for r in attempted if r.get("response_retrieved_at_utc")), default=None)}
    return {"resources": stats, "stop_reason": execution["stop_reason"]}


def seal(output, plan, specs, caches, reason):
    games = {n: [] for n in ORDER}; categories = {}
    for name in ORDER:
        cfg = plan["plans"][name]["config"]
        for planned in plan["plans"][name]["games"]:
            target = output / name / "forecasts" / (planned["game_id"] + ".json")
            if target.exists(): g = json.loads(target.read_text())
            else:
                records = []
                for s in (s for s in specs[name] if s["game_id"] == planned["game_id"]):
                    marker = Path(caches[name]) / s["key"] / "attempt.json"
                    if final_path(name, caches[name], s).exists(): r = load_cached(name, s, cfg, caches[name])
                    elif not s.get("usable", True): r = MODULES[name].cached_group(s, cfg, caches[name])
                    else: r = blank(name, s, cfg, reason["category"], marker.exists(), marker)
                    records.append(r)
                g = game_record(name, planned, records); immutable_json(target, g)
            games[name].append(g)
            for r in ([g] if name == "direct" else g["groups"]):
                categories[name + ":" + r["request_sha256"]] = record_category(name, r, caches[name])
    ledger = [json.loads(p.read_text()) for p in sorted((output / "reservations").glob("*.json"))]
    execution = {"stop_reason": reason, "response_categories": categories}
    immutable_json(output / "execution.json", execution)
    complete = {**public_counts(plan, games, execution), "paid_call_reservations": len(ledger),
        "reserved_cost_usd": math.fsum(r["cost_usd"] for r in ledger), "completed_at_utc": iso(time.time()),
        "files": {str(p.relative_to(output)): digest(p.read_bytes()) for p in sorted(output.rglob("*")) if p.is_file() and p.name != ".running"}}
    immutable_json(output / "completion.json", complete)
    return complete


def execute(plan, specs, output, caches, preflight, allow_paid=False, transport_factory=CapturedHTTP,
        authorization_path=None, seal_interrupted=False):
    output = Path(output); mock = plan["plans"]["direct"]["config"]["provider"] == "mock"
    expected, expected_specs = frozen_plan(True, mock)
    if plan != expected or specs != expected_specs: raise ValueError("Frozen plans/specifications differ")
    if not mock and allow_paid and {n: Path(p).resolve() for n, p in caches.items()} != {n: p.resolve() for n, p in CACHES.items()}:
        # Unit fixtures use an injected transport, never production live calls.
        if transport_factory is CapturedHTTP: raise ValueError("Original shared caches are required")
    for cache in caches.values(): v1.protect_paths(output, cache, DEFAULT_DATA)
    identity = {"plan": plan, "cache_directories": {n: str(Path(p).resolve()) for n, p in caches.items()},
        "preflight": preflight, "max_new_requests": 1200, "max_reserved_cost_usd": 40}
    if (output / "run.json").exists() and json.loads((output / "run.json").read_text()) != identity:
        raise ValueError("Immutable run identity differs")
    if (output / "completion.json").exists(): return verify(output, True)[3]
    if seal_interrupted:
        if not (output / "run.json").exists(): raise ValueError("No interrupted manifest")
        return seal(output, plan, specs, caches, {"category": "interrupted", "message": "Explicit offline sealing; never resend unknown claims"})
    if cost_plan(plan, specs, caches) != preflight["cost_plan"]: raise ValueError("Original cache/preflight changed")
    if not mock and (not allow_paid or not os.environ.get("ANTHROPIC_API_KEY")): raise ValueError("Credential and explicit network/inference opt-ins required")
    if not mock:
        # Single authorization registry cannot be bypassed using another output.
        immutable_json(authorization_path or BASE / "authorization.json", {"output_directory": str(output.resolve()),
            "plan_sha256": digest(PLAN_PATH.read_bytes()), "budget": {"calls": 1200, "reserved_usd": 40}})
    immutable_json(output / "run.json", identity)
    with (output / ".running").open("xb") as f: f.write(b"Active/interrupted held-out run; do not resend claims.\n")
    reason = {"category": "completed", "message": "All frozen requests processed"}; stopped = False; spent = 0.; calls = 0; records = {}
    fresh_ids = set(preflight["cost_plan"]["new_request_ids"])
    try:
        for name, s in sequence(plan, specs):
            cfg = plan["plans"][name]["config"]; cache = caches[name]; token = name + ":" + s["key"]
            if final_path(name, cache, s).exists(): r = load_cached(name, s, cfg, cache)
            elif not s.get("usable", True): r = MODULES[name].cached_group(s, cfg, cache)
            elif stopped: r = blank(name, s, cfg, reason["category"])
            elif not mock and not can_reserve(calls, spent, s["reserved_cost_usd"]):
                stopped = True; reason = {"category": "budget", "request_id": token}; r = blank(name, s, cfg, "budget")
            else:
                if not mock:
                    immutable_json(output / "reservations" / (name + "_" + s["key"] + ".json"),
                        {"request_id": token, "request_sha256": s["key"], "method": name,
                         "cost_usd": s["reserved_cost_usd"], "reserved_at_utc": iso(time.time())})
                    calls += 1; spent += s["reserved_cost_usd"]
                if name == "direct": r = direct.cached_forecast(s, cfg, cache, allow_paid, transport_factory)
                else: r = MODULES[name].cached_group(s, cfg, cache, allow_paid, transport_factory)
            records[token] = r
            if not mock:
                # Provider usage normally lies well below the conservative byte
                # bound. Still stop reserving if reported costs exceed it.
                spent = max(spent, math.fsum(x["estimated_cost_usd"] for k, x in records.items() if k in fresh_ids))
            category = record_category(name, r, cache)
            if category == "access_denial":
                stopped = True; reason = {"category": "access_denial", "request_id": token,
                    "http_status": r["raw_response"]["http_status"]}
            # Seal completed individual game records immediately, before the next request.
            pending = [x for x in specs[name] if x["game_id"] == s["game_id"]]
            if all(name + ":" + x["key"] in records for x in pending):
                planned = next(g for g in plan["plans"][name]["games"] if g["game_id"] == s["game_id"])
                immutable_json(output / name / "forecasts" / (s["game_id"] + ".json"),
                    game_record(name, planned, [records[name + ":" + x["key"]] for x in pending]))
    except KeyboardInterrupt: reason = {"category": "interrupted", "message": "Keyboard interruption; no automatic retry"}
    except Exception as exc: reason = {"category": "execution_error", "error_type": type(exc).__name__, "message": "Stopped without retry; inspect private captures"}
    finally:
        result = seal(output, plan, specs, caches, reason)
        (output / ".running").unlink()
    return result


def validate_games(plan, specs, games):
    for name in ORDER:
        planned = plan["plans"][name]["games"]
        if [g["game_id"] for g in games[name]] != plan["game_ids"]: raise ValueError("Held-out IDs/order changed")
        by_gid = {g["game_id"]: g for g in planned}
        for game in games[name]:
            observations = [game] if name == "direct" else game["groups"]
            requested = [s for s in specs[name] if s["game_id"] == game["game_id"]]
            if len(observations) != len(requested): raise ValueError("Missing/duplicate group slot")
            for r, s in zip(observations, requested):
                MODULES[name].verify_record(r)
                if any(r[k] != s[k] for k in ("game_id", "evidence_sha256")) or r["request_sha256"] != s["key"]:
                    raise ValueError("Request/parent evidence mismatch")
                if name != "direct" and any(r[k] != x for k, x in MODULES[name].brief(s).items()): raise ValueError("Group projection mismatch")
                if r["status"].startswith("not_attempted") and r["estimated_cost_usd"] != 0: raise ValueError("Unattempted request has a charge")
            if game_record(name, by_gid[game["game_id"]], observations) != game: raise ValueError("Frozen aggregation differs")


def verify(output, authorize_evaluation=False):
    if not authorize_evaluation: raise ValueError("Verification requires --authorize-evaluation")
    output = Path(output); run = json.loads((output / "run.json").read_text()); complete = json.loads((output / "completion.json").read_text())
    plan = run["plan"]; mock = plan["plans"]["direct"]["config"]["provider"] == "mock"
    expected, specs = frozen_plan(True, mock)
    if expected != plan: raise ValueError("Completed manifest differs from frozen held-out plan")
    required = {"run.json", "execution.json"} | {n + "/forecasts/" + gid + ".json" for n in ORDER for gid in plan["game_ids"]}
    if not required <= set(complete["files"]): raise ValueError("Incomplete seal")
    for name, sha in complete["files"].items():
        p = (output / name).resolve()
        if output.resolve() not in p.parents or digest(p.read_bytes()) != sha: raise ValueError("Immutable run file changed")
    games = {n: [json.loads((output / n / "forecasts" / (gid + ".json")).read_text()) for gid in plan["game_ids"]] for n in ORDER}
    validate_games(plan, specs, games)
    for name in ORDER:
        cfg = plan["plans"][name]["config"]; cache = Path(run["cache_directories"][name])
        for game in games[name]:
            for r in ([game] if name == "direct" else game["groups"]):
                s = next(s for s in specs[name] if s["key"] == r["request_sha256"])
                if r.get("uncertain_attempt"):
                    if digest((cache / s["key"] / "attempt.json").read_bytes()) != r["attempt_marker_sha256"] or final_path(name, cache, s).exists(): raise ValueError("Uncertain attempt changed")
                elif not r["status"].startswith("not_attempted"):
                    if load_cached(name, s, cfg, cache) != r: raise ValueError("Original cache differs")
                    if r.get("raw_response") and r["raw_response"]["http_status"] == 200 and not r["raw_response"]["truncated"]:
                        try:
                            response = json.loads(gzip.decompress((cache / s["key"] / r["raw_response"]["body_file"]).read_bytes()))
                            parsed = direct.validated_response(response, s, cfg) if name == "direct" else v1.validate_response(response, s, cfg) if name == "v1" else v2.parse_response(response, s, cfg)
                        except (ValueError, TypeError, KeyError, UnicodeError):
                            if r["status"] != "failed": raise ValueError("Response should have failed")
                        else:
                            if name == "direct" and parsed != r["home_win_probability"] or name != "direct" and any(r[k] != x for k, x in parsed.items()): raise ValueError("Raw inference does not reproduce")
    execution = json.loads((output / "execution.json").read_text())
    categories = {n + ":" + r["request_sha256"]: record_category(n, r, Path(run["cache_directories"][n]))
        for n in ORDER for g in games[n] for r in ([g] if n == "direct" else g["groups"])}
    if categories != execution["response_categories"] or any(complete[k] != x for k, x in public_counts(plan, games, execution).items()): raise ValueError("Execution classifications/counters differ")
    reservations = [json.loads(p.read_text()) for p in (output / "reservations").glob("*.json")]
    byid = {n + ":" + s["key"]: s for n, s in sequence(plan, specs)}
    ledger = {r["request_id"]: r for r in reservations}; fresh = set(run["preflight"]["cost_plan"]["new_request_ids"])
    if (len(ledger) != len(reservations) or len(ledger) != complete["paid_call_reservations"] or len(ledger) > 1200
            or math.fsum(r["cost_usd"] for r in reservations) != complete["reserved_cost_usd"]
            or complete["reserved_cost_usd"] > 40 + 1e-12): raise ValueError("Private reservation ledger differs/exceeds authorization")
    for key, r in ledger.items():
        if key not in fresh or key not in byid or r["request_sha256"] != byid[key]["key"] or r["cost_usd"] != byid[key]["reserved_cost_usd"]:
            raise ValueError("Reservation identity/cost differs")
    claimed = []
    for key in fresh:
        n, sha = key.split(":"); marker = Path(run["cache_directories"][n]) / sha / "attempt.json"
        if marker.exists() and not mock:
            claim = json.loads(marker.read_text()); claimed.append(key)
            if key not in ledger or claim["request_sha256"] != sha or timestamp(ledger[key]["reserved_at_utc"]) > timestamp(claim["claimed_at_utc"]): raise ValueError("Private claim without pre-call reservation")
    denials = [k for k, v in categories.items() if v == "access_denial"]; ordering = list(byid)
    if denials and (execution["stop_reason"]["category"] != "access_denial" or any(ordering.index(k) > min(ordering.index(d) for d in denials) for k in claimed)):
        raise ValueError("Inference continued after access denial")
    return run, specs, games, complete, execution


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for flag in ("authorize-evaluation", "plan", "freeze-plan", "save-preflight", "mock", "live", "allow-network", "allow-inference", "seal-interrupted"):
        p.add_argument("--" + flag, action="store_true")
    p.add_argument("--verify", type=Path); a = p.parse_args()
    if not a.authorize_evaluation: p.error("Explicit --authorize-evaluation is required for every held-out operation")
    if (a.plan or a.freeze_plan or a.save_preflight or a.verify or a.seal_interrupted) and any((a.live, a.allow_network, a.allow_inference, a.mock)): p.error("Planning/verification/sealing cannot enable inference")
    if a.mock and any((a.live, a.allow_network, a.allow_inference)): p.error("Mock cannot enable network")
    if a.verify: result = verify(a.verify, True)[3]
    elif a.freeze_plan:
        plan, specs = make_plan(True); immutable_json(PLAN_PATH, plan)
        result = cost_plan(plan, specs, CACHES)
    else:
        plan, specs = frozen_plan(True, a.mock)
        caches = {n: BASE / ("mock_cache_" + n) for n in ORDER} if a.mock else CACHES
        output = BASE / ("mock_" + digest(canonical(plan))[:12] if a.mock else "run")
        if a.live or a.mock or a.seal_interrupted:
            if a.live and not (a.allow_network and a.allow_inference): p.error("All live opt-ins required")
            preflight = (json.loads((output / "run.json").read_text())["preflight"] if (output / "run.json").exists()
                else {"cost_plan": cost_plan(plan, specs, caches)}) if a.mock else json.loads((BASE / "preflight.json").read_text())
            if a.live and not (output / "completion.json").exists():
                if not subprocess.check_output(["git", "show", preflight["git_commit"] + ":experiments/heldout_150_plan.json"], cwd=ROOT) == PLAN_PATH.read_bytes(): raise ValueError("Plan was not committed before inference")
            result = execute(plan, specs, output, caches, preflight, a.live, seal_interrupted=a.seal_interrupted)
        else:
            result = {"cost_plan": cost_plan(plan, specs, caches), "plan_sha256": digest(PLAN_PATH.read_bytes()),
                "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                "credential_present": bool(os.environ.get("ANTHROPIC_API_KEY"))}
            if a.save_preflight: immutable_json(BASE / "preflight.json", result)
    safe = {k: v for k, v in result.items() if k != "files"}
    cp = safe.get("cost_plan", safe)
    cp.pop("cached_request_ids", None); cp.pop("new_request_ids", None)
    print(json.dumps(safe, indent=2))


if __name__ == "__main__": main()
