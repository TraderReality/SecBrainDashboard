# Übergabe

## Produktivstand am 21.10.2026

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

## Nächste Schritte und Grenzen

1. Feature-Branch per Pull Request gegen `main` prüfen.
2. Für Main geschützte Zugangsdaten bereitstellen und HTTPS oder einen
   geschützten Tunnel einrichten; den direkten HTTP-Zugang entsprechend
   begrenzen. Die aktuellen Geheimniswerte wurden nicht gelesen.
3. Vor einem freigegebenen Main-Deployment Backup und Rückweg erneut prüfen,
   dann Dev und Main getrennt testen. Kein Main-Deploy ohne Freigabe.
4. Browser-End-to-End-Tests für Loop, Radar, Upload und 3D-Graph bleiben offen.
5. Der am 21.10.2026 dokumentierte QMD-Abhängigkeitsaudit meldete acht
   transitive Advisories; er wurde in dieser Korrektur nicht neu bewertet.
