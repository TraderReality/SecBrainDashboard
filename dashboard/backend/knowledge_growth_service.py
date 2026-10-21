"""Persistent, Vault-safe scheduling and history for recurring knowledge radar runs."""

import hashlib
import calendar
import json
import os
import tempfile
import threading
import time
import uuid
from pathlib import Path

from knowledge_radar_service import analyze_knowledge_gaps
from knowledge_research_service import research_candidate


SCHEDULE_DAYS = {"manual": 30, "weekly": 7, "monthly": 30}
DEFAULT_CONFIG = {"schedule": "manual", "topic_budget": 3, "last_run_at": None, "next_run_at": None}
MAX_HISTORY = 200


def _utc_timestamp() -> int:
    return int(time.time())


def _state_root() -> Path:
    configured = os.environ.get("SECBRAIN_WATCHER_STATE_DIR", "").strip()
    root = Path(configured).expanduser() if configured else Path.home() / ".local/state/secbrain-watcher/knowledge-radar"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _research_workspace_root() -> Path:
    return Path(tempfile.gettempdir()) / "secbrain-watcher" / "research"


def _read_json(name: str, default):
    path = _state_root() / name
    if not path.is_file():
        return default.copy() if isinstance(default, dict) else list(default)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default.copy() if isinstance(default, dict) else list(default)


def _write_json(name: str, value) -> None:
    target = _state_root() / name
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{name}.", dir=target.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, target)
    finally:
        try:
            Path(temporary_name).unlink(missing_ok=True)
        except OSError:
            pass


def _iso(timestamp: int | None) -> str | None:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(timestamp)) if timestamp else None


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()


def _candidate_key(candidate: dict) -> str:
    return _hash_text(f"{candidate.get('source', '')}\0{candidate.get('title', '')}")


def _source_hash(vault: Path, candidate: dict) -> str:
    path = (vault / str(candidate.get("source") or "")).resolve()
    try:
        if vault.resolve() not in path.parents or not path.is_file():
            return "missing"
        return _hash_text(path.read_text(encoding="utf-8", errors="ignore"))
    except OSError:
        return "unreadable"


def get_growth_config() -> dict:
    stored = _read_json("config.json", DEFAULT_CONFIG)
    config = DEFAULT_CONFIG | {key: stored.get(key) for key in DEFAULT_CONFIG if key in stored}
    return config | {
        "last_run": _iso(config.get("last_run_at")),
        "next_run": _iso(config.get("next_run_at")),
    }


def update_growth_config(schedule: str, topic_budget: int) -> dict:
    if schedule not in SCHEDULE_DAYS:
        raise ValueError("Zeitplan muss manuell, wöchentlich oder monatlich sein.")
    if not isinstance(topic_budget, int) or isinstance(topic_budget, bool) or not 1 <= topic_budget <= 10:
        raise ValueError("Das Themenbudget muss zwischen 1 und 10 liegen.")
    current = get_growth_config()
    now = _utc_timestamp()
    next_run = None if schedule == "manual" else now + SCHEDULE_DAYS[schedule] * 86400
    config = {
        "schedule": schedule,
        "topic_budget": topic_budget,
        "last_run_at": current.get("last_run_at"),
        "next_run_at": next_run,
    }
    _write_json("config.json", config)
    return get_growth_config()


def get_growth_history(limit: int = 20) -> list[dict]:
    limit = max(1, min(int(limit), 100))
    return _read_json("history.json", [])[-limit:][::-1]


def record_research(candidate: dict, research: dict, trigger: str = "manual") -> dict:
    """Keep one durable maintenance record per knowledge topic."""
    now = _utc_timestamp()
    key = _candidate_key(candidate)
    records = _read_json("researched_topics.json", {})
    previous = records.get(key, {})
    sources = [{
        "url": source.get("url"), "title": source.get("title"), "date": source.get("date"),
        "source_type": source.get("source_type"),
        "content_hash": _hash_text(str(source.get("statement") or "")),
    } for source in research.get("sources", [])]
    record = {
        "key": key, "candidate_id": candidate.get("id"), "title": candidate.get("title"),
        "topic": candidate.get("topic"), "source": candidate.get("source"),
        "source_title": candidate.get("source_title"), "first_researched_at": previous.get("first_researched_at") or _iso(now),
        "last_researched_at": _iso(now), "last_run_id": research.get("run_id"),
        "last_query": research.get("query"), "trigger": trigger, "research_count": int(previous.get("research_count") or 0) + 1,
        "sources": sources, "source_count": len(sources), "proposal": previous.get("proposal"),
    }
    records[key] = record
    _write_json("researched_topics.json", records)
    return record


def record_proposal(run_id: str, proposal: dict) -> None:
    records = _read_json("researched_topics.json", {})
    for key, record in records.items():
        if record.get("last_run_id") == run_id:
            record["proposal"] = {
                "proposal_id": proposal.get("proposal_id"), "operation": proposal.get("operation"),
                "target": proposal.get("target"), "confidence": proposal.get("confidence"),
                "created_at": proposal.get("created_at"),
            }
            records[key] = record
            _write_json("researched_topics.json", records)
            return


def researched_topics(vault: Path) -> list[dict]:
    records = _read_json("researched_topics.json", {})
    workspace_root = _research_workspace_root()
    if workspace_root.is_dir():
        for path in sorted(workspace_root.glob("radar-*/run.json"), reverse=True):
            try:
                run = json.loads(path.read_text(encoding="utf-8"))
                candidate = run.get("candidate") or {}
                key = _candidate_key(candidate)
                if candidate.get("id") and key not in records:
                    record_research(candidate, run, "bestand")
                    records = _read_json("researched_topics.json", {})
                proposal_path = path.parent / "proposal.json"
                if key in records and not records[key].get("proposal") and proposal_path.is_file():
                    proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
                    record_proposal(records[key].get("last_run_id") or path.parent.name, proposal)
                    records = _read_json("researched_topics.json", {})
            except (OSError, json.JSONDecodeError):
                continue
    candidates = analyze_knowledge_gaps(vault)["candidates"]
    current_by_key = {_candidate_key(item): item for item in candidates}
    config = get_growth_config()
    interval = SCHEDULE_DAYS[config["schedule"]] * 86400
    now = _utc_timestamp()
    result = []
    for key, stored in records.items():
        item = dict(stored)
        current = current_by_key.get(key)
        last = item.get("last_researched_at")
        try:
            last_timestamp = int(calendar.timegm(time.strptime(last, "%Y-%m-%dT%H:%M:%SZ"))) if last else 0
        except (TypeError, ValueError):
            last_timestamp = 0
        item["candidate_available"] = current is not None
        item["candidate_id"] = current.get("id") if current else item.get("candidate_id")
        item["due"] = now - last_timestamp >= interval
        item["next_check_at"] = _iso(last_timestamp + interval) if last_timestamp else None
        result.append(item)
    return sorted(result, key=lambda item: item.get("last_researched_at") or "", reverse=True)


def growth_status() -> dict:
    config = get_growth_config()
    history = get_growth_history()
    return {"config": config, "history": history, "history_count": len(_read_json("history.json", []))}


_run_lock = threading.Lock()


def run_growth_radar(vault: Path, trigger: str = "manual") -> dict:
    if trigger not in {"manual", "scheduled"}:
        raise ValueError("Ungültiger Auslöser für den Radar-Lauf.")
    if not _run_lock.acquire(blocking=False):
        raise RuntimeError("Ein Radar-Lauf ist bereits aktiv.")
    try:
        now = _utc_timestamp()
        config = get_growth_config()
        snapshots = _read_json("topics.json", {})
        source_index = _read_json("sources.json", {})
        radar = analyze_knowledge_gaps(vault)
        stale_after = SCHEDULE_DAYS[config["schedule"]] * 86400
        eligible = []
        skipped = 0
        for candidate in radar["candidates"]:
            key = _candidate_key(candidate)
            current_hash = _source_hash(vault, candidate)
            previous = snapshots.get(key)
            changed = not previous or previous.get("source_hash") != current_hash
            stale = not previous or now - int(previous.get("checked_at") or 0) >= stale_after
            if changed or stale:
                eligible.append((candidate, key, current_hash, changed, stale))
            else:
                skipped += 1
        selected = eligible[: config["topic_budget"]]
        entries = []
        changed_sources = 0
        for candidate, key, current_hash, changed, stale in selected:
            entry = {
                "candidate_id": candidate["id"], "title": candidate["title"], "topic": candidate["topic"],
                "reason": "geändert" if changed else "veraltet", "status": "failed", "sources": [],
            }
            try:
                research = research_candidate(vault, candidate["id"])
                record_research(candidate, research, trigger)
                entry.update({"status": "completed", "run_id": research["run_id"], "query": research["query"]})
                for source in research["sources"]:
                    content_hash = _hash_text(source.get("statement", ""))
                    previous_source = source_index.get(source["url"], {})
                    source_changed = bool(previous_source) and (
                        previous_source.get("content_hash") != content_hash
                        or previous_source.get("date") != source.get("date")
                    )
                    changed_sources += int(source_changed)
                    source_record = {
                        "url": source["url"], "title": source["title"], "date": source.get("date"),
                        "content_hash": content_hash, "changed": source_changed,
                    }
                    entry["sources"].append(source_record)
                    source_index[source["url"]] = source_record | {"checked_at": now}
            except Exception as exc:
                entry["error"] = str(exc)
            if entry["status"] == "completed":
                snapshots[key] = {"source_hash": current_hash, "checked_at": now, "candidate_id": candidate["id"]}
            entries.append(entry)

        run = {
            "id": f"growth-{time.strftime('%Y%m%d-%H%M%S', time.gmtime(now))}-{uuid.uuid4().hex[:8]}",
            "started_at": _iso(now), "trigger": trigger, "schedule": config["schedule"],
            "topic_budget": config["topic_budget"], "eligible_topics": len(eligible),
            "processed_topics": len(entries), "skipped_unchanged": skipped,
            "changed_sources": changed_sources, "entries": entries,
            "status": "completed" if all(item["status"] == "completed" for item in entries) else "partial",
        }
        history = _read_json("history.json", [])
        history.append(run)
        _write_json("history.json", history[-MAX_HISTORY:])
        _write_json("topics.json", snapshots)
        _write_json("sources.json", source_index)
        next_run = None if config["schedule"] == "manual" else now + SCHEDULE_DAYS[config["schedule"]] * 86400
        _write_json("config.json", {
            "schedule": config["schedule"], "topic_budget": config["topic_budget"],
            "last_run_at": now, "next_run_at": next_run,
        })
        return run
    finally:
        _run_lock.release()


class KnowledgeGrowthScheduler:
    def __init__(self, vault: Path, interval_seconds: int = 60):
        self.vault = vault
        self.interval_seconds = interval_seconds
        self._stop = threading.Event()
        self._thread = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="knowledge-growth-scheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _loop(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            config = get_growth_config()
            if config["schedule"] == "manual" or not config.get("next_run_at"):
                continue
            if _utc_timestamp() >= int(config["next_run_at"]):
                try:
                    run_growth_radar(self.vault, "scheduled")
                except Exception:
                    continue
