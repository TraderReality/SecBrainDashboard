# Archiv: R18–R33 Legacy-Roadmap

> **Historischer Stand, archiviert am 24. August 2026.** Dieses Dokument
> beschreibt die entfernte Vorgängerarchitektur rund um den früheren `app/`
> Block. Es ist kein aktueller Produkt-, API- oder Laufzeitvertrag. Der heutige
> Stand ist in [`../CURRENT_BETA_STATUS.md`](../CURRENT_BETA_STATUS.md)
> dokumentiert.

# SECBrain Watcher

# Productziel R16 Roadmap

## Produktcheckpoint 21.08.2026 — Watcher Beta und 3D Vault Explorer

Der eigenständige Watcher ist als erste integrierte Beta lauffähig. Der
historische R16-Plan unterhalb dieses Checkpoints bleibt als Architektur- und
Zielreferenz erhalten; der reale Produktstand ist inzwischen weiter:

- Dashboard und 12-Stationen-Loop sind als getrennte, kompakte Arbeitsansicht
  umgesetzt.
- Ollama-Modellwahl, KI-Chat, globale und stationsbezogene Wächterregeln sowie
  ein explizit startbarer autonomer read-only Lauf sind integriert.
- KI-Position, Live-Aktivität, vollständige Stationsausgaben und Stoppzustand
  werden im Frontend sichtbar gemacht.
- Der Vault Explorer ist eine eigene Seite und verwendet ausschließlich den
  bestehenden Indexer-Export der Vault.
- Der 3D-Graph besitzt Gehirnmodell, Bühne, kameragebundenen Hintergrund,
  Node-Hover/-Auswahl, animierte Kamerafahrten und einen 2D-Fallback.
- Elf organische Atlasblasen repräsentieren die obersten Vault-Ordner. Nodes
  werden innerhalb ihres jeweiligen 3D-Raums angeordnet und begrenzt.

Nächste priorisierte Produktblöcke:

1. persistente Laufhistorie und Abschlussbericht,
2. gezielte read-only Vault-Kontextauswahl,
3. menschlich bestätigbare Freigabe-Inbox,
4. robuste Wiederholung, Zeitlimits und Ollama-Ausfalltests,
5. weitere fachliche und räumliche Kalibrierung des 3D-Atlas.

Die vollständige Ist-Dokumentation steht in
`docs/CURRENT_BETA_STATUS.md` und in der aktualisierten `README.md`.

## Zweck dieses Dokuments

Dieses Dokument beschreibt die Weiterentwicklung des SECBrain Watchers
ausgehend vom aktuellen Architekturstand R15 hin zum eigentlichen
Produktziel.

Es dient als Referenz für: - Entwicklung - lokale KI-Agenten -
Architekturentscheidungen - zukünftige R16 Implementierungen

------------------------------------------------------------------------

# 1. Produktziel

Der SECBrain Watcher soll eine autonome, nachvollziehbare Vault-Pflege-
und Wissensverarbeitungsplattform werden.

Das System soll Informationen erfassen, analysieren, vergleichen,
einordnen, Vorschläge erzeugen, Freigaben verwalten und nach Bestätigung
die Vault weiterentwickeln.

Grundprinzip:

Keine unkontrollierte Änderung.

Jede Änderung benötigt: - Analyse - Bewertung - Vorschlag - Freigabe -
Integration - Protokollierung

------------------------------------------------------------------------

# 2. Aktueller Architekturstand

## R13 Application Flow

Status:

FROZEN

Verantwortung:

Die fachliche Verarbeitungskette.

Ablauf:

Processing ↓ Decision ↓ Evaluation ↓ Evidence ↓ Provenance

------------------------------------------------------------------------

## R14 Runtime Layer

Status:

FROZEN

Verantwortung:

Die Ausführungsmaschine.

Komponenten:

-   RuntimeEvent
-   RuntimeQueue
-   RuntimeDispatcher
-   RuntimeExecutor
-   RuntimeWorker
-   RuntimeLifecycle

------------------------------------------------------------------------

## R15 Observability Layer

Status:

FROZEN

Verantwortung:

Beobachtung und Nachvollziehbarkeit.

Komponenten:

-   RuntimeMetrics
-   RuntimeTrace
-   RuntimeHistory
-   RuntimeHealth
-   RuntimeFailure

------------------------------------------------------------------------

# 3. Fehlende Produkt-Ebene

Die bisherigen Ebenen bilden den Systemkern.

Es fehlt die eigentliche KI-Vault-Intelligenz.

Diese Ebene wird R16.

------------------------------------------------------------------------

# 4. R16 Vault Intelligence Layer

## Ziel

Verbindung zwischen Runtime-System und intelligentem Vault-Pflege-Loop.

R16 ermöglicht:

-   Wissen erfassen
-   Inhalte verstehen
-   Beziehungen erkennen
-   Vorschläge erstellen
-   Änderungen kontrolliert übernehmen

------------------------------------------------------------------------

# 5. R16 Architektur

    R14 Runtime
          |
          v

    R16 Vault Intelligence Layer

          |
          +-- Scanner
          +-- Analyzer
          +-- Comparator
          +-- Classification
          +-- Proposal Engine
          +-- Approval Gate
          +-- Integration Engine
          +-- Indexer
          +-- Linker
          +-- Validation
          +-- Reporting

          |
          v

    R15 Observability

------------------------------------------------------------------------

# 6. R16 Module

## R16-01 Vault Scanner

Produktziel:

Erfassen

Aufgabe:

-   neue Dateien erkennen
-   Änderungen erkennen
-   Eingänge sammeln

Keine Änderung an der Vault.

------------------------------------------------------------------------

## R16-02 Knowledge Analyzer

Produktziel:

Analysieren

Aufgabe:

-   Inhalte verstehen
-   Themen erkennen
-   Informationen extrahieren

------------------------------------------------------------------------

## R16-03 Knowledge Comparator

Produktziel:

Vergleichen

Aufgabe:

-   bestehendes Wissen prüfen
-   Duplikate erkennen
-   Konflikte erkennen

------------------------------------------------------------------------

## R16-04 Classification Engine

Produktziel:

Einordnen

Aufgabe:

-   passenden Vault-Bereich bestimmen
-   Strukturzuordnung vorbereiten

------------------------------------------------------------------------

## R16-05 Proposal Engine

Produktziel:

Vorschlag erstellen

Aufgabe:

Erzeugt:

-   Änderungsvorschläge
-   neue Dokumente
-   Verlinkungen

Keine direkte Änderung.

------------------------------------------------------------------------

## R16-06 Approval Gate

Produktziel:

Freigabe abwarten

Aufgabe:

Kontrollpunkt zwischen KI und Vault.

------------------------------------------------------------------------

## R16-07 Integration Engine

Produktziel:

Übernehmen

Aufgabe:

Nach Freigabe:

-   Dateien ablegen
-   Struktur aktualisieren
-   Beziehungen übernehmen

------------------------------------------------------------------------

## R16-08 Vault Indexer

Produktziel:

Indexieren

Aufgabe:

-   Suchindex
-   Graphdaten
-   KI-Wissensindex

------------------------------------------------------------------------

## R16-09 Knowledge Linker

Produktziel:

Verlinken

Aufgabe:

-   Wissensbeziehungen erzeugen
-   Graph erweitern

------------------------------------------------------------------------

## R16-10 Validation Engine

Produktziel:

Prüfen

Aufgabe:

-   Regeln prüfen
-   Konflikte erkennen
-   Qualität sichern

------------------------------------------------------------------------

## R16-11 Reporting Engine

Produktziel:

Protokollieren und Berichten

Aufgabe:

-   Änderungen dokumentieren
-   Statusberichte erzeugen
-   Verlauf erhalten

------------------------------------------------------------------------

# 7. R16 Entwicklungsregeln

Jede R16-Komponente benötigt:

1.  Modul
2.  Contract Test
3.  Regression Test
4.  Dokumentation
5.  Git Commit
6.  Acceptance Test
7.  Freeze

------------------------------------------------------------------------

# 8. Architekturgrenzen

Nicht erlaubt:

R16 verändert direkt:

-   R13 Fachlogik
-   R14 Runtime Steuerung
-   R15 Observability Daten

R16 nutzt diese Ebenen.

------------------------------------------------------------------------

# 9. Entwicklungsreihenfolge

Empfohlene Reihenfolge:

R16-01 Vault Scanner

↓

R16-02 Knowledge Analyzer

↓

R16-03 Comparator

↓

R16-04 Classification

↓

R16-05 Proposal Engine

↓

R16-06 Approval Gate

↓

R16-07 Integration

↓

R16-08 Indexer

↓

R16-09 Linker

↓

R16-10 Validation

↓

R16-11 Reporting

------------------------------------------------------------------------

# 10. Auftrag für lokale KI

Lese zuerst:

SECBrain_Watcher_Master_Dokumentation.md

Danach:

SECBrain_Watcher_Productziel_R16_Roadmap.md

Arbeite nur innerhalb dieser Architektur.

Jede Erweiterung muss: - nachvollziehbar - getestet - dokumentiert -
reproduzierbar

sein.

------------------------------------------------------------------------

# Ende Dokument


------------------------------------------------------------------------

# 7. Erweiterte Architekturstände


## R18 Agent Layer

Status:

FROZEN

Freeze:

R18-AGENT-LAYER-FROZEN


Zweck:

Bereitstellung einer kontrollierten Agent Runtime Architektur.


Komponenten:

- Local Model Runtime Client
- Model Registry
- Agent Core
- Agent Tool Boundary
- Agent Execution Runtime
- Agent Tool Invocation
- Agent Task Planner
- Agent Result Handling


------------------------------------------------------------------------


## R19 Memory Layer

Status:

FROZEN

Freeze:

R19-MEMORY-LAYER-FROZEN


Zweck:

Bereitstellung einer kontrollierten Memory Architektur.


Komponenten:

- Memory Object Model
- Memory Collection
- Memory Storage Boundary
- Agent Memory Access Layer
- Memory Integration Boundary
- Memory Pipeline Coordinator


------------------------------------------------------------------------


## R20 Knowledge Layer

Status:

FROZEN

Freeze:

R20-KNOWLEDGE-LAYER-FROZEN


Zweck:

Bereitstellung einer kontrollierten Knowledge Architektur.


Komponenten:

- Knowledge Object Model
- Knowledge Collection
- Knowledge Storage Boundary
- Knowledge Access Layer
- Knowledge Integration Boundary
- Knowledge Pipeline Coordinator


------------------------------------------------------------------------


# 8. Nächster Architekturabschnitt


## R21 Evidence / Provenance Layer


Status:

PLANNED


Ziel:

Aufbau einer nachvollziehbaren Evidenz- und Herkunftsschicht.


Grundprinzip:

Keine automatische Bewertung.

Keine autonome Entscheidung.

Nur strukturierte Erfassung und Referenzierung.


Geplante Verantwortung:

- Evidence Objects
- Provenance Objects
- Evidence Boundaries
- Provenance Boundaries
- kontrollierte Verknüpfung mit Memory Layer
- kontrollierte Verknüpfung mit Knowledge Layer


------------------------------------------------------------------------


# 9. R21 Evidence / Provenance Layer


Status:

FROZEN


Freeze:

R21-EVIDENCE-PROVENANCE-LAYER-FROZEN


Zweck:

Bereitstellung einer kontrollierten Evidenz- und Herkunftsarchitektur.


Komponenten:

- Evidence Object Model
- Provenance Object Model
- Evidence Collection
- Provenance Collection
- Evidence Storage Boundary
- Provenance Storage Boundary
- Evidence / Provenance Integration Boundary
- Evidence / Provenance Pipeline Coordinator


Grundprinzip:

Keine automatische Bewertung.

Keine autonome Entscheidung.

Keine automatische Herkunftsermittlung.

Nur strukturierte Erfassung,
kontrollierte Verknüpfung
und nachvollziehbare Referenzierung.


------------------------------------------------------------------------


# Architekturfluss


R18 Agent Layer

        |

        v


R19 Memory Layer

        |

        v


R20 Knowledge Layer

        |

        v


R21 Evidence / Provenance Layer

        |

        v


R22 Next Intelligence Layer


------------------------------------------------------------------------


# 10. Nächster Architekturabschnitt


## R22 Next Intelligence Layer


Status:

PLANNED


Ziel:

Aufbau der nächsten kontrollierten Intelligenzschicht
oberhalb von Memory, Knowledge und Evidence.


Grundprinzip:

Keine autonome Systemänderung.

Jede intelligente Verarbeitung bleibt:

- nachvollziehbar
- überprüfbar
- kontrolliert
- revisionsfähig


Geplante Verantwortung:

- intelligente Analyse-Schichten
- kontrollierte Entscheidungsunterstützung
- Verbindung zwischen Knowledge und Evidence
- vorbereitete Agent Intelligence Erweiterungen


------------------------------------------------------------------------


------------------------------------------------------------------------


# 11. R22 Intelligence Layer


Status:

FROZEN


Freeze:

R22-INTELLIGENCE-LAYER-FROZEN


Zweck:

Bereitstellung einer kontrollierten Intelligence Architektur
oberhalb von Knowledge und Evidence.


Komponenten:

- Intelligence Object Model
- Intelligence Collection
- Intelligence Storage Boundary
- Intelligence Access Layer
- Intelligence Integration Boundary
- Intelligence Pipeline Coordinator


Grundprinzip:

Keine autonome Intelligenz.

Keine automatische Entscheidung.

Keine automatische Systemänderung.

Keine unkontrollierte Inferenz.


Intelligence bleibt:

- nachvollziehbar
- kontrolliert
- überprüfbar
- revisionsfähig


------------------------------------------------------------------------


# Architekturfluss aktualisiert


R18 Agent Layer

        |

        v


R19 Memory Layer

        |

        v


R20 Knowledge Layer

        |

        v


R21 Evidence / Provenance Layer

        |

        v


R22 Intelligence Layer

        |

        v


R23 Next Architecture Layer


------------------------------------------------------------------------


# 12. Nächster Architekturabschnitt


## R23 Next Architecture Layer


Status:

PLANNED


Ziel:

Aufbau der nächsten kontrollierten Architekturschicht
oberhalb der Intelligence Layer.


Grundprinzip:

Jede Erweiterung bleibt:

- modular
- nachvollziehbar
- überprüfbar
- revisionsfähig


Geplante Verantwortung:

- Erweiterung kontrollierter Intelligence Prozesse
- vorbereitete höhere Verarbeitungsschichten
- Architekturverbindungen zwischen Layern
- weitere Boundary Definitionen


------------------------------------------------------------------------


------------------------------------------------------------------------


# 13. R24 Next Architecture Layer


Status:

FROZEN


Freeze:

R24-NEXT-ARCHITECTURE-LAYER-FROZEN


Zweck:

Bereitstellung einer kontrollierten nächsten
Architektur Generation oberhalb der Architecture Layer.


Komponenten:

- Next Architecture Object Model
- Next Architecture Collection
- Next Architecture Storage Boundary
- Next Architecture Access Layer
- Next Architecture Integration Boundary
- Next Architecture Pipeline Coordinator


Grundprinzip:

Keine autonome Architektur.

Keine automatische Architekturänderung.

Keine automatische Strukturierung.

Keine unkontrollierte Anpassung.


Next Architecture bleibt:

- nachvollziehbar
- kontrolliert
- überprüfbar
- revisionsfähig


------------------------------------------------------------------------


# Architekturfluss aktualisiert


R18 Agent Layer

        |

        v


R19 Memory Layer

        |

        v


R20 Knowledge Layer

        |

        v


R21 Evidence / Provenance Layer

        |

        v


R22 Intelligence Layer

        |

        v


R23 Architecture Layer

        |

        v


R24 Next Architecture Layer

        |

        v


R25 Next Evolution Layer


------------------------------------------------------------------------


# 14. Nächster Architekturabschnitt


## R25 Next Evolution Layer


Status:

PLANNED


Ziel:

Aufbau der nächsten kontrollierten Evolutionsschicht
oberhalb der Next Architecture Layer.


Grundprinzip:

Jede Erweiterung bleibt:

- modular
- nachvollziehbar
- überprüfbar
- revisionsfähig


Geplante Verantwortung:

- weitere Architektur Evolution
- kontrollierte Layer Verbindungen
- vorbereitete höhere Systemstrukturen
- zusätzliche Boundary Definitionen


------------------------------------------------------------------------


------------------------------------------------------------------------


# 15. R25 Next Evolution Layer


Status:

FROZEN


Freeze:

R25-NEXT-EVOLUTION-LAYER-FROZEN


Zweck:

Bereitstellung einer kontrollierten Evolutionsschicht
oberhalb der Next Architecture Layer.


Komponenten:

- Next Evolution Object Model
- Next Evolution Collection
- Next Evolution Storage Boundary
- Next Evolution Access Layer
- Next Evolution Integration Boundary
- Next Evolution Pipeline Coordinator


Grundprinzip:

Keine autonome Evolution.

Keine automatische Evolution Änderung.

Keine automatische Strukturierung.

Keine unkontrollierte Anpassung.


Next Evolution bleibt:

- nachvollziehbar
- kontrolliert
- überprüfbar
- revisionsfähig


------------------------------------------------------------------------


# Architekturfluss aktualisiert


R18 Agent Layer

        |

        v


R19 Memory Layer

        |

        v


R20 Knowledge Layer

        |

        v


R21 Evidence / Provenance Layer

        |

        v


R22 Intelligence Layer

        |

        v


R23 Architecture Layer

        |

        v


R24 Next Architecture Layer

        |

        v


R25 Next Evolution Layer

        |

        v


R26 Next Evolution Expansion Layer


------------------------------------------------------------------------


# 16. Nächster Architekturabschnitt


## R26 Next Evolution Expansion Layer


Status:

PLANNED


Ziel:

Aufbau einer weiteren kontrollierten Evolutionsstufe
oberhalb der Next Evolution Layer.


Grundprinzip:

Jede Erweiterung bleibt:

- modular
- nachvollziehbar
- überprüfbar
- revisionsfähig


Geplante Verantwortung:

- Erweiterung bestehender Evolutionsgrenzen
- zusätzliche kontrollierte Layer-Verbindungen
- vorbereitete höhere Systemstrukturen
- weitere Boundary Definitionen


Keine geplante Verantwortung:

- keine autonome Selbständerung
- kein autonomes Lernen
- keine automatische Architekturentscheidung


------------------------------------------------------------------------


------------------------------------------------------------------------


# 17. R26 Next Evolution Expansion Layer


Status:

FROZEN


Freeze:

R26-NEXT-EVOLUTION-EXPANSION-LAYER-FROZEN


Zweck:

Bereitstellung einer kontrollierten Erweiterungsschicht
oberhalb der Next Evolution Layer.


Komponenten:

- Next Evolution Expansion Object Model
- Next Evolution Expansion Collection
- Next Evolution Expansion Storage Boundary
- Next Evolution Expansion Access Layer
- Next Evolution Expansion Integration Boundary
- Next Evolution Expansion Pipeline Coordinator


Grundprinzip:

Keine autonome Expansion.

Keine automatische Expansion Änderung.

Keine automatische Strukturierung.

Keine unkontrollierte Anpassung.


Next Evolution Expansion bleibt:

- nachvollziehbar
- kontrolliert
- überprüfbar
- revisionsfähig


------------------------------------------------------------------------


# Architekturfluss aktualisiert


R18 Agent Layer

        |

        v


R19 Memory Layer

        |

        v


R20 Knowledge Layer

        |

        v


R21 Evidence / Provenance Layer

        |

        v


R22 Intelligence Layer

        |

        v


R23 Architecture Layer

        |

        v


R24 Next Architecture Layer

        |

        v


R25 Next Evolution Layer

        |

        v


R26 Next Evolution Expansion Layer

        |

        v


R27 Next Evolution Integration Layer


------------------------------------------------------------------------


# 18. Nächster Architekturabschnitt


## R27 Next Evolution Integration Layer


Status:

PLANNED


Ziel:

Aufbau einer weiteren kontrollierten Integrationsschicht
oberhalb der Next Evolution Expansion Layer.


Grundprinzip:

Jede Erweiterung bleibt:

- modular
- nachvollziehbar
- überprüfbar
- revisionsfähig


Geplante Verantwortung:

- kontrollierte Integration höherer Layer
- definierte Schnittstellen zwischen Evolutionsbereichen
- vorbereitete Integrationsgrenzen
- weitere Boundary Definitionen


Keine geplante Verantwortung:

- keine autonome Selbständerung
- kein autonomes Lernen
- keine automatische Architekturentscheidung
- keine automatische Systemintegration


------------------------------------------------------------------------


------------------------------------------------------------------------


# 19. SECBrain Evolution Master Roadmap


Status:

MASTER PLANNING


Zweck:

Darstellung der langfristigen SECBrain Architekturentwicklung.

Dieser Abschnitt definiert:

- abgeschlossene Architekturphasen
- geplante Evolutionsschritte
- finalen Architekturzustand
- Ende der Kern-Layer Entwicklung


Grundprinzip:

Neue Layer werden nur erstellt wenn:

- eine klare Verantwortung existiert
- eine eigene Boundary notwendig ist
- ein eigener Contract definiert werden kann
- eine isolierte Validierung möglich ist


Keine geplante Verantwortung:

- keine autonome Selbstentwicklung
- keine automatische Architekturentscheidung
- kein unkontrolliertes Wachstum
- keine endlose Layer-Erweiterung


------------------------------------------------------------------------


# Architekturphasen Übersicht


## Phase 1 – Foundation Architecture


R18 Agent Layer

        |

        v


R19 Memory Layer

        |

        v


R20 Knowledge Layer

        |

        v


R21 Evidence / Provenance Layer


Status:

COMPLETED


------------------------------------------------------------------------


## Phase 2 – Intelligence Architecture


R22 Intelligence Layer

        |

        v


R23 Architecture Layer

        |

        v


R24 Next Architecture Layer


Status:

COMPLETED


------------------------------------------------------------------------


## Phase 3 – Evolution Architecture


R25 Next Evolution Layer

        |

        v


R26 Next Evolution Expansion Layer

        |

        v


R27 Next Evolution Integration Layer

        |

        v


R28 Next Evolution Orchestration Layer


Status:

FROZEN


Freeze Referenzen:

R25-NEXT-EVOLUTION-LAYER-FROZEN

R26-NEXT-EVOLUTION-EXPANSION-LAYER-FROZEN

R27-NEXT-EVOLUTION-INTEGRATION-LAYER-FROZEN

R28-NEXT-EVOLUTION-ORCHESTRATION-LAYER-FROZEN


------------------------------------------------------------------------


# Phase 4 – Control Architecture


## R29 Next Evolution Coordination Layer


Status:

PLANNED


Ziel:

Koordination zwischen bestehenden Evolutionsbereichen.


Geplante Verantwortung:

- koordinierte Übergaben
- definierte Kommunikationswege
- Layer Verbindungskontrolle
- Coordination Boundaries


------------------------------------------------------------------------


## R30 Next Evolution Governance Layer


Status:

PLANNED


Ziel:

Regelwerk für die gesamte Evolution Architektur.


Geplante Verantwortung:

- Architekturregeln
- erlaubte Verbindungen
- Contract Richtlinien
- Zugriffsbeschränkungen
- Governance Grenzen


------------------------------------------------------------------------


## R31 Next Evolution Verification Layer


Status:

PLANNED


Ziel:

Überprüfung der gesamten Architektur.


Geplante Verantwortung:

- Integritätsprüfung
- Regression Kontrolle
- Contract Validierung
- Freeze Überprüfung
- Architektur Konsistenz


------------------------------------------------------------------------


# Phase 5 – Transparency Architecture


## R32 Next Evolution Observability Layer


Status:

PLANNED


Ziel:

Transparenz über die gesamte Architektur.


Geplante Verantwortung:

- Layer Status
- Übergaben
- Systemzustände
- Audit Informationen
- Architektur Übersicht


------------------------------------------------------------------------


# Phase 6 – Scaling Architecture


## R33 Next Evolution Federation Layer


Status:

PLANNED


Ziel:

Kontrollierte Verbindung mehrerer SECBrain Komponenten.


Beispiel:


SECBrain Core

        |

        +---- Research Node

        |

        +---- Trading Node

        |

        +---- Development Node

        |

        +---- Knowledge Node


Geplante Verantwortung:

- definierte Federation Boundaries
- kontrollierte Kommunikation
- modulare Erweiterbarkeit


------------------------------------------------------------------------


# SECBrain Architecture Complete State


Zielzustand:


R33 Next Evolution Federation Layer


Status:

ARCHITECTURE MATURITY TARGET


Nach R33:


Keine weiteren Kern-Layer geplant.


Übergang:


Architecture Development

        |

        v


Architecture Maturity Phase


Schwerpunkt:

- Anwendungen
- Module
- Datenquellen
- Interfaces
- reale Nutzung
- Erweiterung bestehender Systeme


------------------------------------------------------------------------
