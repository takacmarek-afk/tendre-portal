"""Moj vyber (audit 27. 9. 2026, P1.3): mesiacRozsah() a jeGenerickyUcel().

Tieto dve funkcie žijú len v public/app.html (klientský JS, žiadny build
krok). Test ich z app.html vytiahne regexom, spustí cez node a porovná
výstup so String.raw JSON poľom vstup->očakávaný výstup — rovnaký princíp
ako test_plany.py pre HTML texty, len tu ide o skutočné volanie funkcie.
Spustenie: python test_moj_vyber.py (vyžaduje node v PATH).
"""
import json
import re
import subprocess
from pathlib import Path

KOREN = Path(__file__).resolve().parent.parent
APP = KOREN / "public" / "app.html"


def _vytiahni(meno):
    t = APP.read_text(encoding="utf-8")
    m = re.search(rf"\nfunction {meno}\([^)]*\) \{{.*?\n\}}\n", t, re.S)
    assert m, f"{meno}() sa v app.html nenašla"
    return m.group(0)


def _spusti_pripady(kod_pred, volanie, pripady):
    """Spustí `volanie(*args)` pre kazdy pripad a vrati zoznam vysledkov."""
    riadky = [f"const V = {json.dumps(pripady)};",
               "const vysledky = V.map(v => (" + volanie + ")(...v));",
               "console.log(JSON.stringify(vysledky));"]
    skript = kod_pred + "\n" + "\n".join(riadky)
    p = subprocess.run(["node", "-e", skript], capture_output=True, text=True)
    assert p.returncode == 0, f"node zlyhal: {p.stderr}"
    return json.loads(p.stdout)


def test_mesiac_rozsah():
    kod = _vytiahni("mesiacRozsah")
    # MESIACE_SK je pouzita vnutri, musi byt v tom istom skripte.
    mesiace = re.search(r"const MESIACE_SK = \[.*?\];", APP.read_text(encoding="utf-8"), re.S).group(0)
    pripady = [
        ["2027-03-15", "2027-09-01"],
        ["2026-11-01", "2027-05-01"],
        ["2027-03-01", "2027-03-20"],
        ["2027-03-01", None],
        [None, None],
    ]
    ocakavane = [
        "marec až september 2027",
        "november 2026 až máj 2027",
        "marec 2027",
        "od marec 2027",
        "",
    ]
    vysledky = _spusti_pripady(mesiace + "\n" + kod, "mesiacRozsah", pripady)
    assert vysledky == ocakavane, f"mesiacRozsah: {vysledky} != {ocakavane}"


def test_je_genericky_ucel():
    kod = _vytiahni("jeGenerickyUcel")
    pripady = [
        ["Zmluva o poskytnutí dotácie"],
        ["Zmluva o poskytnutí dotácie."],
        ["zmluva o poskytnutí nenávratného finančného príspevku"],
        ["Dotačná zmluva"],
        [""],
        [None],
        ["Rekonštrukcia miestnej komunikácie v obci Sliepkovce"],
        ["Oprava strechy materskej školy — II. etapa"],
    ]
    ocakavane = [True, True, True, True, True, True, False, False]
    vysledky = _spusti_pripady(kod, "jeGenerickyUcel", pripady)
    assert vysledky == ocakavane, f"jeGenerickyUcel: {vysledky} != {ocakavane}"


if __name__ == "__main__":
    for meno, f in list(globals().items()):
        if meno.startswith("test_") and callable(f):
            f()
            print("OK", meno)
