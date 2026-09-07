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
    """0-100. Hodnota ide logaritmicky — linearna skala by zotrela rozdiel
    medzi 20 a 100 tisic, co je presne pasmo nasho zakaznika."""
    hodnota = float(r.get("price_total") or 0)
    s = min(40.0, 12 * math.log10(hodnota / 1000 + 1)) if hodnota > 0 else 0.0
    s += min(25, (r.get("historicky_pocet") or 0) * 5)
    s += min(20, (r.get("pocet_dodavatelov") or 0) * 5)
    s += min(15, r.get("class_score") or 0)

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

    okno = df[
        df["effective_to"].notna()
        & (df["effective_to"] >= od)
        & (df["effective_to"] <= do)
        & (df["status_id"].isin([2, 3]))
        & (df["price_total"].fillna(0) >= MIN_HODNOTA_EUR)
    ].copy()

    if okno.empty:
        return pd.DataFrame()

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
    # Region z adresy, mesacna cena proti medianu sektora, navysenie
    # dodatkami a typicka dlzka zmluvy u toho isteho uradu.
    okno = regiony.doplnit(okno)
    okno = analytics.mesacna_cena(okno)
    okno = analytics.navysenie(okno)

    vsetky_s_cenou = analytics.mesacna_cena(df)
    medianyDf = analytics.medianyMesacnej(vsetky_s_cenou)
    okno = analytics.porovnaj_so_sektorom(okno, medianyDf)

    cykly = analytics.cykly(vsetky_s_cenou)
    if not cykly.empty:
        okno = okno.merge(cykly[["authority_cin", "sector", "typicka_dlzka_dni"]],
                          on=["authority_cin", "sector"], how="left")
    else:
        okno["typicka_dlzka_dni"] = None

    stlpce = [
        "contract_id", "sector", "cpv", "authority_name", "authority_cin",
        "department", "subject", "subject_description", "effective_to",
        "dni_do_konca", "odhad_vyhlasenia", "price_total", "supplier_name",
        "top_dodavatel", "podiel_top_dodavatela", "historicky_pocet",
        "pocet_dodavatelov", "riziko", "skore", "okres_kod",
        "mesto", "kraj", "mesacna_cena", "median_mesacna", "odchylka_pct",
        "vzoriek", "navysenie_pct", "typicka_dlzka_dni",
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
                   "pocet_dodavatelov", "skore", "vzoriek", "typicka_dlzka_dni"):
        vysledok[stlpec] = pd.to_numeric(vysledok[stlpec], errors="coerce").astype("Int64")

    return vysledok
