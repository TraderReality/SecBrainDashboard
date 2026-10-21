# SecBrain Watcher

# BLOCK 12C.3-B-R2
# Test Fixture / Real EvaluationFinding Validation

---

## Zweck

Diese Runde repariert ausschließlich die Test-Fixture
des BLOCK-12C.3-B-Contract-Tests.

Es wurde kein Produktionscode verändert.

Der Contract wurde nicht verändert.

---

## Contract

    findings   = CURRENT_STATION
    deviations = CURRENT_STATION

Decision:

    B

---

## Ausgangsbefund aus R1

Der Contract-Test war infrastrukturell ausführbar,
scheiterte jedoch beim Erzeugen des realen
`EvaluationFinding`.

Fehler:

    EvaluationFinding.__init__()
    missing required positional argument:
    check_type

Damit konnte die eigentliche Stationsübergangsprüfung
noch nicht ausgeführt werden.

---

## R2-Maßnahme

Die reale Signatur von:

    EvaluationFinding

wurde direkt aus:

    app.models.evaluation

ermittelt.

Die Test-Fixture wurde ausschließlich in einer
isolierten Testkopie angepasst.

Ergänzt wurde:

    check_type = "CONTRACT_TEST"

Die Produktionsklasse wurde nicht verändert.

---

## Test Fixture

Quelle:

    /tmp/secbrain_12c3br1/test_observerstate_current_station_contract.py

Isolierte Testkopie:

    /tmp/secbrain_12c3br2/test_observerstate_current_station_contract.py

---

## Import Smoke Test

Exit:

    0

---

## EvaluationFinding Construction

Die reale Klasse konnte mit der angepassten
Test-Fixture konstruiert werden.

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

    Die Test-Fixture ist nun ausführbar; mindestens eine echte Contract-Prüfung ist fehlgeschlagen.

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

        method = _apply_evaluation_method(state)

        try:
>           method(state, finding_n)
E           TypeError: ObserverState.apply_evaluation() takes 2 positional arguments but 3 were given

/tmp/secbrain_12c3br2/test_observerstate_current_station_contract.py:268: TypeError

During handling of the above exception, another exception occurred:

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

        method = _apply_evaluation_method(state)

        try:
            method(state, finding_n)
        except TypeError:
            try:
>               method(finding_n)

/tmp/secbrain_12c3br2/test_observerstate_current_station_contract.py:271:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

self = ObserverState(current_station=1, status='idle', started_at=None, updated_at=None, completed_stations=[], current_rule_...lls=[], current_inputs=[], current_outputs=[], findings=[], deviations=[], last_evaluation=None, last_ai_analysis=None)
evaluation = EvaluationFinding(station_number=1, station_name='Station N', check_type='CONTRACT_TEST', description='FINDING_STATION...ontract-test', rule_reference='BLOCK-12C.3-B', skill_reference='BLOCK-12C.3-B', evidence='synthetic contract evidence')

    def apply_evaluation(
        self,
        evaluation: EvaluationResult,
    ) -> None:
        """
        Übernimmt ein EvaluationResult in den
        eigenständigen Observer-Zustand.

        Die Evaluation selbst findet NICHT hier statt.

        Diese Methode übernimmt ausschließlich das
        bereits berechnete Ergebnis.
        """

        if not isinstance(
            evaluation,
            EvaluationResult,
        ):
>           raise TypeError(
                "ObserverState.apply_evaluation erwartet "
                "ein EvaluationResult."
            )
E           TypeError: ObserverState.apply_evaluation erwartet ein EvaluationResult.

app/models/observer.py:156: TypeError

During handling of the above exception, another exception occurred:

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

        method = _apply_evaluation_method(state)

        try:
            method(state, finding_n)
        except TypeError:
            try:
                method(finding_n)
            except Exception as exc:
>               pytest.fail(
                    f"apply_evaluation() konnte mit EvaluationFinding nicht "
                    f"angewendet werden: {exc!r}"
                )
E               Failed: apply_evaluation() konnte mit EvaluationFinding nicht angewendet werden: TypeError('ObserverState.apply_evaluation erwartet ein EvaluationResult.')

/tmp/secbrain_12c3br2/test_observerstate_current_station_contract.py:273: Failed
=========================== short test summary info ============================
FAILED ../../../../tmp/secbrain_12c3br2/test_observerstate_current_station_contract.py::test_station_n_findings_are_not_carried_into_station_n_plus_1
1 failed, 7 passed in 0.06s
```

---

## Production Code

Geprüfte Dateien:

- app/models/observer.py
- app/models/evaluation.py
- app/core/observer_engine.py

Production Code verändert:

    NEIN

---

## Architekturgrenze

R2 verändert NICHT:

- app/models/observer.py
- app/models/evaluation.py
- app/core/observer_engine.py
- Contract Specification
- Decision Record
- bestehende Projekt-Tests

---

## Interpretation

Die Test-Fixture ist jetzt valide und der eigentliche
Contract-Test wurde tatsächlich ausgeführt.

Mindestens eine fachliche Prüfung ist fehlgeschlagen.

Dies ist jetzt ein echter Kandidat für eine
Contract Violation bzw. einen echten Testfehler.

R2 selbst führt trotzdem keinen Production Patch durch.

---

## Architecture Sequence

    CONTRACT
        ↓
    TEST INFRASTRUCTURE
        ↓
    REAL EVALUATIONFINDING FIXTURE
        ↓
    CONTRACT TEST
        ↓
    CONFORMANCE RESULT
        ↓
    ggf. separater PRODUCTION PATCH
