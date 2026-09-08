"""Predikcna vrstva: konciace zmluvy, koncentracia dodavatela, skore.

Oproti povodnej verzii pracuje s DataFrame namiesto SQLite, inak je logika
aj kalibracia prahov rovnaka.
"""
import math
import re
import logging
from datetime import date, timedelta

import pandas as pd

import analytics
import regiony
from classify import SEKTOR_DOTACIE, bez_diakritiky
from config import DNI_MIN, DNI_MAX, MIN_HODNOTA_EUR, SEKTORY


def _historia(df: pd.DataFrame) -> pd.DataFrame:
    """Pre kazdu dvojicu (obstaravatel, sektor) spocita historiu nakupov."""
    zdroj = df[df["authority_cin"].notna()]
    if zdroj.empty:
        return pd.DataFrame(columns=[
            "authority_cin", "sector", "historicky_pocet", "pocet_dodavatelov",
            "priemerna_hodnota", "top_dodavatel", "podiel_top_dodavatela",
        ])

    out = []
    for (cin, sector), g in zdroj.groupby(["authority_cin", "sector"]):
        dodavatelia = g["supplier_name"].dropna()
        if len(dodavatelia):
            pocty = dodavatelia.value_counts()
            top, podiel = pocty.index[0], round(float(pocty.iloc[0]) / pocty.sum(), 2)
        else:
            top, podiel = None, None
        priemer = g["price_total"].dropna().mean()
        out.append({
            "authority_cin": cin,
            "sector": sector,
            "historicky_pocet": int(len(g)),
            "pocet_dodavatelov": int(dodavatelia.nunique()),
            "priemerna_hodnota": round(float(priemer), 2) if pd.notna(priemer) else None,
            "top_dodavatel": top,
            "podiel_top_dodavatela": podiel,
        })
    return pd.DataFrame(out)


def _riziko(r):
    """Koncentracia dodavatela. Pozor na velkost vzorky: dve zmluvy s tym istym
    dodavatelom daju 100 %, a pritom to nic neznamena — moze ist o jednu ramcovu
    zmluvu predlzenu raz. Preto tvrde prahy na pocet zaznamov."""
    podiel = r.get("podiel_top_dodavatela")
    pocet = r.get("historicky_pocet") or 0
    dodavatelov = r.get("pocet_dodavatelov") or 0

    if podiel is None or pd.isna(podiel) or pocet < 3:
        return "NEZNAME"
    if pocet >= 5 and podiel >= 0.8 and dodavatelov <= 2:
        return "VYSOKE"
    if podiel >= 0.7:
        return "STREDNE"
    if podiel <= 0.5 or dodavatelov >= 3:
        return "NIZKE"
    return "STREDNE"


def _skore(r):
    """0-100 SILA SIGNALU. Nie je to pravdepodobnost, ze zakaznik zakazku
    vyhra — je to sila predtendrovej stopy, ktoru v datach vidime.

    DVE OPRAVY OPROTI PRVEJ VERZII, obe najdene az na skutocnych datach:

    1. CENA 0 NEZNAMENA MALU ZAKAZKU. 47 % zmluv (21 138 zo 44 566) ma
       `price` nula — su to ramcove zmluvy a zmluvy s jednotkovymi cenami.
       Povodny vzorec im dal 0 bodov zo 40, cim systematicky poslal na dno
       rankingu prave ten najhodnotnejsi opakovany biznis. Teraz dostavaju
       strednu hodnotu a v UI su oznacene ako "cena neuvedena".

    2. HODNOTA NESMIE DOMINOVAT. Povodne mala 40 zo 100 bodov, takze
       ranking v praxi zoradoval "velke zmluvy". Velka zmluva je pritom
       presne ta, kde mala firma nevyhra — skore mohlo byt antikorelovane
       so sancou nasho zakaznika. Teraz ma hodnota 25 bodov a vahu prebrala
       opakovanost a sutazivost, teda to, ci sa zakazka bude naozaj
       obstaravat znova a ci ma zmysel sa o nu uchadzat.
    """
    hodnota = float(r.get("price_total") or 0)
    if hodnota > 0:
        s = min(25.0, 8 * math.log10(hodnota / 1000 + 1))
    else:
        s = 12.0   # cena neuvedena: stred pasma, nie dno

    s += min(30, (r.get("historicky_pocet") or 0) * 6)
    s += min(25, (r.get("pocet_dodavatelov") or 0) * 6)
    s += min(20, (r.get("class_score") or 0) * 1.5)

    riziko = r.get("riziko")
    if riziko == "VYSOKE":
        s -= 25
    elif riziko == "STREDNE":
        s -= 10
    return max(0, min(100, round(s)))


# CRZ zverejnuje jednu zmluvu aj po castiach — kazda cast je samostatny
# zaznam s vlastnym ID a v predmete ma prilepene "Zverejnene strany zmluvy
# 1-7", "8-13" a tak dalej. Bez odstranenia by klient videl tu istu zakazku
# pat krat a portal by posobil rozbito.
_STRANY = re.compile(
    r"\s*zverejnen[éeá]\s+stran[ayái]\s+zmluvy.*$", re.I | re.S)
_BOILERPLATE = re.compile(
    r"^\s*zmluva o dielo\s*:\s*predmetom\s+zmluvy\s+(?:s[úu]|je)\s*", re.I)


def vycisti_predmet(text) -> str:
    """Odstrani z predmetu pravnu vatu a oznacenie zverejnenych stran."""
    if not text:
        return ""
    t = _STRANY.sub("", str(text))
    t = _BOILERPLATE.sub("", t)
    return re.sub(r"\s+", " ", t).strip(" .:;-")


# Dodatok nie je prilezitost. Nikto ho nevyhlasuje — je to zmena uz podpisanej
# zmluvy, casto navysenie ceny. V tabulke contracts ho ponechavame (je to cenny
# signal o tom, ktory dodavatel si systematicky priplacuje), ale medzi zakazky,
# na ktore sa da sutazit, nepatri.
#
# Stlpec kind_id v CRZ na toto pouzit nemozno — dokumentacia sama uvadza, ze
# dodatky su v zdroji oznacovane nespravne. Ide sa preto podla textu.
_DODATOK = re.compile(
    r"(^|\W)(dodat(?:ok|ku|kom|ky|kov)|zmena\s+zmluvy|zmene\s+zmluvy|"
    r"uprava\s+rozpoctu|upravu\s+rozpoctu|upravy\s+rozpoctu)(\W|$)")


def je_dodatok(subject, popis) -> bool:
    """Pozor na diakritiku: "Úprava rozpočtu" nesedi na vzor "uprava rozpoctu",
    kym text neznormalizujeme. Rovnaka chyba nas uz raz stala tri stvrtiny
    zhod v klasifikatore, preto sa tu pouziva ta ista normalizacia."""
    return bool(_DODATOK.search(bez_diakritiky(f"{subject or ''} {popis or ''}")))


def prilezitosti(df: pd.DataFrame, dnes: date = None) -> pd.DataFrame:
    """Vstup: vsetky ulozene zmluvy. Vystup: riadky pre tabulku opportunities."""
    dnes = dnes or date.today()
    if df.empty:
        return pd.DataFrame()

    # Dotacie sem nepatria. Nie je to zakazka, na ktoru sa da sutazit, ale
    # signal, ze tender pride. Maju vlastnu tabulku a vlastnu logiku.
    df = df[df["sector"] != SEKTOR_DOTACIE].copy()
    if df.empty:
        return pd.DataFrame()

    df["effective_to"] = pd.to_datetime(df["effective_to"], errors="coerce")
    df["price_total"] = pd.to_numeric(df["price_total"], errors="coerce")

    od = pd.Timestamp(dnes + timedelta(days=DNI_MIN))
    do = pd.Timestamp(dnes + timedelta(days=DNI_MAX))

    # CENA 0 NEZNAMENA MALU ZAKAZKU, ale neuvedenu cenu — ramcova dohoda
    # alebo zmluva s jednotkovymi cenami. Tyka sa to 47 % zmluv (21 138
    # zo 44 566). Povodna podmienka `price_total >= MIN_HODNOTA_EUR` ich
    # vyhadzovala uz tu, teda skor, nez sa vobec dostali ku skore — a boli
    # medzi nimi prave tie najhodnotnejsie opakovane nakupy.
    #
    # Neznamu cenu preto prepustame a v UI ju oznacujeme, namiesto toho aby
    # sme neznamu hodnotu tichu stotoznili s nulovou.
    cena = df["price_total"].fillna(0)
    okno = df[
        df["effective_to"].notna()
        & (df["effective_to"] >= od)
        & (df["effective_to"] <= do)
        & (df["status_id"].isin([2, 3]))
        & ((cena >= MIN_HODNOTA_EUR) | (cena <= 0))
    ].copy()

    if okno.empty:
        return pd.DataFrame()

    bez_ceny = int((okno["price_total"].fillna(0) <= 0).sum())
    if bez_ceny:
        logging.getLogger("score").info(
            "Prilezitosti s neuvedenou cenou (ramcove zmluvy): %s z %s",
            bez_ceny, len(okno))

    # Dodatky von. Robi sa to az tu, nie pri stahovani — v tabulke contracts
    # ich chceme mat, len medzi prilezitostami nie.
    pred_dodatkami = len(okno)
    okno = okno[~okno.apply(
        lambda r: je_dodatok(r["subject"], r["subject_description"]), axis=1)].copy()
    if pred_dodatkami != len(okno):
        logging.getLogger("score").info(
            "Dodatky vylucene z prilezitosti: %s z %s",
            pred_dodatkami - len(okno), pred_dodatkami)
    if okno.empty:
        return pd.DataFrame()

    okno = okno.merge(_historia(df), on=["authority_cin", "sector"], how="left")
    okno["riziko"] = okno.apply(_riziko, axis=1)
    okno["skore"] = okno.apply(_skore, axis=1)

    okno["dni_do_konca"] = (okno["effective_to"] - pd.Timestamp(dnes)).dt.days
    okno["odhad_vyhlasenia"] = (okno["effective_to"] - pd.Timedelta(days=75)).dt.strftime("%Y-%m-%d")
    okno["effective_to"] = okno["effective_to"].dt.strftime("%Y-%m-%d")
    okno["cpv"] = okno["sector"].map({k: v["cpv"] for k, v in SEKTORY.items()})
    okno["contract_id"] = okno["id"]
    okno["okres_kod"] = None

    # ── Analyticka vrstva ────────────────────────────────────────────────
    okno = regiony.doplnit(okno)
    okno = analytics.cenovy_zaklad(okno)

    vsetky_s_cenou = analytics.cenovy_zaklad(df)
    medianyDf = analytics.medianySektora(vsetky_s_cenou)
    okno = analytics.porovnaj_so_sektorom(okno, medianyDf)

    cykly = analytics.cykly(vsetky_s_cenou)
    if not cykly.empty:
        okno = okno.merge(cykly[["authority_cin", "sector", "typicka_dlzka_dni"]],
                          on=["authority_cin", "sector"], how="left")
    else:
        okno["typicka_dlzka_dni"] = None

    # ── Karta "kto to ma teraz" ──────────────────────────────────────────
    # Nahrada za detektor koncentracie, ktory oznacil 8 zaznamov z 864.
    # Toto ma stopercentne pokrytie, nulovu pravnu expoziciu a zakaznik
    # to vie pouzit hned: vie, proti komu ide, ako dlho tam ten dodavatel
    # je a kolko zmluv so statom celkovo ma.
    okno["dodavatel_od"] = pd.to_datetime(
        okno["effective_from"], errors="coerce").dt.strftime("%Y-%m-%d")
    zmluv_dodavatela = (df[df["supplier_cin"].notna()]
                        .groupby("supplier_cin").size()
                        .rename("dodavatel_zmluv_celkom").reset_index())
    okno = okno.merge(zmluv_dodavatela, on="supplier_cin", how="left")

    # Cena 0 nie je mala zakazka, ale ramcova zmluva alebo jednotkove ceny.
    # UI to musi povedat, inak zakaznik vidi "—" a mysli si, ze nam chybaju data.
    okno["cena_neuvedena"] = (okno["price_total"].fillna(0) <= 0)

    stlpce = [
        "contract_id", "sector", "cpv", "authority_name", "authority_cin",
        "department", "subject", "subject_description", "effective_to",
        "dni_do_konca", "odhad_vyhlasenia", "price_total", "cena_neuvedena",
        "supplier_name", "dodavatel_od", "dodavatel_zmluv_celkom",
        "top_dodavatel", "podiel_top_dodavatela", "historicky_pocet",
        "pocet_dodavatelov", "riziko", "skore", "okres_kod",
        "mesto", "kraj", "typicka_dlzka_dni",
        # Nasledujuce su PRO. store.py ich odlomi do vlastnej tabulky,
        # do `opportunities` sa NESMU dostat — RLS je riadkova, nie stlpcova,
        # takze Start by si ich vytiahol cez ?select=*.
        "porovnavacia_cena", "zaklad", "median_cena", "odchylka_pct",
        "vzoriek", "q1", "q3",
    ]
    okno["subject"] = okno["subject"].apply(vycisti_predmet)
    okno["subject_description"] = okno["subject_description"].apply(vycisti_predmet)

    vysledok = okno[stlpce].sort_values("skore", ascending=False).reset_index(drop=True)

    # Odstranenie duplikatov tej istej zakazky. Kluc je obstaravatel + presna
    # suma + datum konca — dve rozne zakazky sa v tychto troch naraz nezhodnu.
    # Sortenie je uz podla skore, takze keep="first" ponecha najlepsi zaznam.
    vysledok["_kluc_uradu"] = (vysledok["authority_cin"]
                               .fillna(vysledok["authority_name"]))
    pred = len(vysledok)
    vysledok = vysledok.drop_duplicates(
        subset=["_kluc_uradu", "price_total", "effective_to"], keep="first")
    vysledok = vysledok.drop(columns=["_kluc_uradu"]).reset_index(drop=True)
    if pred != len(vysledok):
        logging.getLogger("score").info(
            "Duplikaty tej istej zakazky: %s z %s zaznamov odstranenych",
            pred - len(vysledok), pred)

    # Postgres ma tieto stlpce ako celé cisla. Pandas ich po spojeni s historiou
    # drzi ako desatinne (musia uniest prazdne hodnoty), takze by sme poslali
    # "174.0" a databaza to odmietne. Int64 s velkym I je typ, ktory zvlada
    # cele cisla AJ prazdne hodnoty naraz.
    for stlpec in ("contract_id", "dni_do_konca", "historicky_pocet",
                   "pocet_dodavatelov", "skore", "vzoriek", "typicka_dlzka_dni",
                   "dodavatel_zmluv_celkom"):
        vysledok[stlpec] = pd.to_numeric(vysledok[stlpec], errors="coerce").astype("Int64")

    return vysledok


# Stlpce, ktore patria do PRO tabulky `ceny_prilezitosti`. Do `opportunities`
# sa nesmu dostat: RLS v Postgrese je riadkova, nie stlpcova, takze zakaznik
# na plane Start by si ich vytiahol jednoduchym ?select=*.
PRO_STLPCE = ("contract_id", "porovnavacia_cena", "zaklad", "median_cena",
              "odchylka_pct", "vzoriek", "q1", "q3")


def rozdel_na_start_a_pro(df: pd.DataFrame):
    """Rozdeli vysledok na to, co vidi kazdy platic, a na Pro cast."""
    if df is None or df.empty:
        return df, pd.DataFrame()
    pro = df[[c for c in PRO_STLPCE if c in df.columns]].copy()
    # Riadky bez benchmarku nema zmysel ukladat.
    if "median_cena" in pro.columns:
        pro = pro[pro["median_cena"].notna()]
    start = df.drop(columns=[c for c in PRO_STLPCE if c != "contract_id"],
                    errors="ignore")
    return start, pro.reset_index(drop=True)
