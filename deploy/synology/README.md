# Synology-Deployment für SECBrain Watcher

Die Compose-Definition stellt getrennte Main- und Dev-Profile bereit. Das
App-Container-Root-Dateisystem und Quellmount sind schreibgeschützt; nur Vault
und State sind dort beschreibbar. Das Main-Profil enthält einen eigenen
HTTPS-Proxy mit separat beschreibbarem Zertifikatsspeicher;
DSM-Firewall, DSM-Reverse-Proxy und Router werden von diesen Dateien nicht
verändert.

## QMD-Laufzeit

Das Image baut auf Python 3.12 und Node.js 22 auf und installiert
`@tobilu/qmd@2.8.3`. Vor dem Start des Backends:

1. setzt der Entrypoint `XDG_CACHE_HOME` und `XDG_CONFIG_HOME` auf getrennte
   Verzeichnisse im State-Mount,
2. legt er die konfigurierte QMD-Kollektion für `/vault` an oder aktualisiert
   sie,
3. prüft er `qmd status`,
4. startet er erst danach Uvicorn.

Main und Dev haben getrennte State-Mounts und damit getrennte QMD-Indizes.
QMD nutzt für die Watcher-Suche BM25; ein Modell-Download oder
`qmd embed` ist dafür nicht erforderlich. Das Image lässt deshalb die
optionalen llama.cpp-/GPU-Laufzeiten aus und enthält nur die für Status,
Indexierung und BM25-Suche benötigte Linux-sqlite-vec-Laufzeit.

## Benötigte Konfiguration

Es wird bewusst keine `.env`-Datei versioniert. Die folgenden Werte müssen über
die Umgebung oder eine geschützte Datei außerhalb des Repositorys gesetzt
werden:

- `SECBRAIN_UID`, `SECBRAIN_GID`
- `SECBRAIN_OLLAMA_URL`, `SECBRAIN_OBSERVER_MODEL`
- `SECBRAIN_MAIN_VAULT`, `SECBRAIN_MAIN_STATE`
- `SECBRAIN_DEV_VAULT`, `SECBRAIN_DEV_STATE`
- `SECBRAIN_MAIN_HTTP_USER`, `SECBRAIN_MAIN_HTTP_PASSWORD`
- `SECBRAIN_DEV_HTTP_USER`, `SECBRAIN_DEV_HTTP_PASSWORD`
- `SECBRAIN_TLS_DATA` (geschützter, dauerhaft gesicherter NAS-Pfad für die
  lokale Zertifizierungsstelle)
- `SECBRAIN_MAIN_EXCALIDRAW_TOKEN`, `SECBRAIN_DEV_EXCALIDRAW_TOKEN` (verschiedene
  zufällige Dienst-Tokens)
- `SECBRAIN_MAIN_EXCALIDRAW_DIR=/volume1/Local/Work/excalidraw`
- `SECBRAIN_DEV_EXCALIDRAW_DIR=/volume1/Local/Work/excalidraw-dev`

## Excalidraw-Generator

Im Dashboard-Chat schreibt nur `/excalidraw <Beschreibung>` eine Datei. Der
Generator prüft die JSON-Szene und erzeugt einen eigenen Dateinamen. Main und
Dev haben getrennte Worker, Tokens und Work-Ordner. Beide Worker sind nur im
Compose-Netz erreichbar; es gibt keinen Host-Port. Der offizielle statische
Excalidraw-Container bleibt gestoppt, weil er keine KI-Anfragen verarbeitet.

Die Zielordner vor dem Start auf dem NAS anlegen und dem konfigurierten
`SECBRAIN_UID:SECBRAIN_GID` Schreibrechte geben. Der Container sieht sie unter
`/work/excalidraw`; SMB-Clients finden dieselben Dateien unter
`Local/Work/excalidraw` beziehungsweise `Local/Work/excalidraw-dev`. Es werden
keine SMB-Zugangsdaten im Container gebraucht. Fehlende Ordner dürfen nicht
durch einen Docker-Bind-Mount unbemerkt als neue Host-Verzeichnisse entstehen.

Zuerst nur Dev bauen und starten:

```bash
docker compose --env-file "$config" --profile dev config --quiet
docker compose --env-file "$config" --profile dev build dev excalidraw-dev
docker compose --env-file "$config" --profile dev up -d dev excalidraw-dev
docker compose --env-file "$config" --profile dev ps
```

Nach einer authentisierten Dashboard-Anfrage die erzeugte Datei auf dem NAS
als JSON lesen und ihre Bytes über die SMB-Freigabe vergleichen. Der normale
Chat darf keine Datei erzeugen. Bei Fehlern `excalidraw-dev` und gegebenenfalls
das aktualisierte Dev-Dashboard stoppen; Dev-Ausgabedateien bleiben zur Prüfung
erhalten. Main erst nach Review, Sicherung und separater Freigabe umstellen.

Compose setzt `SECBRAIN_AUTH_REQUIRED=1`. Die App startet bei fehlenden
Zugangsdaten nicht. Browser zeigen die HTTP-Basic-Anmeldung automatisch an;
Oberfläche und sämtliche API-Routen sind geschützt. Nur `/healthz` bleibt
für den Container-Healthcheck ohne Anmeldung erreichbar. Main und Dev verwenden
getrennte Zugangsdaten. Secret-Werte dürfen nicht im Repository, in Befehlslogs
oder in Berichten stehen.

**Main-HTTPS:** `https-main` nutzt Caddy mit einer lokalen Zertifizierungsstelle
und bedient standardmäßig `https://192.168.0.79:18443`. Die App bindet ihren
HTTP-Port ausschließlich an `127.0.0.1` des NAS; der Proxy erreicht sie über
das interne Compose-Netz. Zertifikate und CA-Schlüssel liegen dauerhaft unter
`SECBRAIN_TLS_DATA`. Nur `root.crt` darf zur Vertrauensstellung auf MacBook,
KI-Server und Handy kopiert werden; private Schlüssel bleiben auf dem NAS.
Die IP-Adresse wird im Zertifikat geprüft. Weil manche Clients bei IP-Adressen
kein SNI senden, setzt Caddy sie außerdem als Standard-SNI.

Vor der Nutzung mit echten Zugangsdaten muss das Stammzertifikat auf jedem
Client als vertrauenswürdig eingerichtet und sein SHA-256-Fingerabdruck gegen
die NAS-Quelle abgeglichen sein. Browserwarnungen dürfen nicht übergangen
werden. Keine Router- oder öffentliche Freigabe daraus ableiten.

Optionale Werte:

- `SECBRAIN_MAIN_PORT` (Standard: `8080`)
- `SECBRAIN_TLS_HOST` (Standard: `192.168.0.79`, Zertifikatsname)
- `SECBRAIN_HTTPS_BIND` (Standard: `192.168.0.79`)
- `SECBRAIN_HTTPS_PORT` (Standard: `18443`)
- `SECBRAIN_DEV_BIND` (Standard: `127.0.0.1`)
- `SECBRAIN_DEV_PORT` (Standard: `8011`)
- `SECBRAIN_IMAGE_TAG`, `SECBRAIN_MAIN_QMD_COLLECTION`,
  `SECBRAIN_DEV_QMD_COLLECTION`

## Prüfablauf

```bash
# Die Datei liegt außerhalb des Repositorys.
config=/geschuetzter/pfad/secbrain-dev.env

./preflight.sh "$config"
docker compose --env-file "$config" --profile dev config --quiet
docker compose --env-file "$config" --profile dev build dev
docker compose --env-file "$config" --profile dev up -d dev
docker compose --env-file "$config" --profile dev ps
curl --fail http://127.0.0.1:8011/healthz
test "$(curl --silent --output /dev/null --write-out '%{http_code}' http://127.0.0.1:8011/api/status)" = 401
curl --fail --netrc-file /geschuetzter/pfad/secbrain-dev.netrc http://127.0.0.1:8011/api/status
curl --fail --netrc-file /geschuetzter/pfad/secbrain-dev.netrc http://127.0.0.1:8011/api/vault/retrieval/status
```

Der Retrieval-Status muss `available: true`, das erwartete Dev-
Kollektionslabel und `/usr/local/bin/qmd` melden. Erst danach darf ein
separater Main-Änderungsprozess geplant werden. Dieses Repository-Update
deployed weder Main noch Dev automatisch.

Für einen Vault mit Git einmalig eine lokale Autorenkennung im laufenden
App-Container setzen und vor einem Loop-Lauf prüfen. Die Kennung gehört nur
zum jeweiligen Vault-Repository; sie ändert keine globale Git-Konfiguration:

```bash
docker compose --env-file "$config" --profile main exec main \
  git -C /vault config --local user.name "SECBrain Watcher"
docker compose --env-file "$config" --profile main exec main \
  git -C /vault config --local user.email "watcher@local.invalid"
docker compose --env-file "$config" --profile main exec main \
  git -C /vault var GIT_AUTHOR_IDENT
```

Für Main zusätzlich `https-main` im selben Compose-Projekt starten. Nach dem
ersten TLS-Aufruf das öffentliche CA-Zertifikat aus
`$SECBRAIN_TLS_DATA/caddy/pki/authorities/local/root.crt` exportieren und den
Fingerabdruck mit `openssl x509 -noout -fingerprint -sha256` prüfen. Mit
`curl --cacert root.crt https://192.168.0.79:18443/healthz` muss die
Zertifikatsprüfung ohne `-k` bestehen. Die Oberfläche und `/api/status` müssen
ohne Anmeldung HTTP 401, mit geschützter Testanmeldung HTTP 200 liefern. Der
direkte App-Port darf nur über NAS-Loopback erreichbar sein.

## Rollback

Ein fehlgeschlagener Dev-Test wird durch Stoppen des Dev-Profils zurückgerollt.
Vault und State werden dabei nicht gelöscht. Vor Main-Deployment Quellstand,
Compose-Datei, Image-ID, Vault, State und `SECBRAIN_TLS_DATA` mit Prüfsummen
sichern. Bei Fehlern zuerst den HTTPS-Proxy stoppen und den vorherigen
Main-Stand aus der gesicherten Compose-/Image-Version wiederherstellen. Die
lokale CA darf bei einem Container-Neustart nicht neu erzeugt werden, sonst
verlieren bereits vertraute Clients die Zertifikatskette.
