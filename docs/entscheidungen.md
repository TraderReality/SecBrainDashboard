# Entscheidungen

Kurze Einträge: Datum, Entscheidung, Grund.

## 2026-10-22: Vault-Scanner und gemeinsame Schreibprüfung

Der Scanner vergleicht SHA-256-Inventare mit dem letzten vollständig geprüften
Stand. Der erste vollständige Scan legt die Basis an; unvollständige Versuche
behalten die vorherige Basis. Die Ansicht zeigt Vergleichsbasis, jüngsten Versuch,
Fortschritt, neue/geänderte/entfernte Dateien sowie technische und KI-Befunde
getrennt. Bei Modellfehler, unklarem Urteil, fehlendem Bericht oder ausstehender
App-Übernahme bleibt die Anzeige ohne grünen Gesamterfolg. Scanner- und Laufstatus
lesen dafür auch den dauerhaften Übernahmemarker; ein nach Neustart ruhender
Orchestrator hebt ihn nicht auf. Ein nicht lesbarer Markerstatus bleibt unklar.
Die Statusabfrage endet
nach höchstens 120 Abfragen mit je 2 Sekunden Abstand; „Aktualisieren“ setzt sie fort.

Unveränderliche JSON-Berichte liegen in der aktiven Vault unter
`09 Werkzeuge/Scanner-Berichte/`. Ein begrenzter Vault-Git-Commit enthält nur den
neuen Bericht; fremde gestagte und ungesicherte Änderungen bleiben erhalten.
Erst nach dauerhaft veröffentlichtem Bericht und Commit wird eine vollständige
Vergleichsbasis freigegeben. Der Bericht ist eine eng begrenzte Systemoperation,
kein allgemeiner Weg an der Schreibprüfung vorbei. Er enthält Hashes und
Befunde, keine Kopien roher Dokumentinhalte.

Der gemeinsame `VaultWriteGuard` prüft konkrete Änderungen und die vollständige
AGENTS-Regelquelle vor Inbox-/Radar-Übernahme, Upload, DokuLader und AGENTS-Speichern.
Verstöße oder Unklarheit sperren diese App-Schreibwege (fail closed); externe
Programme unterliegen dieser Sperre nicht. KI-Bewertung bietet keine absolute
Garantie semantischer Regelkonformität. Der Scanner ist eine Momentaufnahme.

Materielle Grenze dieses Stands: echte PDF-/ZIP-Dateien, andere binäre,
übergroße oder für das Modell unverarbeitbare Inhalte sind nicht vollständig
bewertbar. Betroffene App-Übernahmen antworten mit HTTP 409 ohne Vault-Schreibzugriff.
Da die Prüfung den vorhandenen Vault-Kontext einbezieht, können solche Bestände
oder ausgeschöpfte Modellbudgets auch fachlich unbeteiligte Änderungen sperren.

Der Branch baut auf der Validierung aus PR #13 auf; diese Abhängigkeit muss bei
Integration berücksichtigt werden. Kein Merge und kein NAS-Main-Rollout sind
Teil dieser Umsetzung. Für den zunächst fehlenden Vault-Indexer ist inzwischen
ein geprüfter Paket-Fallback vorhanden (siehe folgende Entscheidung).

## 2026-10-22: Fehlenden Vault-Indexer durch Paket-Fallback ergänzen

`09 Werkzeuge/indexer.py` bleibt bei Vorhandensein maßgeblich. Nur wenn diese
Datei fehlt, führt der Watcher `dashboard/backend/loop/vault_indexer.py` aus;
fehlen beide Dateien, benennt die Fehlermeldung beide Pfade. Ein fehlerhaftes
Vault-Skript wird nicht durch den Fallback übergangen. Es gibt keine Migration
oder Skriptkopie in die Vault.

Die vom Nutzer gelieferte lesbare Quelle vom 23.08.2026 wurde mit dokumentierter
SHA-256 übernommen und um den ausdrücklichen Ausschluss des gesamten relativen
Ordners `09 Werkzeuge/Scanner-Berichte/` ergänzt. Der Ausschluss gilt für alle
aus diesem Inventar erzeugten Sichten einschließlich QMD-Manifest; echte
isolierte Subprozess-Tests prüfen JSON-Bericht, Markdown-Köder und reguläre
Notizen. Neue QMD-Kollektionen erhalten explizit die Markdown-Maske `**/*.md`.
Die unabhängige QMD-Dateisuche und bestehende QMD-Konfiguration werden nicht
umgebaut; die Maske schließt JSON-Berichte aus, aber keine dort abgelegten
Markdown-Dateien. Vorhandene Vault-Skripte benötigen ihre eigene Prüfung.

Die externe Quelldatei bleibt unverändert, die mitgelieferte `.pyc` wird nicht
ausgeführt. Diese Umsetzung bestätigt keine aktuelle NAS-Indexer-Version und
ist noch nicht auf NAS-Main ausgerollt. Eine später verfügbare neuere Quelle
kann andere Export- oder QMD-Eigenschaften haben; vor einem Austausch müssen
diese verglichen werden. Herkunft und Testnachweis stehen in der Übergabe und
im Indexer-Fallback-Bericht.

## 2026-10-22: Validierung des letzten abgeschlossenen Laufs vorbereiten

Die erste bedienbare Validierungsansicht bezieht sich auf den letzten erfolgreichen
Inbox- oder Wissensradar-Lauf. Sie zeigt den gespeicherten Übernahmenachweis und
prüft auf Anforderung Dateien, Commit, Indexer-Export und QMD erneut lesend.
Ein dauerhafter Marker verhindert nach einem Prozessabbruch einen irreführenden
grünen Altstatus. Ein neuer erfolgreicher Lauf ersetzt den Nachweis; nach
einem kontrolliert fehlgeschlagenen Lauf bleibt der vorherige erhalten.
Ein späterer Lauf kann den Indexer-Export ändern; die Ansicht kennzeichnet
dies als Änderung seit dem geprüften Lauf, nicht als damaligen Indexer-Fehler.
Der abgestimmte Entwurf steht unter
`docs/superpowers/specs/2026-10-22-letzten-lauf-validieren-design.md` und wurde
vom Nutzer freigegeben. Der Umsetzungsplan liegt unter
`docs/superpowers/plans/2026-10-22-letzten-lauf-validieren.md`.

## 2026-10-22: Geprüften Watcher nach Main übernehmen

Nach Abschlussreview, bestandenem Testlauf und ausdrücklicher Freigabe wurde
PR #11 gemergt und das exakt getestete Image auf NAS-Main ausgerollt. Eine
konsistente Sicherung einschließlich TLS-CA entstand bei gestopptem Main und
Proxy. Das vorige Image und sein Quellbaum bleiben als Rückweg erhalten.
Wegen der geänderten Freigabe- und Commitstrecke wurde der gesamte
12-Stationen-Ablauf mit einer markierten Testquelle produktiv geprüft.
Nachweise und Sicherungsprüfsumme stehen in `docs/uebergabe.md`.

## 2026-10-22: Freigabe-Fehler mit begrenztem Commit und Rückweg behandeln

Git-Autor und Committer werden vor einem Watcher-Lauf geprüft. Ein Lauf stagiert
und committet nur seine eigenen Pfade; bereits gestagte fremde Änderungen
blockieren ihn. Die Inhaltsbytes werden vor der Mutation in einem dauerhaft
geschriebenen Journal im getrennten State gesichert. Ein Git-Commit entsteht
aus genau den geprüften Bytes und literalen Dateipfaden in einem temporären
Index; der Git-HEAD wird nur bei unverändertem Ausgangs-HEAD gesetzt.
Bei Fehler oder Prozessabbruch stellt der nächste Start eigene Vault-Dateien
kontrolliert wieder her. Fremd geänderte oder gestagte Laufdateien bleiben
bei einem Konflikt erhalten und erfordern manuelle Prüfung. Das gilt auch
für den Wissensradar-Freigabepfad. Vor einer möglichen Indexänderung wird
QMD als unsynchron markiert und vor dem nächsten Lauf neu aufgebaut.

## 2026-10-22: Indexer auf den aktiven Vault festlegen

Der Watcher setzt beim Start des Vault-Indexers `SECBRAIN_VAULT` auf seinen
aktiven Vault-Pfad. Sonst verwendet das migrierte Indexer-Skript den alten
KI-Server-Pfad des Governance Layers. Für das NAS wird nur der QMD-BM25-Index
aktualisiert; `SECBRAIN_QMD_EMBED=0` verhindert einen unkonfigurierten
Vektor-Modell-Download.

## 2026-10-22: Sichtbare Ollama-Chatantwort für den Watcher anfordern

Der Ollama-Chataufruf setzt `think: false`. Beim produktiven Loop-Test lieferte
das bisherige Qwen-Modell für die lange Stationsanweisung nur `thinking`, aber
keinen `content`, weil `num_predict` ausgeschöpft war. Mit demselben Prompt
und deaktiviertem Denkmodus lieferte das Modell eine auswertbare Antwort.
Die Ollama-Adresse auf dem KI-Server war bereits korrekt.

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

## 2026-10-22: HTTPS über NAS-IP und lokale CA

Ein eigener Domainname ist derzeit nicht vorhanden. Das Main-Profil erhält
deshalb einen separat gepinnten Caddy-Proxy auf `192.168.0.79:18443`, der
Zertifikate für die NAS-IP mit einer lokalen CA ausstellt. Der direkte
App-Port wird fest an `127.0.0.1` gebunden; der Proxy erreicht die App über
das interne Compose-Netz. Der CA-Speicher wird außerhalb des Repositorys
persistiert und gesichert. Auf jedem Client muss nur das öffentliche
Stammzertifikat nach Fingerabdruckprüfung vertraut werden. Der private
CA-Schlüssel bleibt auf dem NAS. Ein isolierter NAS-Test hat HTTPS,
Authentisierung und QMD zusammen geprüft. Main wurde anschließend auf HTTPS
umgestellt.

## 2026-10-22: Loop-Vorschläge bis zur Freigabe im State halten

Die Stationen 01–05 schreiben ihren Vorschlag in den getrennten Watcher-State.
Eine Ablehnung verändert den Vault nicht. Erst nach Station-06-Freigabe wird
der Vorschlag zusammen mit den freigegebenen Änderungen im Vault abgelegt und
committet. So erzeugt die Analyse keine ungesicherten Vault-Änderungen und
blockiert spätere Läufe nicht selbst.

## 2026-10-22: Main-Vault lokal baselinefähig halten

Die vor der Migration entstandenen Vault-Änderungen wurden erst nach einer
geprüften NAS-Sicherung als lokaler Commit erfasst. Der Main-Vault wird nicht
in das Anwendungs-Repository oder nach GitHub übertragen. Im Vault ignoriert
`.gitignore` Python-Zwischendateien; die lokale Git-Konfiguration ignoriert
reine Dateimodusabweichungen auf Synology. So kann der Watcher einen sauberen
Ausgangsstand vor jedem produktiven Loop-Lauf prüfen.
