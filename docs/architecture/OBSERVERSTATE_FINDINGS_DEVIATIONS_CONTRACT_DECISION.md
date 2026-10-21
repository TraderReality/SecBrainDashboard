# SecBrain Watcher

# BLOCK 12C.2-R2
# Explicit Contract Definition
# ObserverState.findings / deviations

---

## Contract Decision

**B**

---

## Decision

`ObserverState.findings` und `ObserverState.deviations`
sind verbindlich als:

    CURRENT_STATION

definiert.

---

## Findings Scope

`ObserverState.findings` repräsentiert ausschließlich
die Findings der aktuell aktiven Station.

Scope:

    CURRENT_STATION

---

## Deviations Scope

`ObserverState.deviations` repräsentiert ausschließlich
die Deviations der aktuell aktiven Station.

Scope:

    CURRENT_STATION

---

## Lifetime

Die Werte gelten für die aktuell aktive Station.

Beim Stationswechsel endet ihre Gültigkeit als
aktueller stationsbezogener State.

---

## Station Transition

Bei:

    Station N
        ->
    Station N + 1

werden `findings` und `deviations` nicht als
kumulative Historie fortgeführt.

Der State der neuen Station ersetzt den vorherigen
aktuellen stationsbezogenen State.

---

## Re-Evaluation

Bei erneuter Evaluation derselben Station repräsentieren
`findings` und `deviations` das aktuelle Ergebnis.

Eine erneute Evaluation erzeugt keine implizite
Historienliste innerhalb dieser Felder.

---

## New Observer Run

Ein neuer Observer-Lauf übernimmt keine vorherigen
Findings oder Deviations implizit.

Die Felder besitzen keine kumulative
Observer-Run-History-Semantik.

---

## last_evaluation

`last_evaluation` bezeichnet weiterhin das zuletzt
angewendete `EvaluationResult`.

Es ist logisch von:

    findings
    deviations

getrennt.

Die Semantik von `findings` und `deviations` wird
nicht aus `last_evaluation` abgeleitet.

---

## Historical Data

`findings` und `deviations` enthalten ausdrücklich
keine kumulative Historie aller bisher bearbeiteten
Stationen.

Historische Daten benötigen eine eigene explizite
Architekturstruktur.

---

## Observer-KI Boundary

Die Observer-KI darf:

- `findings` nicht verändern
- `deviations` nicht verändern
- keine Findings anderer Stationen hinzufügen
- keine Deviations anderer Stationen hinzufügen
- `current_station` nicht verändern
- `next_station()` nicht aufrufen
- `last_evaluation` nicht verändern
- `EvaluationResult` nicht verändern

---

## 12-Stationen-Loop

Die externe Loop-Logik bleibt ausschließlich für
den Stationswechsel verantwortlich.

Der fachliche Ablauf lautet:

    Station N
        ↓
    Evaluation
        ↓
    CURRENT_STATION findings/deviations
        ↓
    Observer-KI-Analyse
        ↓
    externe Loop-Kontrolle
        ↓
    Station N + 1

---

## Evidence Status

BLOCK 12C.2-R1 hat bestätigt:

- keine belastbare direkte A-Contract-Evidence
- keine belastbare direkte B-Contract-Evidence
- vorhandene A/B-Texte waren Entscheidungsoptionen bzw.
  ausdrücklich verbotene Ableitungen
- bestehendes Runtime-Verhalten ist kein Soll-Vertrag

Daher wurde der fehlende Contract in diesem Block
explizit als Architekturentscheidung definiert.

---

## Production Code Status

BLOCK 12C.2-R2 verändert keinen Produktionscode.

Keine Änderung an:

    app/models/observer.py
    app/models/evaluation.py
    app/core/observer_engine.py

Keine Tests wurden verändert.

---

## Contract Status

Vorher:

    C_PENDING

Jetzt:

    B

Bedeutung:

    findings/deviations sind stationsbezogene
    aktuelle Befunde.

---

## Nächster Schritt

    BLOCK 12C.3-B
    STATIONS-CONTRACT-TEST

Der nächste Block darf ausschließlich prüfen,
ob die bestehende Implementierung diesem Contract
entspricht.

Bei Contract Violation darf anschließend ein
Produktionspatch diskutiert werden.

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
    CONTRACT TEST
        ↓
    IMPLEMENTATION CONFORMANCE
        ↓
    ggf. PRODUCTION PATCH
