"""Controlled web research for a selected, locally detected knowledge gap."""

import json
import difflib
import hashlib
import re
import shutil
import tempfile
import time
import urllib.parse
import uuid
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from dokulader_service import USER_AGENT, _fetch_html_once
from knowledge_radar_service import analyze_knowledge_gaps


MAX_RESEARCH_SOURCES = 5
WORKSPACE_TTL_SECONDS = 24 * 60 * 60
SEARCH_URL = "https://html.duckduckgo.com/html/"
STOPWORDS = {"aber", "auch", "dass", "dem", "den", "der", "des", "die", "eine", "einer", "eines", "für", "ist", "mit", "nicht", "oder", "sich", "sind", "und", "von", "was", "wie", "wird", "zum", "zur"}
QUERY_FILLERS = STOPWORDS | {"als", "das", "ein", "noch", "soll", "thema", "werden", "welche", "warum"}
GENERIC_FORMAT_TERMS = {"csv", "doc", "docx", "html", "json", "md", "pdf", "txt", "xml", "yaml", "yml", "zip"}


def _tokens(text: str) -> set[str]:
    return {word.casefold() for word in re.findall(r"[\wÄÖÜäöüß-]{3,}", text) if word.casefold() not in STOPWORDS}


def _similarity(left: str, right: str) -> float:
    a, b = _tokens(left), _tokens(right)
    return len(a & b) / len(a | b) if a and b else 0.0


def _build_query(candidate: dict) -> tuple[str, list[str]]:
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9._+-]*", candidate["title"])
    technical = []
    for word in words:
        folded = word.casefold()
        if folded in QUERY_FILLERS or folded == "secbrain" or len(folded) < 2:
            continue
        acronym_parts = re.findall(r"(?<![A-Z])[A-Z]{2,}(?![A-Z])", word)
        if acronym_parts:
            technical.extend(acronym_parts)
        elif len(word) <= 5 or any(character.isdigit() for character in word) or word.isupper():
            technical.append(word)
    required = [term for term in dict.fromkeys(technical) if term.casefold() not in GENERIC_FORMAT_TERMS][:2]
    quoted = " ".join(f'"{word}"' for word in required)
    return f"{quoted} {candidate['title']}".strip(), required


def _search_candidate(candidate: dict) -> tuple[str, list[dict]]:
    query, required_terms = _build_query(candidate)
    source_title = str(candidate.get("source_title") or "").strip()
    if not required_terms and source_title:
        return source_title, _search(source_title, [])
    try:
        return query, _search(query, required_terms)
    except RuntimeError:
        if not source_title:
            raise
        quoted = " ".join(f'"{term}"' for term in required_terms)
        contextual_query = f"{quoted} {source_title}".strip()
        if contextual_query == query:
            raise
        return contextual_query, _search(contextual_query, required_terms)


def _search(query: str, required_terms: list[str] | None = None) -> list[dict]:
    response = requests.post(
        SEARCH_URL,
        data={"q": query},
        headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
        timeout=(5, 20),
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    results = []
    seen = set()
    for result in soup.select(".result"):
        anchor = result.select_one(".result__a")
        if not anchor:
            continue
        url = str(anchor.get("href") or "").strip()
        parsed = urllib.parse.urlsplit(url)
        if parsed.netloc.endswith("duckduckgo.com"):
            url = urllib.parse.parse_qs(parsed.query).get("uddg", [""])[0]
        url = urllib.parse.urlunsplit((*urllib.parse.urlsplit(url)[:4], ""))
        if not url or url in seen:
            continue
        seen.add(url)
        snippet = result.select_one(".result__snippet")
        snippet_text = snippet.get_text(" ", strip=True) if snippet else ""
        haystack = f"{anchor.get_text(' ', strip=True)} {snippet_text}".casefold()
        if required_terms and not all(term.casefold() in haystack for term in required_terms):
            continue
        results.append({
            "title": anchor.get_text(" ", strip=True),
            "url": url,
            "snippet": snippet_text,
        })
        if len(results) >= MAX_RESEARCH_SOURCES:
            break
    if not results:
        raise RuntimeError("Die kontrollierte Suche lieferte keine verwertbaren Treffer.")
    return results


def _source_type(url: str) -> str:
    host = (urllib.parse.urlsplit(url).hostname or "").casefold()
    path = urllib.parse.urlsplit(url).path.casefold()
    if host in {"doi.org", "arxiv.org"} or "paper" in path:
        return "Studie"
    if host.endswith("github.com"):
        return "Repository"
    if "docs" in host or "/docs" in path or "/documentation" in path or "/manual" in path:
        return "Dokumentation"
    return "Webseite"


def _extract_source(item: dict) -> dict:
    final_url, html = _fetch_html_once(item["url"])
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else item["title"]
    date = "nicht angegeben"
    for selector, attribute in (
        ('meta[property="article:published_time"]', "content"),
        ('meta[name="date"]', "content"),
        ('meta[name="last-modified"]', "content"),
        ("time[datetime]", "datetime"),
    ):
        node = soup.select_one(selector)
        if node and node.get(attribute):
            date = str(node.get(attribute)).strip()[:32]
            break
    for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form"]):
        tag.decompose()
    main = soup.select_one("main, article, #content, .content") or soup.body or soup
    paragraphs = [node.get_text(" ", strip=True) for node in main.select("p")]
    summary = next((text for text in paragraphs if len(text) >= 80), item["snippet"])
    return {
        "title": title[:300], "url": final_url, "date": date,
        "source_type": _source_type(final_url), "statement": summary[:900],
    }


def _vault_documents(vault: Path) -> tuple[list[dict], dict]:
    radar = analyze_knowledge_gaps(vault)
    excluded = {"01 Inbox", "06 Archiv", "07 Anhänge", "_index", "_Vorschlaege"}
    documents = []
    for path in vault.rglob("*.md"):
        relative = path.relative_to(vault)
        if path.name.startswith("_") or any(part in excluded for part in relative.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        documents.append({"path": relative.as_posix(), "text": text[:80_000]})
    return documents, radar


def _compare(statement: str, documents: list[dict]) -> dict:
    matches = sorted(
        ((round(_similarity(statement, doc["text"]), 3), doc["path"]) for doc in documents),
        reverse=True,
    )
    score, path = matches[0] if matches else (0.0, "")
    classification = "bereits_vorhanden" if score >= 0.42 else ("verwandt" if score >= 0.16 else "neu")
    return {"classification": classification, "similarity": score, "vault_match": path or None}


def _workspace_root() -> Path:
    root = Path(tempfile.gettempdir()) / "secbrain-watcher" / "research"
    root.mkdir(parents=True, exist_ok=True)
    cutoff = time.time() - WORKSPACE_TTL_SECONDS
    for child in root.iterdir():
        try:
            if child.is_dir() and child.stat().st_mtime < cutoff:
                shutil.rmtree(child, ignore_errors=True)
        except OSError:
            continue
    return root


def _run_workspace(run_id: str) -> Path:
    if not re.fullmatch(r"radar-\d{8}-\d{6}-[a-f0-9]{8}", str(run_id)):
        raise ValueError("Ungültige Recherchekennung.")
    workspace = _workspace_root() / run_id
    if not workspace.is_dir():
        raise ValueError("Der temporäre Recherchelauf wurde nicht gefunden oder ist abgelaufen.")
    return workspace


def _proposal_conflicts(sources: list[dict]) -> list[dict]:
    conflicts = []
    negative = re.compile(r"\b(?:kein|keine|nicht|never|no|without|unsupported)\b", re.IGNORECASE)
    for left_index, left in enumerate(sources):
        for right in sources[left_index + 1:]:
            similarity = _similarity(left["statement"], right["statement"])
            if similarity >= 0.24 and bool(negative.search(left["statement"])) != bool(negative.search(right["statement"])):
                conflicts.append({
                    "type": "moeglicher_quellenwiderspruch",
                    "message": "Ähnliche Aussagen unterscheiden sich in ihrer Verneinung und müssen manuell geprüft werden.",
                    "sources": [left["url"], right["url"]],
                })
    return conflicts


def create_integration_proposal(vault: Path, run_id: str) -> dict:
    workspace = _run_workspace(run_id)
    run_data = json.loads((workspace / "run.json").read_text(encoding="utf-8"))
    candidate, sources = run_data["candidate"], run_data["sources"]
    required_terms = _build_query(candidate)[1]
    all_new = all(source["vault_comparison"]["classification"] == "neu" for source in sources)
    existing_topic = None
    if required_terms:
        matches = [
            path for path in vault.rglob("*.md")
            if path.stem.casefold() == required_terms[0].casefold()
            and not any(part in {"01 Inbox", "06 Archiv", "07 Anhänge", "_Vorschlaege"} for part in path.relative_to(vault).parts)
        ]
        existing_topic = sorted(matches, key=lambda path: (len(path.parts), path.as_posix()))[0] if matches else None
    create_new = bool(required_terms and all_new and existing_topic is None)
    if existing_topic is not None:
        target_relative = existing_topic.relative_to(vault)
        operation = "bestehende_seite_ergaenzen"
        original = existing_topic.read_text(encoding="utf-8")
        page_title = existing_topic.stem
    elif create_new:
        page_title = required_terms[0]
        target_relative = Path(candidate["topic"]) / f"{page_title}.md"
        operation = "neue_seite"
        original = ""
    else:
        target_relative = Path(candidate["source"])
        operation = "bestehende_seite_ergaenzen"
        target = (vault / target_relative).resolve()
        if vault.resolve() not in target.parents or not target.is_file():
            raise ValueError("Die vorgeschlagene Zielseite ist nicht mehr vorhanden.")
        original = target.read_text(encoding="utf-8")
        page_title = target.stem

    vault_links = [candidate["source_title"]]
    for source in sources:
        comparison = source["vault_comparison"]
        match = comparison.get("vault_match")
        if match and comparison.get("classification") != "neu":
            vault_links.append(Path(match).stem)
    wikilinks = list(dict.fromkeys(link for link in vault_links if link and link != page_title))[:8]
    citations = "\n".join(
        f"- [{source['title']}]({source['url']}) — {source['source_type']}, {source['date']}"
        for source in sources
    )
    findings = "\n".join(f"- {source['statement']} [{index}]" for index, source in enumerate(sources, 1))
    relations = " · ".join(f"[[{link}]]" for link in wikilinks) or "Keine zusätzlichen Wikilinks vorgeschlagen."
    section = (
        f"\n\n## Rechercheergänzung — {candidate['title']}\n\n### Kernaussagen\n\n{findings}\n\n"
        f"### Bezug zum Bestand\n\n{relations}\n\n### Quellen\n\n{citations}\n"
    )
    if operation == "neue_seite":
        proposed = (
            "---\n"
            f"id: {re.sub(r'[^a-z0-9]+', '-', page_title.casefold()).strip('-')}\n"
            f"typ: ressource\ntitel: {page_title}\nstatus: entwurf\ntags: [recherche, wissensradar]\n---\n\n"
            f"# {page_title}\n{section.lstrip()}"
        )
    else:
        proposed = original.rstrip() + section
    diff = "\n".join(difflib.unified_diff(
        original.splitlines(), proposed.splitlines(),
        fromfile=f"a/{target_relative.as_posix()}", tofile=f"b/{target_relative.as_posix()}", lineterm="",
    ))
    conflicts = _proposal_conflicts(sources)
    primary_count = sum(source["source_type"] in {"Dokumentation", "Repository", "Studie"} for source in sources)
    confidence = min(95, 45 + len(sources) * 7 + primary_count * 4 - len(conflicts) * 15)
    proposal_id = f"proposal-{uuid.uuid4().hex[:10]}"
    proposal = {
        "proposal_id": proposal_id, "run_id": run_id, "kind": "knowledge_radar",
        "candidate": candidate, "operation": operation, "target": target_relative.as_posix(),
        "target_exists": (vault / target_relative).is_file(), "markdown_diff": diff,
        "proposed_markdown": proposed, "original_hash": hashlib.sha256(original.encode("utf-8")).hexdigest(),
        "proposed_hash": hashlib.sha256(proposed.encode("utf-8")).hexdigest(), "wikilinks": wikilinks,
        "confidence": confidence, "conflicts": conflicts, "sources": sources,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "temporary": True,
    }
    (workspace / "proposal.json").write_text(json.dumps(proposal, ensure_ascii=False, indent=2), encoding="utf-8")
    (workspace / "proposal.diff").write_text(diff, encoding="utf-8")
    return proposal


def load_integration_proposal(run_id: str, proposal_id: str) -> dict:
    workspace = _run_workspace(run_id)
    path = workspace / "proposal.json"
    if not path.is_file():
        raise ValueError("Für diesen Recherchelauf existiert kein Einpflegevorschlag.")
    proposal = json.loads(path.read_text(encoding="utf-8"))
    if proposal.get("proposal_id") != proposal_id:
        raise ValueError("Einpflegevorschlag und Recherchelauf stimmen nicht überein.")
    return proposal


def load_research_run(run_id: str) -> dict:
    return json.loads((_run_workspace(run_id) / "run.json").read_text(encoding="utf-8"))


def research_candidate(vault: Path, candidate_id: str) -> dict:
    documents, radar = _vault_documents(vault)
    candidate = next((item for item in radar["candidates"] if item["id"] == candidate_id), None)
    if not candidate:
        raise ValueError("Der Forschungskandidat gehört nicht zum aktuellen Wissensradar.")
    query, search_results = _search_candidate(candidate)
    sources, errors = [], []
    for item in search_results:
        try:
            source = _extract_source(item)
            source["vault_comparison"] = _compare(source["statement"], documents)
            sources.append(source)
        except Exception as exc:
            errors.append({"url": item["url"], "reason": str(exc)})
    if not sources:
        raise RuntimeError("Keine gefundene Quelle konnte sicher gelesen werden.")

    run_id = f"radar-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
    workspace = _workspace_root() / run_id
    workspace.mkdir()
    created_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    source_lines = []
    for index, source in enumerate(sources, 1):
        comparison = source["vault_comparison"]
        source_lines.append(
            f"### {index}. {source['title']}\n\n- URL: {source['url']}\n- Datum: {source['date']}\n"
            f"- Quellentyp: {source['source_type']}\n- Vault-Abgleich: {comparison['classification']} "
            f"({comparison['similarity']:.3f})\n- Ähnlichste Vault-Seite: {comparison['vault_match'] or 'keine'}\n\n"
            f"> {source['statement']}"
        )
    report = (
        f"# Kontrollierte Recherche — {candidate['title']}\n\n"
        f"- Lauf: {run_id}\n- Erstellt: {created_at}\n- Kandidat: {candidate['id']}\n"
        f"- Ausgangsseite: {candidate['source']}\n- Suchanfrage: {query}\n"
        "- Status: temporär, nicht in die Vault übernommen\n\n## Quellen und Vault-Vergleich\n\n"
        + "\n\n".join(source_lines)
        + "\n\n## Hinweise\n\nDie Ähnlichkeitsklassifikation ist ein lokaler Textvergleich und keine Wahrheitsprüfung. "
          "Vor einer späteren Übernahme müssen Aussagen und Primärquellen fachlich geprüft werden.\n"
    )
    (workspace / "report.md").write_text(report, encoding="utf-8")
    (workspace / "sources.json").write_text(json.dumps(sources, ensure_ascii=False, indent=2), encoding="utf-8")
    (workspace / "run.json").write_text(json.dumps({
        "run_id": run_id, "created_at": created_at, "candidate": candidate,
        "query": query, "sources": sources, "errors": errors,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "status": "completed", "run_id": run_id, "created_at": created_at,
        "candidate": candidate, "query": query, "sources": sources, "errors": errors,
        "report": report, "workspace": str(workspace), "temporary": True,
    }
