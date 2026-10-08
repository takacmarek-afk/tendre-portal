"""
Oznacenie dotacii PPA, ktore uz boli VYPLATENE (projekt je zrealizovany).

PREC: Pôdohospodárska platobná agentúra (PPA) vyplaca nenavratny
financny prispevok AZ PO realizacii projektu (refundacia). Zmluva v CRZ
je teda zvycajne podpisana pred projektom, ale vyplatena dotacia znamena,
ze obec uz postavila, co mala — verejne obstaravanie je za nou. Pre
zakaznika, ktory hlada prilezitost, je taka dotacia sum.

ZDROJ: PPA kazdy rok zverejnuje zoznam prijimatelov (priloha VIII
vykonavacieho nariadenia EU 2022/128). Financny rok N trva 16. 10. (N-1)
az 15. 10. N. Prevodnik xlsx -> csv je v `ppa_xlsx_do_csv.py`, vysledok
lezi v `pipeline/data/ppa_vyplatene.csv` (fy, fy_koniec, obec, kod, suma).
V zozname NIE JE nazov projektu ani ICO — parujem teda podla nazvu obce
a sumy.

PARUJEM OPATRNE. Falosne "vyplatene" skryje skutocnu prilezitost, kym
falosne "nevyplatene" len nechá riadok tam, kde bol doteraz. Preto:
  * poskytovatel musi byt PPA,
  * obec sa musi zhodovat v nazve (bez diakritiky a predpony Obec/Mesto),
  * vyplatena operacia nesmie koncit pred podpisom zmluvy,
  * suma operacie musi byt v [90 %, 100,5 %] sumy zmluvy (cast projektov
    sa preplati nizsie — kratenie, neuznatelne naklady),
  * jedna operacia vyplaty sa pouzije najviac pre jednu zmluvu
    (najmensia odchylka ma prednost).
Odmerane na 149 PPA dotaciach obci: presna zhoda (±0,5 %) 24 %.
"""
import csv
import logging
import os
import re
import unicodedata
from datetime import date

import pandas as pd

log = logging.getLogger("ppa_vyplatene")

CESTA = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "data", "ppa_vyplatene.csv")

TOLERANCIA_HORE = 1.005   # operacia nesmie byt vyssia nez zmluva (okrem zaokruhlenia)
TOLERANCIA_DOLE = 0.90    # a nie nizsia ako 90 % zmluvnej sumy

_PREDPONA = re.compile(r"^\s*(obec|mesto|mestska\s+cast)\s+")


def _norm(s) -> str:
    if not isinstance(s, str):
        return ""
    # CRZ casto posiela "Obec Xyz, Xyz 21, 951 44 Xyz" — nazov je pred ciarkou.
    s = s.split(",")[0]
    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = _PREDPONA.sub("", s)
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def je_ppa(poskytovatel) -> bool:
    n = _norm(poskytovatel)
    return "platobn" in n and "agentur" in n


def nacitaj(cesta: str = None) -> pd.DataFrame:
    """Nacita CSV; ked chyba, vrati prazdny DataFrame (nic sa neoznaci)."""
    cesta = cesta or CESTA
    if not os.path.exists(cesta):
        log.warning("PPA vyplatene: subor %s neexistuje, nic sa neoznaci.", cesta)
        return pd.DataFrame(columns=["fy", "fy_koniec", "obec", "kod", "suma"])
    p = pd.read_csv(cesta, dtype={"fy": str})
    p["suma"] = pd.to_numeric(p["suma"], errors="coerce")
    p["fy_koniec"] = pd.to_datetime(p["fy_koniec"], errors="coerce")
    return p.dropna(subset=["suma", "fy_koniec"]).reset_index(drop=True)


def oznac(d: pd.DataFrame, ppa: pd.DataFrame = None) -> pd.DataFrame:
    """Prida stlpce `vyplatene` (bool) a `vyplatene_fy` (text alebo None).

    Vstup `d` musi mat: prijimatel, poskytovatel, suma, podpisane, ucinne_od
    (retazce alebo datumy)."""
    d = d.copy()
    d["vyplatene"] = False
    d["vyplatene_fy"] = None
    if d.empty:
        return d
    if ppa is None:
        ppa = nacitaj()
    if ppa.empty:
        return d

    kluc_op = ppa["obec"].map(_norm)
    podla_obce = {}
    for i, k in kluc_op.items():
        if k:
            podla_obce.setdefault(k, []).append(i)

    podpis = pd.to_datetime(d["podpisane"], errors="coerce").fillna(
        pd.to_datetime(d["ucinne_od"], errors="coerce"))

    kandidati = []
    for idx, r in d.iterrows():
        if not je_ppa(r["poskytovatel"]):
            continue
        suma = r["suma"]
        if not suma or suma <= 0:
            continue
        for j in podla_obce.get(_norm(r["prijimatel"]), []):
            op = ppa.at[j, "suma"]
            pomer = op / suma
            if not (TOLERANCIA_DOLE <= pomer <= TOLERANCIA_HORE):
                continue
            if pd.notna(podpis[idx]) and ppa.at[j, "fy_koniec"] < podpis[idx]:
                continue
            kandidati.append((abs(1 - pomer), idx, j))

    kandidati.sort()
    pouzite_zmluvy, pouzite_op = set(), set()
    for _, idx, j in kandidati:
        if idx in pouzite_zmluvy or j in pouzite_op:
            continue
        pouzite_zmluvy.add(idx)
        pouzite_op.add(j)
        d.at[idx, "vyplatene"] = True
        d.at[idx, "vyplatene_fy"] = "FY" + str(ppa.at[j, "fy"])
    log.info("PPA vyplatene: %s z %s dotacii oznacenych ako vyplatene.",
             len(pouzite_zmluvy), len(d))
    return d
