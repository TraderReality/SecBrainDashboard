# SecBrainDashboard

Gemeinsamer Kontext für alle Claude-Sessions auf allen Geräten
(MacBook, KI-Server, Handy, Cloud).

## Zweck
SECBrain Watcher bündelt Vault-Analyse, Wissenspflege, Recherche und lokale KI
in einer auf dem NAS betriebenen Web-App.

Anforderungen:
- Die Übersicht ist frei gestaltbar (Anordnung und Inhalte bestimmt der Nutzer).
- Auf allen Geräten (MacBook, KI-Server, Handy) derselbe Datenstand, ohne Unterschiede.
  Das muss bei der Wahl des Tech-Stacks (zentrale Datenhaltung, mobile Nutzbarkeit) berücksichtigt werden.

Betrieb:
- Das Dashboard wird auf dem NAS im Heimnetzwerk aufgebaut und betrieben.
- Vault- und Laufzeitdaten werden außerhalb dieses Repositorys als Mounts
  bereitgestellt und niemals eingecheckt.
- Cloud-Sessions haben keinen Zugriff auf das NAS.
- Erste Ausbaustufe nur im Heimnetz, mobiler Zugriff von unterwegs kommt später.

NAS-Details (Synology DS1821+, Docker, Stolpersteine): `docs/nas.md`.

Weitere Details und Status siehe `README.md`.

## Struktur
- `dashboard/` Anwendungscode und automatisierte Tests
- `deploy/synology/` Container- und Compose-Definitionen
- `scripts/` Hilfs- und Build-Skripte
- `docs/` Dokumentation, Entscheidungen und Übergabe-Notizen

## Arbeitsregeln
- GitHub (`traderreality/secbraindashboard`) ist die einzige Quelle der Wahrheit.
- Vor jeder Session `git pull`, nach jeder Session committen und pushen.
- Änderungen arbeiten auf eigenen Feature-Branches und kommen per Pull Request nach `main`.
- Aktuellen Stand und nächste Schritte in `docs/uebergabe.md` pflegen.
- Getroffene Entscheidungen in `docs/entscheidungen.md` festhalten.
- Geheimnisse (Tokens, Passwörter, `.env`-Dateien) niemals committen.
- Vaults, QMD-Indizes, Laufzeitdaten, Backups und Build-Abhängigkeiten niemals
  committen.
- Änderungen am Deployment zuerst auf dem isolierten Dev-Profil prüfen;
  NAS-Main weder stillschweigend umbauen noch neu deployen.
- Sprache: Deutsch.
