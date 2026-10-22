# Übergabe

## Validierung des letzten Laufs (Feature-Branch vom 22.10.2026)

Der freigegebene Entwurf und Plan sind auf dem isolierten Feature-Branch
`codex/validation-last-run-impl` umgesetzt. Nach einem erfolgreichen Inbox-
oder Wissensradar-Lauf speichert der Watcher einen versionierten Prüfnachweis
im getrennten State. Ein dauerhafter Übernahmemarker verhindert, dass nach
einem Prozessabbruch ein älterer Nachweis irreführend grün erscheint. Die neue
Ansicht „Validierung“ zeigt den Lauf und prüft auf Knopfdruck Dateien, lokalen
Vault-Commit, Indexer-Export und aktuellen QMD-Status ausschließlich lesend.
Vor Einführung der Funktion abgeschlossene Läufe haben keinen nachträglich
erfundenen Nachweis.

Lokal bestanden 100 Backend-Tests und 3 Subtests, alle Frontend-JavaScript-
Syntaxprüfungen und `git diff --check`. Im isolierten lokalen Browser wurden
der leere Zustand, ein gespeicherter Lauf, eine nachträglich geänderte
Archivdatei, nicht verfügbares QMD und die schmale Ansicht geprüft. NAS-Main
wurde nicht geändert. Ausstehend sind Gesamt-Review, Pull Request und ein
separater Dev-/Main-Rollout nach den bestehenden Freigabeschritten. Scanner
und Reports bleiben weiterhin inerte UI-Einträge (P2); das iPhone-Zertifikat
bleibt zurückgestellt.

## Main-Rollout von PR #11 am 22.10.2026 (Schritt 5 abgeschlossen)

- Nach ausdrücklicher Freigabe wurde PR #11 nach `main` gemergt (`a02ee24d58d16cb621f13f9d9461faef5bc321ca`). Der ausgelieferte Quellbaum hat denselben Git-Tree `317881943bfdd71bf7758b64ff3a8e4b6818b661` wie der abschließend getestete Branch. Der erneute lokale Gesamtlauf vor dem Merge bestand mit `83 passed, 3 subtests passed`; `git diff --check` war sauber.
- Vor der Umschaltung wurden Main und HTTPS-Proxy gestoppt. Die konsistente NAS-Sicherung unter `/volume1/docker/secbrain/secbrain-main/backups/2026-10-22-pre-a02ee24/main-consistent.tar.gz` enthält Main-Vault, State, TLS-Daten, alten Quellbaum und alte Proxy-Konfiguration: 527 reguläre Dateien, 782 Archiveinträge, 25.770.504 Byte, Modus 0600, SHA-256 `8f5b2c29e6f16dd716a0182a0a993f9d274917805c0f479dc346ebe47ca3ff87`. Alle Datei-Inhalte im Archiv wurden lesend geprüft. Das alte App-Image ist als `secbrain-dashboard:rollback-pre-a02ee24` erhalten.
- Main läuft mit `secbrain-dashboard:a02ee24` (Image-ID `sha256:e75995816499994e19e2624c47110ccecc755108cd4c543f5611553f36148bdb`) aus `/volume1/docker/secbrain/secbrain-main/watcher-main-a02ee24`. Vault und State nutzen ihre bisherigen getrennten Mounts; der bestehende Proxy und seine CA blieben erhalten. Die archivierte und die aktive CA stimmen bytegleich überein; Fingerabdruck der öffentlichen Root-CA: `D4:25:0B:54:9A:01:36:A9:10:E3:2B:87:A9:27:54:58:72:5B:2F:CE:2A:9D:5C:39:AF:DD:FC:B7:53:C7:A2:40`.
- HTTPS mit CA-Prüfung: `/healthz` 200, unangemeldete API 401, angemeldete API 200. QMD meldet `available: true` und Collection `secbrain-main`. Main, Proxy und bisheriges Dev laufen ohne Neustarts; das getrennte Dev blieb unverändert.
- Weil die Freigabe- und Commitstrecke geändert wurde, lief ein vollständiger produktiver 12-Stationen-Test mit der eindeutig markierten Quelle `2026-10-22 SECBrain Main Rollout Smoke.md`. Vor Freigabe enthielt der Vorschlag ausschließlich diese Quelle. Danach: `completed`, 12 Stationen, Indexer `ok: true`, Commit `54ba3ba11fada6ca7a46a0e7f3365519686fee18`. Die Rohquelle liegt bytegleich im Archiv (SHA-256 `f3b5158fc801b1b5261375dc2c96d008c7ba92ea0e14b72bd8b93a47d2e56c98`), nicht mehr in der Inbox. Vault-Git ist sauber.
- Rückweg bei einem später entdeckten App-Fehler: Main anhand des erhaltenen alten Quellbaums und Image-Tags zurücksetzen, dann Health, HTTPS/Auth und QMD prüfen. Vault und State nur bei tatsächlicher Beschädigung und mit Prüfung späterer Nutzerdaten aus der konsistenten Sicherung wiederherstellen; die CA nicht neu erzeugen. Die drei inerten UI-Einträge Scanner, Validierung und Reports bleiben als P2 offen. Das iPhone-Zertifikat bleibt zurückgestellt.

## Branch-Review und zusätzliche Rückwege am 22.10.2026 (Schritt 5, noch kein Rollout)

- Der Review des Feature-Branches fand vier reproduzierbare Lücken: ein erfolgreicher Indexer konnte fremde Inhalte einer Laufdatei mitcommitten; ein Inbox-Dateiname mit `*` erweiterte Git-Pathspecs auf einen späteren Eingang; der Fehler-Rückweg verwarf fremde gestagte Bytes auf einem Laufpfad; ein Prozessabbruch während `apply()` hinterließ einen Teilstand ohne QMD-Marker. Alle vier Fälle wurden zunächst als scheiternde Regressionen festgehalten.
- Der Watcher schreibt vor der ersten Inhaltsmutation ein dauerhaftes Transaktionsjournal und markiert QMD als unsynchron. Beim nächsten Start stellt er einen unterbrochenen Lauf vor der Git-Vorprüfung kontrolliert wieder her. Ein Abbruch direkt nach dem Git-HEAD-Wechsel repariert den Git-Index anhand des Journalzustands. Fremde Änderungen oder gestagte Laufdateien bleiben bei Konflikten erhalten.
- Der Abschluss-Commit verwendet einen gesperrten temporären Git-Index, literale Pfade und die vorab geprüften eigenen Inhaltsbytes. Eine fremde Datei mit passendem Platzhalternamen gelangt damit nicht in den Commit. Der Wissensradar-Freigabepfad nutzt denselben Rückweg für Zielseite, Log und Indexerfehler.
- Lokal wurden die vier Gegenproben, ein Prozessabbruch unmittelbar nach dem Git-HEAD-Wechsel und ein Wissensradar-Indexerfehler mit realen temporären Git-Vaults geprüft. Der zweite Review fand zwei Git-Index-Rennen beim Wiederanlauf. Unbekannte Git-Sperren bleiben nun erhalten; der eigene Sperrmarker bleibt bis nach dem atomaren Indexersatz bestehen, und der Indexhash wird unter der Sperre geprüft. Zwei zusätzliche Regressionen belegen diese Fälle. Gesamtlauf auf dem auf `origin/main` aufgebauten Branch: `83 passed, 3 subtests passed`; `git diff --check` und Python-Syntax ohne Befund. Der unabhängige Abschlussreview von `caafdda..938650d` meldete keine offenen Critical-/Important-Befunde und prüfte zusätzlich echtes paralleles `git add` sowie Abbrüche vor dem Ref-Wechsel und nach der Indexinstallation.
- Das NAS-Image aus dem vorherigen Review-Commit `814cab5` wurde als `secbrain-dashboard:review-814cab5` (ID `sha256:1e680524…`) gebaut. Ein netzloser Container mit eigenem Vault/State rollte einen Indexerfehler zurück, arbeitete den QMD-Marker mit einem reparierten Test-Indexer ab und schloss die Wiederholung mit sauberem Git-Status ab. Die App aus demselben Image lieferte Health 200, unangemeldeten API-Zugriff 401 und angemeldeten API-Zugriff 200. Main und bestehendes Dev blieben unverändert. Wegen des späteren Git-Index-Fixes war ein neuer Image-Nachweis erforderlich.
- Der korrigierte Code-Commit `938650d` wurde auf dem NAS vollständig als `secbrain-dashboard:review-938650d` gebaut (ID `sha256:e75995816499994e19e2624c47110ccecc755108cd4c543f5611553f36148bdb`). Ein netzloser Linux-Container mit eigener Vault und eigenem State rollte einen Indexerfehler zurück, arbeitete den QMD-Marker vor der Wiederholung mit dem reparierten Test-Indexer ab und schloss mit Vault-Commit und sauberem Git-Status ab. Der echte QMD-Indexer wurde zuvor separat im isolierten Dev geprüft. Die temporäre App aus demselben Image lieferte `/healthz` 200, API ohne Anmeldung 401 und mit Testanmeldung 200. Main und bisheriges Dev blieben `healthy`; Main nutzt weiter `a9f498b`, Vault-HEAD `bdb8bde`, Git-Status 0.
- Lokale NAS-Review-Sicherung von Main-Vault, Main-State und bisherigem Quellbaum: `/volume1/docker/secbrain/secbrain-main/backups/2026-10-22-review-938650d/main-review.tar.gz`, 517 reguläre Dateien, 25.766.012 Byte, Modus 0600, SHA-256 `476840996162d040c649a2ca63d261e23fc30f4bab81a9a261309af0f2193e27`. Alle Archiveinträge wurden lesend geprüft. Dies ist ein Snapshot während laufendem Main. Direkt vor einer produktiven Umschaltung ist eine neue konsistente Sicherung einschließlich TLS-CA und Prüfsumme nötig.
- Vorbereiteter Rückweg: bisheriges Image `secbrain-dashboard:a9f498b` (ID `sha256:251b8bba…`) und Quellbaum `watcher-main-a9f498b` beibehalten; bei einem fehlerhaften App-Rollout den Main-Dienst auf diese Version zurücksetzen und Health, HTTPS/Auth und QMD prüfen. Vault und State nur bei tatsächlich beschädigten Daten aus der konsistenten Sicherung wiederherstellen, damit spätere Nutzerdaten erhalten bleiben. Die Caddy-CA nicht neu erzeugen. Eine produktive Umschaltung erfolgt erst nach ausdrücklicher Freigabe.

## Neustart und Wiederherstellung am 22.10.2026 (Schritt 4, isoliertes Dev)

- Der temporäre Dev-Container wurde nach einem lokalen Vault-Git-Baseline-Commit gestoppt. Ein Archiv von Test-Vault und Test-State enthielt 74 reguläre Dateien, hatte Modus 0600 und SHA-256 `e0db036248ba40f4eafeb1f0356b28801d994cd481e21634bd0ae1391b54d92f`. Archiv und Dateimanifest wurden vor dem Rückweg geprüft; es enthielt ausschließlich gekennzeichnete Dev-Testdaten und deren QMD-State.
- Nach dem Neustart desselben Containers waren Vault und State bytegleich, die Vault-Git-Arbeitskopie sauber und die lokale Autorenkennung vorhanden. `/healthz` und QMD waren erreichbar; die eigene Collection blieb `secbrain-step3-check`.
- Das geprüfte Archiv wurde in ein zweites, getrenntes Verzeichnis entpackt: 74/74 Dateihashes stimmten. Ein zweiter Container mit dieser Kopie meldete Health 200, QMD `available:true`, einen Treffer für die bekannte Testquelle, sauberen Git-Status und lokale Git-Konfiguration. Nach seinem Start änderte sich nur die Git-interne Indexdatei durch Stat-Refresh; Vault-Inhalte und QMD-State blieben bytegleich.
- Main, bisheriges Dev und die beiden Testcontainer hatten getrennte Vault-/State-Mounts; Main blieb `healthy`, Vault-HEAD `bdb8bde`, Git-Status leer. Der produktive HTTPS-Proxy verwendete weiter den persistenten CA-Mount `/volume1/docker/secbrain/secbrain-main/tls-data:/data` und hatte 0 Neustarts. Kein Main-Dienst wurde für die Probe neu gestartet.
- Ressourcenmaßnahme: Die zuvor gemessene Swap-Nutzung bleibt ein Beobachtungspunkt, löste bei gesunden Containern und 0 Neustarts aber keinen Umbau aus. Vor einem Main-Rollout sind neue Main-Sicherung, exakter Image-/Commit-Abgleich und Rückwegprüfung erforderlich. Die temporären Testcontainer, Testdaten und die Prüfsummen-Sicherung werden nach dem Nachweis entfernt.

## Kernabläufe im isolierten Dev am 22.10.2026 (Schritt 3)

- Ein temporärer NAS-Container `secbrain-step3-check` verwendet das bestehende Image mit dem Schritt-2-Code als schreibgeschütztem Einzeldatei-Mount sowie eine eigene Test-Vault, einen eigenen State und die QMD-Collection `secbrain-step3-check`. Er bindet nur an NAS-Loopback `127.0.0.1:18012`; Main und der bestehende Dev-Dienst blieben unverändert.
- Angemeldete Oberfläche, Frontend-Skript, Status, Graph, Regelwerk und Wissensradar antworteten mit HTTP 200; die API ohne Anmeldung mit 401. QMD war verfügbar. Freier Chat lieferte sichtbaren Inhalt; mit dem bekannten Testbegriff erschien genau eine QMD-Quelle aus der Test-Vault. Die lesenden Aufrufe änderten keine Vault-Datei.
- DokuLader im laufenden Dev: ein echtes einseitiges PDF erzeugte Original, Seitenstück und Inbox-Manifest; eine öffentliche Dokumentations-URL wurde importiert; ein kleines ZIP mit 100 Markdown-Dateien wurde samt Original angenommen. Ein ZIP mit nur zwei Dateien wurde entsprechend der dokumentierten Paketgrenze abgewiesen. Alle Testartefakte liegen ausschließlich in der temporären Dev-Vault.
- Wissensradar: Ein Testthema wurde mit fünf Quellen recherchiert und als konkreter Zielseiten-Vorschlag an Station 06 übergeben. Ablehnung ließ die Vault bytegleich; eine erneute Übergabe und Freigabe änderte nur die vorgesehene Zielseite und erzeugte das Vault-Log sowie abgeleitete Indizes. Der Lauf zeigte `completed`.
- **Restfehler P2:** Die sichtbaren Menüeinträge „Scanner“, „Validierung“ und „Reports“ sind in der ausgelieferten Oberfläche nicht mit `data-view` oder einer Aktion verbunden. Sie sind derzeit keine bedienbaren Funktionen. Für diese drei Bereiche liegt daher kein Funktionsnachweis vor; Umsetzung beziehungsweise eindeutige Kennzeichnung benötigt eine gesonderte Produktentscheidung. Keine unbelegte Backend-Funktion wurde dafür erfunden.
- Nächster Arbeitspunkt: Schritt 4, Neustart und Wiederherstellung in dieser isolierten Dev-Instanz mit Prüfsummen-Sicherung. Kein Main-Rollout.

## Fehler nach Freigabe abgesichert am 22.10.2026 (Feature-Branch, noch kein Rollout)

- Die früheren Fehler wurden in getrennten temporären Git-Dev-Vaults reproduziert: fehlende Autorenkennung fiel erst beim Commit auf, ein scheiternder Indexer ließ archivierte Quellen und uncommittete Teiländerungen zurück. Main- und bestehende Dev-Vault blieben unangetastet.
- Der Feature-Branch prüft Git-Autor und Committer vor Analyse und nochmals vor Anwendung. Er verweigert vorhandene gestagte Änderungen, committet nur Laufpfade und lässt einen späteren Inbox-Eingang außerhalb des Commits. Nach Indexer- oder Commitfehler stellt er eigene Inbox-, Vorschlags-, Log- und Indexdateien auf die gesicherten Bytes zurück; bei unerwartet veränderten Laufdateien stoppt er ohne Überschreiben. Ein State-Marker veranlasst vor dem nächsten Lauf einen QMD-Wiederaufbau und verschwindet erst nach Erfolg.
- Regressionen: fehlende Identität, Indexer-Abbruch, unveränderte Wiederholung nach Reparatur, spätere Inbox-Datei, fremd gestagte Änderung, veränderte Inbox, vorhandenes Archivziel und Konflikt beim Rückweg. Der spätere Review ergänzte weitere Gegenproben im Abschnitt oben.
- Isolierter NAS-Container mit dem Feature-Code und eigenem Vault/State: Identität vor Schreibbeginn blockiert, Indexerfehler zurückgerollt, QMD-Marker vor Wiederholung abgearbeitet, erneuter Lauf mit sauberem Vault-Commit abgeschlossen. Separat lief der echte produktive Indexer in einem netzlosen Testcontainer mit eigener QMD-Collection; der QMD-Wiederaufbau gelang und temporäre Vault-Indexdateien wurden wiederhergestellt. Beide Testverzeichnisse und Container wurden entfernt. Das Main-Image blieb `a9f498b`; kein Main-Rollout.
- Nächster Arbeitspunkt: Schritt 3 des Hauptsystemplans, die noch nicht belegten Kernabläufe in isoliertem Dev prüfen. Vor einem Main-Rollout bleiben Branch-Review, exakte Sicherung und ausdrückliche Freigabe erforderlich.

## Hauptsystem-Abgleich am 22.10.2026 (Schritt 1, lesend)

- Lokaler Code-Checkout: Feature-Branch `codex/secbrain-hauptsystem-resilience` auf `5b3ffaa`; `origin/main` steht auf `caafdda`. Die elf lokalen Zusatzcommits betreffen Odysseus, keinen neuen Watcher-Rollout. Beide bislang unversionierten Plan-Dateien bleiben erhalten.
- NAS-Main: Projekt `secbrain-main`, Image `secbrain-dashboard:a9f498b` (ID `sha256:251b8bba…`), Quelle `watcher-main-a9f498b`, Health `healthy`, Neustarts 0. Von 109 regulären Dateien entsprechen 107 bytegleich `a9f498b`; die zwei Betriebsdokumente entsprechen dem späteren `origin/main`. Main-Vault und State sind separat gemountet; Vault-HEAD `bdb8bde`, Git-Status 0 Einträge, lokale Autorenkennung gesetzt. QMD ist verfügbar (`secbrain-main`), Ollama-Ziel `192.168.0.116:11434`, Modell `smtek/Qwen3.8-27B:Q2_K_XL`.
- Main-HTTPS auf `192.168.0.79:18443`: TLS-Prüfung erfolgreich. `/healthz` meldet 200; Oberfläche, `/api/status` und Retrieval-Status ohne Anmeldung 401, mit Anmeldung 200. Interner HTTP-Port bindet nur an `127.0.0.1:18080`.
- Bestehendes NAS-Dev: eigenes Projekt, Vault und State, Image `secbrain-dev-dev` (ID `sha256:a88fb90b…`), `healthy`, Neustarts 0, Port nur `127.0.0.1:18011`. Es ist ein Altstand vom 20.10.: `/healthz` fehlt, `/api/status` ist ohne Anmeldung erreichbar, QMD meldet `available:false`/„QMD wurde nicht gefunden“, und Git fehlt im Container. Die Dev-Vault hat 112 Status-Einträge und keine lokale Git-Autorenkennung. Dieser Dienst eignet sich nicht als Prüfbasis für den aktuellen Watcher; seine Daten werden nicht verändert.
- NAS-Ressourcen beim Abgleich: 3.889 MiB RAM, 620 MiB verfügbar; 2.491 von 4.383 MiB Swap belegt. Main, Dev, Hermes und Odysseus hatten jeweils 0 Container-Neustarts; keine OOM-Meldung bei Hermes/Odysseus. Kein Eingriff allein aus diesem Messwert.
- Priorität: **P1** Fehler nach Station-06-Freigabe in einer frischen isolierten Dev-Instanz reproduzieren und Wiederanlauf festlegen; **P1** bestehenden Dev-Altstand getrennt behandeln, ohne seine 112 Vault-Änderungen zu übernehmen; **P2** übrige Kernabläufe und Wiederherstellung prüfen. Der bestandene Lauf `WL-BDC8C469` wird ohne verhaltensrelevante Änderung nicht wiederholt.

## Abgeschlossener produktiver Browser-Loop am 22.10.2026

- NAS-Main läuft mit `secbrain-dashboard:a9f498b` aus PR #9, Quellbaum
  `/volume1/docker/secbrain/secbrain-main/watcher-main-a9f498b`. Alle 109
  versionierten Dateien stimmten vor dem Build per SHA-256 mit GitHub-`main`
  überein. HTTPS und Container-Healthcheck sind grün; der angemeldete
  Retrieval-Endpunkt meldet QMD `available: true`, Collection `secbrain-main`.
- Der über die Weboberfläche gestartete Lauf `WL-BDC8C469` erreichte nach
  Station-06-Freigabe alle 12 Stationen und zeigte **FERTIG**. Die Testnotiz
  wurde bytegleich (SHA-256
  `2119649a2c63bb9e9ad58bd7f1ed61c8eec8da3b806c8ab4dca34e7423ad9838`)
  nach `06 Archiv` verschoben. Quellenseite, Vault-Vorschlag, Log und Index
  wurden erstellt bzw. aktualisiert; die QMD-Indexaktualisierung war erfolgreich.
  Der lokale Main-Vault-Commit lautet `bdb8bde`; sein Git-Status ist leer.
  Der freigegebene State-Vorschlag steht auf `umgesetzt` und hat Modus 0600.
- Vor dem erfolgreichen Lauf schlug der Commit von `WL-1E96406E` wegen einer
  fehlenden Git-Autorenkennung fehl. Der Teilstand wurde unter
  `/volume1/docker/secbrain/backups/secbrain-main-pre-commit-retry-20261022.tar.gz`
  gesichert (SHA-256
  `f1fc67c5dbd9e4e057d07142052743e4c9a99ced8628ac6a0fcf4a1f59a7860e`,
  Modus 0600) und kontrolliert zurückgesetzt. Nur für das Main-Vault-Repository
  wurde `SECBrain Watcher <watcher@local.invalid>` als lokale Git-Identität
  eingetragen. Die Governance-Vault blieb unberührt.
- Vor dem Indexer-Fix wurde der damals fehlgeschlagene Teilstand unter
  `/volume1/docker/secbrain/backups/secbrain-main-partial-loop-20261022.tar.gz`
  gesichert (SHA-256
  `69c70053f3901ca47629b7119d2e08c48fb68791a80da38d5a310e37ace3ecb5`,
  Modus 0600). Vor dem Rollout von PR #9 lag zusätzlich die bereinigte
  Main-Sicherung unter
  `/volume1/docker/secbrain/backups/secbrain-main-pre-indexer-fix-20261022.tar.gz`
  (SHA-256 `3d2898e1ee5a014873159242509a936021bc1857529f00d5cb735d925665073e`,
  Modus 0600). Das vorige Image ist als
  `secbrain-dashboard:rollback-before-indexer-fix-20261022` markiert.

## Folgefehler beim produktiven Loop am 22.10.2026

- Nach PR #8 (Merge `43e9897`) und gesichertem NAS-Main-Rollout durchlief
  der Browser-Lauf `WL-5D833260` Stationen 01–06. Vor der Freigabe war nur
  die Testnotiz in `01 Inbox` unversioniert; der Vorschlag lag mit Modus 0600
  im State. Nach der Freigabe archivierte der Watcher die Notiz und legte
  Quellenseite, Vault-Vorschlag und Logeintrag an. Der Indexer stoppte wegen
  seines alten Standardpfads `/home/secbrain/Dokumente/SecBrain` auf dem
  schreibgeschützten NAS-Container; es erfolgte kein Vault-Commit.
- Der damalige Teilstand im Main-Vault wurde anhand der Testartefakte
  kontrolliert auf den Zustand vor der Freigabe zurückgesetzt. Eine Sicherung von Quellstand, Vault und
  State liegt unter
  `/volume1/docker/secbrain/backups/secbrain-main-pre-ollama-fix-20261022.tar.gz`
  (SHA-256 `ed77eb9637cd8f860d857f6d667bbed52e34c88ffc6e11d3bd90e745be93e006`,
  Modus 0600). Das vorige Image trägt den Tag
  `secbrain-dashboard:rollback-before-ollama-fix-20261022`.
- Der Watcher setzt künftig `SECBRAIN_VAULT` explizit auf seinen aktiven
  Vault-Pfad und `SECBRAIN_QMD_EMBED=0` für die vorhandene BM25-Laufzeit.
  Ein Regressionstest scheiterte vor dem Fix und bestand danach; insgesamt
  bestanden 68 Tests und 3 Subtests. Ein isolierter NAS-Container führte
  das echte Vault-Indexer-Skript mit separatem Vault und State aus. Graph,
  Suchindex und eigene QMD-Kollektion wurden erfolgreich erstellt.

## Produktiver Browser-Loop und Ollama-Fix am 22.10.2026

- Die interne Testnotiz `SECBrain-Loop-Browser-Test-2026-10-22.md` wurde über
  die produktive HTTPS-Weboberfläche nach `01 Inbox` geladen. SHA-256 von
  Upload und lokaler Vorlage stimmen überein. Der Lauf `WL-CE57F499` stoppte
  an Station 01 mit „Ollama hat keine Chat-Antwort geliefert“; der Vault hatte
  danach ausschließlich die unversionierte Testnotiz, keine Vorschlagsdatei.
- Main zeigte bereits auf den richtigen KI-Server `192.168.0.116:11434` und
  das dort installierte Modell `smtek/Qwen3.8-27B:Q2_K_XL`. Der echte Prompt
  von Station 01 ergab ohne `think: false` nur `thinking` (512 von 512
  Ausgabetokens), mit `think: false` einen sichtbaren `content` (332 Tokens).
- Der Connector fordert deshalb sichtbare Chatantworten mit `think: false`
  an. Ein Regressionstest reproduzierte den Fehler vor dem Fix. Danach
  bestanden lokal 67 Tests und 3 Subtests. Ein isolierter NAS-Container mit
  dem geänderten Connector erhielt vom bisherigen Modell auf einen 5267
  Zeichen langen Prompt eine sichtbare Antwort.
- Der Fix wurde mit PR #8 nach `main` gebracht und auf NAS-Main ausgerollt.
  Der vollständige Browser-Loop ist oben dokumentiert.

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
  wurde damals auf NAS-Main ausgerollt. Der später abgeschlossene Browser-Test
  ist oben dokumentiert.

## Vorheriger Produktivstand nach PR #6 am 22.10.2026

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
