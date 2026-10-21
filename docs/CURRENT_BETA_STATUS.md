# SecBrain Watcher — aktueller Beta-Stand

**Stand:** 24. August 2026

**Betriebsart:** lokal, kontrolliert schreibend, Ollama-gestützt

**Status:** funktionierende Beta

## Produktgrenze

Der Watcher ist eine eigenständige Anwendung. Das frühere SecBrain Dashboard
ist keine Laufzeitabhängigkeit mehr. Die Vault liegt außerhalb des
Watcher-Repositories; der Watcher speichert sie nicht im eigenen Git.

## Verifizierter Umfang

- Dashboard, Ollama-Chat und visualisierter 12-Stationen-Loop
- menschliche Freigabe oder Ablehnung an Station 06
- deterministische Übernahme einschließlich Indexer, Qualitätsprüfung,
  Vault-Log und Abschluss-Commit
- Wissensradar mit offenen und recherchierten Themen, kontrollierter Recherche,
  lokaler KI-Auswertung, Diff-Vorschlag und Station-06-Übergabe
- Radar-Zeitplan mit Themenbudget, Quellen-Hashes und Recherchehistorie
- Upload/DokuLader für Markdown, URLs, PDF und Paketimporte
- Regelwerk-Ansicht und gesicherter `AGENTS.md`-Editor
- Vault Explorer mit 2D-Fallback, WebGL-/Three.js-Modell und Atlas-Editor

## Schreibgrenzen

| Aktion | Ziel | Schutz |
| --- | --- | --- |
| Upload | `01 Inbox` | Dateityp, UTF-8, Größe und Zielpfad geprüft |
| DokuLader | `01 Inbox` | Limits, Dublettenprüfung, Manifest, atomare Ablage |
| Regelwerk | `AGENTS.md` | explizite Aktion und Zeitstempel-Backup |
| Loop | Archiv, Quelle, Log | Snapshot, Station 06, Ziele, Indexer, Commit |
| Wissensradar | Zielseite, Log | Hashes, Station 06, atomarer Replace, Indexer, Commit |

Chat, Loop und Radar besitzen getrennte Sitzungen. Eine Chatnachricht darf
weder Loop noch Radar fortschalten.

## Loop-Ablauf

Stationen 01–05 erhalten nur tatsächlich gelesene Inbox- und Vault-Inhalte.
Die KI liefert Arbeitsnotizen, führt aber keine Aktionen aus. Station 06 wartet
auf den Menschen. Nach Freigabe übernimmt Code die Stationen 07–12:

1. Inhalt übernehmen,
2. Index neu erzeugen,
3. Verlinkungen berücksichtigen,
4. Snapshot/Hash und Ziele prüfen,
5. Vault-Log ergänzen,
6. Abschluss berichten und committen.

Ein Lauf verweigert den Start, wenn außerhalb von `01 Inbox` ungesicherte
Vault-Änderungen bestehen.
Unfreigegebene Loop-Vorschläge liegen im getrennten Watcher-State unter
`loop-proposals/`. Bei Ablehnung bleibt die Vault unverändert; erst nach
Freigabe wird eine Kopie des Vorschlags mit den übernommenen Quellen im Vault
protokolliert.

## Wissensradar

Der Radar arbeitet in vier sichtbaren Phasen plus Übergabe:

1. Wissenslücken erkennen,
2. Quellen recherchieren und mit der Vault vergleichen,
3. Zielseite, Markdown-Diff, Wikilinks, Vertrauen und Konflikte vorschlagen,
4. recherchierte Themen wiederkehrend pflegen,
5. Vorschlag an Station 06 übergeben.

Recherche liegt temporär unter `/tmp/secbrain-watcher/research`. Zeitplan und
Historie liegen unter `~/.local/state/secbrain-watcher/knowledge-radar` oder im
per `SECBRAIN_WATCHER_STATE_DIR` gesetzten Verzeichnis.

## 3D-Graph

`vault-graph-3d.js` bleibt der Einstieg, delegiert aber Daten, Szene,
Atlasdarstellung, Editor, Interaktionen und Effekte an eigenständige Module.
Die Funktionen wurden dabei nicht neu geschrieben.

## Aktuelle Verifikation

- Python: 43 Tests und 3 Subtests bestanden
- JavaScript: Syntaxprüfung aller Frontendmodule bestanden
- Live-API: Status, Graph, Ollama, Loop und Wissensradar mit HTTP 200
- Git: gesamter Produktstand erfasst, keine unversionierten Produktdateien
- Diff: keine Whitespace- oder Patchfehler

## Offene Arbeiten

1. Browser-End-to-End-Tests für Loop, Radar, Upload und 3D-Graph ergänzen.
2. Backend-Routen, Atlas-Modul und CSS weiter modularisieren.
3. Historische R18–R33-Kompatibilitätsmetadaten später kontrolliert ablösen.

Die alte Planung ist unter
[`archive/R18-R33_LEGACY_ROADMAP.md`](archive/R18-R33_LEGACY_ROADMAP.md)
archiviert und kein aktueller Produktvertrag.
