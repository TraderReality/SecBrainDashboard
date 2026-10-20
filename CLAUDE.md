# SecBrainDashboard

Gemeinsamer Kontext für alle Claude-Sessions auf allen Geräten
(MacBook, KI-Server, Handy, Cloud).

## Zweck
SecBrainDashboard ist ein Dashboard rund um den SecBrain-Vault.
Details zum Zweck, zur Zielgruppe und zum Status: siehe `README.md`.

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
