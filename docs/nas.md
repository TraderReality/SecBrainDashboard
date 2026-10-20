# NAS (Betriebsumgebung)

Quelle: Auskunft aus dem alten Chat (SecDash). Spezifikation, nicht live geprüft.
Keine Zugangsdaten oder Schlüssel in diese Datei schreiben.

## Hardware und Netz
- Synology DS1821+, DSM 7.3.2
- IP 192.168.0.79, Heimnetz 192.168.0.0/24
- Offene Ports: 22 (SSH), 5000/5001 (DSM), 445 (SMB), 548 (AFP), 8000 (Paperless), 8010 (SecDash). 2049 gefiltert.
- SSH nur mit Schlüssel. Deploy-Benutzer `secdash-deploy`, UID 1028, Gruppe `administrators`.

## Docker
- Container Manager, Docker 24.0.2, Compose v2.20.1
- Nur mit vollem Pfad aufrufbar: `/usr/local/bin/docker`, `/usr/local/bin/docker-compose`
- Aufruf mit `sudo -n /usr/local/bin/docker ...` (Sudo-Regel gilt nur für diese Binaries)
- Socket `/var/run/docker.sock` root:root 660, kein Zugriff über eine Gruppe `docker`
- Laufende Container des alten Projekts: secdash (8010), secdash-dev (8011), paperless (8000), paperless-db, paperless-redis

## Bekannte Stolpersteine
- Container stürzt mit `sqlite3.OperationalError: unable to open database file` ab: DSM-ACL gibt UID 1000 nur Leserechte. Lösung: Container mit `user: "1028:100"` starten.
- `sudo -n docker ...` ohne vollen Pfad schlägt fehl (Passwortabfrage). Immer den vollen Pfad nutzen.
- rsync zum NAS: "Permission denied, please try again". Lösung: `--rsync-path=/usr/bin/rsync`.
- Port 8000 gehört Paperless.

## Folgen für SecBrainDashboard
- Docker ist verfügbar, das Dashboard kann als Container auf dem NAS laufen.
- Eigenen freien Port wählen (nicht 8000, 8010, 8011, 5000, 5001).
- Neues Verzeichnis unter `/volume1/docker/` anlegen, Berechtigungen vorab prüfen (ACL-Problem).
- Das alte Projekt SecDash wird nicht berücksichtigt; seine Container nicht anfassen.
