# SecBrainDashboard

SecBrainDashboard enthält den migrierten **SECBrain Watcher**: eine lokale
Weboberfläche für Analyse, Recherche, Visualisierung und kontrollierte Pflege
einer Markdown-Vault. Die Anwendung kombiniert ein FastAPI-Backend, ein
statisches JavaScript-Frontend, Ollama und eine read-only QMD-Suchschicht.

## Status

Der importierte Anwendungsstand stammt aus dem für NAS-Main gebauten
Migrations-Staging vom 21. Oktober 2026. Produktiv läuft dieser Stand auf einer
Synology DS1821+ im Heimnetz. Dieses Repository enthält Quellcode, Tests und
Deployment-Definitionen, aber keine Vault-, Index-, Laufzeit- oder
Sicherungsdaten und keine `.env`-Dateien.

## Struktur

```text
dashboard/          FastAPI-Backend, Frontend und Tests
deploy/synology/    Container-Build, Compose und QMD-Initialisierung
desktop/            Desktop-Starter-Vorlage
docs/               Architektur, Betrieb, Entscheidungen und Übergabe
scripts/            lokale Start- und Installationshilfen
tools/              Generatoren für Architekturartefakte
```

## Lokale Entwicklung

Voraussetzungen: Python 3.12, Node.js für die JavaScript-Syntaxprüfung und
optional QMD 2.8.3 für eine echte Retrieval-Prüfung.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
find dashboard/frontend -name '*.js' -print0 | xargs -0 -n1 node --check
```

Der Backend-Start für einen isolierten lokalen Test:

```bash
SECBRAIN_VAULT_PATH=/pfad/zu/einer/test-vault \
SECBRAIN_WATCHER_REPOSITORY="$PWD" \
.venv/bin/python -m uvicorn dashboard_api:app \
  --app-dir dashboard/backend --host 127.0.0.1 --port 8011
```

Konfiguration wird ausschließlich über die dokumentierten Umgebungsvariablen
bereitgestellt. Lokale `.env`-Dateien bleiben außerhalb von Git.

## Synology-Deployment

Das Image unter `deploy/synology/` enthält Python 3.12 und die gepinnte
QMD-Version 2.8.3 auf Node.js 22. Beim Containerstart wird eine eigene
QMD-Kollektion für den gemounteten Vault angelegt oder aktualisiert. Der Index
liegt im jeweiligen State-Volume; Main und Dev teilen weder Vault noch Index.

Die Compose-Konfiguration besitzt getrennte Profile. Das Main-Profil stellt
einen HTTPS-Proxy mit lokaler Zertifizierungsstelle auf der NAS-IP bereit; der
direkte App-Port ist auf NAS-Loopback begrenzt. Änderungen werden zuerst
mit dem Dev-Profil und einer separaten Vault-Kopie geprüft. Details und die
benötigten Variablennamen stehen in [deploy/synology/README.md](deploy/synology/README.md).

## Sicherheitsmodell

- Vault und State sind die einzigen beschreibbaren Mounts.
- Der Quellbaum und das Container-Root-Dateisystem sind schreibgeschützt.
- Linux-Capabilities der App sind entfernt; `no-new-privileges` ist aktiv. Der
  HTTPS-Proxy besitzt nur `NET_BIND_SERVICE`, das sein Image zum Start braucht.
- Das Compose-Deployment verlangt getrennte Main-/Dev-Zugangsdaten. HTTP Basic
  schützt Oberfläche und API; nur `/healthz` ist ohne Anmeldung erreichbar.
- Für Main muss das lokale CA-Stammzertifikat auf jedem Client geprüft und
  vertraut werden, bevor Zugangsdaten über HTTPS verwendet werden.
- KI-Antworten führen keine Dateisystem- oder Git-Aktionen selbst aus.
- Schreibende Watcher-Abläufe erfordern weiterhin die fachliche Freigabestufe.
- Geheimnisse, `.env`-Dateien, Vaults, QMD-Indizes und Backups werden nicht
  versioniert.

Weitere technische Details stehen in [docs/README.md](docs/README.md) und der
aktuelle Übergabestand in [docs/uebergabe.md](docs/uebergabe.md).
