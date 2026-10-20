# Übergabe

Aktueller Stand für die nächste Session, egal auf welchem Gerät.
Am Ende jeder Session aktualisieren.

## Stand
- Grundgerüst steht (README, Ordnerstruktur).
- Zweck und Anforderungen sind in README.md und CLAUDE.md beschrieben.
- Noch kein Anwendungscode, Tech-Stack nicht festgelegt.

- Betrieb auf dem NAS im Heimnetz. Dort wird ein neuer Vault aufgesetzt (kein Bezug zum alten SecVault).

- NAS ist eine Synology DS1821+ mit Docker, Details in `docs/nas.md`.

## Offene Fragen
- Welcher bereits offene Port wird genutzt, und wie grenzt sich das Deployment von dem ab, was ChatGPT gerade auf dem NAS aufsetzt?
- Ordnerstruktur und Konventionen des Vaults (Markdown-Dateien, z. B. Frontmatter, Tags).
- Später: mobiler Zugriff von unterwegs (VPN ins Heimnetz o. Ä.).

## Nächste Schritte
- Festlegen, welche Alltagsbereiche das Dashboard zuerst abdecken soll.
- Tech-Stack festlegen (zentrale Datenhaltung für identischen Stand auf allen Geräten, mobil nutzbar) und in `docs/entscheidungen.md` eintragen.
- Startbefehl und Voraussetzungen in der README ergänzen.
