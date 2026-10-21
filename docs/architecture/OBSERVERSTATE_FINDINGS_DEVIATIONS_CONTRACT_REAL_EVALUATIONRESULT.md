# SecBrain Watcher

# BLOCK 12C.3-B-R3
# REAL EVALUATIONRESULT FIXTURE / CONTRACT EXECUTION

---

## Zweck

R3 führt den CURRENT_STATION-Contract erstmals
über die reale Produktionsstruktur:

    EvaluationResult
        ↓
    ObserverState.apply_evaluation()
        ↓
    ObserverState.findings

aus.

Kein Produktionscode wurde verändert.

Der Contract wurde nicht verändert.

---

## Contract

    findings   = CURRENT_STATION
    deviations = CURRENT_STATION

Decision:

    B

---

## Ausgangsbefund R2

R2 hatte erfolgreich die reale
EvaluationFinding-Fixture hergestellt.

Der Test scheiterte anschließend daran,
dass:

    ObserverState.apply_evaluation()

ein:

    EvaluationResult

erwartet und kein:

    EvaluationFinding.

---

## R3-Maßnahme

Die reale Klasse:

    EvaluationResult

wurde aus:

    app.models.evaluation

ermittelt.

Der Contract-Test verwendet jetzt reale:

    EvaluationFinding

innerhalb realer:

    EvaluationResult

Objekte.

Der Stationsübergang wird über die reale Methode:

    ObserverState.apply_evaluation()

ausgeführt.

---

## Test Fixture

Quelle:

    /tmp/secbrain_12c3br2/test_observerstate_current_station_contract.py

Isolierte Testkopie:

    /tmp/secbrain_12c3br3/test_observerstate_current_station_contract.py

---

## Import Smoke Test

Exit:

    0

---

## Contract Test

Pytest Exit:

    1

Test Status:

    CONTRACT_VIOLATION_OR_TEST_FAILURE

---

## Final Status

    CONTRACT_VIOLATION_OR_TEST_FAILURE

Begründung:

    Der Contract-Test wurde mit realen EvaluationResult-Objekten tatsächlich ausgeführt und mindestens eine Contract-Prüfung ist fehlgeschlagen.

---

## Pytest Output

```
..F.....                                                                 [100%]
=================================== FAILURES ===================================
________ test_station_n_findings_are_not_carried_into_station_n_plus_1 _________

    def test_station_n_findings_are_not_carried_into_station_n_plus_1():
        """
        Kernprüfung des CURRENT_STATION-Vertrags.

        Station N:
            FINDING_STATION_N

        Station N+1:
            FINDING_STATION_N_PLUS_1

        Nach dem Wechsel darf der aktuelle State keine
        Findings der vorherigen Station mehr enthalten.
        """
        cls = _observer_state_class()
        state = _safe_construct(cls)

        finding_n = _make_finding(
            1,
            "Station N",
            "FINDING_STATION_N",
        )

        finding_n1 = _make_finding(
            2,
            "Station N+1",
            "FINDING_STATION_N_PLUS_1",
        )

        evaluation_n = _make_evaluation_result(
            1,
            "Station N",
            finding_n,
        )

        evaluation_n1 = _make_evaluation_result(
            2,
            "Station N+1",
            finding_n1,
        )

        method = _apply_evaluation_method(state)

        try:
            method(evaluation_n)
        except Exception as exc:
            pytest.fail(
                "ObserverState.apply_evaluation() konnte "
                f"EvaluationResult für Station N nicht übernehmen: {exc!r}"
            )

        findings_after_n = list(_get_value(state, "findings"))

        assert "FINDING_STATION_N" in _finding_description_list(
            findings_after_n
        ), (
            "Station-N-Finding wurde nach der ersten Evaluation "
            "nicht im State gefunden."
        )

        try:
            method(evaluation_n1)
        except Exception as exc:
            pytest.fail(
                "ObserverState.apply_evaluation() konnte "
                f"EvaluationResult für Station N+1 nicht übernehmen: {exc!r}"
            )

        findings_after_n1 = list(_get_value(state, "findings"))
        descriptions = _finding_description_list(findings_after_n1)

        assert "FINDING_STATION_N_PLUS_1" in descriptions, (
            "Station-N+1-Finding fehlt im aktuellen State."
        )

>       assert "FINDING_STATION_N" not in descriptions, (
            "CONTRACT VIOLATION: Finding von Station N bleibt nach "
            "dem Übergang zu Station N+1 im aktuellen findings-State."
        )
E       AssertionError: CONTRACT VIOLATION: Finding von Station N bleibt nach dem Übergang zu Station N+1 im aktuellen findings-State.
E       assert 'FINDING_STATION_N' not in ['FINDING_STATION_N', 'FINDING_STATION_N_PLUS_1']

/tmp/secbrain_12c3br3/test_observerstate_current_station_contract.py:406: AssertionError
=========================== short test summary info ============================
FAILED ../../../../tmp/secbrain_12c3br3/test_observerstate_current_station_contract.py::test_station_n_findings_are_not_carried_into_station_n_plus_1
1 failed, 7 passed in 0.06s
```

---

## Production Code

Geprüft:

- app/models/observer.py
- app/models/evaluation.py
- app/core/observer_engine.py

Production Code verändert:

    NEIN

---

## Architekturgrenze

R3 verändert NICHT:

- app/models/observer.py
- app/models/evaluation.py
- app/core/observer_engine.py
- Contract Specification
- Decision Record
- bestehende Projekt-Tests

---

## Interpretation

Der Test wurde tatsächlich über die reale
EvaluationResult-/ObserverState-Struktur ausgeführt.

Mindestens eine fachliche Contract-Prüfung ist
fehlgeschlagen.

Damit liegt erstmals ein echter Kandidat für eine
Contract Violation bzw. einen fachlichen Testfehler vor.

R3 verändert trotzdem keinen Production-Code.

Ein Patch darf ausschließlich in einem nachfolgenden,
separaten Production-Patch-Block erfolgen.

---

## Architecture Sequence

    CONTRACT
        ↓
    TEST INFRASTRUCTURE
        ↓
    REAL EvaluationFinding
        ↓
    REAL EvaluationResult
        ↓
    ObserverState.apply_evaluation()
        ↓
    CURRENT_STATION CONTRACT
        ↓
    CONFORMANCE RESULT
        ↓
    ggf. separater PRODUCTION PATCH
