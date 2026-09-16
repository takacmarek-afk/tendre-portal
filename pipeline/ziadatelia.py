"""TRETIA VRSTVA: obce, ktore si najali projektanta na ziadost o dotaciu.

Najdlhsi predstih v celom produkte.

RETAZ, KTORU TO VYUZIVA:
    obec si najme projektanta  ->  dotacia  ->  tender
             ~382 dni                 6-18 mesiacov

ODMERANE 16. 9. 2026 na vlastnych datach:
    101 obci si najalo sprostredkovatela na napisanie ziadosti
     70 z nich (69,3 %) potom dotaciu DOSTALO
    median odstupu najatie -> dotacia: 382 dni (p25 219, p75 584)
    median sumy takej dotacie: 129 094 EUR

DVE VECI, KTORE TREBA HOVORIT NAHLAS:

1. Tych 69,3 % NIE JE PRICINNOST. Obec, ktora si najme poradcu, je uz typ
   obce, co o peniaze ide. Na predikciu to nevadi — korelacia staci. Ale
   nikde netvrdime "vdaka poradcovi", pretoze to z tychto dat nevieme.

2. Je to SPODNA hranica, nie horna. Obce, ktore si poradcu najali nedavno,
   dotaciu dostat jednoducho nestihli, takze sa pocitaju ako neuspesne.
   Skutocny podiel bude vyssi.

CO S TOUTO VRSTVOU ROBIT: pri dvoch az dvoch a pol roku predstihu sa
neda pripravovat ponuka. Da sa nadviazat vztah s obcou — a to je presne
to okno, kedy sa to da urobit bez konkurencie.
"""
import logging
import re
from datetime import date, timedelta

import pandas as pd

import analytics
import regiony

log = logging.getLogger("ziadatelia")

# Rovnaky vzor ako v obce.sprostredkovatelia — drzim ho na jednom mieste
# tam a tu ho len importujem, aby sa obe vrstvy nemohli rozist.
import obce as _obce

MIN_CENA_SLUZBY = 500        # pod tym to nie je projektovy manazment
ODSTUP_MEDIAN_DNI = 382      # odmerane, nie odhadnute
ODSTUP_P25_DNI = 219
ODSTUP_P75_DNI = 584

# Kolko dni po najati uz signal nema cenu. Pri p75 = 584 dni davam rok
# navyse: co sa nestalo do dvoch rokov, sa uz asi nestane.
PLATNOST_DNI = 730


def z_contracts(df: pd.DataFrame, dnes: date = None) -> pd.DataFrame:
    """Obce, ktore si najali projektanta a dotaciu este nemaju.

    Obce, ktore uz dotaciu dostali, sem NEPATRIA — tie su vo vrstve dotacii
    a boli by tu druhy raz. Tato vrstva je o tom, co sa este len chysta.
    """
    dnes = dnes or date.today()
    if df is None or df.empty:
        return pd.DataFrame()

    chyba = [c for c in ("sector", "authority_name", "authority_cin",
                         "authority_address", "supplier_name", "supplier_cin",
                         "subject", "price_total", "signed_on")
             if c not in df.columns]
    if chyba:
        raise KeyError(f"Ziadatelia: v datach chybaju stlpce {chyba}.")

    # ── 1. Obce, ktore si kupili napisanie ziadosti ────────────────────────
    d = df[df["authority_name"].fillna("").apply(_obce._je_obec)].copy()
    d = d[d["subject"].fillna("").apply(
        lambda s: bool(_obce._PROJEKTOVE_SLUZBY.search(s)))]
    if d.empty:
        log.info("Ziadatelia: ziadna obec si nekupila projektove sluzby.")
        return pd.DataFrame()

    d["cena"] = pd.to_numeric(d["price_total"], errors="coerce")
    d["najate"] = pd.to_datetime(d["signed_on"], errors="coerce")
    d = d[d["najate"].notna() & (d["cena"].fillna(0) >= MIN_CENA_SLUZBY)]
    if d.empty:
        return pd.DataFrame()

    # GDPR: zivnostnici ako sprostredkovatelia sa nezverejnuju, rovnako
    # ako pri profiloch dodavatelov.
    d = d[d["supplier_name"].apply(analytics.je_pravnicka_osoba)].copy()
    if d.empty:
        return pd.DataFrame()

    d["kluc"] = (d["authority_cin"].astype(str).str.strip()
                  .replace({"": None, "nan": None, "None": None}))
    d["kluc"] = d["kluc"].fillna(d["authority_name"].str.lower())

    # Pri viacerych zmluvach beriem NAJNOVSIU — obec, ktora si najala
    # poradcu vlani aj teraz, je aktivnejsia, nie dvakrat v zozname.
    d = (d.sort_values("najate", ascending=False)
           .drop_duplicates("kluc", keep="first").copy())

    # ── 2. Vyradenie tych, ktore uz dotaciu dostali ───────────────────────
    dot = df[df["sector"] == "DOTACIE_NFP"].copy()
    dot["suma"] = pd.to_numeric(dot["price_total"], errors="coerce")
    dot["kedy"] = pd.to_datetime(dot["signed_on"], errors="coerce")
    dot = dot[(dot["suma"] >= 20000) & dot["kedy"].notna()]
    dot["kluc"] = (dot["supplier_cin"].astype(str).str.strip()
                    .replace({"": None, "nan": None, "None": None}))
    dot["kluc"] = dot["kluc"].fillna(dot["supplier_name"].str.lower())
    posledna_dotacia = dot.groupby("kluc")["kedy"].max()

    d["dotacia_po_najati"] = d.apply(
        lambda r: (posledna_dotacia.get(r["kluc"]) is not None
                   and pd.notna(posledna_dotacia.get(r["kluc"]))
                   and posledna_dotacia.get(r["kluc"]) >= r["najate"]), axis=1)

    pred = len(d)
    d = d[~d["dotacia_po_najati"]].copy()
    log.info("Ziadatelia: %s obci si najalo projektanta, %s z nich uz "
             "dotaciu dostalo (su vo vrstve dotacii), zostava %s",
             pred, pred - len(d), len(d))
    if d.empty:
        return pd.DataFrame()

    # ── 3. Okno, v ktorom sa da cakat dotacia ─────────────────────────────
    # Nie odhad z brucha: p25 a p75 odmerane na 70 obciach, ktorym to
    # naozaj preslo.
    d["okno_od"] = d["najate"] + pd.Timedelta(days=ODSTUP_P25_DNI)
    d["okno_do"] = d["najate"] + pd.Timedelta(days=ODSTUP_P75_DNI)
    d["ocakavane"] = d["najate"] + pd.Timedelta(days=ODSTUP_MEDIAN_DNI)

    # Co je starsie nez dva roky, uz signal nie je.
    hranica = pd.Timestamp(dnes - timedelta(days=PLATNOST_DNI))
    pred = len(d)
    d = d[d["najate"] >= hranica].copy()
    if pred != len(d):
        log.info("Ziadatelia: %s zaznamov starsich nez %s dni vyradenych",
                 pred - len(d), PLATNOST_DNI)
    if d.empty:
        return pd.DataFrame()

    # A ZAROVEN von s tymi, ktorym uz CELE OKNO PRESLO. Toto je samostatna
    # podmienka a nie je zbytocna: okno_do je `najate` + 584 dni, ale
    # platnost sa merala na 730, takze obec najata pred 600 dnami filtrom
    # vyssie presla, hoci jej okno zatvorilo pred dvoma mesiacmi. Odmerane
    # 16. 9. 2026 to boli 2 riadky z 24, teda 8,3 % vrstvy — mrtve leady,
    # ktore by sli aj do tyzdenneho e-mailu.
    #
    # Rovnake pravidlo ma subsidies.py (`d = d[d["okno_do"] >= dnes]`).
    # Drzim to konzistentne: co ma okno za sebou, do produktu nepatri.
    pred = len(d)
    d = d[d["okno_do"] >= pd.Timestamp(dnes)].copy()
    if pred != len(d):
        log.info("Ziadatelia: %s zaznamov s uz zatvorenym oknom vyradenych "
                 "(okno_do < dnes)", pred - len(d))
    if d.empty:
        return pd.DataFrame()

    d = regiony.doplnit(d)

    d["obec"] = d["authority_name"]
    d["obec_ico"] = d["authority_cin"]
    d["sprostredkovatel"] = d["supplier_name"]
    d["cena_sluzby"] = d["cena"].round(0)
    d["odkaz"] = "https://www.crz.gov.sk/zmluva/" + d["id"].astype(str) + "/"
    d["contract_id"] = pd.to_numeric(d["id"], errors="coerce").astype("Int64")

    for c in ("najate", "okno_od", "okno_do", "ocakavane"):
        d[c] = d[c].dt.strftime("%Y-%m-%d")

    stlpce = ["contract_id", "obec", "obec_ico", "mesto", "kraj",
              "sprostredkovatel", "cena_sluzby", "najate",
              "okno_od", "ocakavane", "okno_do", "odkaz"]
    out = (d[stlpce].sort_values("najate", ascending=False)
                    .reset_index(drop=True))

    log.info("Ziadatelia: %s obci v okne, najnovsia najala %s",
             len(out), out["najate"].iat[0] if len(out) else "-")
    return out
