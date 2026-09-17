"""Testy pre analytics.py — predtym nemal tento subor ziadne pokrytie.

Zamerne pouziva len synteticke DataFrame, nie mock_crz: testuje cistu
statistiku, nie klasifikaciu ani stahovanie.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pandas as pd
import analytics
from config import SEKTORY_JEDNORAZOVE

SEKTOR = "UPRATOVANIE"
assert SEKTOR not in SEKTORY_JEDNORAZOVE, "test predpoklada opakovanu sluzbu (zaklad=mesiac)"


def _zmluva(cena_mesacna, signed_on, dni=365):
    """Postavi jeden riadok tak, aby cenovy_zaklad() z neho spocital presne
    zadanu mesacnu cenu."""
    return {
        "sector": SEKTOR,
        "effective_from": "2024-01-01",
        "effective_to": pd.Timestamp("2024-01-01") + pd.Timedelta(days=dni),
        "price_total": cena_mesacna * dni / 30.44,
        "signed_on": signed_on,
    }


def _df(riadky):
    return pd.DataFrame(riadky)


# ── 1. Zakladny pripad: median, kvartily, posledna cena ────────────────────
riadky = []
# 10 zmluv v uzkom pasme (500-700 EUR/mes) + 8 dalsich rovnako, aby sme
# presiahli MIN_VZORIEK (8) a mali rozptyl pod MAX_ROZPTYL (8.0).
ceny_a_datumy = [
    (500, "2023-01-10"), (520, "2023-03-10"), (540, "2023-05-10"),
    (560, "2023-07-10"), (580, "2023-09-10"), (600, "2023-11-10"),
    (620, "2024-01-10"), (640, "2024-03-10"), (660, "2024-05-10"),
    (680, "2024-07-10"),
]
for cena, datum in ceny_a_datumy:
    riadky.append(_zmluva(cena, datum))

df = _df(riadky)
zaklad = analytics.cenovy_zaklad(df)
vysledok = analytics.medianySektora(zaklad)

print(f"1) riadkov vo vysledku: {len(vysledok)}")
assert len(vysledok) == 1, vysledok

r = vysledok.iloc[0]
print(f"2) median={r.median_cena} vzoriek={r.vzoriek} q1={r.q1} q3={r.q3} "
      f"spolahlivy={r.spolahlivy}")
assert r.vzoriek == 10
assert r.spolahlivy == True, "uzke pasmo musi byt spolahlive"

# Najnovsi zaznam (podla signed_on) je 2024-07-10 s cenou 680.
print(f"3) posledna_cena={r.posledna_cena} datum={r.posledna_cena_datum}")
assert r.posledna_cena == 680.0, r.posledna_cena
assert r.posledna_cena_datum == "2024-07-10", r.posledna_cena_datum


# ── 2. Outlier s najnovsim datumom sa NESMIE stat "poslednou cenou" ────────
# Rovnaka sada + 15 dalsich riadkov v tesnom pasme (aby bolo n>=20 a orez
# extremov sa aktivoval), plus jeden extremny outlier s najnovsim datumom.
riadky2 = list(riadky)
for i in range(15):
    riadky2.append(_zmluva(600 + i, f"2022-0{(i % 9) + 1}-15"))
# Outlier: 50000 EUR/mes, podpisana najneskor zo vsetkych.
riadky2.append(_zmluva(50000, "2025-01-01"))

df2 = _df(riadky2)
zaklad2 = analytics.cenovy_zaklad(df2)
vysledok2 = analytics.medianySektora(zaklad2)
r2 = vysledok2.iloc[0]

print(f"4) n={r2.vzoriek} posledna_cena={r2.posledna_cena} "
      f"datum={r2.posledna_cena_datum} (outlier NESMIE byt 50000)")
assert r2.posledna_cena != 50000.0, (
    "outlier prekrocil orez extremov a stal sa 'poslednou cenou' — chyba")
assert r2.posledna_cena_datum != "2025-01-01"


# ── 3. Sektor pod MIN_VZORIEK sa nezobrazi vobec (ziadna posledna_cena) ────
malo = _df([_zmluva(500, "2024-01-01"), _zmluva(510, "2024-02-01")])
zaklad3 = analytics.cenovy_zaklad(malo)
vysledok3 = analytics.medianySektora(zaklad3)
print(f"5) sektor s 2 zmluvami (pod MIN_VZORIEK): riadkov={len(vysledok3)}")
assert len(vysledok3) == 0, "pod MIN_VZORIEK sa nesmie zobrazit vobec"

print("VSETKY TESTY PRESLI")
