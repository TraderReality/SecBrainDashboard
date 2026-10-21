# NAS-Betriebsumgebung

Stand der verifizierten Migration vom 21. Oktober 2026. Keine Zugangsdaten,
Schlüssel oder geheimen Variablenwerte in diese Datei schreiben.

## Hardware und Netz

- Synology DS1821+, DSM 7.3.2
- produktive LAN-Bindung: `192.168.0.79:18080`
- zweite NAS-Schnittstelle `.80` stellt Main nicht bereit
- NAS-Dev bleibt an `127.0.0.1:18011` gebunden
- keine Router- oder Internetfreigabe für SECBrain Watcher

Die Adresse `.79` wird derzeit per DHCP vergeben. Für den Dauerbetrieb ist eine
Reservierung im Router sinnvoll.

## Container

- Projekt `secbrain-main`, getrenntes Projekt `secbrain-dev`
- Python 3.12, FastAPI/Uvicorn
- QMD 2.5.3 auf Node.js 22, getrennte Kollektionen und Indizes
- Root-Dateisystem read-only, alle Capabilities entfernt,
  `no-new-privileges`, 768 MB Speichergrenze
- Vault und State pro Umgebung getrennt; Quellcode nur lesend gemountet

## Bekannte Synology-Besonderheiten

- Der Kernel unterstützt die Compose-Einstellung `NanoCPUs` nicht; verwendet
  wird `cpu_shares: 512`.
- Die Prozessanzahl-Begrenzung wird auf diesem DSM-Kernel verworfen und ist
  deshalb nicht Bestandteil der wirksamen Definition.
- Schreibbare Vault-/State-Pfade müssen dem Containerkonto gehören; bei der
  Migration war `1026:100` mit Modus `755` verifiziert.
- Vor jedem späteren Deployment Container, Ports, Mountziele und Sicherungen
  erneut prüfen. Bestehende Projekte nicht überschreiben.

## QMD

QMD schreibt Kollektionseinstellungen unter `XDG_CONFIG_HOME` sowie
SQLite-Index und optionale Modellcaches unter `XDG_CACHE_HOME`. Compose setzt
diese Pfade auf `/state/qmd-config` und `/state/qmd-cache`, sodass das read-only
Root-Dateisystem erhalten bleibt. Der Entrypoint legt die konfigurierte
Kollektion für `/vault` an oder aktualisiert sie vor dem App-Start.
