# SecBrainDashboard

Gemeinsamer Kontext für alle Claude-Sessions auf allen Geräten
(MacBook, KI-Server, Handy, Cloud).

## Zweck
Eigenes Dashboard, das alles Alltägliche an einem Ort bündelt.
Bestehende Programme sind zu starr, man muss Werte in vielen Tools nachschlagen.

Anforderungen:
- Die Übersicht ist frei gestaltbar (Anordnung und Inhalte bestimmt der Nutzer).
- Auf allen Geräten (MacBook, KI-Server, Handy) derselbe Datenstand, ohne Unterschiede.
  Das muss bei der Wahl des Tech-Stacks (zentrale Datenhaltung, mobile Nutzbarkeit) berücksichtigt werden.

Betrieb:
- Das Dashboard wird auf dem NAS im Heimnetzwerk aufgebaut und betrieben.
- Auf dem NAS wird ein neuer Vault als Second Brain des Projekts aufgesetzt. Er hat nichts mit dem alten Projekt SecVault zu tun; dessen Stand wird bewusst nicht berücksichtigt.
- Cloud-Sessions haben keinen Zugriff auf das NAS. Der neue Vault besteht aus Markdown-Dateien. Ordnerstruktur und Konventionen sind noch nicht festgelegt und dürfen nicht angenommen werden.
- Erste Ausbaustufe nur im Heimnetz, mobiler Zugriff von unterwegs kommt später.

NAS-Details (Synology DS1821+, Docker, Stolpersteine): `docs/nas.md`.

Weitere Details und Status siehe `README.md`.

## Struktur
- `src/` Anwendungscode
- `tests/` automatisierte Tests
- `scripts/` Hilfs- und Build-Skripte
- `docs/` Dokumentation, Entscheidungen und Übergabe-Notizen

## Arbeitsregeln
- GitHub (`traderreality/secbraindashboard`) ist die einzige Quelle der Wahrheit.
- Vor jeder Session `git pull`, nach jeder Session committen und pushen.
- Cloud-Sessions arbeiten auf `claude/...`-Branches und kommen per Pull Request nach `main`.
- Aktuellen Stand und nächste Schritte in `docs/uebergabe.md` pflegen.
- Getroffene Entscheidungen in `docs/entscheidungen.md` festhalten.
- Geheimnisse (Tokens, Passwörter, `.env`-Dateien) niemals committen.
- Sprache: Deutsch.
