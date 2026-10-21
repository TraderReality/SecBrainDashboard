# SecBrain Watcher — Roadmap

**Stand:** 24. August 2026

Die funktionierende Beta besitzt Dashboard, 12-Stationen-Loop,
Wissensradar, DokuLader und 3D-Vault-Explorer. Die aktuelle Struktur bleibt
erhalten; weitere Arbeiten erfolgen in kleinen, prüfbaren Schritten.

## Nächste Schritte

1. Laufende UI-Bereinigung und Strukturverbesserungen abschließen.
2. Sichtbare QMD-Kontextanzeige für Chat, Loop und Wissensradar umsetzen:
   - gelesene Vault-Seiten mit Pfad anzeigen,
   - Relevanz und verwendete Textauszüge transparent machen,
   - getrennte Quellenanzeigen für Chat-, Loop- und Radar-Sitzung,
   - weiterhin ausschließlich lesender Zugriff ohne Vault-Änderung.
3. Browser-End-to-End-Tests für Loop, Radar, Upload und 3D-Graph ergänzen.
4. Backend-Routen nach Fachbereich trennen, ohne API-Verträge zu ändern.
5. Atlas nach Geometrie, Persistenz und Editorinteraktion weiter trennen.
6. Doppelte CSS-Regeln kontrolliert in Komponenten-Styles überführen.
7. Frühere R18–R33-Kompatibilitätsfelder dokumentiert ablösen.

## Qualitätsregeln

- keine Struktur- oder Funktionsänderung ohne passenden Test,
- Chat, Loop und Wissensradar bleiben getrennte Sitzungen,
- keine Vault-Änderung ohne sichtbare Freigabe,
- abgeleitete Daten werden nie zur zweiten Quelle der Wahrheit,
- lokale und kontrollierbare Komponenten haben Vorrang.

Die frühere Planung ist unter
[`archive/R18-R33_LEGACY_ROADMAP.md`](archive/R18-R33_LEGACY_ROADMAP.md)
unverändert als Referenz archiviert.
