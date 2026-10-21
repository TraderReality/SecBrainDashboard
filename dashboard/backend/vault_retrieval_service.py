"""Shared, read-only QMD retrieval for chat, loop and knowledge radar."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from typing import Any


DEFAULT_MAX_RESULTS = 5
DEFAULT_MAX_CHARS = 12_000
MAX_RESULTS_LIMIT = 10
MAX_CHARS_LIMIT = 30_000


def _binary() -> str | None:
    configured = os.getenv("SECBRAIN_QMD_BINARY", "").strip()
    return configured or shutil.which("qmd")


def _collection() -> str:
    return os.getenv("SECBRAIN_QMD_COLLECTION", "secbrain").strip() or "secbrain"


def retrieval_status() -> dict[str, Any]:
    binary = _binary()
    status = {
        "available": False,
        "provider": "qmd-bm25",
        "collection": _collection(),
        "binary": binary,
        "error": None,
    }
    if not binary:
        status["error"] = "QMD wurde nicht gefunden."
        return status
    try:
        completed = subprocess.run(
            [binary, "status"], capture_output=True, text=True, timeout=8, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        status["error"] = f"QMD-Status nicht verfügbar: {exc}"
        return status
    status["available"] = completed.returncode == 0
    if completed.returncode:
        status["error"] = (completed.stderr or completed.stdout or "QMD-Status fehlgeschlagen.").strip()[:500]
    return status


def retrieve_vault_context(
    query: str,
    max_results: int | None = None,
    max_chars: int | None = None,
) -> dict[str, Any]:
    """Return bounded QMD hits plus prompt-ready context without writing to the Vault."""
    query = " ".join(str(query or "").split())[:2_000]
    result_limit = _bounded_int(
        max_results, "SECBRAIN_RETRIEVAL_MAX_RESULTS", DEFAULT_MAX_RESULTS, 1, MAX_RESULTS_LIMIT,
    )
    char_limit = _bounded_int(
        max_chars, "SECBRAIN_RETRIEVAL_MAX_CHARS", DEFAULT_MAX_CHARS, 1_000, MAX_CHARS_LIMIT,
    )
    base = {
        "available": False,
        "provider": "qmd-bm25",
        "collection": _collection(),
        "query": query,
        "max_results": result_limit,
        "max_chars": char_limit,
        "used_chars": 0,
        "hits": [],
        "context": "",
        "error": None,
    }
    binary = _binary()
    if not binary:
        base["error"] = "QMD wurde nicht gefunden."
        return base
    if not query:
        base["error"] = "Keine Suchanfrage übergeben."
        return base
    try:
        completed = subprocess.run(
            [binary, "search", query, "-c", base["collection"], "-n", str(result_limit), "--format", "json"],
            capture_output=True, text=True, timeout=12, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        base["error"] = f"QMD-Suche nicht verfügbar: {exc}"
        return base
    if completed.returncode:
        base["error"] = (completed.stderr or completed.stdout or "QMD-Suche fehlgeschlagen.").strip()[:500]
        return base
    try:
        raw_hits = json.loads(_strip_ansi(completed.stdout or "[]"))
    except json.JSONDecodeError:
        base["error"] = "QMD lieferte ungültiges JSON."
        return base
    if not isinstance(raw_hits, list):
        base["error"] = "QMD lieferte ein unerwartetes Trefferformat."
        return base

    hits, blocks, used = [], [], 0
    for raw in raw_hits[:result_limit]:
        if not isinstance(raw, dict):
            continue
        hit = _normalize_hit(raw)
        block = _context_block(hit)
        remaining = char_limit - used
        if remaining <= 0:
            break
        if len(block) > remaining:
            block = block[:remaining].rstrip()
        if not block:
            break
        hits.append(hit)
        blocks.append(block)
        used += len(block) + (2 if len(blocks) > 1 else 0)
    base.update({
        "available": True,
        "hits": hits,
        "context": "\n\n".join(blocks),
        "used_chars": min(used, char_limit),
    })
    return base


def public_retrieval(result: dict[str, Any]) -> dict[str, Any]:
    """Remove prompt-only context while retaining transparent source metadata."""
    return {key: value for key, value in result.items() if key != "context"}


def _bounded_int(value: int | None, env_name: str, default: int, minimum: int, maximum: int) -> int:
    candidate: Any = value if value is not None else os.getenv(env_name, default)
    try:
        parsed = int(candidate)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _normalize_hit(raw: dict[str, Any]) -> dict[str, Any]:
    try:
        score = float(raw.get("score", 0))
    except (TypeError, ValueError):
        score = 0.0
    try:
        line = max(0, int(raw.get("line", 0)))
    except (TypeError, ValueError):
        line = 0
    snippet = str(raw.get("snippet") or raw.get("context") or "").strip()[:1_800]
    return {
        "path": str(raw.get("file") or "")[:1_000],
        "title": str(raw.get("title") or "Unbenannte Vault-Seite")[:300],
        "line": line,
        "score": max(0.0, min(1.0, score)),
        "snippet": snippet,
    }


def _context_block(hit: dict[str, Any]) -> str:
    return (
        f"QUELLE: {hit['path']}\n"
        f"TITEL: {hit['title']}\n"
        f"ZEILE: {hit['line']}\n"
        f"RELEVANZ: {hit['score']:.3f}\n"
        f"AUSZUG:\n{hit['snippet']}"
    )


def _strip_ansi(value: str) -> str:
    return re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", value)
