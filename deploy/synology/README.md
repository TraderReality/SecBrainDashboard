# Synology-Deployment für SECBrain Watcher

Die Compose-Definition stellt getrennte Main- und Dev-Profile bereit. Das
Container-Root-Dateisystem und der Quellmount sind schreibgeschützt; nur Vault
und State sind beschreibbar. DSM-Firewall, Reverse Proxy und Router werden von
diesen Dateien nicht verändert.

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

Compose setzt `SECBRAIN_AUTH_REQUIRED=1`. Die App startet bei fehlenden
Zugangsdaten nicht. Browser zeigen die HTTP-Basic-Anmeldung automatisch an;
Oberfläche und sämtliche API-Routen sind geschützt. Nur `/healthz` bleibt
für den Container-Healthcheck ohne Anmeldung erreichbar. Main und Dev verwenden
getrennte Zugangsdaten. Secret-Werte dürfen nicht im Repository, in Befehlslogs
oder in Berichten stehen.

**Vor Main-Deployment:** Der bisherige direkte HTTP-Port im LAN verschlüsselt
die Basic-Zugangsdaten nicht. Zuerst HTTPS über einen geschützten LAN-Zugang
oder einen Tunnel bereitstellen und die direkte HTTP-Bindung entsprechend
begrenzen. Keine Router- oder öffentliche Freigabe daraus ableiten.

Optionale Werte:

- `SECBRAIN_MAIN_BIND` (sicherer Standard: `127.0.0.1`)
- `SECBRAIN_MAIN_PORT` (Standard: `8080`)
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

## Rollback

Ein fehlgeschlagener Dev-Test wird durch Stoppen des Dev-Profils zurückgerollt.
Vault und State werden dabei nicht gelöscht. Für Main bleibt das zuvor
versionierte Image verfügbar; ein Main-Deployment ist nicht Bestandteil dieses
Änderungsstands.
