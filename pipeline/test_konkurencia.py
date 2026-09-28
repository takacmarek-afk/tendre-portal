"""'Kde chýba konkurencia' (audit 27. 9. 2026, P2.1): jeSlabaKonkurencia().

Rovnaký princip ako test_moj_vyber.py: funkcia žije len v public/app.html,
vytiahne sa regexom a spustí cez node so svojou závislosťou (num()).
Spustenie: python test_konkurencia.py (vyžaduje node v PATH).
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


def test_je_slaba_konkurencia():
    kod = _vytiahni("num") + "\n" + _vytiahni("jeSlabaKonkurencia")
    pripady = [1, 2, 3, 10, 0, None, "2", "0", "neplatne"]
    ocakavane = [True, True, False, False, False, False, True, False, False]
    riadky = [f"const V = {json.dumps(pripady)};",
               "console.log(JSON.stringify(V.map(jeSlabaKonkurencia)));"]
    p = subprocess.run(["node", "-e", kod + "\n" + "\n".join(riadky)],
                        capture_output=True, text=True)
    assert p.returncode == 0, f"node zlyhal: {p.stderr}"
    vysledky = json.loads(p.stdout)
    assert vysledky == ocakavane, f"jeSlabaKonkurencia: {vysledky} != {ocakavane}"


if __name__ == "__main__":
    for meno, f in list(globals().items()):
        if meno.startswith("test_") and callable(f):
            f()
            print("OK", meno)
