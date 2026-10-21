# Übergabe

## Stand

- Der migrierte NAS-Main-Staging-Stand des SECBrain Watchers ist als
  Anwendungscode importiert.
- Dokumente aus dem geschlossenen, nicht gemergten PR #1 wurden inhaltlich
  übernommen und an den tatsächlichen Migrationsstand angepasst.
- `.env`-Dateien, alte `.git`-Historie, Vault-, Laufzeit- und Sicherungsdaten,
  virtuelle Umgebungen und Build-Abhängigkeiten wurden ausgeschlossen.
- Das Synology-Image enthält QMD 2.8.3 und initialisiert getrennte Main-/Dev-
  Indizes im jeweiligen State-Volume.
- NAS-Main wurde für diese Repository-Arbeit nicht verändert oder neu deployt.

## Prüfung

Die Python-Suite (`57 passed, 3 subtests passed`), JavaScript- und Shell-
Syntaxprüfung sowie die Compose-Konfigurationsprüfung für Main und Dev sind
bestanden. Lokaler Test und isolierter NAS-Build melden für App und Retrieval
HTTP 200; QMD 2.8.3 ist mit `available: true` verfügbar. Der temporäre
NAS-Testcontainer ist gestoppt. Der Staging-Secret-Scan fand keine Leaks;
Pfadausschlüsse und Diff-Whitespace-Prüfung sind bestanden.

## Noch offen

- Das aktuell angemeldete GitHub-Konto besitzt im Zielrepository nur
  Leserechte. `main`, Feature-Branch und Pull Request können erst nach Erteilung
  von Schreibrechten veröffentlicht werden.
- Der QMD-Abhängigkeitsaudit meldet trotz aktueller Version 8 transitive
  Advisories (6 hoch, 2 kritisch). Die betroffenen MCP-/LLM-/Git-Pfade werden
  im lokalen BM25-Betrieb nicht verwendet; der Befund bleibt bis zu einer
  bereinigten QMD-Veröffentlichung offen.
- Eine öffentliche Erreichbarkeit ist nicht vorgesehen.
- DHCP-Reservierung für die produktive NAS-Adresse bleibt eine optionale
  Betriebsverbesserung.
