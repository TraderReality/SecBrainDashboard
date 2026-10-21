"""Markdown-backed guardrails for the local KI chat and Loop stations."""

from __future__ import annotations

import re
from pathlib import Path


RULES_FILE = Path(__file__).resolve().parent.parent / "guardian_rules.md"


def _section(title: str) -> str:
    source = RULES_FILE.read_text(encoding="utf-8")
    pattern = (
        rf"^## {re.escape(title)}(?:[ \t]+–[^\n]*)?[ \t]*$\n"
        r"(.*?)(?=^## |\Z)"
    )
    match = re.search(pattern, source, re.MULTILINE | re.DOTALL)

    if not match:
        raise ValueError(f"Wächterregel '{title}' fehlt.")

    return match.group(1).strip()


def for_station(station_id: int) -> dict[str, str | int]:
    if station_id not in range(1, 13):
        raise ValueError("station_id muss zwischen 1 und 12 liegen.")

    return {
        "file": "guardian_rules.md",
        "global": _section("Global"),
        "station_id": station_id,
        "station": _section(f"Station {station_id:02d}"),
    }


def chat_context(station_id: int) -> list[dict[str, str]]:
    rules = for_station(station_id)

    return [
        {
            "role": "system",
            "content": "Du arbeitest in der SECBrain Watcher App. "
            f"Der aktuelle KI-Lauf befindet sich verbindlich in Station {station_id:02d}. "
            "Bleibe bei dieser Station und führe keine Vault-Änderungen selbst aus.",
        },
        {
            "role": "system",
            "content": "Verbindliche globale SECBrain-Wächterregeln:\n"
            + str(rules["global"]),
        },
        {
            "role": "system",
            "content": "Zusätzliche verbindliche Wächterregel für "
            f"Station {station_id:02d}:\n{rules['station']}",
        },
    ]


def free_chat_context() -> list[dict[str, str]]:
    """Guardrails for chat that is explicitly independent from the Loop."""

    return [
        {
            "role": "system",
            "content": "Du arbeitest im freien SECBrain Chat. Dieser Chat ist von den "
            "12 Pflege-Loop-Stationen vollständig getrennt: Er startet, beendet oder "
            "verschiebt keine Station und führt keine Vault-Änderung aus.",
        },
        {
            "role": "system",
            "content": "Verbindliche globale SECBrain-Wächterregeln:\n" + _section("Global"),
        },
    ]
