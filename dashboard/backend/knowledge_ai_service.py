"""Optional one-shot local-AI review for the knowledge radar."""

import json
import re
from pathlib import Path
from typing import Any, Callable

from knowledge_radar_service import analyze_knowledge_gaps
from knowledge_research_service import load_research_run
from vault_retrieval_service import public_retrieval, retrieve_vault_context


ALLOWED_RECOMMENDATIONS = {"erweitern", "aktualisieren", "schliessen", "weiter_recherchieren"}


def _json_object(text: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE)
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end <= start:
        raise RuntimeError("Das lokale Modell lieferte keine auswertbare JSON-Bewertung.")
    try:
        value = json.loads(cleaned[start:end + 1])
    except json.JSONDecodeError as exc:
        raise RuntimeError("Das lokale Modell lieferte ungültiges JSON.") from exc
    if not isinstance(value, dict):
        raise RuntimeError("Die KI-Bewertung besitzt ein ungültiges Format.")
    return value


def _validated(value: dict, model: str, phase: str, rule_score: int) -> dict:
    recommendation = str(value.get("recommendation") or "weiter_recherchieren")
    if recommendation not in ALLOWED_RECOMMENDATIONS:
        recommendation = "weiter_recherchieren"
    confidence = value.get("confidence", 0)
    confidence = max(0, min(100, int(confidence) if isinstance(confidence, (int, float)) else 0))
    strings = lambda key, limit: [str(item)[:300] for item in value.get(key, []) if str(item).strip()][:limit]
    return {
        "phase": phase, "model": model, "rule_score": rule_score,
        "summary": str(value.get("summary") or "Keine Zusammenfassung geliefert.")[:1200],
        "reasoning": str(value.get("reasoning") or "Keine Begründung geliefert.")[:1600],
        "duplicates": strings("duplicates", 8), "conflicts": strings("conflicts", 8),
        "wikilinks": strings("wikilinks", 8), "proposed_target": str(value.get("proposed_target") or "")[:300],
        "confidence": confidence, "recommendation": recommendation,
        "advisory_only": True, "vault_changed": False,
    }


def evaluate_candidate(vault: Path, candidate_id: str, model: str, chat: Callable[..., dict[str, Any]]) -> dict:
    radar = analyze_knowledge_gaps(vault)
    candidate = next((item for item in radar["candidates"] if item["id"] == candidate_id), None)
    if not candidate:
        raise ValueError("Der Kandidat gehört nicht zum aktuellen Wissensradar.")
    source = (vault / candidate["source"]).resolve()
    if vault.resolve() not in source.parents or not source.is_file():
        raise ValueError("Die Quellseite des Kandidaten fehlt.")
    related = [item for item in radar["candidates"] if item["id"] != candidate_id][:30]
    retrieval = retrieve_vault_context(candidate["title"], max_results=5, max_chars=10_000)
    payload = {
        "candidate": candidate, "source_content": source.read_text(encoding="utf-8", errors="ignore")[:16000],
        "other_candidates": [{"title": item["title"], "source": item["source"], "topic": item["topic"]} for item in related],
        "qmd_vault_context": retrieval["context"],
    }
    result = chat(messages=[
        {"role": "system", "content": _system_prompt()},
        {"role": "user", "content": "Bewerte diese lokale Wissenslücke.\n" + json.dumps(payload, ensure_ascii=False)},
    ], model=model)
    validated = _validated(_json_object(str(result.get("message", {}).get("content", ""))), model, "kandidat", int(candidate["score"]))
    validated["vault_retrieval"] = public_retrieval(retrieval)
    return validated


def evaluate_research(vault: Path, run_id: str, model: str, chat: Callable[..., dict[str, Any]]) -> dict:
    run = load_research_run(run_id)
    retrieval = retrieve_vault_context(run["candidate"]["title"], max_results=5, max_chars=10_000)
    payload = {"candidate": run["candidate"], "sources": run["sources"], "qmd_vault_context": retrieval["context"]}
    result = chat(messages=[
        {"role": "system", "content": _system_prompt()},
        {"role": "user", "content": "Vergleiche Recherchequellen und Vault-Abgleich.\n" + json.dumps(payload, ensure_ascii=False)},
    ], model=model)
    validated = _validated(_json_object(str(result.get("message", {}).get("content", ""))), model, "recherche", int(run["candidate"]["score"]))
    validated["vault_retrieval"] = public_retrieval(retrieval)
    return validated


def _system_prompt() -> str:
    return (
        "Du bist die optionale lokale Bewertungsinstanz des SecBrain-Wissensradars. "
        "Du darfst nichts schreiben, keinen Workflow fortschalten und nur die gelieferten Daten bewerten. "
        "Antworte ausschließlich als JSON mit: summary, reasoning, duplicates (Array), conflicts (Array), "
        "confidence (0-100), recommendation (erweitern|aktualisieren|schliessen|weiter_recherchieren), "
        "proposed_target und wikilinks (Array). Behaupte keine nicht gelieferten Vault-Fakten."
    )
