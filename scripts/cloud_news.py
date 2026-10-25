"""Two-phase news: acquire eligible bytes, then extract without source access."""
import json
from dataclasses import asdict

from cloud_state import durable_json
from evidence_documents import DocumentStore, canonical, digest
from investigate_kalshi import iso, timestamp
from prospective_research import (Budget, CATEGORIES, allowed_page, news_section, planned_queries,
    validate_findings, validate_page)
from research_providers import EXTRACTION_INSTRUCTIONS


def acquire(game, cutoff, provider, documents, settings, clock):
    """No model call; search snippets remain audit-only. Clock is actual UTC."""
    budget = Budget(**{k: v for k, v in settings.items() if k != "max_extraction_calls"})
    queries = planned_queries(game, budget, dated_articles=True)
    results, decisions, sources, seen = [], [], [], set()
    pages = 0; tokens = 0
    for index, query in enumerate(queries):
        if clock() > cutoff: raise ValueError("News retrieval deadline passed")
        tokens += provider.search_token_bound
        if tokens > budget.max_tokens: raise ValueError("Search response token budget exceeded")
        rows = provider.search(query, cutoff)
        results.append({"query": query, "results": rows})
        for row in rows:
            value = row["url"]
            if value in seen or not allowed_page(value, dated_articles=True):
                decisions.append({"url": value, "reason": "duplicate_or_disallowed_source"}); continue
            # Preserve room for both prespecified query themes.
            if pages >= budget.max_pages or (index == 0 and pages >= (budget.max_pages+1)//2):
                decisions.append({"url": value, "reason": "page_budget_exhausted_for_query"}); continue
            seen.add(value)
            meta, body = documents.get(value); pages += 1
            result = validate_page(value, body, meta, cutoff, enforce_retrieval=True, dated_articles=True)
            if clock() < timestamp(meta["retrieved_at_utc"]):
                raise ValueError("Source retrieval clock is in the future")
            sources.append(result)
    safe = [{"source_id": s["source_id"], "published_at_utc": s["published_at_utc"], "snippets": s["snippets"]}
        for s in sources if s.get("usable")]
    context = {"home_team": game["home_name"], "away_team": game["away_name"],
        "cutoff_utc": iso(cutoff), "allowed_categories": CATEGORIES, "sources": safe}
    if len(canonical(context)) + 2048 + budget.max_output_tokens + tokens > budget.max_tokens:
        raise ValueError("Combined news token reservation exceeds budget")
    return {"context": context, "context_sha256": digest(canonical(context)), "sources_and_validation": sources,
        "raw_search_results": results, "decisions": decisions, "budgets": asdict(budget),
        "captured_at_utc": iso(clock()), "extraction_prompt": EXTRACTION_INSTRUCTIONS,
        "extraction_prompt_sha256": digest(EXTRACTION_INSTRUCTIONS.encode())}


def extract(game, acquisition, provider, cutoff, freeze_deadline, settings, folder, clock):
    """No fetch/search argument exists here. Context is hashed pre-cutoff data."""
    if clock() > freeze_deadline: raise ValueError("Extraction/freeze deadline passed")
    if acquisition["context_sha256"] != digest(canonical(acquisition["context"])): raise ValueError("Captured extraction context changed")
    safe_ids = {s["source_id"] for s in acquisition["sources_and_validation"] if s.get("usable")}
    if {s["source_id"] for s in acquisition["context"]["sources"]} != safe_ids: raise ValueError("Unvalidated extraction source")
    started = clock()
    candidates = provider.extract(acquisition["context"], settings["max_output_tokens"]) if safe_ids else []
    finished = clock()
    findings, decisions = validate_findings(candidates, acquisition["sources_and_validation"], game, cutoff, format_recovery=True)
    result = {"news": news_section(findings, acquisition["sources_and_validation"], True),
        "audit": {"acquisition": acquisition, "agent_candidates": candidates, "finding_decisions": decisions,
            "started_at_utc": iso(started), "finished_at_utc": iso(finished), "input_context_sha256": acquisition["context_sha256"],
            "reported_provider_usage": provider.usage, "provider_requests": provider.http.calls}}
    durable_json(folder / "extraction.json", result)
    if finished > freeze_deadline: raise ValueError("Extraction completed after freeze deadline")
    return result


def replay_sources(game,acquisition,extraction,folder,cutoff):
    documents=DocumentStore(folder/acquisition['document_directory'],True,lambda u:allowed_page(u,dated_articles=True))
    sources=[]
    for old in acquisition['sources_and_validation']:
        meta,body=documents.get(old['url'])
        sources.append(validate_page(old['url'],body,meta,cutoff,enforce_retrieval=True,dated_articles=True))
    if sources!=acquisition['sources_and_validation']:raise ValueError('Article parsing/provenance differs on replay')
    findings,decisions=validate_findings(extraction['audit']['agent_candidates'],sources,game,cutoff,format_recovery=True)
    if news_section(findings,sources,True)!=extraction['news'] or decisions!=extraction['audit']['finding_decisions']:
        raise ValueError('Grounded extraction validation differs on replay')
