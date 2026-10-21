# SECBrain-HTTPS auf eigenen Geräten

Produktiver LAN-Zugang: `https://192.168.0.79:18443`.

Die lokale Zertifizierungsstelle wurde am 22.10.2026 auf dem NAS erzeugt.
**Nur das öffentliche Zertifikat**
`/Users/mariuskahl/SecBrain-CA-2026-10-22.crt` verteilen. Der private
CA-Schlüssel bleibt auf dem NAS. Vor dem Vertrauen den SHA-256-Fingerabdruck
des Zertifikats prüfen:

```text
D4:25:0B:54:9A:01:36:A9:10:E3:2B:87:A9:27:54:58:72:5B:2F:CE:2A:9D:5C:39:AF:DD:FC:B7:53:C7:A2:40
```

## MacBook

Das Zertifikat wurde am 22.10.2026 dem Benutzer-Schlüsselbund als vertrauenswürdige
CA hinzugefügt. Der native macOS-Curl-Aufruf prüfte die Verbindung ohne
Ausnahme erfolgreich. Bei einem anderen Mac das öffentliche Zertifikat in
Schlüsselbundverwaltung importieren und die SSL-Vertrauensstellung prüfen.
Der Desktop-Starter verwendet das öffentliche Zertifikat unter dem oben
genannten Pfad automatisch. Für einen anderen Speicherort
`SECBRAIN_CA_CERT=/pfad/zum/zertifikat.crt` setzen.

## iPhone

1. Das öffentliche `.crt`-Zertifikat vom MacBook per AirDrop auf das iPhone
   übertragen. Vorher den oben stehenden Fingerabdruck auf dem MacBook prüfen.
2. In **Einstellungen → Profil geladen** die Installation abschließen. Das
   installierte Profil ist unter **Allgemein → VPN und Geräteverwaltung** sichtbar.
3. Unter **Einstellungen → Allgemein → Info → Zertifikatsvertrauenseinstellungen**
   für diese CA **volles Vertrauen** aktivieren.
4. In Safari die HTTPS-Adresse öffnen. Erst wenn keine Zertifikatswarnung
   erscheint, die Main-Zugangsdaten aus der geschützten Benutzerdatei eingeben.

Die manuelle Profilinstallation und die gesonderte SSL-Vertrauensstellung sind
in den [Apple-Anleitungen zur Profilinstallation](https://support.apple.com/de-de/102400)
und zu [Root-Zertifikaten](https://support.apple.com/de-de/102390) beschrieben.

## KI-Server (Ubuntu)

Das öffentliche Zertifikat liegt dort bereits unter
`/home/secbrain/SecBrain-CA-2026-10-22.crt`. Ein Aufruf mit `curl --cacert`
lieferte über HTTPS HTTP 200. Für systemweites Vertrauen sind administrative
Rechte erforderlich:

```bash
sudo install -m 0644 /home/secbrain/SecBrain-CA-2026-10-22.crt \
  /usr/local/share/ca-certificates/secbrain.crt
sudo update-ca-certificates
curl --fail https://192.168.0.79:18443/healthz
```

Dies entspricht der [Ubuntu-Anleitung für lokale CA-Zertifikate](https://ubuntu.com/server/docs/how-to/security/install-a-root-ca-certificate-in-the-trust-store/).

## Zugangsdaten

Main- und Dev-Zugangsdaten stehen ausschließlich in der geschützten Datei
`/Users/mariuskahl/SecBrain-Zugang-2026-10-22.txt` (Modus 0600) und in der
geschützten NAS-Compose-Umgebung. Sie gehören nicht in Git oder Screenshots.
