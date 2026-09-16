"""Vrstva pre OBCE. Opacna strana trhu nez zvysok portalu.

Zvysok portalu hovori dodavatelovi, ktora obec dostala peniaze. Tento modul
hovori obci, kde peniaze su. Zdroj je ten isty — Centralny register zmluv —
a nic nove sa nestahuje.

PRECO TO VZNIKLO: starostka malej obce po telefonate povedala, ze nevie ani
kde vyzvy hladat. Zoznam otvorenych vyziev sa ale z verejnych dat spolahlivo
zostavit neda (ITMS API vracia 403, eurofondy.gov.sk nema strukturovany
zdroj). Preto tu pocitam nieco ine, co sa z CRZ zostavit DA a co je v istom
zmysle silnejsie: kto PRAVE TERAZ realne podpisuje zmluvy s obcami.

Vyzva je prislub. Podpisana zmluva je dokaz, ze program plati.

DVE TABULKY:
  aktivne_programy   — kto rozdava, na co, kolko, kedy naposledy
  sprostredkovatelia — firmy, ktore obciam pisu ziadosti

POZOR NA SPROSTREDKOVATELOV. Starostka si priala vidiet ich uspesnost.
Uspesnost tu zamerne NIE JE a nikdy nebude, pretoze:
  1. V ziadosti o dotaciu sprostredkovatel nefiguruje — ziadost podava obec.
     Nedokazeme teda odlisit "obec dostala dotaciu vdaka firme X" od
     "obec dostala dotaciu a zhodou okolnosti mala aj zmluvu s firmou X".
  2. Firiem je ~70 a najvacsia ma nieco pod desiatku obci. Percento
     uspesnosti pri n = 2 nie je statistika.
  3. Zle cislo pri mene firmy, ktorej z toho zije, je pravny problem.
Publikujeme teda len FAKTY Z VEREJNYCH ZMLUV a kazdy sa da overit v CRZ.
"""
import logging
import re
from datetime import date, timedelta

import pandas as pd

import regiony

log = logging.getLogger("obce")

# Kto je samosprava. Rovnaky filter ako v subsidies, ale tu ide o obec
# v roli OBSTARAVATELA, nie prijimatela dotacie.
_JE_OBEC = re.compile(
    r"^\s*(obec|mesto|mestsk[aá]\s*[cč]as[tť])\s+", re.IGNORECASE)

# Zmluvy, ktorymi si obec kupuje pisanie ziadosti a riadenie projektu.
# Vzory su zamerne siroke — lepsie zachytit viac a dat to do kontextu,
# nez tvrdit, ze firiem je menej, nez v skutocnosti je.
_PROJEKTOVE_SLUZBY = re.compile(
    r"(vypracovan|spracovan)\w*\s+(a\s+)?(podan\w*\s+)?[zž]iadost"
    r"|[zž]iadost\w*\s+o\s+(poskytnutie\s+)?(nen[aá]vratn|dot[aá]ci)"
    r"|extern\w*\s+(projektov|riaden|mana[zž])"
    r"|projektov\w*\s+(mana[zž]|riaden)"
    r"|(poradenstv|konzulta)\w*.{0,40}(eurofond|dot[aá]ci|v[yý]zv)"
    r"|implement[aá]ci\w*\s+projekt",
    re.IGNORECASE)

# Okna, v ktorych meriame aktivitu programu.
DNI_KRATKE = 30
DNI_DLHE = 90

# Pod tolko zmluv v dlhom okne uz program nepovazujem za aktivny.
# Jedna zmluva za kvartal nie je program, je to nahoda.
MIN_ZMLUV_AKTIVNY = 3

MIN_OBCI_SPROSTREDKOVATEL = 1   # aj jedna obec je fakt, len to treba povedat
MIN_SUMA_DOTACIE = 20000        # rovnaky prah ako v subsidies


def _je_obec(nazov) -> bool:
    return bool(nazov) and bool(_JE_OBEC.match(str(nazov)))


def aktivne_programy(df: pd.DataFrame, dnes: date = None) -> pd.DataFrame:
    """Kto v poslednych mesiacoch realne podpisoval dotacne zmluvy s obcami.

    Vstup: vsetky zmluvy. Pri dotacnej zmluve je poskytovatel v poli
    obstaravatela a prijimatel (obec) v poli dodavatela — je to naopak
    nez pri beznej zmluve.
    """
    dnes = dnes or date.today()
    if df.empty:
        return pd.DataFrame()

    chyba = [c for c in ("sector", "authority_name", "supplier_name",
                         "price_total", "signed_on") if c not in df.columns]
    if chyba:
        raise KeyError(f"Aktivne programy: v datach chybaju stlpce {chyba}.")

    d = df[df["sector"] == "DOTACIE_NFP"].copy()
    if d.empty:
        return pd.DataFrame()

    d["podpisane"] = pd.to_datetime(d["signed_on"], errors="coerce")
    d["suma"] = pd.to_numeric(d["price_total"], errors="coerce")
    d = d[d["podpisane"].notna() & (d["suma"] >= MIN_SUMA_DOTACIE)]
    d = d[d["supplier_name"].apply(_je_obec)].copy()
    if d.empty:
        log.warning("Aktivne programy: po filtroch nezostala ziadna zmluva.")
        return pd.DataFrame()

    hranica_dlha = pd.Timestamp(dnes - timedelta(days=DNI_DLHE))
    hranica_kratka = pd.Timestamp(dnes - timedelta(days=DNI_KRATKE))

    okno = d[d["podpisane"] >= hranica_dlha].copy()
    if okno.empty:
        log.warning("Aktivne programy: za poslednych %s dni ziadna zmluva. "
                    "Bud je to sezona, alebo sa zastavil prisun dat.", DNI_DLHE)
        return pd.DataFrame()

    okno["kratke"] = (okno["podpisane"] >= hranica_kratka).astype(int)

    g = okno.groupby("authority_name")
    out = pd.DataFrame({
        "poskytovatel": g.size().index,
        "zmluv_90d": g.size().values,
        "zmluv_30d": g["kratke"].sum().values,
        "obci_90d": g["supplier_name"].nunique().values,
        "objem_90d": g["suma"].sum().round(0).values,
        "median_dotacie": g["suma"].median().round(0).values,
        "najmensia": g["suma"].min().round(0).values,
        "najvacsia": g["suma"].max().round(0).values,
        "posledna_zmluva": g["podpisane"].max().dt.strftime("%Y-%m-%d").values,
    })

    # Najcastejsi ucel poskytovatela.
    #
    # POZOR, TU BOLA CHYBA. Povodne som to cital zo stlpca `sektor_odhad`,
    # ktory na tabulke contracts VOBEC NIE JE — vznika az v subsidies.
    # Podmienka `if "sektor_odhad" in okno.columns` teda nikdy nesadla
    # a `hlavny_ucel` bol NULL pri vsetkych programoch. Na stranke sa
    # tym stratila jedina informacia, ktoru starostka naozaj potrebuje:
    # NA CO ten program peniaze dava. Tichy `else: None` to zamaskoval.
    #
    # Teraz sa ucel urcuje z textu zmluvy nasou taxonomiou, ktora je
    # napisana v jazyku obce ("Cesty, chodníky, most"), nie v sektoroch
    # navrhnutych na parovanie dodavatelov ("STAVEBNE_PRACE").
    import ucely
    text = (okno["subject"].fillna("") + " "
            + okno.get("subject_description", pd.Series("", index=okno.index)).fillna(""))
    okno["_ucel"] = [ucely.priradit(t)[1] for t in text]

    najcastejsi = (okno[okno["_ucel"].notna()]
                   .groupby("authority_name")["_ucel"]
                   .agg(lambda s: s.mode().iat[0] if not s.mode().empty else None))
    out["hlavny_ucel"] = out["poskytovatel"].map(najcastejsi)

    bez_ucelu = int(out["hlavny_ucel"].isna().sum())
    if bez_ucelu:
        log.info("Programov bez urceneho ucelu: %s z %s", bez_ucelu, len(out))

    out = out[out["zmluv_90d"] >= MIN_ZMLUV_AKTIVNY].copy()
    out = out.sort_values("objem_90d", ascending=False).reset_index(drop=True)

    for c in ("zmluv_90d", "zmluv_30d", "obci_90d"):
        out[c] = out[c].astype("Int64")

    log.info("Aktivnych programov (>=%s zmluv za %s dni): %s",
             MIN_ZMLUV_AKTIVNY, DNI_DLHE, len(out))
    return out


def sprostredkovatelia(df: pd.DataFrame) -> pd.DataFrame:
    """Firmy, ktore obciam pisu ziadosti o dotacie a riadia projekty.

    Iba fakty z verejnych zmluv. Ziadne skore, ziadne poradie podla
    uspesnosti — vysvetlenie je v hlavicke modulu.
    """
    if df.empty:
        return pd.DataFrame()

    chyba = [c for c in ("authority_name", "supplier_name", "supplier_cin",
                         "subject", "price_total", "signed_on")
             if c not in df.columns]
    if chyba:
        raise KeyError(f"Sprostredkovatelia: chybaju stlpce {chyba}.")

    d = df[df["authority_name"].apply(_je_obec)].copy()
    if d.empty:
        return pd.DataFrame()

    d = d[d["subject"].fillna("").apply(lambda s: bool(_PROJEKTOVE_SLUZBY.search(s)))]
    if d.empty:
        log.info("Sprostredkovatelia: ziadna zmluva na projektove sluzby.")
        return pd.DataFrame()

    # GDPR: zivnostnici von, rovnako ako pri profiloch dodavatelov.
    # Pri pochybnosti nezverejnujeme.
    import analytics
    d = d[d["supplier_name"].apply(analytics.je_pravnicka_osoba)].copy()
    if d.empty:
        return pd.DataFrame()

    d["suma"] = pd.to_numeric(d["price_total"], errors="coerce")
    d["podpisane"] = pd.to_datetime(d["signed_on"], errors="coerce")

    # Kraj obce, ktora si sluzbu kupila. Starostka chce vediet, kto robi
    # u nej v okoli — firma z druheho konca krajiny jej velmi nepomoze.
    d = regiony.doplnit(d)

    d["kluc"] = (d["supplier_cin"].astype(str).str.strip()
                  .replace({"": None, "nan": None, "None": None}))
    d["kluc"] = d["kluc"].fillna(d["supplier_name"].str.lower())

    g = d.groupby("kluc")
    out = pd.DataFrame({
        "kluc": g.size().index,
        "sprostredkovatel": g["supplier_name"].agg(lambda s: s.mode().iat[0]).values,
        "supplier_cin": g["supplier_cin"].first().values,
        "obci": g["authority_name"].nunique().values,
        "zmluv": g.size().values,
        "kraje": g["kraj"].agg(
            lambda s: ", ".join(sorted({x for x in s.dropna()}))[:120] or None).values,
        "median_ceny": g["suma"].median().round(0).values,
        "prva_zmluva": g["podpisane"].min().dt.strftime("%Y-%m-%d").values,
        "posledna_zmluva": g["podpisane"].max().dt.strftime("%Y-%m-%d").values,
    })

    out = out[out["obci"] >= MIN_OBCI_SPROSTREDKOVATEL].copy()

    # Zoradene podla poctu obci, co je FAKT, nie podla uspesnosti,
    # ktoru nemame. Pri rovnakom pocte rozhoduje novsia aktivita.
    out = out.sort_values(["obci", "posledna_zmluva"],
                          ascending=[False, False]).reset_index(drop=True)
    for c in ("obci", "zmluv"):
        out[c] = out[c].astype("Int64")

    log.info("Sprostredkovatelov: %s (obci spolu %s, zmluv %s)",
             len(out), int(out["obci"].sum()), int(out["zmluv"].sum()))
    return out


def porovnanie_okresov(df: pd.DataFrame, dnes: date = None) -> pd.DataFrame:
    """Kolko dotacii dostali obce v jednotlivych krajoch a ako su rozdelene.

    Toto je ten argument, po ktorom starostka zdvihne telefon: susedia si
    rozdelili X milionov, my sme dostali nula. Aby to ale nebolo zavadzajuce,
    pocitam aj kolko obci nedostalo NIC — bez toho by to vyzeralo, ze peniaze
    dostava kazdy okrem nas.
    """
    dnes = dnes or date.today()
    if df.empty:
        return pd.DataFrame()

    d = df[df["sector"] == "DOTACIE_NFP"].copy()
    d["suma"] = pd.to_numeric(d["price_total"], errors="coerce")
    d["podpisane"] = pd.to_datetime(d["signed_on"], errors="coerce")
    d = d[d["podpisane"].notna() & (d["suma"] >= MIN_SUMA_DOTACIE)]
    d = d[d["supplier_name"].apply(_je_obec)].copy()
    if d.empty:
        return pd.DataFrame()

    d = regiony.doplnit_z_nazvu(d, "supplier_name")
    d = d[d["kraj"].notna()].copy()
    if d.empty:
        log.warning("Porovnanie krajov: ziadnej obci sa nepodarilo urcit kraj.")
        return pd.DataFrame()

    g = d.groupby("kraj")
    out = pd.DataFrame({
        "kraj": g.size().index,
        "obci_s_dotaciou": g["supplier_name"].nunique().values,
        "dotacii": g.size().values,
        "objem_eur": g["suma"].sum().round(0).values,
        "median_dotacie": g["suma"].median().round(0).values,
        "od": g["podpisane"].min().dt.strftime("%Y-%m-%d").values,
    }).sort_values("objem_eur", ascending=False).reset_index(drop=True)

    for c in ("obci_s_dotaciou", "dotacii"):
        out[c] = out[c].astype("Int64")

    log.info("Porovnanie krajov: %s krajov, %s obci s dotaciou",
             len(out), int(out["obci_s_dotaciou"].sum()))
    return out
