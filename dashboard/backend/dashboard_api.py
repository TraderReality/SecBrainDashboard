"""
SECBrain Watcher

Dashboard API
SECBrain <-> Ollama Integration
"""

import base64
import binascii
import json
import os
import re
import tempfile
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from access_control import BasicAuthMiddleware, validate_auth_configuration
from runtime.runtime_manager import RuntimeManager
from guardian_rules import chat_context, for_station, free_chat_context
from dokulader_service import import_package, import_pdf, import_urls
from knowledge_radar_service import analyze_knowledge_gaps
from knowledge_ai_service import evaluate_candidate, evaluate_research
from knowledge_research_service import create_integration_proposal, load_integration_proposal, research_candidate
from knowledge_growth_service import (
    KnowledgeGrowthScheduler,
    growth_status,
    run_growth_radar, researched_topics, record_research, record_proposal,
    update_growth_config,
)
from vault_retrieval_service import public_retrieval, retrieval_status, retrieve_vault_context
from loop.watcher_loop_orchestrator import WatcherLoopOrchestrator
from loop.watcher_loop_runtime import WatcherLoopRuntime


BASE_DIR = Path(__file__).resolve().parent

FRONTEND_DIR = (
    BASE_DIR.parent /
    "frontend"
)


@asynccontextmanager
async def app_lifespan(_app):
    validate_auth_configuration()
    knowledge_growth_scheduler.start()
    try:
        yield
    finally:
        knowledge_growth_scheduler.stop()


app = FastAPI(title="SECBrain Watcher Dashboard", lifespan=app_lifespan)
app.add_middleware(BasicAuthMiddleware)


@app.get("/healthz", include_in_schema=False)
def healthz():
    return {"status": "ok"}


watcher_loop = WatcherLoopRuntime()

runtime = RuntimeManager()
watcher_orchestrator = WatcherLoopOrchestrator(
    watcher_loop,
    runtime.ollama.chat,
    str(runtime.vault.path),
)
knowledge_growth_scheduler = KnowledgeGrowthScheduler(runtime.vault.path)


def watcher_status() -> dict:
    state = watcher_loop.status()
    state["orchestration"] = watcher_orchestrator.status()
    return state


def vault_graph_path() -> Path:
    return runtime.vault.path / "08 KI-Wissensbank" / "_index" / "graph.json"


@app.get("/api/vault/retrieval/status")
def vault_retrieval_status():
    """Report whether the shared read-only QMD retrieval path is ready."""
    return retrieval_status()


@app.get("/api/knowledge-radar")
def knowledge_radar():
    """Analyze local Vault gaps without network access or persistent writes."""
    return analyze_knowledge_gaps(runtime.vault.path)


@app.post("/api/knowledge-radar/research")
def knowledge_radar_research(payload: dict):
    try:
        candidate_id = str(payload.get("candidate_id") or "")
        radar = analyze_knowledge_gaps(runtime.vault.path)
        candidate = next((item for item in radar["candidates"] if item["id"] == candidate_id), None)
        if not candidate:
            raise ValueError("Der Forschungskandidat gehört nicht zum aktuellen Wissensradar.")
        result = research_candidate(runtime.vault.path, candidate_id)
        record_research(candidate, result, "manual")
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/knowledge-radar/ai-evaluate")
def knowledge_radar_ai_evaluate(payload: dict):
    try:
        model = str(payload.get("model") or runtime.ollama.get_config().get("model") or "").strip()
        if not model:
            raise ValueError("Für die KI-Radarbewertung muss ein lokales Modell gewählt sein.")
        run_id = str(payload.get("run_id") or "").strip()
        if run_id:
            return evaluate_research(runtime.vault.path, run_id, model, runtime.ollama.chat)
        return evaluate_candidate(
            runtime.vault.path, str(payload.get("candidate_id") or ""), model, runtime.ollama.chat
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/knowledge-radar/proposal")
def knowledge_radar_proposal(payload: dict):
    try:
        run_id = str(payload.get("run_id") or "")
        proposal = create_integration_proposal(runtime.vault.path, run_id)
        record_proposal(run_id, proposal)
        return proposal
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/knowledge-radar/handoff")
def knowledge_radar_handoff(payload: dict):
    try:
        proposal = load_integration_proposal(
            str(payload.get("run_id") or ""), str(payload.get("proposal_id") or "")
        )
        model = str(payload.get("model") or runtime.ollama.get_config().get("model") or "")
        return watcher_orchestrator.stage_research_proposal(proposal, model)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/knowledge-radar/growth")
def knowledge_radar_growth_status():
    return growth_status()


@app.get("/api/knowledge-radar/researched")
def knowledge_radar_researched():
    return {"topics": researched_topics(runtime.vault.path)}


@app.put("/api/knowledge-radar/growth/config")
def knowledge_radar_growth_config(payload: dict):
    try:
        return update_growth_config(str(payload.get("schedule") or "manual"), payload.get("topic_budget"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/knowledge-radar/growth/run")
def knowledge_radar_growth_run():
    try:
        return run_growth_radar(runtime.vault.path, "manual")
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def vault_graph_sync(graph: dict, graph_updated_at: float) -> dict:
    """Compare the export with its Markdown sources without persisting state."""

    excluded_dirs = {
        ".git",
        ".cptr",
        ".obsidian",
        "node_modules",
        "07 Anhänge",
        "_Vorschlaege",
    }
    documents = []
    for candidate in runtime.vault.path.rglob("*.md"):
        relative = candidate.relative_to(runtime.vault.path)
        if candidate.name.startswith("_"):
            continue
        if any(part in excluded_dirs for part in relative.parts):
            continue
        documents.append(candidate)

    latest_source_update = max(
        (document.stat().st_mtime for document in documents),
        default=0.0,
    )
    exported_documents = int(
        graph.get("dateien_indexiert", len(graph.get("nodes") or []))
    )
    current = (
        graph_updated_at >= latest_source_update
        and exported_documents == len(documents)
    )
    return {
        "state": "current" if current else "stale",
        "current": current,
        "graph_updated_at": graph_updated_at,
        "vault_updated_at": latest_source_update or None,
        "exported_documents": exported_documents,
        "vault_documents": len(documents),
    }


def agents_md_path() -> Path:
    return runtime.vault.path / "AGENTS.md"


MAX_INBOX_UPLOAD_BYTES = 512 * 1024


def safe_inbox_filename(filename: str) -> str:
    """Return a plain Markdown filename without accepting path components."""
    name = Path(str(filename or "")).name.strip()
    if name != str(filename or "").strip() or name in {"", ".", ".."}:
        raise ValueError("Ungültiger Dateiname.")
    if not name.lower().endswith(".md"):
        raise ValueError("Es können nur Markdown-Dateien (.md) hochgeladen werden.")
    if not re.fullmatch(r"[^\x00-\x1f/\\]+\.md", name, flags=re.IGNORECASE):
        raise ValueError("Der Dateiname enthält unzulässige Zeichen.")
    return name


def write_inbox_upload(filename: str, content_base64: str) -> dict:
    name = safe_inbox_filename(filename)
    try:
        content = base64.b64decode(content_base64 or "", validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("Die Upload-Daten sind ungültig.") from exc
    if not content:
        raise ValueError("Die Datei ist leer.")
    if len(content) > MAX_INBOX_UPLOAD_BYTES:
        raise ValueError("Die Datei ist größer als 512 KiB.")
    try:
        content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Die Markdown-Datei muss UTF-8-kodiert sein.") from exc

    inbox = runtime.vault.path / "01 Inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    target = inbox / name
    if target.exists():
        raise FileExistsError(f"{name} existiert bereits in der Inbox.")

    descriptor, temporary_name = tempfile.mkstemp(prefix=".upload-", suffix=".tmp", dir=inbox)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary_name, target)
    finally:
        Path(temporary_name).unlink(missing_ok=True)
    return {"status": "uploaded", "filename": name, "bytes": len(content)}


# ============================================================
# DASHBOARD STATUS
# ============================================================

@app.get("/api/status")
def status():

    result = runtime.status()

    result["loop"] = watcher_status()

    return result


@app.post("/api/vault/inbox/upload")
def vault_inbox_upload(payload: dict):
    """Accept one small UTF-8 Markdown file for the Watcher inbox."""
    try:
        return write_inbox_upload(
            str(payload.get("filename") or ""),
            str(payload.get("content_base64") or ""),
        )
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/dokulader/urls")
def dokulader_urls(payload: dict):
    urls = payload.get("urls")
    if not isinstance(urls, list):
        raise HTTPException(status_code=400, detail="URLs müssen als Liste übergeben werden.")
    try:
        return import_urls(runtime.vault.path, [str(url) for url in urls])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/dokulader/package")
def dokulader_package(payload: dict):
    try:
        return import_package(
            runtime.vault.path,
            str(payload.get("filename") or ""),
            str(payload.get("content_base64") or ""),
        )
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/dokulader/pdf")
def dokulader_pdf(payload: dict):
    try:
        return import_pdf(
            runtime.vault.path,
            str(payload.get("filename") or ""),
            str(payload.get("content_base64") or ""),
        )
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ============================================================
# VAULT GRAPH — READ-ONLY INDEXER EXPORT
# ============================================================

@app.get("/api/vault/graph")
def vault_graph():
    """Expose the indexer's graph view without creating a second data source."""

    source = vault_graph_path()
    if not source.is_file():
        raise HTTPException(
            status_code=404,
            detail="Der Indexer-Export graph.json wurde noch nicht gefunden.",
        )

    try:
        graph = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Der Indexer-Export kann nicht gelesen werden: {exc}",
        ) from exc

    updated_at = source.stat().st_mtime
    return {
        "source": "08 KI-Wissensbank/_index/graph.json",
        "updated_at": updated_at,
        "sync": vault_graph_sync(graph, updated_at),
        "graph": graph,
    }


# ============================================================
# AGENTS.md — REGELQUELLE (Station Details · Markdown-Badge)
# ============================================================

@app.get("/api/vault/agents-md")
def agents_md_read():
    """Liefert den aktuellen Inhalt von AGENTS.md aus der Vault."""

    source = agents_md_path()
    if not source.is_file():
        raise HTTPException(
            status_code=404,
            detail="AGENTS.md wurde in der Vault nicht gefunden.",
        )

    try:
        content = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"AGENTS.md kann nicht gelesen werden: {exc}",
        ) from exc

    return {
        "path": "AGENTS.md",
        "content": content,
        "updated_at": source.stat().st_mtime,
    }


@app.put("/api/vault/agents-md")
def agents_md_write(payload: dict):
    """Speichert Änderungen an AGENTS.md und sichert vorher die bisherige Version."""

    content = payload.get("content")
    if not isinstance(content, str) or not content.strip():
        raise HTTPException(
            status_code=400,
            detail="content darf nicht leer sein.",
        )

    target = agents_md_path()
    if not target.is_file():
        raise HTTPException(
            status_code=404,
            detail="AGENTS.md wurde in der Vault nicht gefunden.",
        )

    try:
        backup = target.with_name(
            target.name + f".bak-{int(time.time() * 1000)}"
        )
        backup.write_text(
            target.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        target.write_text(content, encoding="utf-8")

    except OSError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"AGENTS.md konnte nicht gespeichert werden: {exc}",
        ) from exc

    return {
        "success": True,
        "path": "AGENTS.md",
        "updated_at": target.stat().st_mtime,
    }


# ============================================================
# OLLAMA STATUS
# ============================================================

@app.get("/api/ollama/status")
def ollama_status():

    return runtime.ollama.status()


# ============================================================
# OLLAMA CONFIG
# ============================================================

@app.get("/api/ollama/config")
def ollama_config():

    return runtime.ollama.get_config()


# ============================================================
# OLLAMA CONFIG UPDATE
# ============================================================

@app.post("/api/ollama/config")
def ollama_config_update(
    payload: dict
):

    if ("model" in payload or "default_model" in payload) and watcher_orchestrator.is_active():
        raise HTTPException(
            status_code=409,
            detail="Während eines autonomen Laufs kann das Modell nicht gewechselt werden.",
        )

    config = runtime.ollama.configure(
        payload
    )

    return {
        "success": True,
        "config": config,
    }


# ============================================================
# OLLAMA CHAT
# ============================================================

@app.post("/api/ollama/chat")
def ollama_chat(payload: dict):

    messages = payload.get("messages")

    if not isinstance(messages, list):
        raise HTTPException(
            status_code=400,
            detail="messages muss eine Liste sein.",
        )

    query = next((
        str(item.get("content") or "") for item in reversed(messages)
        if isinstance(item, dict) and item.get("role") == "user"
    ), "")
    retrieval = retrieve_vault_context(query)

    try:
        guarded_messages = free_chat_context()
        if retrieval["context"]:
            guarded_messages.append({
                "role": "system",
                "content": (
                    "Nutze den folgenden aktuellen, read-only QMD-Vault-Kontext nur soweit er zur Frage passt. "
                    "Nenne verwendete Quellen mit ihrem QMD-Pfad und erfinde keine Vault-Inhalte.\n\n"
                    + retrieval["context"]
                ),
            })
        guarded_messages += messages

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Wächterregeln konnten nicht geladen werden: {exc}",
        ) from exc

    try:
        result = runtime.ollama.chat(
            messages=guarded_messages,
            model=str(payload.get("model") or ""),
        )
        response = dict(result)
        response["vault_retrieval"] = public_retrieval(retrieval)
        return response

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Ollama-Chat nicht verfügbar: {exc}",
        ) from exc


# ============================================================
# STATION GUARDIAN RULES
# ============================================================

@app.get("/api/stations/{station_id}/guardian-rule")
def station_guardian_rule(station_id: int):

    try:
        return for_station(station_id)

    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc


# ============================================================
# WATCHER LOOP RUNTIME
# ============================================================

@app.get("/api/watcher-loop/status")
def watcher_loop_status():

    return watcher_status()


@app.post("/api/watcher-loop/autonomous/start")
def watcher_loop_autonomous_start(payload: dict):

    try:
        return watcher_orchestrator.start(
            str(payload.get("goal") or ""),
            str(payload.get("model") or runtime.ollama.get_config().get("model") or ""),
            str(payload.get("author") or ""),
        )

    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/watcher-loop/autonomous/stop")
def watcher_loop_autonomous_stop():

    return watcher_orchestrator.stop()


@app.post("/api/watcher-loop/autonomous/approve")
def watcher_loop_autonomous_approve():
    try:
        return watcher_orchestrator.approve()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/watcher-loop/autonomous/reject")
def watcher_loop_autonomous_reject():
    try:
        return watcher_orchestrator.reject()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

# ============================================================
# FRONTEND
# ============================================================

app.mount(

    "/",

    StaticFiles(
        directory=str(FRONTEND_DIR),
        html=True
    ),

    name="frontend"

)
