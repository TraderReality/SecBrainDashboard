# SecBrain Watcher

# ObserverState.findings / deviations
# Architecture Contract Specification
#
# BLOCK 12C.2-R2
#
# STATUS:
# EXPLICIT CONTRACT DEFINED
#
# IMPORTANT:
# Diese Spezifikation definiert jetzt verbindlich die
# Soll-Semantik von ObserverState.findings und
# ObserverState.deviations.
#
# Produktionscode wird durch diesen Block NICHT verändert.


# 1. Zweck

Diese Spezifikation definiert die verbindliche Architekturgrenze für:

    ObserverState.findings
    ObserverState.deviations
    ObserverState.last_evaluation

Die Semantik dieser Felder wird als expliziter
Architekturvertrag festgelegt.

Die Semantik darf nicht aus dem aktuellen
Implementierungsverhalten abgeleitet werden.


# 2. Verbindliche Contract Decision

Die verbindliche Architekturentscheidung lautet:

    findings
        CURRENT_STATION

    deviations
        CURRENT_STATION

Damit repräsentieren `findings` und `deviations`
ausschließlich den fachlichen Befund der aktuell
aktiven Observer-Station.


# 3. Findings-Vertrag

`ObserverState.findings` represents:

    die Findings der aktuell aktiven Station.

Scope:

    CURRENT_STATION

Das Feld enthält ausschließlich Findings,
die der aktuell aktiven Station zugeordnet sind.

Findings anderer Stationen dürfen nach einem
Stationswechsel nicht weiter als aktueller
Station-Status in diesem Feld enthalten sein.


# 4. Deviations-Vertrag

`ObserverState.deviations` represents:

    die Deviations der aktuell aktiven Station.

Scope:

    CURRENT_STATION

Das Feld enthält ausschließlich Abweichungen,
die der aktuell aktiven Station zugeordnet sind.

Deviations anderer Stationen dürfen nach einem
Stationswechsel nicht weiter als aktueller
Station-Status in diesem Feld enthalten sein.


# 5. Lifetime

`findings` und `deviations` besitzen einen
stationsbezogenen Lebenszyklus.

Die Werte sind gültig für:

    die aktuell aktive Station

Beim Wechsel auf eine andere Station endet die
Gültigkeit der bisherigen stationsbezogenen
Findings/Deviations als aktueller State.


# 6. Stationswechsel

Beim Übergang:

    Station N
        ->
    Station N + 1

werden:

    findings
    deviations

nicht als kumulative Historie fortgeführt.

Die neuen Felder repräsentieren ausschließlich
den Zustand der neuen aktiven Station.

Damit gilt:

    Station N Findings
        ->
    nicht mehr Bestandteil des aktuellen
    findings-State nach Übergang zu Station N + 1

und:

    Station N Deviations
        ->
    nicht mehr Bestandteil des aktuellen
    deviations-State nach Übergang zu Station N + 1


# 7. Re-Evaluation derselben Station

Wenn dieselbe Station erneut evaluiert wird,
repräsentieren `findings` und `deviations`
das Ergebnis der aktuellen Evaluation dieser Station.

Die erneute Evaluation erzeugt keine implizite
Historienliste innerhalb dieser Felder.

Es gilt:

    aktuelle Evaluation
        ->
    aktueller stationsbezogener State

Nicht:

    aktuelle Evaluation
        ->
    zusätzliche historische Einträge


# 8. Observer-Run-Grenze

Ein neuer Observer-Lauf besitzt einen eigenen
stationsbezogenen State.

Ergebnisse eines vorherigen Observer-Laufs werden
nicht automatisch in:

    findings
    deviations

übernommen.

Eine Observer-Run-Historie darf nicht implizit aus
diesen Feldern konstruiert werden.


# 9. Historien-Semantik

`findings` und `deviations` sind ausdrücklich
KEINE kumulative Observer-Run-Historie.

Insbesondere bedeutet:

    findings

nicht:

    alle Findings aller bisher durchlaufenen Stationen

und:

    deviations

nicht:

    alle Deviations aller bisher durchlaufenen Stationen.

Eine historische Darstellung muss über eine dafür
explizit vorgesehene Architekturstruktur erfolgen.


# 10. Stationszuordnung

Da `findings` und `deviations` den Scope:

    CURRENT_STATION

besitzen, muss der aktuelle State eindeutig der
aktiven Station zugeordnet sein.

Die Felder dürfen nicht als implizite Historie
mehrerer Stationen interpretiert werden.


# 11. Beziehung zu last_evaluation

`last_evaluation` bezeichnet:

    das zuletzt angewendete EvaluationResult.

`last_evaluation` und:

    findings
    deviations

sind logisch getrennte Zustandsdimensionen.

Aus der Semantik von `last_evaluation` darf nicht
auf die Semantik von `findings` oder `deviations`
geschlossen werden.

Der Contract für `findings` und `deviations`
ist unabhängig und explizit definiert.


# 12. Beziehung zu EvaluationResult

`EvaluationResult` bleibt das Ergebnis der
deterministischen Evaluation.

`ObserverState` bleibt der Zustand des
eigenständigen Observers.

Die Contract-Entscheidung definiert lediglich,
welcher Teil dieses Ergebnisses als aktueller
stationsbezogener State in:

    findings
    deviations

repräsentiert werden darf.


# 13. Beziehung zur Observer-KI

Die Observer-KI darf:

    findings
    deviations

nicht verändern.

Die Observer-KI darf insbesondere nicht:

    - den Findings-Scope verändern
    - Deviations historisieren
    - Findings anderer Stationen hinzufügen
    - Deviations anderer Stationen hinzufügen
    - Stationswechsel auslösen
    - current_station verändern
    - next_station() aufrufen
    - EvaluationResult verändern
    - last_evaluation verändern


# 14. 12-Stationen-Loop

Der 12-Stationen-Loop bleibt unter Kontrolle
der externen Loop-Logik.

Die fachliche Semantik lautet:

    Station N
        ->
    Evaluation
        ->
    CURRENT_STATION findings/deviations
        ->
    Observer-KI-Analyse
        ->
    externe Loop-Kontrolle
        ->
    Station N + 1

Beim Übergang auf die nächste Station beginnt
der stationsbezogene Findings/Deviations-State
für die neue Station.


# 15. finish()

Beim Abschluss des Observer-Laufs dürfen
`findings` und `deviations` nicht als implizite
Run-Historie interpretiert werden.

Die Bedeutung bleibt:

    aktueller stationsbezogener State

Eine Persistierung historischer Informationen
benötigt einen eigenen expliziten Contract.


# 16. Verbotene Ableitungen

Folgende Ableitungen sind ausdrücklich unzulässig:

    apply_evaluation() kumuliert
        ->
    findings müssen kumulativ sein

    last_evaluation ist stationsbezogen
        ->
    findings müssen stationsbezogen sein

Die Contract-Entscheidung wird nicht aus diesen
technischen Eigenschaften abgeleitet.

Der Contract ist eine eigenständige
Architekturentscheidung.


# 17. Contract Status

Vor diesem Block:

    C_PENDING

Nach diesem Block:

    B

Bedeutung:

    findings/deviations sind stationsbezogene
    aktuelle Befunde.


# 18. Verbindliche Contract Matrix

| Dimension | findings | deviations |
|---|---|---|
| Scope | CURRENT_STATION | CURRENT_STATION |
| Lifetime | aktuelle Station | aktuelle Station |
| Station Transition | neuer aktueller State | neuer aktueller State |
| Re-Evaluation | aktuelles Ergebnis | aktuelles Ergebnis |
| New Observer Run | kein implizites Carry-over | kein implizites Carry-over |
| Historie | nicht enthalten | nicht enthalten |
| Stationsbezug | aktuelle Station | aktuelle Station |
| Kumulative Run-History | NEIN | NEIN |

`last_evaluation` bleibt davon logisch getrennt.


# 19. Implementierungsregel

Erst nachdem dieser Contract festgelegt wurde,
darf geprüft werden, ob:

    ObserverState.apply_evaluation()

und/oder:

    ObserverEngine.apply_evaluation()

dem Vertrag entsprechen.

Eine Abweichung zwischen Implementierung und diesem
Contract ist anschließend eine:

    CONTRACT VIOLATION


# 20. Patch-Regel

Dieser Block verändert keinen Produktionscode.

Insbesondere werden nicht verändert:

    app/models/observer.py
    app/models/evaluation.py
    app/core/observer_engine.py

Ein Produktionspatch darf erst nach einem
fehlgeschlagenen Contract-Test entwickelt werden.


# 21. Architektur-Sequenz

    BEOBACHTUNG
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
