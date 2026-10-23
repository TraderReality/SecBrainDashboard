# NAS-Main-Rollout: Excalidraw-Generator

**Stand:** 23.10.2026. **Status:** vorbereitet, noch nicht freigegeben oder ausgeführt.
**Code:** Draft-PR #15, Branch `codex/excalidraw-generator`. Den endgültigen
Commit und Tree unmittelbar vor dem Rollout erneut mit dem geprüften Stand
vergleichen.

## Ist-Stand und geplante Änderung

- NAS-Main: `secbrain-main-main-1`, Image
  `sha256:a4d76bb4b82009000c289144b3ce38128700dae1cc4d84c8be3e2648db6e50d9`,
  Quelle `/volume1/docker/secbrain/secbrain-main/watcher-main-16f8d84`, gesund.
- HTTPS-Proxy: `secbrain-main-https-main-1`, Image
  `sha256:f77f856a30f0004200b36b322d61da17fade31e24875699d77fb968399b9eb77`,
  laufend. Seine CA und der bisherige HTTPS-Port bleiben erhalten.
- Vorhandene Main-Mounts: `/volume1/docker/secbrain/secbrain-main/main/vault:/vault`,
  `/volume1/docker/secbrain/secbrain-main/main/state:/state`, aktueller
  Quellenordner `:/source:ro`. Diese Mounts bleiben bestehen.
- Hinzu kommt ein eigener privater Worker mit
  `/volume1/Local/Work/excalidraw:/work/excalidraw` und internem Port 8090.
  Der Dashboard-Container erhält nur interne Worker-URL und Token, keinen
  zusätzlichen Schreib-Mount. Der Work-Ordner wird vor dem Start mit
  Schreibrecht für UID 1026/GID 100 angelegt.
- Der geschützte Main-Env-Pfad ist für den SSH-Deploy-Nutzer nicht direkt
  lesbar. Bestehende Laufzeitwerte können bei der freigegebenen Umstellung
  im NAS-Prozess aus `docker inspect` übernommen werden, ohne sie auszugeben.
  Der neue Main-Token sowie Compose-pflichtige Dev-Testwerte werden in einer
  neuen geschützten Env-Datei (0600) erzeugt; keine Secrets kommen in Git,
  Shell-Ausgabe oder Bericht.

## Freigabepflichtige Reihenfolge

1. PR #15 und finalen Tree prüfen; NAS-Dev-Nachweis aus `docs/uebergabe.md`
   gegen den finalen Stand abgleichen. Compose mit geschützter Main-Env-Datei
   und `--profile main config --quiet` vorab prüfen. Den neuen Work-Ordner,
   dessen Besitzer/Rechte und die lokale Ollama-Verbindung kontrollieren.
2. Main und HTTPS-Proxy kontrolliert stoppen. Quellbaum, Compose-Konfiguration,
   Main-Vault, Main-State und TLS-Daten konsistent in einem neuen Archiv unter
   `/volume1/docker/secbrain/secbrain-main/backups/` sichern. Archiv auf
   Lesbarkeit, Inhalt, Modus 0600 und SHA-256 prüfen. Aktuelles Dashboard-Image
   mit einem eindeutigen Rollback-Tag behalten.
3. Exakt den geprüften PR-Tree in einen **neuen** NAS-Quellenordner kopieren,
   beide neuen Images bauen und deren IDs notieren. Compose-Projekt
   `secbrain-main` mit `main`, `excalidraw-main` und `https-main` aus diesem
   Ordner starten. Kein bestehender Vault-, State- oder TLS-Inhalt wird ersetzt.
4. Main- und Worker-Health, Neustartzähler, HTTPS-Zertifikatsprüfung mit der
   bestehenden CA und HTTP 401 ohne Anmeldung/200 mit Anmeldung prüfen.
   Einen markierten `/excalidraw`-Testprompt senden; die zurückgegebene Datei
   als Excalidraw-v2-JSON lesen und ihren SHA-256 über Worker und SMB
   vergleichen. Einen normalen Chat-Aufruf ohne neue Diagrammdatei prüfen.
   Den Vault-Git-HEAD und den Status vor/nach der Probe vergleichen.
5. Bei Abweichung Main und Proxy stoppen und den vorherigen Compose-Stand mit
   dem markierten alten Image wieder starten. Vault/State/TLS nur bei
   nachgewiesener Beschädigung aus dem konsistenten Archiv zurückspielen;
   bereits erzeugte Work-Dateien nicht still löschen. Die CA niemals neu
   erzeugen. Danach Health, HTTPS/Auth und QMD erneut prüfen.

Dieser Plan beschreibt eine produktive Unterbrechung für die konsistente
Sicherung und mindestens eine neue Testdatei auf `Local/Work/excalidraw`.
Beide Schritte benötigen die gesonderte Main-Rollout-Freigabe.
