#!/usr/bin/env python3
"""
SecBrain Indexer
=================
Scannt die Vault nach Markdown-Dateien, extrahiert Frontmatter und Wikilinks,
und erzeugt die abgeleiteten Sichten:

In der Vault (08 KI-Wissensbank/_index/):
  - graph.json        (Nodes + Edges)
  - search_index.json (Volltext + Metadaten je Datei)
  - statistics.json   (Statistiken)
  - qmd-manifest.json (Brücke Dateipfad ↔ Kennung für die qmd-Suchschicht)
  - cache/
      metadaten.json  (alle Metadaten)
      wikilinks.json  (alle Links)
      broken-links.json
      waisen.json

Danach wird die qmd-Kollektion aufgefrischt (siehe qmd_auffrischen), damit
Vault-Loop und qmd-Loop denselben Stand haben. Reihenfolge ist bindend:
Vault lesen → Vault-Sichten → qmd. Alles aus einem Lauf,
mit einem Zeitstempel.

Grundsatz: Markdown ist die einzige Wahrheit (CLAUDE.md, Grundregel 1).
Alle hier erzeugten Dateien sind abgeleitete Sichten und jederzeit
löschbar und neu erzeugbar. Der Indexer schreibt niemals in eine
Inhaltsdatei der Vault.

Kennungen folgen AGENTS.md, Abschnitt 4 („Kennungen bilden"): die `id` aus
dem Frontmatter ist der Schlüssel, der Index und Graph zusammenhält.

Paket-Fallback: aus der vom Nutzer bereitgestellten lesbaren Quelle
`/Volumes/Local/Neuer Ordner/indexer.py` (Stand 2026-08-23) übernommen.
SHA-256 der unveränderten Quelle:
942b64b09be886062102843d3633e09eced2bbc94c45f0bff3519ea5aa66312d
Anpassungen: Scanner-Berichte explizit aus den abgeleiteten Sichten
ausschließen; neue QMD-Kollektionen auf Markdown begrenzen; Quellen und
Ausgaben ohne Symlink-Folgen mit Identitäts- und Inhaltsprüfung öffnen. Die externe
Quelldatei wurde nicht verändert; vorhandene Vault-Indexer haben Vorrang.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
import sys
import unicodedata
from datetime import datetime, date
from pathlib import Path

# The Watcher invokes this package file directly, not with ``python -m``.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scanner.inventory import _open_root, _DIRECTORY_FLAGS, _signature, _current_stat
from scanner.safe_files import FileState, _read_at, file_state, mutate_file

try:
    import yaml
except ImportError:
    print("Fehler: PyYAML nicht installiert. Installiere es: pip install pyyaml")
    sys.exit(1)

VAULT_ROOT = Path(
    os.environ.get("SECBRAIN_VAULT", "/home/secbrain/Dokumente/SecBrain")
)
OUTPUT_DIR = VAULT_ROOT / "08 KI-Wissensbank" / "_index"
CACHE_DIR = OUTPUT_DIR / "cache"
GRAPH_FILE = OUTPUT_DIR / "graph.json"
SEARCH_INDEX_FILE = OUTPUT_DIR / "search_index.json"
STATS_FILE = OUTPUT_DIR / "statistics.json"
QMD_MANIFEST_FILE = OUTPUT_DIR / "qmd-manifest.json"
META_CACHE_FILE = CACHE_DIR / "metadaten.json"
LINKS_CACHE_FILE = CACHE_DIR / "wikilinks.json"
BROKEN_LINKS_FILE = CACHE_DIR / "broken-links.json"
WAISEN_FILE = CACHE_DIR / "waisen.json"

# Ausschlüsse
EXCLUDE_DIRS = {"_Vorschlaege", ".git", ".cptr", ".obsidian", "node_modules", "07 Anhänge"}
EXCLUDE_RELATIVE_DIRS = {Path("09 Werkzeuge/Scanner-Berichte")}
EXCLUDE_PREFIX = "_"

WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|(.*?))?\]\]")

# Name der qmd-Kollektion, unter der die Vault dort geführt wird.
QMD_COLLECTION = os.environ.get("SECBRAIN_QMD_COLLECTION", "secbrain")

# Umlaute und ß werden ausgeschrieben, bevor der Rest transliteriert wird.
UMLAUT_MAP = {
    "ä": "ae",
    "ö": "oe",
    "ü": "ue",
    "Ä": "ae",
    "Ö": "oe",
    "Ü": "ue",
    "ß": "ss",
}


class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        return super().default(obj)


def normalize_id(raw_id: str) -> str:
    """Bildet eine Kennung nach AGENTS.md, Abschnitt 4.

    Kleinbuchstaben, Umlaute ausgeschrieben (ä → ae), Leerzeichen zu
    Bindestrichen, Sonderzeichen entfallen. Aus `Über mich` wird `ueber-mich`.

    Zusätzlich robust gegen Wikilink-Schreibweisen: ein Anker (`Seite#Kapitel`)
    und ein Pfadanteil (`04 Ressourcen/Thema`) werden abgeschnitten, eine
    `.md`-Endung entfällt.
    """
    text = raw_id.strip()

    # Anker und Pfadanteile aus Wikilinks entfernen.
    text = text.split("#", 1)[0]
    text = text.split("/")[-1]
    if text.lower().endswith(".md"):
        text = text[:-3]

    # Umlaute ausschreiben, bevor unicodedata sie zu nackten Vokalen abbaut.
    for src, dst in UMLAUT_MAP.items():
        text = text.replace(src, dst)

    text = text.lower()

    # Restliche diakritische Zeichen abbauen (é → e).
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))

    # Alles, was kein Buchstabe, keine Ziffer und kein Bindestrich ist,
    # wird zum Trenner. Damit entfallen &, —, ., ( ) usw.
    text = re.sub(r"[^a-z0-9]+", "-", text)

    # Mehrfache Trenner verdichten, Ränder säubern.
    text = re.sub(r"-{2,}", "-", text).strip("-")

    return text


def qmd_uri(rel_path: str) -> str:
    """Bildet den Pfad auf die Adresse ab, unter der qmd dieselbe Datei führt.

    qmd formt jeden Pfadabschnitt um: alles außer Buchstaben und Ziffern wird
    zum Trenner, Mehrfachtrenner werden verdichtet, Ränder fallen weg. Umlaute
    bleiben erhalten. Die Endung `.md` bleibt unangetastet.

        04 Ressourcen/KI & Autonome Agentensysteme/KI & Autonome Agentensysteme.md
        → 04-Ressourcen/KI-Autonome-Agentensysteme/KI-Autonome-Agentensysteme.md

    Diese Abbildung ist der Verbindungsschlüssel zwischen Suche und Graph:
    qmd liefert im JSON das Feld `file` als `qmd://<kollektion>/<pfad>`, und
    darüber findet ein Treffer seinen Knoten.

    Geprüft am 2026-08-16 gegen alle 37 von qmd indexierten Dateien der Vault —
    alle 37 exakt reproduziert.
    """
    segmente = []
    for segment in Path(rel_path).parts:
        endung = ""
        if segment.lower().endswith(".md"):
            segment, endung = segment[:-3], ".md"
        segment = re.sub(r"[^0-9A-Za-zÀ-ÖØ-öø-ÿ]+", "-", segment).strip("-")
        segmente.append(segment + endung)
    return "/".join(segmente)


def scan_vault() -> dict[Path, FileState]:
    """Snapshot Markdown through no-follow descriptors, never pathname reads."""
    markdown_files = {}
    signatures = {}
    root_fd = _open_root(VAULT_ROOT)

    def walk(directory, relative):
        before = os.fstat(directory)
        for name in sorted(os.listdir(directory)):
            rel = relative / name
            if name in EXCLUDE_DIRS or rel in EXCLUDE_RELATIVE_DIRS:
                continue
            entry = os.stat(name, dir_fd=directory, follow_symlinks=False)
            if stat.S_ISLNK(entry.st_mode):
                raise RuntimeError(f"Indexer: Symlink ist nicht zulässig: {rel}")
            if stat.S_ISDIR(entry.st_mode):
                child = os.open(name, _DIRECTORY_FLAGS, dir_fd=directory)
                try:
                    if _signature(os.fstat(child)) != _signature(entry):
                        raise RuntimeError(f"Indexer: Verzeichnis wurde verändert: {rel}")
                    walk(child, rel)
                finally:
                    os.close(child)
            elif name.endswith(".md") and not name.startswith(EXCLUDE_PREFIX):
                state = _read_at(directory, name)
                if _signature(os.stat(name, dir_fd=directory, follow_symlinks=False)) != _signature(entry):
                    raise RuntimeError(f"Indexer: Quelle wurde verändert: {rel}")
                markdown_files[VAULT_ROOT / rel] = state
            signatures[rel.as_posix()] = _signature(entry)
        if _signature(os.fstat(directory)) != _signature(before):
            raise RuntimeError("Indexer: Verzeichnis wurde während des Lesens verändert.")

    try:
        walk(root_fd, Path())
        for relative, signature in signatures.items():
            if _signature(_current_stat(root_fd, relative)) != signature:
                raise RuntimeError(f"Indexer: Pfad wurde während des Lesens verändert: {relative}")
        _verify_root(root_fd)
    finally:
        os.close(root_fd)
    return dict(sorted(markdown_files.items()))


def _verify_root(root_fd):
    fresh = _open_root(VAULT_ROOT)
    try:
        original, current = os.fstat(root_fd), os.fstat(fresh)
        if (original.st_dev, original.st_ino) != (current.st_dev, current.st_ino):
            raise RuntimeError("Indexer: Vault-Verzeichnis wurde ersetzt.")
    finally:
        os.close(fresh)


def parse_frontmatter(content: str) -> tuple[dict | None, str]:
    if not content.startswith("---\n"):
        return None, content
    rest = content[4:]
    lines = rest.split("\n")
    closing_line_idx = None
    for i, line in enumerate(lines):
        if line.strip() == "---":
            closing_line_idx = i
            break
    if closing_line_idx is None:
        return None, content
    yaml_block = "\n".join(lines[:closing_line_idx])
    body = "\n".join(lines[closing_line_idx + 1:])
    try:
        metadata = yaml.safe_load(yaml_block)
    except yaml.YAMLError:
        return None, body
    if not isinstance(metadata, dict):
        return None, body
    return metadata, body


FENCE_RE = re.compile(r"^\s*(```|~~~)", re.MULTILINE)


def strip_code(body: str) -> str:
    """Entfernt umschlossene Codeblöcke vor der Linkerkennung.

    Vorlagen in `AGENTS.md` und `KNOWLEDGE_SCHEMA.md` enthalten Platzhalter
    wie `[[Wikilink]]` oder `[[Seite A]]`. Das sind Beispiele, keine Links —
    sie dürfen weder Kanten noch gebrochene Links erzeugen.

    Inline-Code wird bewusst **nicht** entfernt: in dieser Vault ist die
    Schreibweise `` `[[Ziel]]` `` üblich und meint einen echten Link
    (siehe `04 Ressourcen/Loop-Anleitung/So arbeitet der Loop.md`).
    """
    lines = body.split("\n")
    kept = []
    in_fence = False
    fence_marker = ""
    for line in lines:
        match = FENCE_RE.match(line)
        if match:
            marker = match.group(1)
            if not in_fence:
                in_fence = True
                fence_marker = marker
            elif marker == fence_marker:
                in_fence = False
                fence_marker = ""
            continue
        if not in_fence:
            kept.append(line)
    return "\n".join(kept)


def extract_wikilinks(body: str) -> list[tuple[str, str]]:
    # Umschlossene Codeblöcke entfernen, dann ein- und vier-Backtick-Inline-Code
    # neutralisieren. Zusätzlich bekannte Dokumentations-Platzhalter ausblenden,
    # die als Beispiele in Schema-, Wiki- und Audit-Dokumenten vorkommen und
    # keine echten Links sind.
    ALLOWED_PLACEHOLDER_IDS = {
        "Wikilink", "Wikilinks", "Notizentitel", "Note", "_SCHEMA",
        "Quelle A", "Thema A", "Seite A", "Beispiel — erzeugt keine Kante",
        "id-der-anderen-seite",
    }
    body_clean = strip_code(body)
    body_clean = re.sub(r"`[^`]*`", " ", body_clean)
    body_clean = re.sub(r"``[^`]*``", " ", body_clean)
    links = []
    for match in WIKILINK_RE.finditer(body_clean):
        raw_id = match.group(1).strip()
        display = match.group(2).strip() if match.group(2) else raw_id
        if raw_id not in ALLOWED_PLACEHOLDER_IDS:
            links.append((raw_id, display))
    return links


def cluster_and_sub(rel_path: str) -> tuple[str, str]:
    """Cluster ist der oberste Ordner, sub der darunterliegende.

    Dateien auf oberster Ebene (CLAUDE.md, AGENTS.md, INDEX.md) bekommen den
    Cluster `00 Regelwerk`, damit sie im Graphen nicht in einem namenlosen
    Cluster landen.
    """
    parts = Path(rel_path).parts
    if len(parts) == 1:
        return "00 Regelwerk", ""
    cluster = parts[0]
    sub = parts[1] if len(parts) > 2 else ""
    return cluster, sub


def qmd_auffrischen(anzahl_dateien: int) -> dict:
    """Bringt die qmd-Kollektion auf denselben Stand wie der Index.

    Vault-Loop und qmd-Loop teilen sich damit **einen** Auslöser: Station 09
    des Pflege-Loops (AGENTS.md, Abschnitt 2). Der Indexer ist der Taktgeber,
    qmd die Suchschicht darüber. Beide lesen dieselben Markdown-Dateien.

    Steuerung über Umgebungsvariablen:
      SECBRAIN_QMD=0        qmd-Station überspringen
      SECBRAIN_QMD_EMBED=1  zusätzlich `qmd embed` (Vektor-Embeddings) laufen
                            lassen — deutlich langsamer, deshalb nicht Standard
      SECBRAIN_QMD_COLLECTION  Name der Kollektion (Standard: secbrain)

    Scheitert etwas, ist das ein **Fund**, kein Abbruch: der Indexer meldet es
    und läuft regulär weiter (analog Station 09, AGENTS.md Abschnitt 2).
    """
    bericht = {
        "ausgefuehrt": False,
        "grund": None,
        "kollektion": QMD_COLLECTION,
        "schritte": [],
    }

    if os.environ.get("SECBRAIN_QMD", "1").lower() in {"0", "off", "nein"}:
        bericht["grund"] = "per SECBRAIN_QMD abgeschaltet"
        return bericht

    if shutil.which("qmd") is None:
        bericht["grund"] = "qmd ist nicht installiert (nicht im PATH)"
        return bericht

    def lauf(argumente: list[str], zweck: str) -> bool:
        try:
            ergebnis = subprocess.run(
                ["qmd", *argumente],
                capture_output=True,
                text=True,
                timeout=1800,
            )
        except (subprocess.TimeoutExpired, OSError) as fehler:
            bericht["schritte"].append(
                {"zweck": zweck, "ok": False, "meldung": str(fehler)}
            )
            return False

        ok = ergebnis.returncode == 0
        bericht["schritte"].append({
            "zweck": zweck,
            "ok": ok,
            "meldung": (ergebnis.stderr or ergebnis.stdout).strip()[:500],
        })
        return ok

    # Kollektion anlegen, falls sie noch nicht existiert.
    try:
        vorhanden = subprocess.run(
            ["qmd", "collection", "list"],
            capture_output=True, text=True, timeout=120,
        )
        kennt_kollektion = QMD_COLLECTION in (vorhanden.stdout or "")
    except (subprocess.TimeoutExpired, OSError):
        kennt_kollektion = False

    if not kennt_kollektion:
        lauf(
            ["collection", "add", str(VAULT_ROOT), "--name", QMD_COLLECTION, "--mask", "**/*.md"],
            "Kollektion anlegen",
        )

    lauf(["update"], "Index auffrischen")

    if os.environ.get("SECBRAIN_QMD_EMBED", "0").lower() in {"1", "on", "ja"}:
        lauf(["embed"], "Embeddings erzeugen")

    bericht["ausgefuehrt"] = True
    bericht["dateien"] = anzahl_dateien
    return bericht


def build_index() -> None:
    root_fd = _open_root(VAULT_ROOT)
    try:
        _build_index(root_fd)
    finally:
        os.close(root_fd)


def _build_index(root_fd) -> None:
    print("SecBrain Indexer — Start")
    print(f"Vault:     {VAULT_ROOT}")

    outputs = (GRAPH_FILE, SEARCH_INDEX_FILE, STATS_FILE, META_CACHE_FILE,
               QMD_MANIFEST_FILE, LINKS_CACHE_FILE, BROKEN_LINKS_FILE, WAISEN_FILE)
    output_states = {path: file_state(path) for path in outputs}
    markdown_files = scan_vault()

    def verify_sources():
        _verify_root(root_fd)
        for path, expected in markdown_files.items():
            if file_state(path) != expected:
                raise RuntimeError(f"Indexer: Quelle wurde seit dem Lesen verändert: {path}")

    print(f"\nGefundene Dateien zum Indexieren: {len(markdown_files)}")
    for f in markdown_files:
        print(f"  - {f.relative_to(VAULT_ROOT)}")

    all_metadata: dict[str, dict] = {}
    all_links: dict[str, list[str]] = {}
    ohne_frontmatter: list[str] = []

    # --- Durchgang 1: Metadaten und Kennungen -------------------------------

    for file_path in markdown_files:
        rel_path = str(file_path.relative_to(VAULT_ROOT))
        # Match the former read_text() universal-newline behavior for parsing.
        # Keep the original FileState bytes unchanged for identity/content checks.
        content = markdown_files[file_path].data.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
        metadata, body = parse_frontmatter(content)

        if metadata is None:
            ohne_frontmatter.append(rel_path)
            metadata = {}

        # Die Kennung kommt aus dem Frontmatter. Fehlt sie, wird sie aus dem
        # Dateinamen abgeleitet — nach denselben Regeln, damit Links greifen.
        raw_key = metadata.get("id") or normalize_id(file_path.stem)
        key = str(raw_key).strip()

        # Kollisionen bekommen einen Zähler (AGENTS.md, Abschnitt 4).
        if key in all_metadata:
            counter = 2
            while f"{key}-{counter}" in all_metadata:
                counter += 1
            print(
                f"  ! Kennung '{key}' doppelt vergeben "
                f"({rel_path}) → '{key}-{counter}'"
            )
            key = f"{key}-{counter}"

        cluster, sub = cluster_and_sub(rel_path)

        titel = metadata.get("titel") or file_path.stem
        if isinstance(titel, (datetime, date)):
            titel = titel.isoformat()
        titel = str(titel)

        all_metadata[key] = {
            "id": key,
            "typ": metadata.get("typ", "unknown"),
            "titel": titel,
            "status": metadata.get("status", "entwurf"),
            "erstellt": metadata.get("erstellt"),
            "geaendert": metadata.get("geaendert"),
            "tags": metadata.get("tags") or [],
            "quelle": metadata.get("quelle"),
            "pfad": rel_path,
            "dateiname": file_path.stem,
            "cluster": cluster,
            "sub": sub,
            "bytes": len(markdown_files[file_path].data),
            "korpus": body,
            "hat_frontmatter": bool(metadata),
        }

        all_links[key] = [link[0] for link in extract_wikilinks(body)]

    # --- Auflösungstabelle --------------------------------------------------
    #
    # Ein Wikilink darf auf drei Arten geschrieben sein:
    #   [[ueber-mich]]   — die Kennung selbst
    #   [[Über mich]]    — der Titel
    #   [[Über mich.md]] — der Dateiname
    # Alle drei werden über die normalisierte Form aufgelöst.

    resolution: dict[str, str] = {}

    def register(alias, target_key: str) -> None:
        if alias is None:
            return
        if isinstance(alias, (datetime, date)):
            alias = alias.isoformat()
        norm = normalize_id(str(alias))
        if norm and norm not in resolution:
            resolution[norm] = target_key

    for key, meta in all_metadata.items():
        register(key, key)
    for key, meta in all_metadata.items():
        register(meta["titel"], key)
        register(meta["dateiname"], key)

    # --- Durchgang 2: Kanten ------------------------------------------------

    edges: list[dict] = []
    broken_links_map: dict[str, list[str]] = {}
    outgoing_map: dict[str, list[str]] = {}

    for key in all_metadata:
        raw_targets = all_links.get(key, [])
        resolved: list[str] = []
        broken: list[str] = []

        for raw in raw_targets:
            target = resolution.get(normalize_id(raw))
            if target is None:
                broken.append(raw)
            elif target != key:  # Selbstlinks erzeugen keine Kante
                resolved.append(target)

        # Doppelte Kanten zwischen denselben zwei Seiten einmal zählen.
        seen = set()
        unique_resolved = []
        for target in resolved:
            if target not in seen:
                seen.add(target)
                unique_resolved.append(target)

        outgoing_map[key] = unique_resolved
        broken_links_map[key] = broken

        for target in unique_resolved:
            edges.append({"from": key, "to": target, "typ": "wikilink"})

    # --- Grad, Fremdcluster, Waisen ----------------------------------------

    grad: dict[str, int] = {key: 0 for key in all_metadata}
    fremdcluster: dict[str, int] = {key: 0 for key in all_metadata}

    for edge in edges:
        grad[edge["from"]] += 1
        grad[edge["to"]] += 1
        if (
            all_metadata[edge["from"]]["cluster"]
            != all_metadata[edge["to"]]["cluster"]
        ):
            fremdcluster[edge["from"]] += 1
            fremdcluster[edge["to"]] += 1

    # Waisen: Knoten ohne jede Verbindung. Daily Notes (typ: daily) und
    # Systemdateien (typ: system) sind bewusst ohne eingehende Links —
    # sie sind Protokoll bzw. Steuerung, kein Wissen. Sie werden nicht als
    # Waisen gemeldet. Siehe AGENTS.md, Abschnitt 11, Ausschlussliste.
    waisen = sorted(
        key for key, meta in all_metadata.items()
        if grad[key] == 0 and meta.get("typ") not in ("daily", "system")
    )

    # --- Vault-Sichten ------------------------------------------------------

    nodes = []
    for key, meta in all_metadata.items():
        nodes.append({
            "id": key,
            "typ": meta["typ"],
            "titel": meta["titel"],
            "status": meta["status"],
            "pfad": meta["pfad"],
            "cluster": meta["cluster"],
            "sub": meta["sub"],
            "erstellt": meta["erstellt"],
            "geaendert": meta["geaendert"],
            "tags": meta["tags"],
            "quelle": meta["quelle"],
            "outgoing_links": outgoing_map[key],
            "grad": grad[key],
            "fremdcluster": fremdcluster[key],
        })

    timestamp = datetime.now().isoformat()

    graph = {
        "timestamp": timestamp,
        "vault_root": str(VAULT_ROOT),
        "dateien_gesamt": len(markdown_files),
        "dateien_indexiert": len(nodes),
        "nodes": nodes,
        "edges": edges,
        "self_links": [e for e in edges if e["from"] == e["to"]],
    }

    search_index = {
        "timestamp": timestamp,
        "dateien": [
            {
                "id": key,
                "titel": meta["titel"],
                "typ": meta["typ"],
                "status": meta["status"],
                "tags": meta["tags"],
                "pfad": meta["pfad"],
                "erstellt": meta["erstellt"],
                "geaendert": meta["geaendert"],
                "text": meta["korpus"][:50000],
            }
            for key, meta in all_metadata.items()
        ],
    }

    typ_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    tag_counts: dict[str, int] = {}
    for node in nodes:
        typ_counts[node["typ"]] = typ_counts.get(node["typ"], 0) + 1
        status_counts[node["status"]] = status_counts.get(node["status"], 0) + 1
        for tag in node["tags"]:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1

    broken_gesamt = sum(len(v) for v in broken_links_map.values())

    stats = {
        "timestamp": timestamp,
        "dateien_gesamt": len(markdown_files),
        "dateien_indexiert": len(nodes),
        "typen": typ_counts,
        "status": status_counts,
        "tags": tag_counts,
        "broken_links": broken_gesamt,
        "broken_links_details": {
            k: v for k, v in broken_links_map.items() if v
        },
        "ohne_frontmatter": ohne_frontmatter,
        "ohne_frontmatter_anzahl": len(ohne_frontmatter),
        "waisen": waisen,
        "waisen_anzahl": len(waisen),
        "relationen_gesamt": len(edges),
        "forward_links": len(edges),
        "backward_links": len(edges),
    }

    # qmd arbeitet auf Dateipfaden, der Graph auf Kennungen. Das Manifest ist
    # die Brücke: ein qmd-Treffer lässt sich damit auf genau einen Knoten des
    # Graphen abbilden — und umgekehrt.
    pfad_zu_id = {meta["pfad"]: key for key, meta in all_metadata.items()}

    # qmd liefert Treffer als `qmd://<kollektion>/<umgeformter pfad>`. Diese
    # Tabelle übersetzt eine solche Adresse zurück in eine Kennung — damit
    # zeigt ein Suchtreffer auf genau einen Knoten des Graphen.
    uri_zu_id = {
        f"qmd://{QMD_COLLECTION}/{qmd_uri(meta['pfad'])}": key
        for key, meta in all_metadata.items()
    }

    qmd_manifest = {
        "generated": timestamp,
        "vault_root": str(VAULT_ROOT),
        "kollektion": QMD_COLLECTION,
        "dokumente_gesamt": len(all_metadata),
        "pfad_zu_id": pfad_zu_id,
        "uri_zu_id": uri_zu_id,
        "dokumente": [
            {
                "id": key,
                "pfad": meta["pfad"],
                "absolut": str(VAULT_ROOT / meta["pfad"]),
                "qmd_uri": f"qmd://{QMD_COLLECTION}/{qmd_uri(meta['pfad'])}",
                "titel": meta["titel"],
                "typ": meta["typ"],
                "status": meta["status"],
                "cluster": meta["cluster"],
                "sub": meta["sub"],
                "tags": meta["tags"],
            }
            for key, meta in all_metadata.items()
        ],
    }

    # --- Schreiben ----------------------------------------------------------

    def write_json(path: Path, data: object) -> None:
        _verify_root(root_fd)
        content = json.dumps(data, indent=2, ensure_ascii=False, cls=CustomJSONEncoder).encode("utf-8")
        installed = mutate_file(path, content, output_states[path])
        # Reopen from the named Vault: a replaced parent must not be accepted
        # merely because the original directory descriptor remained writable.
        _verify_root(root_fd)
        if file_state(path) != installed:
            raise RuntimeError(f"Indexer: Ausgabepfad wurde ersetzt: {path}")
        output_states[path] = installed
        print(f"  Geschrieben: {path}")

    verify_sources()
    print("\nVault-Sichten:")
    write_json(GRAPH_FILE, graph)
    write_json(SEARCH_INDEX_FILE, search_index)
    write_json(STATS_FILE, stats)
    write_json(META_CACHE_FILE, {
        k: {kk: vv for kk, vv in v.items() if kk != "korpus"} | {"korpus": v["korpus"]}
        for k, v in all_metadata.items()
    })
    write_json(QMD_MANIFEST_FILE, qmd_manifest)
    write_json(LINKS_CACHE_FILE, all_links)
    write_json(BROKEN_LINKS_FILE, broken_links_map)
    write_json(WAISEN_FILE, waisen)

    # --- qmd-Station --------------------------------------------------------
    #
    # Reihenfolge ist bindend: erst die Vault-Sichten, dann qmd. Damit kann
    # die Suchschicht nie einen Stand kennen,
    # den der Graph noch nicht kennt.

    print("\nqmd-Station:")
    verify_sources()
    qmd_bericht = qmd_auffrischen(len(markdown_files))
    if qmd_bericht["ausgefuehrt"]:
        for schritt in qmd_bericht["schritte"]:
            zeichen = "OK " if schritt["ok"] else "FEHLER"
            print(f"  {zeichen} {schritt['zweck']}")
            if not schritt["ok"] and schritt["meldung"]:
                print(f"       {schritt['meldung']}")
    else:
        print(f"  übersprungen — {qmd_bericht['grund']}")

    stats["qmd"] = qmd_bericht
    write_json(STATS_FILE, stats)
    verify_sources()
    for path, expected in output_states.items():
        if file_state(path) != expected:
            raise RuntimeError(f"Indexer: Ausgabe wurde während des Laufs verändert: {path}")

    # --- Bericht ------------------------------------------------------------

    print("\nIndexer abgeschlossen:")
    print(f"  Dateien indexiert: {len(nodes)}")
    print(f"  Relationen:        {len(edges)}")
    print(f"  Broken Links:      {broken_gesamt}")
    print(f"  Waisen:            {len(waisen)}")
    print(f"  Ohne Frontmatter:  {len(ohne_frontmatter)}")

    if broken_gesamt:
        print("\nGebrochene Links (Ziel existiert nicht in der Vault):")
        for key, links in broken_links_map.items():
            if links:
                print(f"  {key}: {links}")

    if waisen:
        print("\nWaisen (keine eingehende und keine ausgehende Verbindung):")
        for w in waisen:
            print(f"  {w}")

    if ohne_frontmatter:
        print("\nOhne Frontmatter (CLAUDE.md, Grundregel 4):")
        for f in ohne_frontmatter:
            print(f"  {f}")


if __name__ == "__main__":
    build_index()
