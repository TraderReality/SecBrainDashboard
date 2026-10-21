# Import- und Migrationsnachweis

## Herkunft

Als Anwendungsquelle wurde ausschließlich der bereits geprüfte NAS-Main-
Staging-Stand unter

`work/nas-main-stage/secbrain-main/watcher`

verwendet. Der Stand lag auf Branch `R12-NEXT` bei Commit
`bb3c22dcd31d2c371363207be1b317d4776b9231`; vorhandene, noch nicht
committete Änderungen wurden als Teil des Migrationsstands übernommen.

Der bestehende Checkout `/home/secbrain/Dokumente/SecBrain Watcher` wurde nur
lesend inventarisiert. Er gehört zu `trox87-prog/SecBrain-Watcher`, liegt
ebenfalls auf `R12-NEXT` und wurde weder bereinigt noch umkonfiguriert oder
beschrieben.

Die Projektdokumente aus dem geschlossenen, nicht gemergten PR #1 wurden aus
dessen Head-Commit `7e90e4b2daeede5942f226180e886428d981129a` übernommen und an den
tatsächlichen Stand angepasst. Der PR selbst wurde nicht gemergt.

## Bewusst ausgeschlossene Inhalte

- `.git`-Historie und Metadaten des Quellrepositories
- alle `.env`-Dateien und Geheimnisse
- Vault-Inhalte sowie Laufzeit-, Index- und Zustandsdaten
- Sicherungen und temporäre Vorher-/Nachher-Kopien
- virtuelle Umgebungen, Caches, `node_modules` und Build-Ausgaben

Geheimniswerte aus vorhandenen `.env`-Dateien wurden nicht gelesen.

## QMD-Befund und Behebung

Das bisherige Synology-Image installierte weder Node.js noch QMD. Deshalb
meldete NAS-Main für `/api/vault/retrieval/status` korrekt `available: false`
und „QMD wurde nicht gefunden“.

Das neue Image baut QMD 2.8.3 in einer separaten Node-22-Stufe und übernimmt
die für BM25 benötigte Laufzeit ohne optionale llama.cpp-/GPU-Pakete in das
Python-Image. Der Entrypoint legt die konfigurierte Collection an beziehungsweise
aktualisiert sie und beendet den Container bei fehlendem QMD oder ungültigem
Status. Main und Dev verwenden getrennte `XDG_CACHE_HOME`- und
`XDG_CONFIG_HOME`-Verzeichnisse im jeweiligen State-Volume, damit
Collection-Konfiguration und Index nicht kollidieren.

## Verifikation

- Python: `57 passed, 3 subtests passed`
- JavaScript-Syntax: bestanden
- Shell-Syntax: bestanden
- Compose-Konfiguration für Main und Dev: bestanden
- isolierter lokaler QMD-Index: eine Testdatei indiziert und gefunden
- isolierter lokaler App-Healthcheck: HTTP 200
- isolierter lokaler Retrieval-Status: HTTP 200, `available: true`,
  Provider `qmd-bm25`
- isolierter Synology-Build: Image `secbrain-dashboard:qmd-check-v4`
  erfolgreich gebaut; QMD meldet Version 2.8.3
- isolierter Synology-Start: Collection `secbrain-qmd-check` für `/vault`
  angelegt, Anwendung gestartet und anschließend gestoppt
- Synology-internes `/api/status`: HTTP 200
- Synology-internes `/api/vault/retrieval/status`: HTTP 200,
  `available: true`, Provider `qmd-bm25`

Der produktive NAS-Main-Dienst wurde für diese Prüfung weder geändert noch neu
gestartet. Der NAS-Containerbuild erfolgte ausschließlich im temporären,
loopback-gebundenen Projekt `secbrain-qmd-check`; dessen Container ist nach der
Prüfung gestoppt. Das Projekt und seine Build-Artefakte bleiben für eine
nachvollziehbare Sichtprüfung erhalten und sind nicht produktiv gebunden.

`npm audit --omit=dev --omit=optional` meldet für die aktuell verfügbare
QMD-Version weiterhin 8 transitive Advisories (6 hoch, 2 kritisch), vor allem
in nicht verwendeten MCP-/LLM-/Git-Pfaden. Die Watcher-Integration ruft nur
lokale `status`-/BM25-Befehle auf und läuft mit verworfenem Capability-Set,
schreibgeschütztem Root-Dateisystem und ohne öffentliche Portbindung. Der
Audit-Befund bleibt dennoch offen und muss vor einem produktiven Rollout gegen
eine bereinigte QMD-Version erneut geprüft werden.

## Rückweg

Der Basisstand des Zielrepositories bleibt der unveränderte Commit
`e812e477decbd8bb85dcb59fa66133f2e4681d7e`. Die Migration liegt auf einem
separaten Feature-Branch. Ein Rollback besteht daher bis zu einem späteren,
ausdrücklich freigegebenen Merge lediglich aus dem Verwerfen dieses Branches;
an NAS-Main ist kein Rückbau erforderlich.
