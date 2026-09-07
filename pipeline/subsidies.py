"""Dotacie ako predzvest tendra.

Ked obec dostane nenavratny financny prispevok na rekonstrukciu skoly,
musi na tu rekonstrukciu vyhlasit verejne obstaravanie. Vidime to teda
o pol roka az rok a pol skor, nez sa tender objavi vo vestniku.

Pozor na semantiku CRZ: pri dotacnej zmluve je poskytovatel (ministerstvo,
agentura) v poli objednavatela a PRIJIMATEL, teda obec, je v poli dodavatela.
Je to naopak nez pri beznej zmluve.
"""
import logging
from datetime import date, timedelta

import pandas as pd

from classify import klasifikuj_ucel, SEKTOR_DOTACIE
from config import DOTACIA_OKNO_OD_DNI, DOTACIA_OKNO_DO_DNI, MIN_DOTACIA_EUR

log = logging.getLogger("subsidies")


def _je_samosprava(nazov: str) -> bool:
    """Hruby filter na obce, mesta, kraje a ich organizacie.
    Firmy dostavaju dotacie tiez, ale tie si obstaravanie robit nemusia."""
    if not nazov:
        return False
    n = str(nazov).lower()
    kluc = ("obec ", "mesto ", "mestska cast", "mestská časť", "samospravny kraj",
            "samosprávny kraj", "vyssi uzemny celok", "vyšší územný celok",
            "zakladna skola", "základná škola", "materska skola", "materská škola",
            "stredna skola", "stredná škola", "gymnazium", "gymnázium",
            "domov socialnych", "domov sociálnych", "nemocnica", "poliklinika")
    return any(k in n for k in kluc)


POTREBNE_STLPCE = ("sector", "price_total", "signed_on", "effective_from",
                   "supplier_name", "supplier_cin", "authority_name",
                   "subject", "subject_description", "id")


def z_contracts(df: pd.DataFrame, dnes: date = None) -> pd.DataFrame:
    """Vstup: vsetky ulozene zmluvy. Vystup: riadky pre tabulku subsidies."""
    dnes = dnes or date.today()
    if df.empty:
        return pd.DataFrame()

    # Chybajuci stlpec sa tu nesmie tvarit ako prazdna hodnota. Prave to nam
    # spravilo "dotacie=0" bez jedinej chybovej hlasky — filter na datum vyhodil
    # vsetko, pretoze `signed_on` sa vobec nestahoval z databazy.
    chyba = [c for c in POTREBNE_STLPCE if c not in df.columns]
    if chyba:
        raise KeyError(
            f"Dotacie: v datach chybaju stlpce {chyba}. "
            f"Doplnte ich do store.nacitaj_contracts.")

    d = df[df["sector"] == SEKTOR_DOTACIE].copy()
    log.info("Dotacnych zmluv v databaze: %s", len(d))
    if d.empty:
        return pd.DataFrame()

    d["suma"] = pd.to_numeric(d["price_total"], errors="coerce")
    d["podpisane"] = pd.to_datetime(d["signed_on"], errors="coerce")
    d["ucinne_od"] = pd.to_datetime(d["effective_from"], errors="coerce")

    # Zaklad pre odhad okna: ucinnost, a ked chyba, tak podpis.
    zaklad = d["ucinne_od"].fillna(d["podpisane"])
    d = d[zaklad.notna() & (d["suma"] >= MIN_DOTACIA_EUR)].copy()
    if d.empty:
        return pd.DataFrame()

    zaklad = d["ucinne_od"].fillna(d["podpisane"])
    d["okno_od"] = zaklad + pd.Timedelta(days=DOTACIA_OKNO_OD_DNI)
    d["okno_do"] = zaklad + pd.Timedelta(days=DOTACIA_OKNO_DO_DNI)

    # Dotacie, ktorym uz okno uplynulo, su bezcenne — tender uz bud bol,
    # alebo sa projekt nerealizoval.
    d = d[d["okno_do"] >= pd.Timestamp(dnes)].copy()
    if d.empty:
        return pd.DataFrame()

    # V CRZ je prijimatel dotacie v poli dodavatela.
    d["prijimatel"] = d["supplier_name"]
    d["prijimatel_ico"] = d["supplier_cin"]
    d["poskytovatel"] = d["authority_name"]

    d = d[d["prijimatel"].apply(_je_samosprava)].copy()
    if d.empty:
        return pd.DataFrame()

    d["ucel"] = d["subject"].fillna("") + " " + d["subject_description"].fillna("")
    d["ucel"] = d["ucel"].str.strip()
    d["sektor_odhad"] = d.apply(
        lambda r: klasifikuj_ucel(r["subject"], r["subject_description"]), axis=1)

    d["odkaz"] = "https://www.crz.gov.sk/zmluva/" + d["id"].astype(str) + "/"
    d["contract_id"] = d["id"]

    for c in ("podpisane", "ucinne_od", "okno_od", "okno_do"):
        d[c] = d[c].dt.strftime("%Y-%m-%d")

    stlpce = ["contract_id", "prijimatel", "prijimatel_ico", "poskytovatel",
              "ucel", "suma", "podpisane", "ucinne_od", "sektor_odhad",
              "okno_od", "okno_do", "odkaz"]
    out = d[stlpce].sort_values("suma", ascending=False).reset_index(drop=True)
    out["contract_id"] = pd.to_numeric(out["contract_id"], errors="coerce").astype("Int64")
    return out
