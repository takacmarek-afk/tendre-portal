"""Klient a dekoder pre Register uctovnych zavierok (registeruz.sk).

API je verejne, bez autentifikacie, licencia CC0 (viz /cruz-public/api-info).
Nema zdokumentovany rate limit, ale slusnost velí neposielat davky sucasne
a posielat vlastne User-Agent s kontaktom - rovnaky vzor ako probe_vykazy.py.

CO TENTO MODUL RIESI A CO NIE
------------------------------
Rieši: pre firmu (podla ICO) najst jej najnovsie podane uctovne zavierky
a z nich vytiahnut dva cisla - "obrat" (proxy za trzby) a "vysledok
hospodarenia po zdaneni" (cisty zisk/strata) - plus NACE kod z karty
firmy. To je cely rozsah funkcie schvalenej Marekom (financny kontext +
NACE), ziadne skore, ziadny "rizikovy" vypocet.

NERIESI: ina templaty nez "Uc MUJ" (mikro uctovna jednotka, sablona 687)
a "Uc POD" (mala/stredna/velka uctovna jednotka, sablona 699). To su dve
najcastejsie sablony pre s.r.o./a.s. v RUZ (overene naživo na LoveHome
s.r.o. a Novogal a.s.). Ine sablony (Uc ROPO pre rozpoctove/prispevkove
organizacie, Uc JU pre jednoduche uctovnictvo, IFRS/konsolidovane
vykazy velkych skupin ako Slovnaft) sa NEPARSUJU - radsej "data
nedostupne" nez hadana hodnota. Nikdy sa nehadaju pozicie v poli podla
cisla, vzdy sa hlada riadok podla PRESNEHO TEXTU z definicie sablony
(ten je preverene stabilny naprieč sablonami - "Vysledok hospodarenia za
uctovne obdobie po zdaneni" je rovnaky text aj v Uc MUJ aj v Uc POD).

OVERENE NAŽIVO (21.9.2026, Browser pane, fetch() priamo na registeruz.sk):
  - LoveHome s.r.o. (ICO 47586362): jednotka 1521664, sablona 687 (Uc MUJ),
    zavierka FY2025, riadok 0 = "Vynosy z hospodarskej cinnosti spolu",
    riadok 37 = "Vysledok hospodarenia za uctovne obdobie po zdaneni".
  - Novogal a.s. (ICO cez jednotku 1806): sablona 699 (Uc POD), 61 riadkov,
    riadok 0 = "Cisty obrat", riadok 60 = "Vysledok hospodarenia za
    uctovne obdobie po zdaneni". Data pole ma presne pocet_riadkov*2
    hodnot (bezne + predchadzajuce obdobie), potvrdene na realnych cislach
    (napr. zisk 4 888 868 / 570 743 sa zhoduje s ocakavanym riadkom).
  - Slovnaft a.s. (ICO 31322832): jedno ICO moze mat VIACERO zaznamov
    "uctovna-jednotka" (dorazeny prazdny duplikat s 0 zavierkami) a jeden
    rok moze mat VIACERO zavierok typu "Riadna" (individualna aj
    konsolidovana, alebo oprava podana v ten isty den) - kod nizsie to
    osetruje vyberom jednotky s najviac zavierkami a zavierky s najvyssim
    id v ramci roka.
  - Novogal a.s., zavierka za 2024: jedna zavierka moze mat VIACERO
    "uctovny-vykaz" id (tu 3) - len prve bolo hlavny financny vykaz
    (sablona 699), druhe "Poznamky" (sablona 700, prazdny obsah), tretie
    len titulna strana (sablona 1171). Kod preto skusa vsetky id v poradi,
    kym nenajde znamu sablonu, nespolieha sa na to, ze prve id je vzdy
    to spravne.
"""
import time
import json
import logging
import os
from pathlib import Path

import requests

log = logging.getLogger("ruz")

BASE = "https://www.registeruz.sk/cruz-public/api"
# Vlastny User-Agent s kontaktom, rovnaky vzor ako probe_vykazy.py (CRZ).
UA = {"User-Agent": "predtendrom.sk research probe (info@predtendrom.sk)"}
TIMEOUT = 30
# Slusnostna pauza medzi volaniami - API nema zdokumentovany limit, ale
# nechceme byt ten klient, kvoli ktoremu niekto rate limit zavedie.
PAUZA_S = float(os.getenv("RUZ_PAUZA_S", "0.15"))

DATA_DIR = Path(__file__).parent / "data"
NACE_SUBOR = DATA_DIR / "sk_nace.json"

# Text riadkov vo "Vykaz ziskov a strat", v poradi priority. Skusa sa prvy,
# ktory sa v danej sablone najde. "Cisty obrat" (Uc POD) je presnejsie
# vyjadrenie trzieb nez "Vynosy z hospodarskej cinnosti spolu" (Uc MUJ,
# zahrna aj ostatne prevadzkove vynosy) - preto je prve.
RIADOK_OBRAT = [
    "Čistý obrat",
    "Výnosy z hospodárskej činnosti spolu",
]
RIADOK_VYSLEDOK = [
    "Výsledok hospodárenia za účtovné obdobie po zdanení",
]
NAZOV_TABULKY_VYKAZ = "Výkaz ziskov a strát"

# Sablony, ktore vieme spolahlivo dekodovat (Uc MUJ, Uc POD). Ina sablona =
# "data nedostupne", nie hadanie.
ZNAME_SABLONY = {687, 699}


class RuzChyba(Exception):
    pass


def _get(cesta, **params):
    url = f"{BASE}/{cesta}"
    r = requests.get(url, params=params, headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    time.sleep(PAUZA_S)
    return r.json()


# ── NACE ─────────────────────────────────────────────────────────────────

_nace_cache = None


def nace_nazov(kod):
    """Nazov NACE kodu zo staticky ulozenej tabulky (pipeline/data/sk_nace.json,
    stiahnute a overene 21.9.2026 z /api/sk-nace, 646 kodov, CC0)."""
    global _nace_cache
    if _nace_cache is None:
        if NACE_SUBOR.exists():
            _nace_cache = json.loads(NACE_SUBOR.read_text(encoding="utf-8"))
        else:
            log.warning("Chyba %s, NACE nazvy nebudu dostupne.", NACE_SUBOR)
            _nace_cache = {}
    return _nace_cache.get(kod)


# ── RUZ API ──────────────────────────────────────────────────────────────

def najdi_jednotky(ico):
    """ID vsetkych 'uctovna-jednotka' zaznamov pre dane ICO.

    `zmenene-od` je POVINNY parameter API (bez neho vracia chybu) - hodnota
    2000-01-01 v praxi znamena "vsetko od zaciatku". Jedno ICO moze mat
    viacero zaznamov (napr. prazdny duplikat) - volajuci si musi vybrat.
    """
    j = _get("uctovne-jednotky", **{"zmenene-od": "2000-01-01", "ico": ico})
    return j.get("id", [])


def nacitaj_jednotku(id_jednotky):
    return _get("uctovna-jednotka", id=id_jednotky)


def najlepsia_jednotka(ico):
    """Z vsetkych zaznamov pre ICO vyberie ten s najviac zavierkami.

    Dovod: Slovnaft (ICO 31322832) ma v RUZ dva zaznamy 'uctovna-jednotka'
    - jeden s 23 zavierkami a jeden prazdny (0 zavierok, zjavne duplikat
    zalozeny omylom alebo pri reorganizacii). Overene naživo 21.9.2026.
    """
    ids = najdi_jednotky(ico)
    if not ids:
        return None
    if len(ids) == 1:
        return nacitaj_jednotku(ids[0])
    kandidati = [nacitaj_jednotku(i) for i in ids]
    return max(kandidati, key=lambda j: len(j.get("idUctovnychZavierok") or []))


def nacitaj_zavierku(id_zavierky):
    return _get("uctovna-zavierka", id=id_zavierky)


def vyber_najnovsie_zavierky_po_rokoch(zavierky):
    """Z pola zavierok (uz nacitanych detailov) vyberie NAJVIAC JEDNU na rok.

    Rok = rok konca obdobia (obdobieDo, format 'YYYY-MM'). Ked ma jeden rok
    viac zavierok (bezne pri velkych firmach - individualna/konsolidovana,
    alebo oprava podana v ten isty den, overene na Slovnafte aj Novogale),
    berie sa ta s NAJVYSSIM id zavierky ako priblizenie "naposledy
    spracovana". Nie je to dokonale (nevieme odlisit konsolidovanu od
    individualnej bez dalsieho volania), ale pre trend obratu/zisku je
    lepsie mat jedno konzistentne cislo na rok nez zdvojene body v grafe.

    Vstup: list dictov {"id": int, "obdobieDo": "YYYY-MM", ...}
    Vystup: dict {rok(int): zavierka}
    """
    podla_roka = {}
    for z in zavierky:
        do = z.get("obdobieDo")
        if not do or len(do) < 4:
            continue
        rok = int(do[:4])
        existujuca = podla_roka.get(rok)
        if existujuca is None or z["id"] > existujuca["id"]:
            podla_roka[rok] = z
    return podla_roka


def nacitaj_vykaz(id_vykazu):
    return _get("uctovny-vykaz", id=id_vykazu)


def _najdi_riadok(sablona_tabulka, kandidati_text):
    """Vrati (index, pocet_stlpcov) prveho riadku, ktoreho text obsahuje
    niektory z kandidatov (v poradi priority), alebo None."""
    riadky = sablona_tabulka["riadky"]
    for potreba in kandidati_text:
        for idx, r in enumerate(riadky):
            if potreba in r["text"]["sk"]:
                return idx
    return None


def _pocet_datovych_stlpcov(sablona_tabulka):
    """Kolko hodnotovych stlpcov ma tabulka (zvycajne 2: bezne + predch.
    obdobie). Pocita z najvyssieho 'stlpec' v hlavicke, minus 3 popisne
    stlpce (Oznacenie/Text/Cislo riadku)."""
    max_stlpec = max(h["stlpec"] for h in sablona_tabulka["hlavicka"])
    return max(max_stlpec - 3, 1)


def dekoduj_vykaz(vykaz, sablona):
    """Z vykazu (uz nacitaneho cez nacitaj_vykaz) a jeho sablony (cez
    nacitaj_sablonu) vytiahne obrat a vysledok hospodarenia za bezne
    obdobie (prvy datovy stlpec).

    Vracia dict {"obrat": float|None, "vysledok_hospodarenia": float|None}
    alebo None, ak sablona/tabulka nie je znama.
    """
    tab_sablona = next(
        (t for t in sablona.get("tabulky", []) if t["nazov"]["sk"] == NAZOV_TABULKY_VYKAZ),
        None,
    )
    # .get(...) na oboch urovniach, nie ["obsah"]["tabulky"] natvrdo: 22.9.2026
    # sa objavilo aspon 5 ICO, kde "obsah" existoval, ale bez kluca "tabulky"
    # (zjavne dalsi tvar odpovede RUZ API, mimo pôvodne overenych LoveHome/
    # Novogal/Slovnaft). Predtym to spadlo na KeyError('tabulky'), co vyhodilo
    # CELE ICO (aj ostatne roky/vykazy) cez vynimku, ktora unikala z cyklu v
    # financie_pre_ico - firma tak nikdy nedostala zaznam v ruz_zaklad a bola
    # dokola prioritne skusana (a padala) v kazdom dalsom behu. Spravne
    # spravanie: tento jeden vykaz je "data nedostupne", skusa sa dalsi
    # idUctovnychVykazov v poradi (viz volajuci cyklus).
    obsah = vykaz.get("obsah") or {}
    tab_data = next(
        (t for t in obsah.get("tabulky", []) if t["nazov"]["sk"] == NAZOV_TABULKY_VYKAZ),
        None,
    )
    if tab_sablona is None or tab_data is None:
        return None

    stlpcov = _pocet_datovych_stlpcov(tab_sablona)
    data = tab_data["data"]
    if len(data) != len(tab_sablona["riadky"]) * stlpcov:
        # Sablona a data sa nezhoduju - nehadaj, radsej nic.
        log.warning("Vykaz %s: dlzka dat (%s) nesedi s poctom riadkov*stlpcov (%s)",
                    vykaz.get("id"), len(data), len(tab_sablona["riadky"]) * stlpcov)
        return None

    idx_obrat = _najdi_riadok(tab_sablona, RIADOK_OBRAT)
    idx_vysledok = _najdi_riadok(tab_sablona, RIADOK_VYSLEDOK)

    def hodnota(idx):
        if idx is None:
            return None
        surova = data[idx * stlpcov]  # prvy datovy stlpec = bezne obdobie
        if surova in (None, ""):
            return None
        try:
            return float(surova.replace(" ", ""))
        except (ValueError, AttributeError):
            return None

    return {
        "obrat": hodnota(idx_obrat),
        "vysledok_hospodarenia": hodnota(idx_vysledok),
    }


_sablona_cache = {}


def nacitaj_sablonu(id_sablony):
    if id_sablony not in _sablona_cache:
        _sablona_cache[id_sablony] = _get("sablona", id=id_sablony)
    return _sablona_cache[id_sablony]


def financie_pre_ico(ico, max_rokov=8):
    """Hlavny vstupny bod modulu. Pre dane ICO vrati:

        {
            "ma_zaznam": bool,       # ma RUZ vobec zaznam o tejto firme
            "nace_kod": str|None,
            "nace_nazov": str|None,
            "pravna_forma": str|None,
            "velkost_organizacie": str|None,
            "roky": [                # zoradene od najnovsieho, max `max_rokov`
                {"rok": int, "obdobie_od": str, "obdobie_do": str,
                 "datum_podania": str|None, "obrat": float|None,
                 "vysledok_hospodarenia": float|None},
                ...
            ],
        }

    Nikdy nevyhadzuje kvoli chybajucim udajom - vsade, kde RUZ nic nema
    alebo sablona nie je znama, necha None/prazdny zoznam. Sietove/HTTP
    chyby (RuzChyba) su na zvazenie volajuceho (pipeline pokracuje dalsim
    ICO, nepada cely beh kvoli jednej firme).
    """
    try:
        jednotka = najlepsia_jednotka(ico)
    except requests.RequestException as e:
        raise RuzChyba(f"ICO {ico}: {e}") from e

    if jednotka is None:
        return {"ma_zaznam": False, "nace_kod": None, "nace_nazov": None,
                "pravna_forma": None, "velkost_organizacie": None, "roky": []}

    nace_kod = jednotka.get("skNace")
    zakladne = {
        "ma_zaznam": True,
        "nace_kod": nace_kod,
        "nace_nazov": nace_nazov(nace_kod) if nace_kod else None,
        "pravna_forma": jednotka.get("pravnaForma"),
        "velkost_organizacie": jednotka.get("velkostOrganizacie"),
        "roky": [],
    }

    ids_zavierok = jednotka.get("idUctovnychZavierok") or []
    if not ids_zavierok:
        return zakladne

    try:
        zavierky = [nacitaj_zavierku(i) for i in ids_zavierok]
    except requests.RequestException as e:
        raise RuzChyba(f"ICO {ico}: {e}") from e

    # len riadne zavierky (nie napr. zrusene) - typ "Riadna" je bezny
    # pripad, ostatne typy zamerne preskakujeme (nechceme hadat, co
    # "Mimoriadna"/"Opravna" znamena pre trend bez dalsieho overenia).
    riadne = [z for z in zavierky if z.get("typ") == "Riadna"]
    podla_roka = vyber_najnovsie_zavierky_po_rokoch(riadne)
    najnovsie_roky = sorted(podla_roka.keys(), reverse=True)[:max_rokov]

    for rok in najnovsie_roky:
        z = podla_roka[rok]
        riadok = {
            "rok": rok,
            "obdobie_od": z.get("obdobieOd"),
            "obdobie_do": z.get("obdobieDo"),
            "datum_podania": z.get("datumPodania"),
            "obrat": None,
            "vysledok_hospodarenia": None,
        }
        # Jedna zavierka moze mat VIAC "uctovny-vykaz" id - overene naživo
        # na Novogal a.s. 2024 (3 id): prve bolo hlavny vykaz (sablona 699,
        # Strana aktiv/pasiv/Vykaz ziskov a strat), druhe "Poznamky"
        # (sablona 700, prazdny obsah), tretie len titulna strana (sablona
        # 1171). Poradie prveho miesta NIE JE zdokumentovane ako zarucene,
        # preto sa skusaju postupne vsetky, kym sa nenajde znama sablona -
        # nie hadanie hodnot, len hladanie SPRAVNEHO vykazu medzi viacerymi.
        for vykaz_id in (z.get("idUctovnychVykazov") or []):
            try:
                vykaz = nacitaj_vykaz(vykaz_id)
            except requests.RequestException as e:
                log.warning("ICO %s rok %s: vykaz %s sa nepodarilo nacitat (%s)",
                            ico, rok, vykaz_id, e)
                continue
            id_sablony = vykaz.get("idSablony")
            if id_sablony not in ZNAME_SABLONY:
                continue
            sablona = nacitaj_sablonu(id_sablony)
            dekod = dekoduj_vykaz(vykaz, sablona)
            if dekod:
                riadok["obrat"] = dekod["obrat"]
                riadok["vysledok_hospodarenia"] = dekod["vysledok_hospodarenia"]
                break
        zakladne["roky"].append(riadok)

    return zakladne
