#!/usr/bin/env python3

"""
SecBrain Watcher

R11 Boundary Series Generator

Erzeugt vollständige Boundary Contract Tests
aus bestehender geprüfter Boundary-Basis.

Beispiel:

python tools/boundary_generator.py FF HH


Erzeugt:

R11-FF-01 ... 05
R11-GG-01 ... 05
R11-HH-01 ... 05


Ablauf:

1. Basis Boundary auswählen
2. Code-Struktur übernehmen
3. Namen ersetzen
4. Dateien erzeugen
5. pytest ausführen
6. Git Commit erzeugen

Kein Production Code wird verändert.
"""


import sys
import subprocess
from pathlib import Path



ROOT = Path(__file__).resolve().parent.parent

CORE = ROOT / "app" / "core"


BOUNDARY_CHAIN = [
    "BB",
    "CC",
    "DD",
    "EE",
    "FF",
    "GG",
    "HH",
    "II",
    "JJ",
    "KK",
    "LL",
    "MM",
    "NN",
    "OO",
    "PP",
    "QQ",
    "RR",
    "SS",
    "TT",
    "UU",
    "VV",
    "WW",
    "XX",
    "YY",
    "ZZ",
]


TESTS = [
    "reference_contract",
    "isolation_boundary",
    "provenance_contract",
    "consistency_contract",
    "integrity_regression",
]


R12_TESTS = [
    "reference_contract",
    "isolation_boundary",
    "provenance_contract",
    "consistency_contract",
    "integrity_regression",
]


GENERATOR_MODE = {
    "R11": "presentation_decision",
    "R12": "r12_architecture",
}



def get_range(start, end):

    if start not in BOUNDARY_CHAIN:
        raise Exception(
            f"Unknown boundary {start}"
        )

    if end not in BOUNDARY_CHAIN:
        raise Exception(
            f"Unknown boundary {end}"
        )


    s = BOUNDARY_CHAIN.index(start)
    e = BOUNDARY_CHAIN.index(end)


    if s > e:
        raise Exception(
            "Invalid range"
        )


    return BOUNDARY_CHAIN[s:e+1]



def previous(boundary):

    index = BOUNDARY_CHAIN.index(
        boundary
    )

    return BOUNDARY_CHAIN[
        index - 1
    ]



def find_template(test):

    candidates = [

        CORE /
        f"presentation_decision_ee_{test}_test.py",

        CORE /
        f"presentation_decision_dd_{test}_test.py",

    ]


    for item in candidates:

        if item.exists():
            return item


    raise Exception(
        f"No template found for {test}"
    )



def replace_boundary(
    content,
    old,
    new
):

    content = content.replace(
        f"R11-{old}",
        f"R11-{new}"
    )


    content = content.replace(
        f"r11{old.lower()}",
        f"r11{new.lower()}"
    )


    content = content.replace(
        f"PresentationDecision{old}",
        f"PresentationDecision{new}"
    )


    content = content.replace(
        f"_{old.lower()}_",
        f"_{new.lower()}_"
    )


    return content



def create_file(
    boundary,
    test,
    mode="R11"
):

    prefix = GENERATOR_MODE.get(
        mode,
        "presentation_decision"
    )


    if mode == "R12":

        target = (
            CORE /
            f"r12_architecture_{test}_test.py"
        )

    else:

        target = (
            CORE /
            f"presentation_decision_{boundary.lower()}_{test}_test.py"
        )


    if target.exists():

        print(
            f"⚠ übersprungen: {target.name}"
        )

        return


    template = find_template(
        test
    )


    content = template.read_text(
        encoding="utf-8"
    )


    if mode == "R12":

        content = content.replace(
            "R12-01",
            "R12-01"
        )

        content = content.replace(
            "R12",
            "R12"
        )

    else:

        source_boundary = (
            template.name
            .split("_")[2]
            .upper()
        )


        content = replace_boundary(
            content,
            source_boundary,
            boundary
        )


    target.write_text(
        content,
        encoding="utf-8"
    )


    print(
        f"✓ erzeugt {target.name}"
    )



def run_pytest():

    print()
    print("=" * 70)
    print(
        "RUNNING REGRESSION TEST"
    )
    print("=" * 70)


    result = subprocess.run(
        [
            "pytest",
            "-q"
        ],
        cwd=ROOT
    )


    if result.returncode != 0:

        raise Exception(
            "pytest failed"
        )



def git_commit(
    start,
    end
):

    subprocess.run(
        [
            "git",
            "add",
            "app/core/presentation_decision_*"
        ],
        cwd=ROOT,
        shell=False
    )


    status = subprocess.run(
        [
            "git",
            "diff",
            "--cached",
            "--quiet"
        ],
        cwd=ROOT
    )


    if status.returncode == 0:

        print(
            "✓ Keine neuen Änderungen - kein Commit notwendig"
        )

        return


    subprocess.run(
        [
            "git",
            "commit",
            "-m",
            f"R11-{start}-{end} Generated Boundary Contract Tests"
        ],
        cwd=ROOT,
        check=True
    )



def main():


    if len(sys.argv) == 2 and sys.argv[1].upper() == "R12":

        print("=" * 70)
        print(
            "R12 Architecture Generator"
        )
        print("=" * 70)


        for test in R12_TESTS:

            create_file(
                "R12",
                test,
                mode="R12"
            )


        run_pytest()


        git_commit(
            "R12",
            "ARCHITECTURE"
        )


        print("=" * 70)
        print(
            "R12 GENERATION COMPLETE"
        )
        print("=" * 70)

        return



    if len(sys.argv) != 3:

        print(
            "Usage:"
        )

        print(
            "python tools/boundary_generator.py FF HH"
        )

        print(
            "python tools/boundary_generator.py R12"
        )

        sys.exit(1)



    start = sys.argv[1].upper()
    end = sys.argv[2].upper()


    boundaries = get_range(
        start,
        end
    )


    print("=" * 70)
    print(
        "R11 Boundary Production Generator"
    )
    print(
        f"{start} -> {end}"
    )
    print("=" * 70)



    for boundary in boundaries:

        print()
        print(
            f"Generating R11-{boundary}"
        )

        for test in TESTS:

            create_file(
                boundary,
                test
            )


    run_pytest()


    git_commit(
        start,
        end
    )


    print()
    print("=" * 70)
    print(
        "GENERATION COMPLETE"
    )
    print("=" * 70)



if __name__ == "__main__":

    main()
