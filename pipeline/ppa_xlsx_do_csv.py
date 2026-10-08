"""Jednorazovy prevod oficialneho xlsx PPA do kompaktneho CSV (data/ppa_vyplatene.csv).

Zdroj: apa.sk -> O nas -> Zverejnovane udaje -> "Prijimatelia pomoci z EPZF
a EPFRV" (Annex VIII, slovenska verzia, jeden subor za financny rok). Subory
sa stahuju RUCNE; pipeline z nich cita len vysledne male CSV v repozitari.

    python ppa_xlsx_do_csv.py "Annex VIII_..._FY 2024.xlsx" "Annex VIII_..._FY 2025.xlsx"

Financny rok N trva od 16. 10. (N-1) do 15. 10. N. Do CSV idu len obce a mesta
(nazov zacina "Obec"/"Mesto"/"Mestska cast") a len opatrenia rozvoja vidieka
(kod zacina "VI."); jeden riadok = jedna vyplatena operacia.

Stlpce vystupu: fy, fy_koniec, obec, kod, suma
"""
import csv
import re
import sys
from pathlib import Path

import openpyxl

_FY = re.compile(r"FY\s*(\d{4})")
_PREFIX = re.compile(r"^\s*(obec|mesto|mestsk[aá]\s*[cč]as[tť])\s+", re.I)


def _cislo(x) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def riadky_zo_suboru(cesta) -> list:
    cesta = Path(cesta)
    m = _FY.search(cesta.name)
    if not m:
        raise ValueError(f"V nazve suboru chyba 'FY RRRR': {cesta.name}")
    fy = int(m.group(1))
    ws = openpyxl.load_workbook(cesta, read_only=True).worksheets[0]
    vystup = []
    for r in ws.iter_rows(min_row=6, values_only=True):
        meno = str(r[0] or "").strip()
        kod = str(r[4] or "").strip()
        if not meno or not _PREFIX.match(meno) or not kod.startswith("VI."):
            continue
        # sucet za operaciu: EPZF + EPFRV + spolufinancovanie (stlpce G, I, K)
        suma = _cislo(r[6]) + _cislo(r[8]) + _cislo(r[10])
        if suma <= 0:
            continue
        vystup.append({"fy": fy, "fy_koniec": f"{fy}-10-15",
                       "obec": _PREFIX.sub("", meno).strip(),
                       "kod": kod, "suma": round(suma, 2)})
    return vystup


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print(__doc__)
        return 2
    vsetky = []
    for a in argv:
        r = riadky_zo_suboru(a)
        print(f"{a}: {len(r)} operacii")
        vsetky += r
    ciel = Path(__file__).parent / "data" / "ppa_vyplatene.csv"
    ciel.parent.mkdir(exist_ok=True)
    with open(ciel, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["fy", "fy_koniec", "obec", "kod", "suma"])
        w.writeheader()
        w.writerows(vsetky)
    print(f"Zapisane: {ciel} ({len(vsetky)} riadkov)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
