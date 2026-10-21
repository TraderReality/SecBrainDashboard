# Entscheidungen

Kurze Einträge: Datum, Entscheidung, Grund.

## 2026-10-20: Gemeinsamer Stand über GitHub
Alle Geräte (MacBook, KI-Server, Handy, Cloud-Sessions) nutzen denselben Claude-Account
und das Repo `traderreality/secbraindashboard` als einzige Quelle der Wahrheit.
Chatverläufe lokaler Sessions werden nicht synchronisiert, deshalb gilt:
`CLAUDE.md` und `docs/` tragen den gemeinsamen Kontext.

## 2026-10-20: Betrieb auf dem NAS
Das Dashboard wird auf dem NAS im Heimnetzwerk betrieben. Dort wird ein neuer Vault als Second Brain des Projekts aufgesetzt. Das alte Projekt SecVault wird bewusst nicht berücksichtigt.
Der Vault besteht aus Markdown-Dateien.
Zugriff zunächst nur im Heimnetz, mobiler Zugriff von unterwegs (sicherer Weg ins Heimnetz) kommt später.

## 2026-10-21: Migrierten SECBrain Watcher als Anwendungsbasis übernehmen

Der auf NAS-Main geprüfte SECBrain-Watcher-Stand wird als App-Quelle dieses
Repositorys übernommen. Die frühere Konzeptstruktur weicht der tatsächlich
betriebenen FastAPI-/JavaScript-Anwendung. Git-Historie des Quellrepositorys,
Vault- und Laufzeitdaten, Sicherungen, `.env`-Dateien und Build-Abhängigkeiten
werden nicht übernommen.

## 2026-10-21: QMD reproduzierbar im Container bereitstellen

Das Synology-Image installiert `@tobilu/qmd` 2.8.3 auf Node.js 22. Jede
Main-/Dev-Instanz verwendet eine eigene QMD-Kollektion und speichert den Index
im jeweiligen State-Volume. Dadurch hängt die Retrieval-API nicht mehr von
einer zufälligen QMD-Installation auf dem Host ab.

## 2026-10-21: Archivquelle und Web-Zugriff

Das NAS-Deployment verwendet einen Quellbaum ohne `.git`. Der Architekturstatus
meldet dafür künftig `SOURCE_ONLY` statt eines Git-Fehlers; bei einem echten
Checkout werden die vorhandenen Tags weiter geprüft. Fehlt das Quellverzeichnis
oder ist Git beschädigt, bleibt der Status `ERROR`.

Das Compose-Deployment verlangt getrennte Main-/Dev-Zugangsdaten und aktiviert
HTTP Basic für die gesamte Oberfläche und API. Nur der inhaltsarme Endpunkt
`/healthz` bleibt für den Container-Healthcheck öffentlich. Fehlende
Zugangsdaten verhindern den App-Start. Wegen der bisherigen HTTP-LAN-Bindung
ist ein HTTPS-Zugang oder geschützter Tunnel Voraussetzung für Main-Deployment.
