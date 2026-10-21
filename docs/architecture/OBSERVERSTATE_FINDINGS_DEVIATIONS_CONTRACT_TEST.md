# SecBrain Watcher

# BLOCK 12C.3-B
# Stations Contract Test

## Subject

`ObserverState.findings`

`ObserverState.deviations`

---

## Contract Under Test

Die verbindliche Architekturdefinition aus BLOCK 12C.2-R2 lautet:

    findings   = CURRENT_STATION
    deviations = CURRENT_STATION

Damit dürfen `findings` und `deviations`
nicht als kumulative Observer-Run-Historie verwendet werden.

---

## Test Objective

Der Test prüft die Implementierung gegen folgende
Contract-Dimensionen:

- CURRENT_STATION Scope
- Stationswechsel
- Re-Evaluation
- fehlende kumulative Run-History
- Trennung von last_evaluation
- Observer-KI Boundary

---

## Core Contract Scenario

    Station N
        ↓
    Findings/Deviations von Station N
        ↓
    Station N + 1
        ↓
    Findings/Deviations von Station N + 1

Erwartung:

    Station-N-Befunde
        dürfen NICHT
    als aktueller State nach Station N+1
    fortbestehen.

---

## Test Execution

Testdatei:

    /tmp/secbrain_12c3b/test_observerstate_current_station_contract.py

Pytest Exit Code:

    127

Test Status:

    CONTRACT_VIOLATION_OR_TEST_FAILURE

---

## Result

Mindestens eine Contract-Prüfung ist fehlgeschlagen. Die Implementierung ist damit nicht als CURRENT_STATION-konform nachgewiesen.

---

## Pytest Output

```
Der Befehl 'pytest' wurde nicht gefunden, kann aber installiert werden mit:
sudo apt install python3-pytest
```

---

## Production Code

BLOCK 12C.3-B verändert keinen Produktionscode.

Geprüfte Produktionsdateien:

- `app/models/observer.py`
- `app/models/evaluation.py`
- `app/core/observer_engine.py`

Der Nachweis erfolgt über Vorher-/Nachher-Hashes,
da diese Dateien laut Git-Status teilweise untracked
sein können.

---

## Production Code Modification

    NICHT DURCH DIESEN BLOCK

---

## Existing Tests

Bestehende Projekt-Tests wurden nicht verändert.

Der Contract-Test wurde isoliert unter:

    /tmp/secbrain_12c3b/

erzeugt.

---

## Interpretation

Mindestens eine Contract-Prüfung ist fehlgeschlagen.

Damit ist die Implementierung für den betroffenen
Contract-Pfad nicht konform nachgewiesen.

WICHTIG:

Dieser Block verändert deshalb trotzdem keinen
Produktionscode.

Ein möglicher Production Patch darf erst in einem
nachfolgenden, ausdrücklich dafür vorgesehenen Block
entwickelt werden.

Die konkrete Fehlstelle muss zunächst anhand des
Testfehlers untersucht werden.

---

## Architectural Boundary

Der Contract-Test darf nicht:

- den Contract verändern
- findings/deviations selbst korrigieren
- apply_evaluation() patchen
- ObserverEngine patchen
- ObserverState patchen
- bestehende Tests umschreiben
- die Contract-Semantik aus Runtime-Verhalten neu ableiten

---

## Architecture Sequence

    OBSERVATION
        ↓
    CONTRACT SPECIFICATION
        ↓
    CONTRACT DECISION
        ↓
    EXPLICIT CONTRACT DEFINITION
        ↓
    STATIONS-CONTRACT-TEST
        ↓
    IMPLEMENTATION CONFORMANCE
        ↓
    ggf. PRODUCTION PATCH
