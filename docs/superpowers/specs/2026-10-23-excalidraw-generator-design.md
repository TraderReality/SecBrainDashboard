# Excalidraw-Diagramme per Dashboard-Anfrage

**Stand:** 23.10.2026

**Status:** Vom Nutzer am 23.10.2026 freigegeben; Umsetzungsplan erstellt

## Ziel und Grenze

Eine ausdrückliche Diagrammanfrage im SECBrain-Dashboard erzeugt mit dem bereits angebundenen lokalen Ollama-Modell eine bearbeitbare `.excalidraw`-Datei. Die produktive Datei liegt auf der NAS-Freigabe `Local/Work/excalidraw`, die auf dem NAS `/volume1/Local/Work/excalidraw` entspricht. Der Generator sieht denselben Ordner im Container unter `/work/excalidraw`. Geräte mit Zugriff auf die bestehende SMB-Freigabe sehen damit denselben Dateistand.

Die erste Version liefert nur die Excalidraw-Quelldatei. Ein eigener Excalidraw-Webeditor, öffentliche Freigabelinks, gleichzeitiges Bearbeiten, SVG-/PNG-Export und ein Vault-Commit gehören nicht zu diesem Schritt. Der bereits heruntergeladene offizielle Excalidraw-Container bleibt gestoppt: Er stellt nur den Browser-Client bereit und verarbeitet keine KI-Anfragen.

## Bestehender Stand und Wahl

Das Dashboard besitzt einen authentisierten Ollama-Chat. Main läuft auf dem NAS mit eigenem Vault- und State-Mount; Ollama läuft auf dem KI-Rechner. Auf dem NAS existiert die SMB-Freigabe `Local/Work`, jedoch noch kein Unterordner `excalidraw`. Das offizielle Excalidraw-Image enthält keinen Generator-Endpunkt. Der Hermes-Excalidraw-Skill auf dem KI-Rechner zeigt ein JSON-Format, ist aber im Hermes-NAS-Container nicht installiert; seine optionale öffentliche Upload-Funktion wird nicht verwendet.

Gewählt ist ein kleiner Generator-Dienst im selben Compose-Verbund wie das Dashboard. Damit kann allein dieser Dienst auf den Work-Ordner schreiben. Eine direkte Ausgabe durch das Dashboard würde den allgemeinen Dashboard-Container um einen weiteren Schreib-Mount erweitern. Eine Erweiterung des statischen Excalidraw-Images würde eine neue, schwer nachvollziehbare Laufzeit voraussetzen. Der Generator verwendet die dokumentierten Excalidraw-Elementregeln als Vorlage, hängt jedoch nicht vom Hermes-Gateway ab.

## Komponenten und Ablauf

1. Im bestehenden Dashboard-Chat löst nur ein ausdrücklich mit `/excalidraw ` beginnender Text die Erzeugung aus. Gewöhnliche Chat-Nachrichten bleiben beim bisherigen lesenden Ollama-Chat. Die Oberfläche zeigt vor dem Senden, dass der Befehl eine Datei auf `Local/Work` schreibt.
2. Das Dashboard ruft nach der bestehenden HTTP-Basic-Authentisierung `POST /api/excalidraw/generate` auf. Die Anfrage enthält Beschreibung und optional das ausgewählte lokale Modell, aber keinen Dateipfad. Ein leerer oder überlanger Prompt wird abgewiesen.
3. Das Dashboard leitet die Anfrage an den Generator über das interne Docker-Netz weiter. Der Generator veröffentlicht keinen Host-Port. Er ruft Ollama auf dem KI-Rechner auf und fordert ausschließlich Excalidraw-JSON an. Weder Modellantwort noch Prompt werden als Shell-Befehl ausgeführt.
4. Der Generator parst die Antwort und prüft ein begrenztes Schema: Excalidraw-Enveloppe Version 2, eine nichtleere begrenzte Elementliste, eindeutige IDs, unterstützte Elementtypen, endliche Koordinaten und Größen, begrenzte Texte sowie gültige Verweise zwischen Elementen. Dateien und eingebettete Binärdaten sind in dieser Version ausgeschlossen. Ungültige Antworten werden als Fehler gemeldet und nicht gespeichert; ein begrenzter zweiter Modellversuch darf die Validierungsfehler zurückmelden.
5. Nach erfolgreicher Prüfung erzeugt der Generator selbst einen kollisionsfesten Dateinamen. Er schreibt zunächst eine temporäre Datei im Zielordner, synchronisiert sie und veröffentlicht sie atomar ohne Überschreiben bestehender Dateien. Er antwortet mit Dateiname, SMB-relativem Pfad, Elementzahl und Modellkennung. Das Dashboard zeigt diese Angaben im Chat. Es gibt keinen API-Pfad zum freien Dateilesen oder Löschen.

## Container und Daten

Der Generator erhält einen schreibbaren Bind-Mount `/volume1/Local/Work/excalidraw:/work/excalidraw`. Auf demselben NAS ist dies ein lokaler Bind-Mount auf die SMB-Freigabe; im Container wird kein SMB-Passwort und kein CIFS-Client benötigt. Dashboard und Generator teilen nur das interne Compose-Netz. Der Generator läuft mit einer numerischen NAS-Benutzerkennung, ohne privilegierte Rechte, mit begrenztem Speicher, schreibgeschütztem Root-Dateisystem und temporärem `/tmp`. Ein Dev-Profil schreibt ausschließlich in einen separaten Testordner und berührt Main-Dateien nicht.

Der Zielordner wird vor dem produktiven Start mit passenden Rechten angelegt. Weder Prompts noch generierte Dateien liegen im Git-Repository oder in der Markdown-Vault. Pro Anfrage entsteht höchstens eine neue `.excalidraw`-Datei; vorhandene Dateien werden nie ersetzt. Ein fehlender oder nicht beschreibbarer Mount verhindert den Start beziehungsweise die Ausgabe mit klarer Fehlermeldung.

## Fehler und Sicherheit

Dashboard und Generator begrenzen Promptgröße, Modell-Antwortgröße, Laufzeit und gleichzeitige Aufträge. Der Generator akzeptiert Anfragen nur aus dem internen Netz und prüft einen gemeinsamen, ausschließlich in den Compose-Umgebungsdateien hinterlegten Dienst-Token mit konstantzeitlichem Vergleich; der Dashboard-Zugang bleibt zusätzlich durch die vorhandene Basic-Authentisierung geschützt. Der Browser erhält keine Zugangsdaten, Ollama-Zieladresse oder internen Worker-Endpunkt. Fehlermeldungen nennen den Grund, aber keine rohen Modellinhalte, Geheimnisse oder vollständigen NAS-Systempfade.

Das Modell erzeugt ausschließlich Daten. Die Anwendung entscheidet anhand fester Regeln über Dateinamen, Pfad und Schreibvorgang. Damit bleibt der Grundsatz erhalten, dass KI-Antworten selbst keine Dateisystemaktionen ausführen. Es werden keine Inhalte an excalidraw.com hochgeladen.

## Prüfung und Rollout

- Unit-Tests prüfen Promptgrenzen, gültige und ungültige Excalidraw-Strukturen, doppelte IDs, Pfad-/Dateinamen-Isolation, atomare Ausgabe und das Verhalten bei Ollama- oder Mount-Fehlern.
- API-Tests prüfen Authentisierung, normale Chat-Isolation, `/excalidraw`-Routing und die Ausgabe ohne interne Details. Frontend-Tests prüfen die Befehlsbehandlung und sichere Textanzeige.
- Ein isolierter NAS-Dev-Lauf verwendet ein Testverzeichnis unter `Local/Work`, ein echtes lokales Ollama-Modell und prüft die erzeugte Datei durch erneutes JSON-Lesen. Der Zugriff über SMB wird mit derselben Datei verglichen. Main-Vault und Main-Container bleiben dabei unverändert.
- Erst nach Code-Review, Sicherung und gesonderter Main-Rollout-Freigabe werden produktiver Bind-Mount und Dashboard-Main umgestellt. Health, Authentisierung, ein markierter Testprompt, Dateisichtbarkeit und Rückweg werden dann geprüft.

## Abnahme

Eine ausdrücklich aus dem Dashboard-Chat gestartete Anfrage erzeugt genau eine gültige `.excalidraw`-Datei unter `Local/Work/excalidraw`; der Antwortpfad benennt diese Datei. Gewöhnlicher Chat erzeugt keine Datei. Fehlerhafte Modellantwort, fehlende Modellverbindung, fehlender Mount oder Schreibfehler hinterlassen keine veröffentlichte Teil-Datei. Der Generator ist nicht direkt im LAN erreichbar und der bestehende Watcher-/Vault-Ablauf bleibt unverändert.
