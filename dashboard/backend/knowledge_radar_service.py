"""Read-only analysis of local Vault topics and knowledge gaps."""

import re
from collections import Counter
from pathlib import Path

import yaml


EXCLUDED_PARTS = {".git", ".obsidian", ".cptr", "node_modules", "06 Archiv", "07 Anhänge", "01 Inbox", "_index", "_Vorschlaege"}
QUESTION_HEADINGS = {"offene fragen", "offene frage", "fragen", "weiterführende fragen"}


def _frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---\n"):
        return {}, text
    parts = text.split("---\n", 2)
    if len(parts) != 3:
        return {}, text
    try:
        return yaml.safe_load(parts[1]) or {}, parts[2]
    except yaml.YAMLError:
        return {}, parts[2]


def _title(path: Path, metadata: dict, body: str) -> str:
    if metadata.get("titel"):
        return str(metadata["titel"]).strip()
    heading = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
    return heading.group(1).strip() if heading else path.stem


def _open_questions(body: str) -> list[str]:
    questions = []
    active = False
    for line in body.splitlines():
        heading = re.match(r"^#{2,6}\s+(.+?)\s*$", line)
        if heading:
            active = heading.group(1).strip().casefold() in QUESTION_HEADINGS
            continue
        todo = re.match(r"^\s*[-*]\s+(?:\[\s?\]\s*)?(.+?)\s*$", line)
        if active and todo:
            value = todo.group(1).strip()
            if value and value not in {"—", "-", "Keine."}:
                questions.append(value)
    return questions


def analyze_knowledge_gaps(vault: Path) -> dict:
    """Return explainable research candidates without modifying the Vault."""
    documents = []
    topic_counts: Counter[str] = Counter()
    inbound: Counter[str] = Counter()
    raw_links = []

    for path in vault.rglob("*.md") if vault.exists() else ():
        relative = path.relative_to(vault)
        if path.name.startswith("_") or any(part in EXCLUDED_PARTS for part in relative.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        metadata, body = _frontmatter(text)
        title = _title(path, metadata, body)
        tags = {str(tag).casefold() for tag in (metadata.get("tags") or [])}
        page_type = str(metadata.get("typ") or "").casefold()
        candidate_eligible = page_type != "system" and not tags.intersection({"system", "schema", "template", "vorlage"})
        links = re.findall(r"\[\[([^\]|#]+)", body)
        raw_links.extend(links)
        topic = relative.parts[0] if len(relative.parts) > 1 else "Vault"
        topic_counts[topic] += 1
        documents.append({
            "path": relative.as_posix(), "title": title, "topic": topic,
            "questions": _open_questions(body),
            "words": len(re.findall(r"\b[\wÄÖÜäöüß-]+\b", body)),
            "links": len(links),
            "candidate_eligible": candidate_eligible,
        })

    title_keys = {doc["title"].casefold(): doc["title"] for doc in documents}
    stem_keys = {Path(doc["path"]).stem.casefold(): doc["title"] for doc in documents}
    for link in raw_links:
        key = Path(link.strip()).name.casefold()
        target = title_keys.get(key) or stem_keys.get(key)
        if target:
            inbound[target] += 1

    candidates = []
    for doc in documents:
        if not doc["candidate_eligible"]:
            continue
        importance = min(inbound[doc["title"]], 10)
        for question in doc["questions"]:
            candidates.append({
                "id": f"question:{doc['path']}:{len(candidates)}",
                "title": question.rstrip("? ") + "?",
                "type": "offene_frage",
                "topic": doc["topic"],
                "source": doc["path"],
                "source_title": doc["title"],
                "score": 90 + importance,
                "reason": "Explizit als offene Frage in einer Vault-Seite festgehalten.",
            })
        if not doc["questions"] and doc["words"] < 140 and doc["links"] < 2:
            thinness = max(0, 140 - doc["words"]) // 14
            candidates.append({
                "id": f"thin:{doc['path']}",
                "title": f"{doc['title']} fachlich vertiefen",
                "type": "duennes_thema",
                "topic": doc["topic"],
                "source": doc["path"],
                "source_title": doc["title"],
                "score": min(89, 55 + thinness + importance),
                "reason": f"Nur {doc['words']} Wörter und {doc['links']} ausgehende Verknüpfungen.",
            })

    candidates.sort(key=lambda item: (-item["score"], item["title"].casefold()))
    topics = [
        {"name": name, "documents": count}
        for name, count in sorted(topic_counts.items(), key=lambda item: (-item[1], item[0].casefold()))
    ]
    return {
        "status": "ready",
        "read_only": True,
        "documents_scanned": len(documents),
        "topics": topics,
        "candidates": candidates[:100],
        "candidate_count": len(candidates),
        "method": "Offene Fragen zuerst; anschließend kurze, schwach verlinkte Wissensseiten.",
    }
