# Übergabe

## Hauptsystemprüfung am 22.10.2026

- NAS-Main und NAS-Dev verwenden getrennte Vault- und State-Mounts. Die alte
  KI-Server-Vault `/home/secbrain/Dokumente/SecBrain` ist laut Nutzer das
  Governance Layer und gehört weder zu Main noch zu Dev. Ein älterer Watcher
  auf dem KI-Server läuft nur auf `127.0.0.1:8011`, meldet den Loop als `idle`
  und verwendet eine getrennte lokale `dev-runtime`-Kopie. Sie ist weder ein
  Symlink zur Governance-Vault noch mit der NAS-Main-Vault verbunden.
- Die produktive NAS-Main-Vault hatte 87 uncommittete Git-Einträge: 33 geändert,
  3 gelöscht, 51 neu; nur einer lag in `01 Inbox`. Vor der Baseline wurde sie unter
  `/volume1/docker/secbrain/backups/secbrain-main-vault-before-baseline-20261022.tar.gz`
  gesichert (SHA-256
  `4ab35575fe27988dca71642eb610a8c8ac84c1544af2fa1221b2e2c1b89335b9`,
  Modus 0600). Alle 304 regulären Archivdateien stimmten per SHA-256 mit dem
  Live-Bestand überein. Das Archiv enthält Nutzerdaten und bleibt auf dem NAS.
- Die 87 Einträge wurden nach einem geprüften Vorabvergleich als lokaler
  Main-Vault-Baseline-Commit `4053d67` erfasst. Nur `.gitignore` wurde um
  `__pycache__/` und `*.pyc` ergänzt; `core.filemode=false` verhindert
  Synology-bedingte reine Modusabweichungen. 119 reguläre Vault-Dateien
  stimmten nach dem Commit bytegleich mit der Sicherung überein. Der Git-Status
  ist leer und `ensure_commit_ready()` besteht. Der Vault-Commit wurde nicht
  nach GitHub übertragen.
- Ein separater Codefehler wurde behoben: Loop-Vorschläge der Stationen 01–05
  werden vor der Freigabe im State statt in der Vault abgelegt. Ablehnung lässt
  die Vault unverändert; erst Freigabe kopiert den Vorschlag in die Vault.
  66 Python-Tests und 3 Subtests bestanden. Ein isolierter NAS-Dev-Container
  prüfte Ablehnung ohne Vault-Änderung und Freigabe mit Archivierung und
  Git-Commit. Healthcheck, Authentisierung und QMD waren grün. Testcontainer,
  Testimage und Testdaten wurden danach entfernt. NAS-Main und bestehender
  NAS-Dev-Dienst blieben gesund.
- Der Codefix aus PR #6 (Merge `446b8f41fb17ebbd971a7166bf02990ca4b06597`)
  ist auf NAS-Main ausgerollt. Ein vollständiger produktiver Loop-Lauf durch
  die Weboberfläche steht als separater End-to-End-Test noch aus.

## Aktueller Produktivstand am 22.10.2026

- NAS-Main verwendet den Quellbaum
  `/volume1/docker/secbrain/secbrain-main/watcher-main-446b8f4` und das Image
  `secbrain-dashboard:446b8f4` (ID
  `sha256:7b2ed012100a14661838d157f792aa103b7148222d931bb30c69b5d92d6e6907`).
  Alle 109 versionierten Quelldateien stimmten vor dem Build bytegleich mit
  GitHub-`main` überein.
- Vor dem Rollout wurden alter Quellbaum, Main-Vault und State unter
  `/volume1/docker/secbrain/backups/secbrain-main-pre-loopfix-20261022.tar.gz`
  gesichert (SHA-256
  `32e1c35227e939d925127fc14c78cb2c4d7f334785f496682c788f5ad4ace8a4`,
  Modus 0600). Alle 417 regulären Archivdateien stimmten mit dem damaligen
  Live-Bestand überein. Das alte Image trägt zusätzlich den Tag
  `secbrain-dashboard:rollback-before-loopfix-20261022`.
- Main und Dev sind `healthy`; der HTTPS-Proxy verwendet den neuen Quellbaum
  bei unverändertem CA-Speicher. TLS-Verifikation vom MacBook, `/healthz`
  HTTP 200, unangemeldete Oberfläche HTTP 401, angemeldeter API-Status
  HTTP 200, Architektur `SOURCE_ONLY` und QMD `available: true` mit Collection
  `secbrain-main` wurden nach dem Rollout geprüft. Main bleibt schreibgeschützt
  gestartet, ohne Linux-Capabilities und mit `no-new-privileges`; HTTP-Port
  `18080` bindet nur an `127.0.0.1`.

## Vorheriger Produktivstand am 22.10.2026

- Die produktive App stammt aus PR #3 (Merge-Commit
  `e8088990d63adee4139ab16d9434dba689f00ce5`); dessen Baum entspricht
  dem auf dem NAS ausgerollten PR-Commit
  `00d7df2fbb75323105d752ddc2bfdd2f435d6215`. PR #4 ergänzte danach
  die Betriebsdokumentation auf GitHub-`main`.
- NAS-Main verwendet Image-ID
  `sha256:4579948354e06cca5fe34ad7146574f1a5a77b4137ccc8ab554856e9b5a65c52`
  und den neuen Quellbaum unter
  `/volume1/docker/secbrain/secbrain-main/watcher-next-00d7df2`. Dessen 108
  versionierte Dateien stimmten vor dem Deployment per SHA-256 mit PR #3
  überein. Der vorherige Quellbaum bleibt für den Rückweg erhalten.
- Der Zugang ist `https://192.168.0.79:18443`. Der direkte HTTP-Port `18080`
  ist nur an NAS-Loopback gebunden und vom MacBook sowie KI-Server aus nicht
  mehr erreichbar. Es wurde kein Router-Port geöffnet.
- Das MacBook vertraut der produktiven lokalen CA im Benutzer-Schlüsselbund;
  der native macOS-Curl-Aufruf prüfte HTTPS ohne Ausnahmeschalter erfolgreich.
  Das öffentliche Zertifikat liegt unter
  `/Users/mariuskahl/SecBrain-CA-2026-10-22.crt` (SHA-256-Fingerabdruck:
  `D4:25:0B:54:9A:01:36:A9:10:E3:2B:87:A9:27:54:58:72:5B:2F:CE:2A:9D:5C:39:AF:DD:FC:B7:53:C7:A2:40`).
  Der private CA-Schlüssel bleibt mit Modus 0600 auf dem NAS.
- Die Zugangsdaten für Main und Dev liegen nur in geschützten Dateien
  außerhalb des Repositorys. Für den Benutzer liegt ein Exemplar unter
  `/Users/mariuskahl/SecBrain-Zugang-2026-10-22.txt` (Modus 0600). Keine
  Zugangsdaten werden in dieser Übergabe wiedergegeben.
- NAS-Main und bestehender Dev-Container sind `healthy`. Über HTTPS:
  `/healthz` HTTP 200; Oberfläche, API und eine Schreibroute ohne Anmeldung
  HTTP 401; Oberfläche, Frontend-Skript und API mit Anmeldung HTTP 200.
  Architektur `SOURCE_ONLY`; QMD `available: true`, Provider `qmd-bm25`,
  Collection `secbrain-main`.
- Der KI-Server erreicht die App mit dem öffentlichen CA-Zertifikat und prüft
  die TLS-Kette erfolgreich. Systemweites Vertrauen auf Ubuntu wurde mangels
  administrativer Rechte dort noch nicht eingerichtet. Das iPhone benötigt
  ebenfalls die manuelle Installation und volle Vertrauensstellung der CA.

## Vorheriger Produktivstand am 21.10.2026

- GitHub-`main`: `f9f06659ee64ddfa5d80044f47b8dffc856c418e`.
- Die 105 versionierten Dateien im NAS-Main-Quellbaum und die 73 ins laufende
  Image übernommenen App-/Entrypoint-/Lock-Dateien wurden per SHA-256 mit
  `main` verglichen: alle bytegleich.
- NAS-Main läuft `healthy` mit QMD 2.8.3 und Collection `secbrain-main`;
  `/api/vault/retrieval/status` meldete `available: true`.
- Der NAS-Quellbaum enthält kein `.git`. Deshalb meldet die bisherige App für
  `architecture` noch `ERROR` bei `git tag`.
- NAS-Main bietet die App bislang direkt per HTTP im LAN an. Die hier
  vorbereitete Anmeldung ist dort **nicht** ausgerollt.

## Korrektur auf dem Feature-Branch

- Der Git-Connector meldet einen gültigen Archiv-Deploy ohne `.git` als
  `SOURCE_ONLY`; echte Checkouts liefern weiterhin Tagdaten. Fehlende Quellen
  und defekte Git-Repositories bleiben Fehler.
- Für das Compose-Deployment ist HTTP Basic auf Oberfläche und API aktiv.
  Main und Dev verlangen getrennte Zugangsdaten; ohne sie startet die App
  nicht. Nur `/healthz` ist ohne Anmeldung erreichbar.
- Der Docker-Healthcheck nutzt `/healthz`; Dokumentation und Entscheidungen
  nennen die im produktiven Container bestätigte QMD-Version 2.8.3.
- Der Desktop-Starter erkennt sowohl den neuen Healthcheck als auch ältere
  NAS-Stände; HTTP 401 der geschützten API gilt als erreichbarer Dienst.
- Zugangsdaten und `.env`-Dateien werden nicht versioniert oder in Berichten
  ausgegeben. Vor einem Main-Rollout ist HTTPS im LAN oder ein geschützter
  Tunnel nötig, da die bisherige direkte HTTP-Bindung Basic-Zugangsdaten
  unverschlüsselt überträgt.

## Prüfung des Korrekturstands

- Lokale Python-Suite: 65 Tests und 3 Subtests bestanden.
- JavaScript- und Shell-Syntax sowie `git diff --check`: bestanden.
- Desktop-Starter mit vier lokalen HTTP-Szenarien geprüft: neuer Dienst,
  bisheriger Dienst, geschützter bisheriger Dienst und nicht erreichbarer Dienst.
- Isoliertes NAS-Dev-Projekt `secbrain-auth-check`: Compose-Konfiguration und
  Image-Build bestanden; Container `healthy` auf `127.0.0.1:18012`. Das
  endgültige Test-Image hat die ID
  `sha256:92b2164236027c9deb96b6e5fdcfd694c1a42fcab78600eec9407b5882ab8057`.
- Ohne Anmeldung: `/healthz` HTTP 200, Oberfläche/API/Schreibroute HTTP 401.
  Mit Testanmeldung: Oberfläche und API HTTP 200; falsche Anmeldung HTTP 401.
- Isolierte Dev-Retrieval-API: `available: true`, Collection
  `secbrain-auth-check-20261021`, Provider `qmd-bm25`.
- Isolierter Dev-Architekturstatus: `SOURCE_ONLY`, `git_available: false`.
  NAS-Main blieb während der Prüfung `healthy` und wurde nicht geändert.
- Der temporäre Testcontainer und seine Test-Zugangsdaten wurden nach der
  Prüfung entfernt. NAS-Main und der bestehende NAS-Dev-Dienst blieben `healthy`.

## Sicherung und Rückweg

- Vor der Änderung wurde `main` als Archiv unter
  `/tmp/secbraindashboard-main-f9f06659-pre-fix-20261021.tar.gz` gesichert;
  SHA-256: `79aacf02fcae66a83c9a545b63a5f0b145ac1bd12240e5a42e38c2f3261c929a`.
- Der Feature-Branch basiert auf dem unveränderten Commit
  `f9f06659ee64ddfa5d80044f47b8dffc856c418e`. Vor einem Merge besteht
  der Code-Rückweg darin, den Branch zu verwerfen; NAS-Main braucht keinen
  Rückbau. Der isolierte Teststand liegt unter
  `/volume1/docker/secbrain/auth-check-20261021` und berührt weder Main- noch
  bestehende Dev-Vault oder State.

## Sicherung und Rückweg für den HTTPS-Rollout

- Vor der Umschaltung wurden Quellbaum, bisherige Compose-Datei, Vault und
  State unter
  `/volume1/docker/secbrain/backups/secbrain-main-pre-https-20261022.tar.gz`
  gesichert (SHA-256:
  `f56dc1c290b750ada7c4a67aa2c3791cddaf346fa3962095d7b9b45b82fd121e`,
  620 Archiveinträge). Die bisherige Image-ID wurde zusätzlich als
  `secbrain-dashboard:rollback-f9f06659-20261022` markiert.
- Die produktive CA wurde separat unter
  `/volume1/docker/secbrain/backups/secbrain-tls-ca-20261022.tar.gz` gesichert
  (SHA-256:
  `6ea9f484ea1b0b04aa041330181ecf445dcbcb0a2dc32f446abb81f6e0198b4c`).
  Beide Archive haben Modus 0600; das CA-Archiv enthält private Schlüssel und
  darf nicht verteilt werden.
- Bei einem Fehler den neuen Compose-Stand stoppen und den bisherigen
  Quellbaum `.../secbrain-main/watcher` mit dem markierten Image wieder
  starten. Vault und State nur dann aus dem Archiv wiederherstellen, wenn
  diese Daten tatsächlich beschädigt wurden; spätere Nutzerdaten sonst
  erhalten. CA-Daten nicht versehentlich neu erzeugen, damit vertraute
  Clients ihre Zertifikatskette behalten.

## Nächste Schritte und Grenzen

1. Auf dem iPhone das öffentliche CA-Zertifikat nach Fingerabdruckprüfung
   installieren und für SSL/TLS ausdrücklich als vertrauenswürdig aktivieren.
2. Auf dem KI-Server bei Bedarf mit administrativen Rechten die CA in den
   Ubuntu-Systemspeicher aufnehmen; die Prüfung mit `curl --cacert` ist
   bereits erfolgreich.
3. Browser-End-to-End-Tests für Loop, Radar, Upload und 3D-Graph auf MacBook
   und iPhone durchführen. Die API- und statischen Frontend-Tests sind grün.
4. Der am 21.10.2026 dokumentierte QMD-Abhängigkeitsaudit meldete acht
   transitive Advisories; er wurde beim HTTPS-Rollout nicht neu bewertet.
