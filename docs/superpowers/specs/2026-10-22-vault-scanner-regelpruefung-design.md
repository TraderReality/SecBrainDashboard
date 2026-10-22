# Vault-Scanner mit Regelprüfung

**Stand:** 22.10.2026
**Status:** Entwurf nach Freigabe der Architektur und der Funktionsabschnitte; schriftliche Freigabe ausstehend

## Ziel und Zusagen

Der Menüpunkt „Scanner“ erfasst neue, geänderte und entfernte Inhaltsdateien der aktiven Vault gegenüber dem letzten vollständig abgeschlossenen Scan. Er zeigt zugleich Regelbefunde. Ein eigener Berichtsordner in der Vault hält die Ergebnisse nachvollziehbar fest. Der Nutzer möchte die Vault sauber und kontrolliert halten: prüfbare Regelverstöße sollen App-Übernahmen sperren; Änderungen außerhalb der App werden beim nächsten Scan gemeldet.

Die vollständige Vault-`AGENTS.md` ist Regelquelle für die lokale KI-Bewertung. Feste technische Schutzregeln gelten unabhängig vom Modell. Bei fehlendem Modell, unvollständigem Kontext, ungültiger Ausgabe oder unklarem Urteil wird eine App-Übernahme gesperrt und der Grund angezeigt. Eine KI kann eine inhaltlich falsche Freigabe liefern; die Anwendung darf daraus keine absolute Garantie für alle natürlichen Sprachregeln ableiten. Externe Dateizugriffe liegen außerhalb des App-Schreibschutzes.

## Bestehender Stand und Abhängigkeit

Die ausgelieferte Oberfläche zeigt „Scanner“ noch ohne Aktion. Der Vault-Connector liefert nur Zählwerte, ohne Änderungsverlauf. Die App besitzt mehrere Vault-Schreibwege: freigegebene Inbox- und Radar-Übernahmen, Inbox-Upload, DokuLader und den AGENTS-Editor. Der Watcher verlangt vor seiner Übernahme einen kontrollierten Vault-Git-Zustand. Die separate Funktion „Validierung des letzten Laufs“ liegt in PR #13; die Scanner-Implementierung baut auf dessen Stand auf, ohne den PR zu mergen oder Main auszurollen.

## Gewählter Ansatz

Ein versionierter Scanstand mit Vault-relativen Pfaden, Dateityp, Größe und SHA-256 liegt atomar im getrennten Watcher-State. Der erste vollständige Scan inventarisiert die Vault und bildet die Vergleichsbasis; er meldet den Altbestand nicht pauschal als „neu“. Spätere Scans klassifizieren `neu`, `geändert`, `entfernt` und `unverändert`; die Ansicht hebt Änderungen und Regelbefunde hervor. Ein Git-Vergleich allein würde nicht versionierte Dateien übersehen. Zeitstempel und Größe allein würden Inhaltsänderungen übersehen. Dateihashes liefern deshalb den Vergleichspunkt.

Der Scanner untersucht reguläre Dateien einschließlich Inbox, Archiv, Wissensseiten und Anhängen. Ausgeschlossen sind `.git/`, jedes `_index/`, `__pycache__/`, `*.pyc`, `.DS_Store` und der eigene Berichtsordner. Die Ausschlüsse stehen als explizite, testbare Liste im Code und im Scanbericht; weitere Dateitypen werden nicht stillschweigend ignoriert. Symlinks werden nicht verfolgt. Ein Pfad, der nach außen zeigt oder während des Lesens wechselt, wird als nicht prüfbar gemeldet und niemals außerhalb der Vault gelesen.

## Regelprüfung

Die Prüfeinheit lädt die vollständige aktuelle `AGENTS.md` ohne Abschneiden und hält ihren Hash im Ergebnis fest. Abschnitte, Aufzählungspunkte und Regelabsätze erhalten stabile Referenzen mit Quellposition. Die lokale KI bewertet jeden anwendbaren Regeltext gegen den belegten Datei- beziehungsweise Änderungskontext und liefert strukturiert `erfüllt`, `verletzt`, `nicht anwendbar` oder `unklar`, mit kurzer Begründung und Referenz. Die Anwendung kontrolliert Format, Vollständigkeit der Regelreferenzen und Zugehörigkeit der genannten Dateien. Fehlende oder widersprüchliche Antworten gelten als `unklar`. Bei einer Änderung von `AGENTS.md` werden alle vorhandenen Inhaltsdateien erneut gegen den neuen Regelstand bewertet; eine App-Änderung der Regelquelle wird gegen den alten und den vorgeschlagenen neuen Regelstand geprüft.

Daneben prüft deterministischer Code mindestens Vault-Grenzen, reguläre Dateitypen, Symlinks, zugelassene Zielpfade, unveränderte Eingaben seit der Freigabe und das Verbot nicht freigegebener Überschreibungen oder Löschungen. Fachliche Aussagen wie Herkunft, thematische Einordnung und Widerspruchsfreiheit bleiben KI-Befunde mit belegtem Kontext. Wenn erforderlicher Dateiinhalt nicht lesbar, nicht vom gewählten Modell verarbeitbar oder zu groß für eine vollständige Bewertung ist, lautet das Ergebnis `unklar`; eine unvollständige Stichprobe darf nicht als vollständig geprüft erscheinen.

## Schreibschutz der App

Ein gemeinsamer `VaultWriteGuard` erhält vor jeder Vault-Mutation der App einen konkret geplanten Änderungssatz mit Vorher-Hashes, Zielpfaden, Operation und vorhandener Freigabe. Er verwendet technische Regeln und die AGENTS-Bewertung, bevor ein Schreibweg weiterläuft. Eine Verletzung oder ein unklares Ergebnis sperrt ihn mit einem Befund; ein vorhandener Verstoß wird nicht durch eine weitere unbeteiligte Übernahme übergangen. Die betroffenen Dateien und der AGENTS-Hash werden unmittelbar vor der Mutation unter einer gemeinsamen prozessübergreifenden App-Sperre erneut geprüft. Das gilt für Watcher-Inbox, Wissensradar, Inbox-Upload, DokuLader und AGENTS-Editor. Der Schutz prüft die geplanten Änderungen, nicht bloß einen vorangegangenen allgemeinen Scan. Eine ausdrücklich freigegebene Korrektur darf durchlaufen, wenn die Vorher-/Nachher-Prüfung den vorhandenen Befund beseitigt und keine neue Verletzung oder Unklarheit erzeugt.

Alle App-Schreibwege erhalten dieselbe Entscheidungsschnittstelle; ein zusätzlicher API-Endpunkt darf sie nicht umgehen. Der Scannerbericht selbst ist eine eng begrenzte, typisierte Systemoperation: Er darf nur im festen Berichtsordner angelegt werden, enthält keinen ungeprüften freien Vault-Inhalt und wird nicht als gewöhnlicher Nutzerdokument-Write behandelt. Diese Ausnahme erlaubt auch bei einem gesperrten Regelbefund dessen Dokumentation, nicht die Änderung von Nutzerdaten. Eine externe Änderung zwischen Prüfung und Schreibzugriff kann die App-Sperre nicht verhindern; geänderte Vorher-Hashes lösen jedoch einen Abbruch statt einer stillen Übernahme aus.

## Scanablauf, Bericht und Konsistenz

Der Scan liest die Vault, vergleicht sie mit dem letzten erfolgreichen Stand und bewertet die Regeln. Ein Scan mit vollständig verarbeiteten Dateien darf auch bei gefundenen Verstößen als Scan abgeschlossen werden; der Befund bleibt gesperrt. Ein Ausfall, abgebrochene Dateilektüre oder eine unvollständige KI-Bewertung erzeugt einen Bericht über den Versuch, ersetzt aber den letzten vollständigen Vergleichsstand nicht. Der Nutzer sieht dann `nicht vollständig geprüft`, niemals einen grünen Gesamterfolg.

Berichte liegen als unveränderliche, datierte JSON-Dateien unter `09 Werkzeuge/Scanner-Berichte/`. Sie enthalten Scan-ID, Zeitpunkt, Vault-Bezug, Hash der Regelquelle, Modellkennung, Ausschlussliste, Dateikategorien und einzelne Regelbefunde mit Quellenreferenz. Rohe Datei-Inhalte und Zugangsdaten werden nicht dupliziert. Ein begrenzter Vault-Git-Commit erfasst ausschließlich den neuen Bericht und lässt fremde gestagte oder ungesicherte Änderungen unangetastet. Fehlen Git-Voraussetzungen oder schlägt das Schreiben beziehungsweise Committen fehl, wird kein vollständiger Scanstand veröffentlicht; die API meldet den Fehler. Bericht und State werden mit Scan-ID und dauerhaftem Marker so abgestimmt, dass ein Prozessabbruch weder einen scheinbaren Erfolg noch doppelte Berichte erzeugt. Der Berichtsordner wird vom Inhaltsvergleich und vom Indexer ausgeschlossen.

## API und Oberfläche

Die bestehenden Authentisierungsregeln schützen Status, Start und Berichtszugriff. `GET /api/scanner/status` zeigt letzten vollständigen Scan, aktuellen Versuch, Fortschritt und Regelstatus. `POST /api/scanner/scan` startet genau einen manuellen Hintergrundscan und gibt dessen ID zurück; ein zweiter gleichzeitiger Scan wird abgewiesen. `GET /api/scanner/reports/{scan_id}` liefert einen begrenzten Bericht ohne freie Pfadparameter. Die Scanner-Ansicht zeigt Basiszeitpunkt, Zeitpunkt des letzten Versuchs, Kategorien `neu`, `geändert`, `entfernt`, technische Verstöße, KI-Befunde und `unklar` getrennt. Jede Zeile nennt Vault-relativen Pfad, Regelreferenz und nachvollziehbaren Grund. Kein grüner Status erscheint bei unvollständigem Scan, unklarem Modellurteil oder ausstehender App-Übernahme. Die Ansicht funktioniert mit der bestehenden Desktop- und mobilen Navigation.

## Fehler und Grenzen

Fehlende oder fehlerhafte `AGENTS.md`, Modellausfall, Zeitüberschreitung, ungültiges Antwortschema und eine nicht vollständig abgedeckte Regelquelle sperren App-Übernahmen. Beschädigter Scan-State wird als nicht prüfbar angezeigt. Der letzte gültige Vergleichsstand bleibt erhalten. Bei gleichzeitiger Vault-Änderung wird der Scan als unvollständig abgebrochen und der nächste Versuch beginnt erneut. Das Scanergebnis ist eine Momentaufnahme; externe Programme können die Vault danach ändern. Die UI nennt deshalb immer den Prüfzeitpunkt.

Die KI-Bewertung ist ein begründeter Prüfhinweis, kein Beweis der semantischen Korrektheit aller Regeln. Der verbindliche technische Schutz ist auf die konkret implementierten, maschinell prüfbaren Regeln und die App-Schreibwege begrenzt. Der Bericht selbst löst keine Reparatur, keinen Indexer-Lauf und keine automatische Umordnung von Dateien aus.

## Abnahme

- Der erste Scan erstellt eine vollständige Basis und einen Bericht; der zweite erkennt neue, inhaltsgeänderte und entfernte Nutzerdateien korrekt, einschließlich nicht versionierter Dateien.
- `.git`, `_index`, Caches, Berichte und Symlink-Ziele außerhalb der Vault werden nicht als Nutzerinhalt gelesen oder als Änderung gemeldet.
- Fehlende oder neue `AGENTS.md`-Regeln führen zu erneuter Bewertung; jeder Regelabschnitt ist im Ergebnis referenziert. Modellfehler und unvollständige Bewertung bleiben `unklar` und sperren App-Schreibwege.
- Jede bestehende App-Vault-Mutation durchläuft den gemeinsamen Guard. Ein veralteter Vorher-Hash, fremder Pfad, unerlaubte Überschreibung oder Regelverstoß bewirkt keine Nutzerdatenänderung.
- Berichte bleiben nach Neustart lesbar. Abbruch zwischen Bericht, Git-Commit und Scanstand führt nicht zu einem grünen oder doppelten Abschluss. Fremde Git-Änderungen bleiben erhalten.
- API und Ansicht zeigen historische Vergleichsbasis, aktuelle Funde und unvollständige Versuche getrennt; nur ein vollständiger Scan ohne Verletzung oder Unklarheit wird grün.
