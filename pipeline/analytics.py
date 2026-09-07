"""Analyticka vrstva — to, co z dat vieme vytiazit bez noveho zdroja.

Styri veci, vsetky z dat, ktore uz mame ulozene:

  1. MESACNA CENA        suma / dlzka zmluvy -> porovnatelna v ramci sektora
  2. NAVYSENIE DODATKAMI price_total - price -> ktory dodavatel si priplaca
  3. CYKLUS OBSTARAVANIA odstupy zmluv toho isteho uradu -> lepsi odhad tendra
  4. PROFIL DODAVATELA   agregat per ICO -> kto najviac pracuje pre stat

Bod 2 je najcennejsi a najdlhsie nam unikal. Schema CRZ definuje
`price` ako zmluvne dohodnutu sumu a `price_total` ako celkovu sumu
VRATANE DODATKOV. Navysenie po podpise teda nemusime nikde dopocitavat
ani parsovat — je to rozdiel dvoch stlpcov pri kazdej zmluve.
"""
import logging

import pandas as pd

log = logging.getLogger("analytics")

# Kratsie zmluvy nemaju zmysel prepocitavat na mesiac — jednorazova dodavka
# za 50 000 EUR na dva tyzdne by vysla na 100 000 EUR mesacne.
MIN_DNI_TRVANIA = 60

# Pod tymto poctom vzoriek median nezobrazujeme. Tri zmluvy nie su benchmark
# a jedno zle porovnanie zabije doveru v cely produkt.
MIN_VZORIEK = 8

# Navysenie pod jedno procento je zaokruhlovanie, nie dodatok.
MIN_NAVYSENIE_PCT = 1.0


# ── 1. MESACNA CENA ──────────────────────────────────────────────────────

def mesacna_cena(df: pd.DataFrame) -> pd.DataFrame:
    """Prida stlpce mesacna_cena, dni_trvania.

    Neporovnava rozsah — upratovanie kancelarie a nemocnice su obe
    "upratovanie". Preto sa vysledok NIKDY nesmie zobrazit ako verdikt
    "toto je drahe", len ako poloha v rozdeleni s poctom vzoriek.
    """
    d = df.copy()
    od = pd.to_datetime(d.get("effective_from"), errors="coerce")
    do = pd.to_datetime(d.get("effective_to"), errors="coerce")
    suma = pd.to_numeric(d.get("price_total"), errors="coerce")

    dni = (do - od).dt.days
    d["dni_trvania"] = dni
    pouzitelne = dni.notna() & (dni >= MIN_DNI_TRVANIA) & suma.notna() & (suma > 0)
    d["mesacna_cena"] = (suma / (dni / 30.44)).where(pouzitelne).round(2)
    return d


def medianyMesacnej(df: pd.DataFrame) -> pd.DataFrame:
    """Median mesacnej ceny per sektor. Vracia aj pocet vzoriek — bez neho
    je median cislo bez vypovednej hodnoty."""
    d = df[df["mesacna_cena"].notna()]
    if d.empty:
        return pd.DataFrame(columns=["sector", "median_mesacna", "vzoriek"])
    g = (d.groupby("sector")["mesacna_cena"]
           .agg(median_mesacna="median", vzoriek="count")
           .reset_index())
    g["median_mesacna"] = g["median_mesacna"].round(2)
    return g[g["vzoriek"] >= MIN_VZORIEK]


def porovnaj_so_sektorom(df: pd.DataFrame, medianyDf: pd.DataFrame) -> pd.DataFrame:
    """Prida median sektora a odchylku v percentach."""
    d = df.merge(medianyDf, on="sector", how="left")
    d["odchylka_pct"] = (
        (d["mesacna_cena"] / d["median_mesacna"] - 1) * 100
    ).round(0)
    d.loc[d["median_mesacna"].isna() | d["mesacna_cena"].isna(), "odchylka_pct"] = None
    return d


# ── 2. NAVYSENIE DODATKAMI ───────────────────────────────────────────────

def navysenie(df: pd.DataFrame) -> pd.DataFrame:
    """Prida navysenie_eur a navysenie_pct z rozdielu price a price_total."""
    d = df.copy()
    zmluvna = pd.to_numeric(d.get("price"), errors="coerce")
    celkova = pd.to_numeric(d.get("price_total"), errors="coerce")

    platne = zmluvna.notna() & celkova.notna() & (zmluvna > 0)
    rozdiel = (celkova - zmluvna).where(platne)
    pct = (rozdiel / zmluvna * 100).where(platne).round(1)

    # Zaporne hodnoty su chyby v zdroji alebo znizenie ceny, nie navysenie
    d["navysenie_eur"] = rozdiel.where(pct >= MIN_NAVYSENIE_PCT).round(2)
    d["navysenie_pct"] = pct.where(pct >= MIN_NAVYSENIE_PCT)
    return d


# ── 3. CYKLUS OBSTARAVANIA ───────────────────────────────────────────────

def cykly(df: pd.DataFrame) -> pd.DataFrame:
    """Pre kazdu dvojicu (urad, sektor) zisti typicku dlzku zmluvy.

    Lepsi odhad, kedy pride tender, nez pausalne "koniec minus 75 dni":
    ak urad obstarava upratovanie kazdych 24 mesiacov, vieme to z historie
    jeho vlastnych zmluv.
    """
    d = df.copy()
    d["dni_trvania"] = pd.to_numeric(d.get("dni_trvania"), errors="coerce")
    d = d[d["dni_trvania"].between(60, 2000) & d["authority_cin"].notna()]
    if d.empty:
        return pd.DataFrame(columns=["authority_cin", "sector",
                                     "typicka_dlzka_dni", "zmluv_v_historii"])
    g = (d.groupby(["authority_cin", "sector"])["dni_trvania"]
           .agg(typicka_dlzka_dni="median", zmluv_v_historii="count")
           .reset_index())
    g["typicka_dlzka_dni"] = g["typicka_dlzka_dni"].round(0)
    return g[g["zmluv_v_historii"] >= 2]


# ── 4. PROFIL DODAVATELA ─────────────────────────────────────────────────

def dodavatelia(df: pd.DataFrame, min_zmluv: int = 3) -> pd.DataFrame:
    """Kto najviac pracuje pre stat, za kolko, a kto si priplaca dodatkami.

    POZOR NA FORMULACIU: vysoke navysenie nie je dokaz niceho nekaleho.
    Legitimne dovody existuju — zmena projektu, najdene skryte konstrukcie,
    inflacia pri viacrocnych stavbach. Zobrazuj to ako fakt s kontextom,
    nikdy ako obvinenie.
    """
    d = df[df["supplier_cin"].notna() & (df["supplier_cin"].astype(str) != "")].copy()
    if d.empty:
        return pd.DataFrame()

    d["price_total"] = pd.to_numeric(d["price_total"], errors="coerce")
    d["navysenie_pct"] = pd.to_numeric(d.get("navysenie_pct"), errors="coerce")

    g = d.groupby("supplier_cin").agg(
        dodavatel=("supplier_name", "first"),
        zmluv=("id", "count"),
        objem_eur=("price_total", "sum"),
        uradov=("authority_cin", "nunique"),
        sektorov=("sector", "nunique"),
        zmluv_s_navysenim=("navysenie_pct", "count"),
        priemerne_navysenie_pct=("navysenie_pct", "mean"),
        prva_zmluva=("signed_on", "min"),
        posledna_zmluva=("signed_on", "max"),
    ).reset_index()

    g = g[g["zmluv"] >= min_zmluv].copy()
    if g.empty:
        return pd.DataFrame()

    g["objem_eur"] = g["objem_eur"].round(2)
    g["priemerne_navysenie_pct"] = g["priemerne_navysenie_pct"].round(1)
    g["podiel_zmluv_s_navysenim"] = (
        g["zmluv_s_navysenim"] / g["zmluv"]).round(2)
    g["priemerna_zmluva_eur"] = (g["objem_eur"] / g["zmluv"]).round(2)

    # Hlavny sektor dodavatela
    hlavny = (d.groupby(["supplier_cin", "sector"]).size()
                .reset_index(name="n")
                .sort_values("n", ascending=False)
                .drop_duplicates("supplier_cin")[["supplier_cin", "sector"]]
                .rename(columns={"sector": "hlavny_sektor"}))
    g = g.merge(hlavny, on="supplier_cin", how="left")

    return g.sort_values("objem_eur", ascending=False).reset_index(drop=True)
