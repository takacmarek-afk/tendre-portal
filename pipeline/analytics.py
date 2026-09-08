"""Analyticka vrstva — to, co z dat vieme vytiazit bez noveho zdroja.

  1. CENOVY BENCHMARK   median ceny v sektore, so zakladom podla typu sektora
  2. CYKLUS OBSTARAVANIA odstupy zmluv toho isteho uradu -> lepsi odhad tendra
  3. PROFIL DODAVATELA   agregat per ICO -> kto najviac pracuje pre stat

CO TU UZ NIE JE A PRECO
-----------------------
Bola tu funkcia `navysenie()`, ktora pocitala `price_total - price` ako
navysenie dodatkami. Dokumentacia CRZ definuje `price_total` ako celkovu sumu
vratane dodatkov. Meranie na 44 566 nedotacnych zmluvach ukazalo:

    price_total = price          23 374 zmluv
    price_total > price * 1.01       34 zmluv   (0,15 %)

`price_total` je v praxi duplikat `price`. Dodatky su v CRZ samostatne
zaznamy s vlastnym ID a rodicovska zmluva sa neprepisuje. Funkcia bola
odstranena aj s celou nadvazujucou funkcionalitou v UI.

Pouceniе: definiciu pola zo schemy vzdy odmerat na datach skor, nez sa na
nej postavi funkcia produktu.
"""
import logging

import pandas as pd

from config import SEKTORY_JEDNORAZOVE, PRAVNE_FORMY

log = logging.getLogger("analytics")

# Kratsie zmluvy nema zmysel prepocitavat na mesiac — jednorazova dodavka
# za 50 000 EUR na dva tyzdne by vysla na 100 000 EUR mesacne.
MIN_DNI_TRVANIA = 60

# Pod tymto poctom vzoriek median nezobrazujeme. Tri zmluvy nie su benchmark
# a jedno zle porovnanie zabije doveru v cely produkt.
MIN_VZORIEK = 8

# Minimalny pocet zmluv, aby sme dodavatela vobec profilovali.
MIN_ZMLUV_DODAVATELA = 3


# ── 1. CENOVY BENCHMARK ──────────────────────────────────────────────────

def zaklad_sektora(sektor: str) -> str:
    """"mesiac" pre opakovane sluzby, "zmluva" pre jednorazove prace."""
    return "zmluva" if sektor in SEKTORY_JEDNORAZOVE else "mesiac"


def cenovy_zaklad(df: pd.DataFrame) -> pd.DataFrame:
    """Prida stlpce dni_trvania, mesacna_cena a porovnavaciu_cenu.

    `porovnavacia_cena` je to, co sa naozaj porovnava s medianom: pri
    opakovanych sluzbach mesacna sadzba, pri jednorazovych pracach celkova
    cena zmluvy.
    """
    d = df.copy()
    od = pd.to_datetime(d.get("effective_from"), errors="coerce")
    do = pd.to_datetime(d.get("effective_to"), errors="coerce")
    suma = pd.to_numeric(d.get("price_total"), errors="coerce")

    dni = (do - od).dt.days
    d["dni_trvania"] = dni

    pouzitelne = dni.notna() & (dni >= MIN_DNI_TRVANIA) & suma.notna() & (suma > 0)
    d["mesacna_cena"] = (suma / (dni / 30.44)).where(pouzitelne).round(2)

    d["zaklad"] = d["sector"].apply(zaklad_sektora)
    d["porovnavacia_cena"] = d["mesacna_cena"].where(
        d["zaklad"] == "mesiac", suma.where(suma > 0))
    return d


def medianySektora(df: pd.DataFrame) -> pd.DataFrame:
    """Median porovnavacej ceny per sektor, s poctom vzoriek a kvartilmi.

    Kvartily su tam zamerne. Jediny median bez rozptylu vyzera ako presna
    hodnota, ktorou sa da nacenit ponuka — a to nie je. Zakaznik ma vidiet,
    ako siroke je pasmo, v ktorom sa realne zmluvy pohybuju.
    """
    prazdna = pd.DataFrame(columns=["sector", "median_cena", "vzoriek",
                                    "q1", "q3", "zaklad"])
    if df.empty or "porovnavacia_cena" not in df.columns:
        return prazdna
    d = df[df["porovnavacia_cena"].notna()]
    if d.empty:
        return prazdna

    g = (d.groupby("sector")["porovnavacia_cena"]
           .agg(median_cena="median", vzoriek="count",
                q1=lambda s: s.quantile(0.25), q3=lambda s: s.quantile(0.75))
           .reset_index())
    for c in ("median_cena", "q1", "q3"):
        g[c] = g[c].round(2)
    g["zaklad"] = g["sector"].apply(zaklad_sektora)
    return g[g["vzoriek"] >= MIN_VZORIEK].reset_index(drop=True)


def porovnaj_so_sektorom(df: pd.DataFrame, medianyDf: pd.DataFrame) -> pd.DataFrame:
    """Prida median sektora a odchylku v percentach."""
    if medianyDf.empty:
        for c in ("median_cena", "vzoriek", "q1", "q3", "odchylka_pct"):
            df[c] = None
        return df

    d = df.merge(medianyDf.drop(columns=["zaklad"]), on="sector", how="left")
    d["odchylka_pct"] = (
        (d["porovnavacia_cena"] / d["median_cena"] - 1) * 100
    ).round(0)
    d.loc[d["median_cena"].isna() | d["porovnavacia_cena"].isna(),
          "odchylka_pct"] = None
    return d


# ── 2. CYKLUS OBSTARAVANIA ───────────────────────────────────────────────

def cykly(df: pd.DataFrame) -> pd.DataFrame:
    """Pre kazdu dvojicu (urad, sektor) zisti typicku dlzku zmluvy.

    Lepsi odhad, kedy pride tender, nez pausalne "koniec minus 75 dni":
    ak urad obstarava upratovanie kazdych 24 mesiacov, vieme to z historie
    jeho vlastnych zmluv.

    NEZVALIDOVANE: neviem, ci urad s dvoma dvojrocnymi zmluvami podpise
    tretiu tiez na dva roky. Prve meranie bude mozne az z historizacie.
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


# ── 3. PROFIL DODAVATELA ─────────────────────────────────────────────────

def je_pravnicka_osoba(nazov) -> bool:
    """Ma nazov rozpoznatelnu pravnu formu?

    Zivnostnik je fyzicka osoba. Jeho meno spolu s ICO, objemom zmluv
    a zoznamom uradov je profilovanie osobnych udajov — a to za platenou
    stenou potrebuje pravny zaklad, informacnu povinnost podla cl. 14 GDPR
    a zrejme posudenie vplyvu. Nespracuvat ich je lacnejsie nez to riesit.

    Pri pochybnosti vraciame False: radsej vypustit firmu, nez zverejnit
    fyzicku osobu.
    """
    if not nazov:
        return False
    n = str(nazov).lower().replace(",", " ")
    return any(f in n for f in PRAVNE_FORMY)


def dodavatelia(df: pd.DataFrame, min_zmluv: int = MIN_ZMLUV_DODAVATELA) -> pd.DataFrame:
    """Kto najviac pracuje pre stat, za kolko, u kolkych uradov a odkedy dokedy.

    Stlpec `posledna_zmluva` je pre zakaznika cennejsi, nez vyzera:
    konkurent, ktory naposledy vyhral v roku 2022, uz nie je hrozba.
    """
    if df.empty or "supplier_cin" not in df.columns:
        return pd.DataFrame()

    d = df[df["supplier_cin"].notna() & (df["supplier_cin"].astype(str) != "")].copy()
    if d.empty:
        return pd.DataFrame()

    # GDPR: fyzicke osoby von, este pred agregaciou.
    pred = d["supplier_cin"].nunique()
    d = d[d["supplier_name"].apply(je_pravnicka_osoba)].copy()
    if d.empty:
        log.warning("Po vylucení fyzickych osob nezostal ziadny dodavatel.")
        return pd.DataFrame()
    log.info("Dodavatelia: %s z %s ICO ma rozpoznatelnu pravnu formu",
             d["supplier_cin"].nunique(), pred)

    d["price_total"] = pd.to_numeric(d["price_total"], errors="coerce")

    g = d.groupby("supplier_cin").agg(
        dodavatel=("supplier_name", "first"),
        zmluv=("id", "count"),
        objem_eur=("price_total", "sum"),
        uradov=("authority_cin", "nunique"),
        sektorov=("sector", "nunique"),
        prva_zmluva=("signed_on", "min"),
        posledna_zmluva=("signed_on", "max"),
    ).reset_index()

    g = g[g["zmluv"] >= min_zmluv].copy()
    if g.empty:
        return pd.DataFrame()

    g["objem_eur"] = g["objem_eur"].round(2)
    g["priemerna_zmluva_eur"] = (g["objem_eur"] / g["zmluv"]).round(2)

    hlavny = (d.groupby(["supplier_cin", "sector"]).size()
                .reset_index(name="n")
                .sort_values("n", ascending=False)
                .drop_duplicates("supplier_cin")[["supplier_cin", "sector"]]
                .rename(columns={"sector": "hlavny_sektor"}))
    g = g.merge(hlavny, on="supplier_cin", how="left")

    return g.sort_values("objem_eur", ascending=False).reset_index(drop=True)
