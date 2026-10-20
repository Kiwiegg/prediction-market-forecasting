"""Audit-only counters and query attribution; never changes evidence eligibility."""

from collections import Counter
from urllib.parse import parse_qs, urlsplit

from investigate_kalshi import timestamp


def summarize_research(audit, findings, prices):
    from prospective_research import allowed_page
    sources = {s["url"]: s for s in audit.get("sources_and_validation", [])}
    searches = [{**s, "results": s["results"] if isinstance(s.get("results"), list) else []}
                for s in audit.get("raw_search_results", [])]
    finding_decisions = audit.get("finding_decisions", [])
    requests = audit.get("provider_requests", [])
    usage = audit.get("actual_provider_usage", [])
    by_query = []
    for search in searches:
        urls = [r["url"] for r in search["results"] if isinstance(r, dict) and isinstance(r.get("url"), str)]
        referenced = {r["source_ref"] for f in findings for r in f["source_references"] if r["url"] in urls}
        by_query.append({"query": search["query"], "results_discovered": len(urls), "urls": urls,
            "pages_retrieved": sum(u in sources for u in set(urls)),
            "pages_rejected": sum(u in sources and not sources[u]["usable"] for u in set(urls)),
            "validated_findings": sum(any(r["url"] in urls for r in f["source_references"]) for f in findings),
            "supporting_references": sorted(referenced),
            "url_status": [{"url": u, "status": ("retrieved_usable" if sources[u]["usable"] else sources[u]["reason"])
                if u in sources else "disallowed_source_url" if not allowed_page(u) else "not_retrieved_budget_or_abort"} for u in dict.fromkeys(urls)],
            "rejection_reasons": dict(Counter(sources[u]["reason"] for u in set(urls)
                if u in sources and not sources[u]["usable"]))})
    reasons = Counter(d["reason"] for d in audit.get("decisions", []) if d.get("reason"))
    reasons.update(s["reason"] for s in sources.values() if not s["usable"])
    reasons.update(d["reason"] for d in finding_decisions if d.get("reason"))
    latency = {"search": [], "inference": []}
    for request in requests:
        kind = "search" if request["method"] == "GET" else "inference"
        seconds = request.get("latency_seconds")
        if seconds is None and request.get("started_at_utc"):
            seconds = round(timestamp(request["retrieved_at_utc"]) - timestamp(request["started_at_utc"]), 6)
        latency[kind].append({"source_id": request["source_id"], "seconds": seconds,
                             "http_status": request["http_status"]})
        if kind == "search":
            query = parse_qs(urlsplit(request["url"]).query).get("q", [None])[0]
            if query is None:
                continue
            match = next((q for q in by_query if q["query"] == query), None)
            if match is None:
                by_query.append({"query": query, "results_discovered": 0, "urls": [], "provider_failure": True})
            else:
                match["provider_source_id"] = request["source_id"]
    input_tokens = output_tokens = 0
    valid_usage = len(usage) == len(latency["inference"])
    for item in usage:
        u = item.get("usage")
        if not isinstance(u, dict) or any(type(u.get(k)) is not int or u[k] < 0 for k in ("input_tokens", "output_tokens")):
            valid_usage = False
            continue
        input_tokens += u["input_tokens"]
        output_tokens += u["output_tokens"]
        if (u.get("cache_creation_input_tokens", 0) or u.get("cache_read_input_tokens", 0)
                or not isinstance(u.get("server_tool_use", {}), dict) or any(u.get("server_tool_use", {}).values())):
            valid_usage = False
    return {"counters": {"queries_attempted": audit.get("usage_upper_bounds", {}).get("queries", 0),
        "queries_returned_results": sum(isinstance(s.get("results"), list) for s in audit.get("raw_search_results", [])), "results_discovered": sum(len(s["results"]) for s in searches),
        "unique_urls_discovered": len({r["url"] for s in searches for r in s["results"] if isinstance(r, dict) and isinstance(r.get("url"), str)}),
        "pages_retrieved": len(sources), "pages_rejected": sum(not s["usable"] for s in sources.values()),
        "validated_findings": len(findings), "duplicate_claims": sum(d.get("reason") == "duplicate_underlying_fact" for d in finding_decisions)},
        "searches": by_query, "rejection_reasons": dict(sorted(reasons.items())), "provider_latency_seconds": latency,
        "reported_token_usage": {"input_tokens": input_tokens if valid_usage else None,
                                 "output_tokens": output_tokens if valid_usage else None, "raw": usage},
        "estimated_cost_usd": {"reserved_upper_bound": audit.get("usage_upper_bounds", {}).get("estimated_cost_usd", 0),
            "search_requests": len(latency["search"]) * prices["query_usd"],
            "retrieved_pages": len(sources) * prices["page_usd"],
            "reported_inference_usage": (input_tokens * prices["input_usd_per_million"] + output_tokens * prices["output_usd_per_million"]) / 1e6 if valid_usage else None}}
