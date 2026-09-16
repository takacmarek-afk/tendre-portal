"""NA CO obce dostavaju peniaze. Vyslovene v jazyku starostky.

PRECO TO VZNIKLO: stranka pre obce ukazovala "Ministerstvo dopravy SR
rozdelilo 39,5 M EUR" — a to je z pohladu starostky nepouzitelne. Chybalo
tam to jedine slovo, ktore potrebuje: NA CO. Bez toho nevie, ci sa jej to
vobec tyka.

Povodne som na to chcel pouzit nase sektory (STAVEBNE_PRACE, UPRATOVANIE...).
Dve chyby: `sektor_odhad` na tabulke contracts vobec nie je, takze stlpec
`hlavny_ucel` bol vzdy NULL — a aj keby bol, "stavebné práce" starostke
nepovie nic. Tie sektory su navrhnute na parovanie DODAVATELOV, nie na
popis ucelu dotacie.

Tu je teda vlastna taxonomia, postavena na tom, co obce realne riesia
a ako o tom hovoria: cesta, vodovod, skolka, zateplenie, cintorin,
hasicska zbrojnica. Kazdy ucel je jeden riadok s poctom obci, typickou
sumou a tym, kto to dava.

ZAMERNE SU TO AGREGATY, NIE ZOZNAM ZAKAZIEK. Riadkove dotacie s otvorenym
oknom su obsah dodavatelskej casti portalu a tu ich verejne nedavame —
inak by sme si vlastny produkt rozdali zadarmo. Starostke staci vediet,
ze na cesty dotacie existuju, kolko byva a kto ich dava.
"""
import logging
import re
import unicodedata

import pandas as pd

log = logging.getLogger("ucely")

MIN_SUMA = 20000        # rovnaky prah ako vsade v dotacnej vrstve
MIN_ZMLUV_UCEL = 3      # pod tolko to nie je ucel, je to nahoda

_JE_OBEC = re.compile(r"^\s*(obec|mesto|mestsk[aá]\s*[cč]as[tť])\s+", re.I)


def _norm(t) -> str:
    """Bez diakritiky a malymi. Vzory potom nemusia riesit mackovane znaky."""
    nfkd = unicodedata.normalize("NFKD", str(t or ""))
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


# ── TAXONOMIA ──────────────────────────────────────────────────────────────
# (kluc, co sa zobrazi starostke, vzor nad textom BEZ diakritiky)
#
# Poradie ROZHODUJE: zmluva sa priradi k PRVEMU ucelu, ktory sadne, aby sa
# jedna dotacia nepocitala pod piatimi ucelmi naraz a sucet nedaval viac
# nez je zmluv. Specifickejsie ucely su preto vyssie nez vseobecne.
UCELY = [
    ("skola", "Škola a školská jedáleň",
     r"\b(zakladn\w*\s+skol|zs\b|skolsk\w*\s+jedalen|telocvicn|skolsk\w*\s+klub"
     r"|ucebn|skolsk\w*\s+areal)"),
    ("skolka", "Materská škola a jasle",
     r"\b(matersk\w*\s+skol|ms\b|jasl|detsk\w*\s+jasl|predskol)"),
    ("voda", "Vodovod, kanalizácia, čistička",
     r"\b(vodovod|kanaliz|stokov\w*\s+siet|cistiar\w*\s+odpadov|cov\b"
     r"|pitn\w*\s+vod|odpadov\w*\s+vod|vodohospodar)"),
    ("cesty", "Cesty, chodníky, most",
     r"\b(miestn\w*\s+komunikac|cest\w*|chodnik|most\b|mostn|parkovis"
     r"|spevnen\w*\s+ploch|autobusov\w*\s+zastav)"),
    ("energie", "Zateplenie a úspora energie",
     r"\b(zateplen|energetick\w*\s+naroc|tepeln\w*\s+izolac|fotovolt"
     r"|tepeln\w*\s+pump|kotoln|rekuperac|vykurovan|obnov\w*\s+budov)"),
    ("odpady", "Odpady, zberný dvor, kompostovanie",
     r"\b(zbern\w*\s+dvor|kompost|trieden\w*\s+zber|odpadov\w*\s+hospodar"
     r"|skladk|zhodnocovan\w*\s+odpad)"),
    ("hasici", "Hasičská zbrojnica a technika",
     r"\b(hasicsk|zbrojnic|dobrovoln\w*\s+hasic|protipozia)"),
    # "domov\s+socialn" by nesadlo na "domova socialnych sluzieb" (genitiv),
    # preto aj tu \w*. Vo "zariaden\w*\s+pre\s+senior" je "pre" predlozka,
    # ktora sa nesklonuje, takze tam \w* netreba.
    ("socialne", "Sociálne služby a denný stacionár",
     r"\b(socialn\w*\s+sluz|denn\w*\s+stacionar|zariaden\w*\s+pre\s+senior"
     r"|domov\w*\s+socialn|opatrovat|komunitn\w*\s+centr|terenn\w*\s+socialn)"),
    # Cintorin MUSI byt nad kulturou. "rozsirenie cintorina a dom smutku"
    # sadalo na kulturu, pretoze "dom smutku" je vo vzore oboch — a dotacia
    # na cintorin sa tak zobrazila ako dotacia na kulturny dom.
    ("cintorin", "Cintorín a dom smútku",
     r"\b(cintorin|pohrebis|urnov|dom\w*\s+smutku)"),
    ("kultura", "Kultúrny dom, obecný úrad, knižnica",
     r"\b(kulturn\w*\s+dom|obecn\w*\s+urad|mestsk\w*\s+urad"
     r"|kniznic|muze|pamiatk|kostol|amfiteatr)"),
    ("sport", "Šport a detské ihrisko",
     r"\b(detsk\w*\s+ihrisk|sportov\w*\s+areal|multifunkcn\w*\s+ihrisk"
     r"|futbalov|sportov\w*\s+hal|workout|skatepark|telovychov)"),
    ("zelen", "Zeleň, park, revitalizácia",
     r"\b(revitalizac|verejn\w*\s+zelen|park\b|parkov\w*\s+uprav|vysadb"
     r"|zelen\w*\s+infrastrukt|modr\w*\s+infrastrukt)"),
    ("osvetlenie", "Verejné osvetlenie",
     r"\b(verejn\w*\s+osvetlen|osvetlen|sveteln\w*\s+bod)"),
    ("bezpecnost", "Kamery a bezpečnosť",
     r"\b(kamerov\w*\s+system|kamer|bezpecnostn\w*\s+system|prevenci\w*\s+krimin)"),
    ("byty", "Nájomné byty",
     r"\b(najomn\w*\s+byt|obstaran\w*\s+najomn|bytov\w*\s+dom|bytov\w*\s+vystavb)"),
    ("technika", "Technika a vybavenie",
     r"\b(traktor|nakladac|malotraktor|komunaln\w*\s+technik|kosack"
     r"|technick\w*\s+vybaven|nakup\w*\s+vozidl)"),
    ("digital", "Digitalizácia a IT",
     r"\b(digitaliz|informacn\w*\s+system|elektronick\w*\s+sluz|wifi"
     r"|pocitac|kybernetick)"),
    ("povodne", "Protipovodňová ochrana",
     r"\b(protipovodn|povodn|zadrzan\w*\s+vod|vodn\w*\s+tok|brehov"
     r"|preventivn\w*\s+opatren)"),
    ("cyklo", "Cyklotrasy a cyklodoprava",
     r"\b(cyklotras|cyklodoprav|cyklisti|cyklochodnik)"),
]

_ZOSTAVENE = [(k, p, re.compile(v)) for k, p, v in UCELY]


def priradit(text: str):
    """Vrati (kluc, popis) prveho ucelu, ktory sadne, inak (None, None)."""
    n = _norm(text)
    for kluc, popis, vzor in _ZOSTAVENE:
        if vzor.search(n):
            return kluc, popis
    return None, None


def z_contracts(df: pd.DataFrame) -> pd.DataFrame:
    """Prehlad ucelov: na co obce dostavaju peniaze, kolko a od koho."""
    if df is None or df.empty:
        return pd.DataFrame()

    chyba = [c for c in ("sector", "authority_name", "supplier_name",
                         "subject", "subject_description", "price_total",
                         "signed_on") if c not in df.columns]
    if chyba:
        raise KeyError(f"Ucely: v datach chybaju stlpce {chyba}.")

    d = df[df["sector"] == "DOTACIE_NFP"].copy()
    d["suma"] = pd.to_numeric(d["price_total"], errors="coerce")
    d["podpisane"] = pd.to_datetime(d["signed_on"], errors="coerce")
    d = d[d["suma"] >= MIN_SUMA]
    d = d[d["supplier_name"].fillna("").apply(lambda s: bool(_JE_OBEC.match(s)))]

    # Poskytovatel musi byt verejna institucia. Inak by sa v stlpci
    # "Kto to dáva" objavilo "Neuvedené · Mgr. Gabriela Skotáková" —
    # co bol skutocny vystup prvej verzie. Vysvetlenie je v obce.py.
    import obce
    pred = len(d)
    d = d[d["authority_name"].apply(obce.je_verejny_poskytovatel)].copy()
    if pred:
        log.info("Ucely: %s z %s dotacii ma verejneho poskytovatela (%.0f %%). "
                 "Zvysok su zvycajne granty, ktore obec sama rozdava, "
                 "a role v CRZ tam byvaju naopak.",
                 len(d), pred, 100.0 * len(d) / pred)

    if d.empty:
        log.warning("Ucely: po filtroch nezostala ziadna dotacia obci.")
        return pd.DataFrame()

    # `subject_description` je v CRZ VZDY prazdny — odmerane na celej
    # databaze aj priamo na API, podrobnosti v crz.py. Zretazenie tu teda
    # nic nepridava a nechavam ho len preto, aby sa kod nerozbil, keby
    # zdroj to pole niekedy zacal plnit. Nehladaj tu zisk.
    text = (d["subject"].fillna("") + " " + d["subject_description"].fillna(""))
    priradene = text.apply(priradit)
    d["ucel"] = [p[0] for p in priradene]
    d["ucel_popis"] = [p[1] for p in priradene]

    nezaradene = int(d["ucel"].isna().sum())
    log.info("Ucely: zaradenych %s z %s dotacii (%.0f %%), nezaradenych %s",
             len(d) - nezaradene, len(d),
             100.0 * (len(d) - nezaradene) / len(d), nezaradene)
    if nezaradene / max(len(d), 1) > 0.5:
        log.warning("UCELY: viac nez polovica dotacii sa nezaradila. "
                    "Pozri ukazky nizsie a doplnte vzory do ucely.UCELY.")
        for s in d.loc[d["ucel"].isna(), "subject"].head(5):
            log.warning("   nezaradene: %s", str(s)[:110])

    d = d[d["ucel"].notna()].copy()
    if d.empty:
        return pd.DataFrame()

    g = d.groupby(["ucel", "ucel_popis"])
    out = pd.DataFrame({
        "ucel": [k[0] for k in g.groups.keys()],
        "popis": [k[1] for k in g.groups.keys()],
        "obci": g["supplier_name"].nunique().values,
        "dotacii": g.size().values,
        "median_suma": g["suma"].median().round(0).values,
        "najmensia": g["suma"].min().round(0).values,
        "najvacsia": g["suma"].max().round(0).values,
        "objem_eur": g["suma"].sum().round(0).values,
        "posledna": g["podpisane"].max().dt.strftime("%Y-%m-%d").values,
    })

    # Kto to dava. Tri najcastejsi poskytovatelia na ucel — to je pre
    # starostku ta najpraktickejsia informacia: komu napisat.
    def top_poskytovatelia(skupina):
        p = (skupina["authority_name"].value_counts().head(3).index.tolist())
        return " · ".join(str(x)[:60] for x in p) or None

    # include_groups=False: bez toho pandas varuje, ze buduce verzie
    # stlpce skupiny do funkcie posielat prestanu.
    try:
        kto = g.apply(top_poskytovatelia, include_groups=False)
    except TypeError:
        kto = g.apply(top_poskytovatelia)       # starsie pandas
    out["poskytovatelia"] = [kto.get(k) for k in
                             zip(out["ucel"], out["popis"])]

    out = out[out["dotacii"] >= MIN_ZMLUV_UCEL].copy()
    out = out.sort_values("dotacii", ascending=False).reset_index(drop=True)
    for c in ("obci", "dotacii"):
        out[c] = out[c].astype("Int64")

    log.info("Ucelov s aspon %s dotaciami: %s", MIN_ZMLUV_UCEL, len(out))
    return out
