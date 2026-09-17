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


# ── 4. tamSektora() a trhovyPodiel() ────────────────────────────────────────
#
# DNES je fixny referencny bod, aby testy nezavideli od aktualneho datumu.
# Okno DNI_TAM=365 pocita spatne od tohto dna.
DNES = pd.Timestamp("2026-09-17")


def _zmluva_tam(cena, dni_dozadu, ico="12345678", nazov="Firma s.r.o.",
                sektor=SEKTOR):
    """Riadok s POSTOU cenou (price_total), nie odvodenou mesacnou — presne
    to, co tamSektora()/trhovyPodiel() pouzivaju priamo, bez cenovy_zaklad()."""
    return {
        "sector": sektor,
        "price_total": cena,
        "signed_on": (DNES - pd.Timedelta(days=dni_dozadu)).strftime("%Y-%m-%d"),
        "supplier_cin": ico,
        "supplier_name": nazov,
    }


# 6) TAM: zaklad — vsetky zmluvy v okne, vsetky so znamou cenou.
riadky_tam = [_zmluva_tam(1000 + i * 10, dni_dozadu=i * 20, ico=f"ico{i}")
              for i in range(10)]
df_tam = _df(riadky_tam)
tam = analytics.tamSektora(df_tam, DNES)
print(f"6) TAM riadkov={len(tam)}")
assert len(tam) == 1, tam
r = tam.iloc[0]
print(f"   objem={r.objem_eur} pocet_s_cenou={r.pocet_s_cenou} spolahlivy={r.spolahlivy}")
assert r.objem_eur == sum(1000 + i * 10 for i in range(10)), r.objem_eur
assert r.pocet_s_cenou == 10
assert r.pocet_bez_ceny == 0
assert r.spolahlivy == True

# 7) TAM: zmluvy STARSIE nez DNI_TAM (365 dni) sa do okna nepocitaju.
riadky_okno = list(riadky_tam) + [_zmluva_tam(999999, dni_dozadu=400, ico="stary")]
df_okno = _df(riadky_okno)
tam2 = analytics.tamSektora(df_okno, DNES)
r2 = tam2.iloc[0]
print(f"7) so starou zmluvou (400 dni) objem={r2.objem_eur} (nesmie obsahovat 999999)")
assert r2.objem_eur == r.objem_eur, "zmluva mimo okna DNI_TAM sa nesmie pocitat"

# 8) TAM: ramcove dohody (cena 0) sa NEPOCITAJU do objem_eur, ale zvysia
#    pocet_bez_ceny. Vela z nich -> spolahlivy=False.
riadky_ramcove = list(riadky_tam) + [
    _zmluva_tam(0, dni_dozadu=10, ico=f"ramcova{i}") for i in range(15)
]
df_ramcove = _df(riadky_ramcove)
tam3 = analytics.tamSektora(df_ramcove, DNES)
r3 = tam3.iloc[0]
print(f"8) s 15 ramcovymi (0 EUR): objem={r3.objem_eur} pocet_bez_ceny={r3.pocet_bez_ceny} "
     f"spolahlivy={r3.spolahlivy}")
assert r3.objem_eur == r.objem_eur, "ramcove dohody (cena 0) nesmu zvysit objem_eur"
assert r3.pocet_bez_ceny == 15
assert r3.spolahlivy == False, "15 z 25 (60 %) bez ceny prekracuje MAX_PODIEL_BEZ_CENY"

# 9) TAM: sektor pod MIN_VZORIEK_TAM (menej nez 8 zmluv so ZNAMOU cenou)
#    sa vobec nezobrazi.
riadky_malo = [_zmluva_tam(500, dni_dozadu=5, ico=f"malo{i}") for i in range(5)]
tam4 = analytics.tamSektora(_df(riadky_malo), DNES)
print(f"9) 5 zmluv (pod MIN_VZORIEK_TAM): riadkov={len(tam4)}")
assert len(tam4) == 0

# 10) trhovyPodiel: TOP 5 z 8 dodavatelov, podiel_sektora_pct sa scita na
#     blizko 100 % (viac firiem ako TOP 5 v menovateli, takze menej).
riadky_podiel = []
for i in range(8):
    riadky_podiel += [_zmluva_tam(1000 * (8 - i), dni_dozadu=5,
                                   ico=f"firma{i}", nazov=f"Firma{i} s.r.o.")
                      for _ in range(2)]  # 2 zmluvy kazda firma, aby n>=8
podiel = analytics.trhovyPodiel(_df(riadky_podiel), DNES)
print(f"10) trhovy podiel riadkov={len(podiel)} (top 5 z 8 firiem)")
assert len(podiel) == 5, podiel
assert list(podiel["poradie"]) == [1, 2, 3, 4, 5]
assert podiel.iloc[0]["supplier_cin"] == "firma0", "najvacsi objem musi byt na 1. mieste"
assert podiel["podiel_sektora_pct"].iloc[0] > podiel["podiel_sektora_pct"].iloc[-1]

# 11) trhovyPodiel: fyzicka osoba (bez pravnej formy v nazve) sa NESMIE
#     objavit, ani keby mala najvacsi objem.
riadky_fo = list(riadky_podiel) + [
    _zmluva_tam(999999, dni_dozadu=5, ico="fyzickaosoba", nazov="Jan Novak")
    for _ in range(3)
]
podiel2 = analytics.trhovyPodiel(_df(riadky_fo), DNES)
print(f"11) s fyzickou osobou (najvyssi objem): jej ICO v top5 = "
     f"{'fyzickaosoba' in set(podiel2['supplier_cin'])}")
assert "fyzickaosoba" not in set(podiel2["supplier_cin"]), \
    "fyzicka osoba sa nesmie zobrazit ani s najvacsim objemom (GDPR)"

# 12) trhovyPodiel: sektor pod MIN_VZORIEK_TAM sa vobec nezobrazi.
riadky_malo2 = [_zmluva_tam(1000, dni_dozadu=5, ico=f"m{i}") for i in range(4)]
podiel3 = analytics.trhovyPodiel(_df(riadky_malo2), DNES)
print(f"12) 4 zmluvy v sektore (pod MIN_VZORIEK_TAM): riadkov={len(podiel3)}")
assert len(podiel3) == 0

print("VSETKY TESTY PRESLI (TAM a trhovy podiel)")
