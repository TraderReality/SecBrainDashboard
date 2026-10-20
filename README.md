# SecBrainDashboard

Ein eigenes Dashboard, das alles bündelt, was im Alltag zu erledigen ist.

## Zweck

- Alles Alltägliche an einem Ort, statt Werte in vielen getrennten Programmen nachzuschlagen.
- Die Übersicht ist frei gestaltbar: Ich bestimme selbst, was wo angezeigt wird.
- Gleicher Stand auf allen Geräten (MacBook, KI-Server, Handy), ohne Unterschiede.

Betrieb: Das Dashboard läuft auf dem NAS im Heimnetzwerk. Auf dem NAS wird ein neuer Vault als Second Brain des Projekts aufgesetzt (unabhängig vom alten Projekt SecVault).

Status: Konzeptphase, Tech-Stack noch nicht festgelegt.

## Projektstruktur

```
SecBrainDashboard/
├── docs/       Dokumentation: Architektur, Entscheidungen, Betrieb
├── src/        Anwendungscode
├── tests/      Automatisierte Tests
├── scripts/    Hilfs- und Build-Skripte
├── README.md   Diese Datei
└── .gitignore  Vom Git ausgeschlossene Dateien
```

## Erste Schritte

> Platzhalter: Voraussetzungen, Installation und Startbefehl ergänzen,
> sobald der Tech-Stack feststeht.

## Entwicklung

- Änderungen auf einem eigenen Branch entwickeln und per Pull Request einbringen.
- Geheimnisse (Tokens, Passwörter, `.env`-Dateien) niemals committen.

## Arbeiten auf mehreren Geräten

- Das GitHub-Repo ist die einzige Quelle der Wahrheit für MacBook, KI-Server, Handy und Cloud-Sessions.
- Vor jeder Session `git pull`, nach jeder Session committen und pushen.
- Kontext für Claude steht in `CLAUDE.md`, Stand und nächste Schritte in `docs/uebergabe.md`.
- Chats in einem claude.ai-Projekt und Cloud-Sessions sind über den Account auf allen Geräten sichtbar. Lokale Sessions auf Mac oder Server sind es nicht, sie werden nur über Git abgeglichen.

## Lizenz

> Platzhalter: Lizenz festlegen.
