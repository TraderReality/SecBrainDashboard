# Validierung des letzten abgeschlossenen Watcher-Laufs

**Stand:** 22.10.2026
**Status:** Vom Nutzer freigegeben; Umsetzungsplan erstellt

## Ziel und Grenze

Der Menüpunkt „Validierung“ soll den letzten erfolgreich abgeschlossenen Watcher-Lauf nachvollziehbar prüfen. Das gilt für Inbox-Läufe und für über Station 06 freigegebene Wissensradar-Übernahmen. Die Ansicht zeigt die bei der Übernahme vorhandenen Nachweise und bietet eine erneute, ausschließlich lesende Prüfung des jetzigen Zustands. Sie bewertet keine beliebigen Dateien der gesamten Vault und führt weder Reparaturen noch den Indexer aus.

Ein Nutzer erkennt auf einen Blick, welcher Lauf geprüft wird, was unmittelbar nach der Übernahme bestätigt wurde, was aktuell noch übereinstimmt und was sich seitdem verändert hat. „Erfolgreich indexiert“ bedeutet nur, dass der Indexer beim Lauf erfolgreich zurückkehrte. Die separate aktuelle QMD-Bereitschaft ist kein Beweis, dass jedes Dokument durchsuchbar ist.

## Bestehender Stand

- Der Executor prüft vor einer Mutation fixierte Inbox-Inhalte, Zielkonflikte und freigegebene Radar-Hashes. Nach dem Indexer prüft er erwartete Inhaltsbytes und erstellt einen begrenzten Vault-Commit. Fehler werden mit einem Transaktionsjournal zurückgerollt.
- Station 10 benennt diese Prüfungen bereits; der Orchestrator hält Ausführung und Stationsresultate bisher nur im Arbeitsspeicher. Nach einem App-Neustart ist dieser Status weg.
- Vault und Watcher-State liegen auf getrennten Mounts. Die bestehende Graph-API liest den Indexer-Export; QMD meldet einen gesonderten Retrieval-Status.

## Gewählter Ansatz

Ein einzelner versionierter Prüfnachweis liegt atomar im getrennten Watcher-State, außerhalb der Vault. Er ersetzt sich erst nach einem erfolgreich abgeschlossenen Lauf. Die API liest diesen Nachweis und berechnet bei Bedarf aktuelle, lesende Prüfungen. Die Oberfläche zeigt beide Zeitpunkte getrennt.

Eine reine Anzeige des In-Memory-Status wäre nach einem Neustart leer. Eine Rekonstruktion allein aus Git-Commits wäre bei mehreren Quelltypen und dem externen QMD-State unvollständig. Der gespeicherte Nachweis ist deshalb die kleinste verlässliche Grundlage für beide Ansichten.

## Nachweis und Lebenszyklus

Der Nachweis enthält eine Schema-Version, eindeutige Laufkennung, Laufart, Abschlusszeit, Vault-relative Pfade und SHA-256 der beim Abschluss geprüften Dateien. Bei Inbox-Läufen umfasst er jede Rohquelle im Archiv, jede erzeugte Quellenseite, den freigegebenen Vorschlag und den Vault-Log. Bei Radar-Läufen umfasst er Zielseite und Vault-Log. Er hält den erfolgreichen Indexer-Rückgabestatus, den Commit-Hash beziehungsweise den expliziten Grund für einen Lauf ohne Commit sowie den Hash des Indexer-Exports fest, falls dieser vorhanden ist. Der Rohinhalt der Quellen und Zugangsdaten werden nicht dupliziert.

Vor `apply()` beziehungsweise `apply_research()` schreibt der Orchestrator einen kleinen dauerhaften Marker „Übernahme begonnen“ in den State. Nach erfolgreicher Rückkehr erstellt er den vollständigen Nachweis; ein temporärer State-Eintrag wird vollständig geschrieben und per atomarem Austausch zum letzten Nachweis gemacht. Danach entfernt er den Marker. Ein regulär abgebrochener, abgelehnter oder fehlgeschlagener Lauf ersetzt den letzten erfolgreichen Nachweis nicht; sein Marker wird nach dem bestehenden Rückweg entfernt. Bleibt der Marker wegen eines Prozessabbruchs oder eines Fehlers beim Nachweisspeichern liegen, zeigt die Validierungsansicht einen unklaren jüngeren Lauf und **keinen** grünen Gesamtstatus des alten Nachweises. Der Vault-Commit bleibt bei einem bloßen Nachweisfehler fachlich bestehen. Der Nachweis alter Läufe wird nicht nachträglich erfunden; die erste prüfbare Version beginnt mit dem ersten erfolgreichen Lauf nach Einführung der Funktion.

## Erneute Prüfung

Eine authentisierte, lesende API lädt den letzten Nachweis. Auf Anforderung prüft sie:

1. Ob jeder verzeichnete Vault-Pfad noch existiert, unterhalb des aktiven Vault-Roots liegt und denselben Inhalts-Hash besitzt. Fehlende oder seit dem Lauf geänderte Dateien erscheinen einzeln mit Grund.
2. Ob der verzeichnete Commit im lokalen Vault-Git vorhanden und in der aktuellen Historie erreichbar ist. Bei einem dokumentierten Lauf ohne Commit wird genau dieser Status angezeigt.
3. Ob der verzeichnete Indexer-Export vorhanden, lesbares JSON und gegenüber dem damaligen Hash unverändert ist. Ein späterer regulärer Lauf kann ihn verändern; das wird als „seitdem geändert“ eingeordnet, nicht als rückwirkendes Scheitern des alten Laufs.
4. Ob die aktuelle QMD-Statusabfrage verfügbar ist. Dieser Live-Status bleibt als eigene Zeile gekennzeichnet und wird nicht mit dem historischen Indexer-Erfolg verwechselt.

Während eine Übernahme läuft, liefert die erneute Prüfung einen klaren „Lauf aktiv, später erneut prüfen“-Zustand, damit kein Zwischenstand als Fehler erscheint. Die Prüfung schreibt weder in Vault noch State, startet keinen Indexer und bereinigt keine Daten. Sie liefert getrennte Ergebnisse `bestanden`, `geändert`, `fehlt` oder `nicht prüfbar` pro Befund; ein Gesamtstatus ist nur dann grün, wenn alle anwendbaren aktuellen Prüfungen bestanden sind. Lesefehler werden mit einem verständlichen Grund angezeigt, ohne rohe Systempfade oder Dateiinhalte an den Browser auszugeben.

## Oberfläche

Der bestehende Menüeintrag „Validierung“ erhält eine eigene Ansicht. Diese zeigt Laufart, Kennung, Abschlusszeit und die historischen Übernahmeprüfungen. Eine Schaltfläche „Erneut prüfen“ startet die aktuelle Prüfung und zeigt deren Zeitpunkt und Einzelbefunde. Historische und aktuelle Ergebnisse sind optisch und sprachlich getrennt. Bei fehlendem Nachweis erscheint „Kein prüfbarer Lauf vorhanden“. Die Ansicht funktioniert auf Desktop und mobilen Geräten mit dem bestehenden Navigationsmuster.

## Sicherheit und Fehlerfälle

Die API verwendet die vorhandene Basic-Authentisierung. Für den Prüfnachweis werden nur serverseitig erzeugte, Vault-relative Pfade akzeptiert; beim Lesen werden Schema und Pfadgrenzen erneut geprüft. Symlinks und Pfadwechsel dürfen keinen Zugriff außerhalb der Vault ermöglichen. Der State-Eintrag enthält keine Geheimnisse und wird mit restriktiven Dateirechten geschrieben. Ein beschädigter oder unbekannt versionierter Nachweis wird als nicht prüfbar gemeldet.

## Abnahme

- Ein erfolgreicher Inbox- und ein erfolgreicher Radar-Lauf erzeugen jeweils einen vollständigen Nachweis; ein Neustart erhält ihn.
- Ein abgelehnter oder fehlgeschlagener Lauf ersetzt den letzten erfolgreichen Nachweis nicht; ein liegen gebliebener Übernahmemarker verhindert einen irreführenden grünen Status nach einem Abbruch.
- Unveränderte Dateien, Commit, Indexer-Export und verfügbares QMD ergeben nachvollziehbare grüne Einzelbefunde.
- Nachträgliche Änderung, Löschung, fehlender Commit, ungültiger Indexer-Export und nicht verfügbares QMD werden präzise und ohne Schreibzugriff gemeldet.
- Die Prüfung während einer aktiven Übernahme und ein fehlender beziehungsweise beschädigter Nachweis liefern keinen scheinbaren Erfolg.
- API und Oberfläche bleiben hinter der bestehenden Anmeldung; die NAS-Main-Instanz wird durch die Implementierung nicht automatisch umgestellt.
