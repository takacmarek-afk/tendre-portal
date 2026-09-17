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

# ── PRAH ROZPTYLU ────────────────────────────────────────────────────────
#
# Nameraně na 227 731 zmluvach: v niektorych sektoroch je medzikvartilove
# rozpetie absurdne siroke.
#
#   ZELEN_ZIMNA_UDRZBA   IQR    57 -  9 192 EUR/mes   = 161x
#   ELEKTROINSTALACIE    IQR    55 -  6 119 EUR/mes   = 111x
#   OSTRAHA              IQR    99 -  8 302 EUR/mes   =  84x
#   STAVEBNE_PRACE       IQR 8 453 -178 721 EUR/zml   =  21x
#   UPRATOVANIE          IQR   449 -  3 137 EUR/mes   =   7x
#   STRAVOVANIE          IQR   960 -  6 141 EUR/mes   =   6x
#   TLAC_KANCELARIA      IQR   616 -  2 684 EUR/mes   =   4x
#
# Ked stredna polovica zmluv siaha od 57 do 9 192 EUR, median nehovori nic.
# Zakaznik, ktory podla neho naceni ponuku, prehra — a bude to nasa vina.
# Dovod je, ze sektor nie je homogenna kategoria: "upratovanie" je kancelaria
# aj nemocnica, "zelen" je jedno kosenie aj celorocna sprava parkov.
#
# Preto sa median zobrazuje ako porovnavacia kotva LEN tam, kde je rozptyl
# znesitelny. Inde zostane pasmo viditelne, ale bez tvrdenia "o X % oproti
# medianu". Radsej menej tvrdeni nez jedno nespravne.
MAX_ROZPTYL = 8.0

# Extremy sa pred vypoctom odstrihnu. Zmluva na osem rokov za 6 000 EUR
# vychadza na 62 EUR mesacne — je to platny zaznam, ale s beznou zakazkou
# porovnatelny nie je a median aj kvartily posuva.
ODSTRIH = 0.05

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


def _orez_extremov(s: pd.Series) -> pd.Series:
    """Boolean maska: True pre hodnoty v ramci orezaneho rozsahu (ODSTRIH).

    Vytiahnute zo `statistiky()` nizsie, aby ten isty orez pouzivala aj
    `posledna_skutocna_cena()` — bez tejto zdielanej funkcie by sa obe
    miesta casom rozisli a "posledna cena" by mohla byt outlier, ktory
    median uz davno vyradil.
    """
    if len(s) < 20:
        return pd.Series(True, index=s.index)
    dolna, horna = s.quantile(ODSTRIH), s.quantile(1 - ODSTRIH)
    return s.between(dolna, horna)


def _posledna_skutocna_cena(d: pd.DataFrame, sektory: set) -> pd.DataFrame:
    """Pre kazdy sektor v `sektory`: cena a datum NAJNOVSIEHO (podla signed_on)
    zaznamu, ktory prezil rovnaky orez extremov ako median.

    Median je abstrakcia rozdelenia. Zakaznik sa casto pyta na konkretnejsiu
    vec: za kolko sa naposledy REALNE sutazilo. Toto je odpoved na tu otazku,
    nie na "aka je typicka cena" — preto vlastne pole, nie nahrada medianu.
    """
    if "signed_on" not in d.columns:
        return pd.DataFrame(columns=["sector", "posledna_cena", "posledna_cena_datum"])
    d = d.copy()
    d["signed_on"] = pd.to_datetime(d["signed_on"], errors="coerce")
    riadky = []
    for sektor, skupina in d.groupby("sector"):
        if sektor not in sektory:
            continue
        skupina = skupina[_orez_extremov(skupina["porovnavacia_cena"])]
        skupina = skupina[skupina["signed_on"].notna()]
        if skupina.empty:
            continue
        posledny = skupina.sort_values("signed_on").iloc[-1]
        riadky.append({
            "sector": sektor,
            "posledna_cena": round(float(posledny["porovnavacia_cena"]), 2),
            "posledna_cena_datum": posledny["signed_on"].strftime("%Y-%m-%d"),
        })
    return pd.DataFrame(riadky, columns=["sector", "posledna_cena", "posledna_cena_datum"])


def medianySektora(df: pd.DataFrame) -> pd.DataFrame:
    """Median porovnavacej ceny per sektor, s poctom vzoriek, kvartilmi,
    priznakom, ci je vobec pouzitelny ako porovnavacia kotva, a poslednou
    skutocnou cenou (konkretne cislo s datumom, popri abstraktnom pasme).

    Kvartily su tam zamerne. Jediny median bez rozptylu vyzera ako presna
    hodnota, ktorou sa da nacenit ponuka — a to nie je.
    """
    stlpce = ["sector", "median_cena", "vzoriek", "q1", "q3",
              "rozptyl", "spolahlivy", "zaklad",
              "posledna_cena", "posledna_cena_datum"]
    if df.empty or "porovnavacia_cena" not in df.columns:
        return pd.DataFrame(columns=stlpce)
    d = df[df["porovnavacia_cena"].notna()]
    if d.empty:
        return pd.DataFrame(columns=stlpce)

    def statistiky(s: pd.Series) -> pd.Series:
        # Odstrih extremov pred vypoctom. Nie kvoli kozmetike: dlhe ramcove
        # zmluvy za male sumy davaju desiatky EUR mesacne a posuvaju aj
        # median, aj kvartily.
        s = s[_orez_extremov(s)]
        if s.empty:
            return pd.Series({"median_cena": None, "vzoriek": 0,
                              "q1": None, "q3": None})
        return pd.Series({
            "median_cena": round(float(s.median()), 2),
            "vzoriek": int(len(s)),
            "q1": round(float(s.quantile(0.25)), 2),
            "q3": round(float(s.quantile(0.75)), 2),
        })

    g = d.groupby("sector")["porovnavacia_cena"].apply(statistiky).unstack().reset_index()
    g = g[g["vzoriek"] >= MIN_VZORIEK].copy()
    if g.empty:
        return pd.DataFrame(columns=stlpce)

    g["rozptyl"] = (g["q3"] / g["q1"]).round(1)
    g["spolahlivy"] = g["rozptyl"].notna() & (g["rozptyl"] <= MAX_ROZPTYL)
    g["zaklad"] = g["sector"].apply(zaklad_sektora)
    g["vzoriek"] = g["vzoriek"].astype("Int64")

    posledne = _posledna_skutocna_cena(d, set(g["sector"]))
    g = g.merge(posledne, on="sector", how="left")

    nespolahlive = g.loc[~g["spolahlivy"], "sector"].tolist()
    if nespolahlive:
        log.info("Benchmark bez porovnavacej kotvy (rozptyl nad %sx): %s",
                 MAX_ROZPTYL, ", ".join(nespolahlive))
    return g[stlpce].reset_index(drop=True)


def porovnaj_so_sektorom(df: pd.DataFrame, medianyDf: pd.DataFrame) -> pd.DataFrame:
    """Prida median sektora, kvartily a odchylku v percentach.

    Odchylka sa pocita LEN v sektoroch, kde je rozptyl znesitelny. Tam, kde
    stredna polovica zmluv siaha cez dva rady velkosti, je "o 15 % nad
    medianom" cislo, ktore znie presne a pritom nic neznamena.
    """
    if medianyDf.empty:
        for c in ("median_cena", "vzoriek", "q1", "q3", "rozptyl",
                  "spolahlivy", "odchylka_pct"):
            df[c] = None
        return df

    d = df.merge(medianyDf.drop(columns=["zaklad"]), on="sector", how="left")
    d["odchylka_pct"] = (
        (d["porovnavacia_cena"] / d["median_cena"] - 1) * 100
    ).round(0)
    d.loc[d["median_cena"].isna()
          | d["porovnavacia_cena"].isna()
          | (d["spolahlivy"] != True), "odchylka_pct"] = None
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


# ── 4. TAM A TRHOVY PODIEL ────────────────────────────────────────────────
#
# Oboje su z toho isteho dovodu "Nizka narocnost" v ziskatelnej analyze
# (Pilier 2 bod 2, Pilier 4 bod 2): ciste agregacie nad uz stiahnutymi
# zmluvami, ziadny novy datovy zdroj. Zdielaju rovnake okno a rovnaky
# hlavny risk: cena 0 v CRZ znamena ramcovu dohodu bez celkovej sumy (rovnaky
# fakt ako _eur()/_cislo_kladne() v posli_email.py), takze objem pocitany
# len zo znamych cien VZDY podhodnocuje skutocny trh o neznamu mieru.

# TAM ma zmysel ako "kolko sa v tomto segmente rocne minie", nie ako
# kumulativny sucet od zaciatku datasetu (ten by len rastol a nehovoril nic
# o buducom roku). Preto klzave okno, nie cela historia.
DNI_TAM = 365

# Pod tymto poctom zmluv SO ZNAMOU CENOU v okne sektor vobec nezobrazujeme —
# rovnaky dovod ako MIN_VZORIEK vyssie.
MIN_VZORIEK_TAM = MIN_VZORIEK

# Ked viac nez tuto cast zmluv v okne nema uvedenu cenu (ramcove dohody),
# objem_eur uz nie je len "trocha nizsie cislo" ale systematicky
# podhodnoteny odhad neznamej velkosti — priznak nespolahlivy, rovnaky
# vzor ako `spolahlivy` pri cenovom medianе.
MAX_PODIEL_BEZ_CENY = 0.5

# Kolko najlepsich dodavatelov na sektor ukazujeme. Viac by uz vyzeralo ako
# uplny zoznam trhu, co nie je — je to len TOP.
TOP_DODAVATELOV_SEKTOR = 5


def tamSektora(df: pd.DataFrame, dnes) -> pd.DataFrame:
    """Odhad velkosti trhu (TAM) za sektor, za poslednych DNI_TAM dni.

    `df` je rovnaky vstup ako pre dodavatelia()/medianySektora() — uz bez
    dotacnych zmluv (tie maju v poli dodavatela prijimatela, nie firmu).
    """
    stlpce = ["sector", "objem_eur", "pocet_s_cenou", "pocet_bez_ceny",
              "podiel_bez_ceny_pct", "spolahlivy"]
    if df.empty or "signed_on" not in df.columns:
        return pd.DataFrame(columns=stlpce)

    d = df.copy()
    d["signed_on"] = pd.to_datetime(d["signed_on"], errors="coerce")
    hranica = pd.Timestamp(dnes) - pd.Timedelta(days=DNI_TAM)
    d = d[d["signed_on"].notna() & (d["signed_on"] >= hranica)]
    if d.empty:
        return pd.DataFrame(columns=stlpce)

    d["cena"] = pd.to_numeric(d.get("price_total"), errors="coerce")
    ma_cenu = d["cena"].notna() & (d["cena"] > 0)

    riadky = []
    for sektor, skupina in d.groupby("sector"):
        s_cenou = skupina[ma_cenu.loc[skupina.index]]
        if len(s_cenou) < MIN_VZORIEK_TAM:
            continue
        pocet_spolu = len(skupina)
        podiel_bez_ceny = 1 - (len(s_cenou) / pocet_spolu)
        riadky.append({
            "sector": sektor,
            "objem_eur": round(float(s_cenou["cena"].sum()), 2),
            "pocet_s_cenou": int(len(s_cenou)),
            "pocet_bez_ceny": int(pocet_spolu - len(s_cenou)),
            "podiel_bez_ceny_pct": round(podiel_bez_ceny * 100, 1),
            "spolahlivy": bool(podiel_bez_ceny <= MAX_PODIEL_BEZ_CENY),
        })
    return pd.DataFrame(riadky, columns=stlpce)


def trhovyPodiel(df: pd.DataFrame, dnes) -> pd.DataFrame:
    """TOP dodavatelov v kazdom sektore za poslednych DNI_TAM dni, s
    podielom na objeme sektora (pocitanom len zo zmluv so znamou cenou).

    GDPR filter je rovnaky ako v dodavatelia() — fyzicke osoby (zivnostnici)
    sem nesmu, aj keby v sektore vyhrali najviac zmluv.
    """
    stlpce = ["sector", "supplier_cin", "dodavatel", "zmluv", "objem_eur",
              "podiel_sektora_pct", "poradie"]
    if (df.empty or "supplier_cin" not in df.columns
            or "signed_on" not in df.columns):
        return pd.DataFrame(columns=stlpce)

    d = df.copy()
    d["signed_on"] = pd.to_datetime(d["signed_on"], errors="coerce")
    hranica = pd.Timestamp(dnes) - pd.Timedelta(days=DNI_TAM)
    d = d[d["signed_on"].notna() & (d["signed_on"] >= hranica)]
    d = d[d["supplier_cin"].notna() & (d["supplier_cin"].astype(str) != "")]
    d["cena"] = pd.to_numeric(d.get("price_total"), errors="coerce")
    d = d[d["cena"].notna() & (d["cena"] > 0)]
    if d.empty:
        return pd.DataFrame(columns=stlpce)

    d = d[d["supplier_name"].apply(je_pravnicka_osoba)].copy()
    if d.empty:
        return pd.DataFrame(columns=stlpce)

    vysledky = []
    for sektor, skupina in d.groupby("sector"):
        if len(skupina) < MIN_VZORIEK_TAM:
            continue
        objem_sektora = float(skupina["cena"].sum())
        if objem_sektora <= 0:
            continue
        g = (skupina.groupby("supplier_cin")
                    .agg(dodavatel=("supplier_name", "first"),
                         zmluv=("cena", "count"),
                         objem_eur=("cena", "sum"))
                    .reset_index()
                    .sort_values("objem_eur", ascending=False)
                    .head(TOP_DODAVATELOV_SEKTOR))
        g["sector"] = sektor
        g["objem_eur"] = g["objem_eur"].round(2)
        g["podiel_sektora_pct"] = (g["objem_eur"] / objem_sektora * 100).round(1)
        g["poradie"] = range(1, len(g) + 1)
        vysledky.append(g)

    if not vysledky:
        return pd.DataFrame(columns=stlpce)
    out = pd.concat(vysledky, ignore_index=True)
    out["zmluv"] = out["zmluv"].astype(int)
    out["poradie"] = out["poradie"].astype(int)
    return out[stlpce]
