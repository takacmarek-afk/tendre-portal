"""Vestník ÚVO: výsledky súťaží a vyhlásené súťaže.

Spustenie:
    python uvo.py --nasucho            # nič nezapíše, vypíše štatistiku
    python uvo.py                      # spracuje ďalšie nespracované čísla
    python uvo.py --od-rok 2025 --limit 40
    python uvo.py --vestnik 193/2026 --nasucho   # len jedno číslo

Potrebné premenné: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY (viz store.py).

ZDROJ
  ÚVO zverejňuje každé číslo Vestníka ako samostatný dataset v Národnom
  katalógu otvorených dát (data.slovensko.sk). Zoznam čísel dáva to isté
  API, ktoré používa frontend katalógu (POST /datasets/search, filter na
  vydavateľa ÚVO). Súbor čísla je JSON:

      {bulletinPublishDate, year, number,
       bulletinItemList: [{itemData: "<JSON reťazec eForms formulára>", ...}]}

  Formulár je strom `components` [{key, value, components}], kľúče sú
  eForms business terms (BT-xxx). Asi 5 % položiek je XML namiesto JSON —
  tie zatiaľ preskakujeme (počítajú sa do `preskocenych`).

  ID organizácií, strán, ponúk a zmlúv (ORG-0001, TPA-0001, TEN-0001,
  CON-0001) sú v dátach ÚVO väčšinou IMPLICITNÉ — dané poradím panelu.
  Odmerané na čísle 193/2026: DL-Context-Org mali len prvé dve
  organizácie, víťazi už nie. Preto: explicitné ID, ak je, inak poradie.

  Prieskum a odmerané pokrytie: Projects doc
  predtendrom-uvo-vestnik-prieskum-2026-09-25.md.
"""
import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import requests

from classify import klasifikuj, SEKTOR_DOTACIE
from config import USER_AGENT

log = logging.getLogger("uvo")

KATALOG = "https://data.slovensko.sk"
UVO_VYDAVATEL = "https://data.gov.sk/id/legal-subject/31797903"
UVO_ICO = "31797903"
ZAKAZKA_URL = "https://www.uvo.gov.sk/vyhladavanie/vyhladavanie-zakaziek/detail/{}"
BRATISLAVA = ZoneInfo("Europe/Bratislava")
NAZOV_CISLA = re.compile(r"^\s*Vestník\s+(\d+)\s*/\s*(\d{4})\s*$")

TIME_BUDGET_MIN = float(os.environ.get("UVO_TIME_BUDGET_MIN", "45"))
DAVKA = 500


# ══════════════════════════════════════════════════════════════════════════
#  Strom formulára
# ══════════════════════════════════════════════════════════════════════════

def najdi(uzly, kluc):
    """Všetky uzly s daným kľúčom (do hĺbky, v poradí dokumentu).

    Do nájdeného uzla sa ďalej nezostupuje — panely rovnakého typu nie sú
    vnorené do seba a zostup by pri zmene tvaru zdvojil záznamy.
    """
    out = []
    for u in uzly or []:
        if not isinstance(u, dict):
            continue
        if u.get("key") == kluc:
            out.append(u)
        else:
            out.extend(najdi(u.get("components"), kluc))
    return out


def listy(uzol):
    """Všetky skalárne hodnoty v podstrome: {kľúč: [hodnoty v poradí]}."""
    out = {}

    def chod(uzly):
        for u in uzly or []:
            if not isinstance(u, dict):
                continue
            k, v = u.get("key"), u.get("value")
            if k and v is not None and v != "" and not isinstance(v, (dict, list)):
                out.setdefault(k, []).append(str(v))
            chod(u.get("components"))

    if isinstance(uzol, dict):
        chod(uzol.get("components"))
        k, v = uzol.get("key"), uzol.get("value")
        if k and v is not None and v != "" and not isinstance(v, (dict, list)):
            out.setdefault(k, []).append(str(v))
    else:
        chod(uzol)
    return out


def prvy(d, kluc, default=None):
    v = d.get(kluc)
    return v[0] if v else default


# ══════════════════════════════════════════════════════════════════════════
#  Hodnoty
# ══════════════════════════════════════════════════════════════════════════

def cislo(v):
    """'84 709.6' / '461 380,30' / '420321.8' -> float; nezmysel -> None."""
    if v is None:
        return None
    s = str(v).replace(" ", "").replace(" ", "").strip()
    if not s:
        return None
    if "," in s and "." in s:
        # 1.234.567,89 alebo 1,234,567.89 — desatinný je ten posledný
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def datum(v):
    if not v:
        return None
    m = re.match(r"(\d{4}-\d{2}-\d{2})", str(v))
    return m.group(1) if m else None


def mesiace(hodnota, jednotka):
    n = cislo(hodnota)
    if n is None:
        return None
    j = (jednotka or "").upper()
    if j == "MONTH":
        return n
    if j == "YEAR":
        return n * 12
    if j == "DAY":
        return round(n / 30.4375, 1)
    if j == "WEEK":
        return round(n * 7 / 30.4375, 1)
    return None


def pridaj_mesiace(d_iso, m):
    """Dátum + m mesiacov (celé mesiace, zvyšok v dňoch)."""
    if not d_iso or m is None:
        return None
    d = date.fromisoformat(d_iso)
    cele = int(m)
    r, mes = divmod(d.month - 1 + cele, 12)
    rok, mesiac = d.year + r, mes + 1
    # posledný deň mesiaca, ak pôvodný deň v cieľovom mesiaci neexistuje
    for den in (d.day, 30, 29, 28):
        try:
            nove = date(rok, mesiac, den)
            break
        except ValueError:
            continue
    nove = nove + timedelta(days=round((m - cele) * 30.4375))
    return nove.isoformat()


def zakazka_id(metadata_order):
    m = re.search(r"\(ID:\s*(\d+)\)", metadata_order or "")
    return int(m.group(1)) if m else None


def lehota(d_str, t_str):
    """BT-131(d) nesie dátum, BT-131(t) čas (s nezmyselným dátumom)."""
    d = datum(d_str)
    if not d:
        return None
    m = re.search(r"T(\d{2}):(\d{2})", t_str or "")
    hod, minuta = (int(m.group(1)), int(m.group(2))) if m else (0, 0)
    miestny = datetime.fromisoformat(d).replace(hour=hod, minute=minuta, tzinfo=BRATISLAVA)
    return miestny.isoformat()


# ══════════════════════════════════════════════════════════════════════════
#  Sektory podľa CPV (poradie: od najšpecifickejšieho)
# ══════════════════════════════════════════════════════════════════════════

CPV_SEKTORY = [
    ("713150", "PASPORTIZACIA_SPRAVA_BUDOV"),
    ("70330", "PASPORTIZACIA_SPRAVA_BUDOV"),
    ("4531", "ELEKTROINSTALACIE"),
    ("4533", "KURENIE_VODA_PLYN"),
    ("4535", "KURENIE_VODA_PLYN"),
    ("4526", "STRECHY_IZOLACIE"),
    ("4532", "STRECHY_IZOLACIE"),
    ("4542", "OKNA_DVERE_POVRCHY"),
    ("4543", "OKNA_DVERE_POVRCHY"),
    ("4544", "OKNA_DVERE_POVRCHY"),
    ("7731", "ZELEN_ZIMNA_UDRZBA"),
    ("7732", "ZELEN_ZIMNA_UDRZBA"),
    ("7734", "ZELEN_ZIMNA_UDRZBA"),
    ("9062", "ZELEN_ZIMNA_UDRZBA"),
    ("9063", "ZELEN_ZIMNA_UDRZBA"),
    ("9091", "UPRATOVANIE"),
    ("9092", "UPRATOVANIE"),
    ("90900", "UPRATOVANIE"),
    ("60", "DOPRAVA_MECHANIZACIA"),
    ("555", "STRAVOVANIE"),
    ("553", "STRAVOVANIE"),
    ("7971", "OSTRAHA"),
    ("72", "IT_TECHNIKA"),
    ("48", "IT_TECHNIKA"),
    ("302", "IT_TECHNIKA"),
    ("798", "TLAC_KANCELARIA"),
    ("22", "TLAC_KANCELARIA"),
    ("3019", "TLAC_KANCELARIA"),
    ("45", "STAVEBNE_PRACE"),
]

# Divízie CPV, pri ktorých má zmysel skúsiť textovú klasifikáciu, keď CPV
# samo nič nepovie (napr. 50 opravy a údržba, 79 služby pre podniky).
# Pri tovaroch (15 potraviny, 33 lieky, …) text radšej neskúšame — inak by
# "Potraviny na zabezpečenie stravovania" skončili v STRAVOVANIE, hoci je
# to dodávka potravín, nie stravovacia služba.
TEXT_DIVIZIE = {"45", "50", "55", "60", "71", "72", "77", "79", "90", "98"}


def sektor(cpv, text):
    c = re.sub(r"\D", "", cpv or "")
    for prefix, s in CPV_SEKTORY:
        if c.startswith(prefix):
            return s
    if c and c[:2] not in TEXT_DIVIZIE:
        return None
    s, _ = klasifikuj(text, None)
    return None if s == SEKTOR_DOTACIE else s


# ══════════════════════════════════════════════════════════════════════════
#  Rozbor formulára
# ══════════════════════════════════════════════════════════════════════════

def _s_id(zoznam, predpona):
    """[(id, listy)] — ID podľa poradia panelu (ORG-0001, TPA-0001, …).

    Explicitné DL-Context-Org/-Lot ZÁMERNE ignorujeme: odmerané na 8 číslach
    (186–193/2026) bolo v 6 formulároch nesprávne (obstarávateľ na 2. mieste
    mal DL-Context-Org = ORG-0003, no odkazy OPT-300-Procedure-Buyer =
    ORG-0002 a OPT-300-Tenderer = ORG-0003 sedeli s poradím). Odkazy vo
    formulári teda počítajú s poradím, nie s týmto poľom.
    """
    return [(f"{predpona}-{i + 1:04d}", listy(uzol)) for i, uzol in enumerate(zoznam)]


def rozober(formular, vestnik, publikovane):
    """Jeden eForms formulár -> (druh, [riadky]).

    druh: 'vysledok' | 'sutaz' | 'predbezne' | None (preskočiť).
    """
    nazov_formulara = (formular.get("name") or "").strip()
    if nazov_formulara.lower().startswith("oprava"):
        return None, []

    koren = formular.get("components") or []
    meta = listy(najdi(koren, "metadataWrapper")[0]) if najdi(koren, "metadataWrapper") else {}
    typ = prvy(meta, "BT-03-notice") or ""
    n = nazov_formulara.lower()
    if typ == "result" or "výsledk" in n:
        druh = "vysledok"
    elif typ == "competition" or "vyhlásení" in n or "výzva" in n:
        druh = "sutaz"
    elif typ == "planning" or "predbežné" in n or "informatívne" in n:
        druh = "predbezne"
    else:
        return None, []

    orgs = dict(_s_id(najdi(koren, "GR-Organisations_panel"), "ORG"))
    vsetko = listy(koren)
    buyer_id = prvy(vsetko, "OPT-300-Procedure-Buyer")
    buyer = orgs.get(buyer_id, {})
    zak_id = zakazka_id(prvy(meta, "DL-Metadata-Order"))

    spolocne = {
        "oznamenie_id": formular.get("id"),
        "vestnik": vestnik,
        "typ_oznamenia": nazov_formulara,
        "zakazka_id": zak_id,
        "obstaravatel_ico": prvy(buyer, "BT-501-Organization-Company-CIN"),
        "obstaravatel_nazov": prvy(buyer, "BT-500-Organization-Company"),
        "nazov": prvy(vsetko, "BT-21-Procedure"),
        "url": ZAKAZKA_URL.format(zak_id) if zak_id else None,
        "publikovane": publikovane,
    }
    proc_cpv = prvy(vsetko, "BT-262-Procedure")
    proc_druh = prvy(vsetko, "BT-23-Procedure")
    proc_nuts = prvy(vsetko, "BT-5071-Procedure")

    lots = {}
    for lot_id, l in _s_id(najdi(koren, "GR-Lot_well"), "LOT"):
        cpv = prvy(l, "BT-262-Lot") or proc_cpv
        cast_nazov = prvy(l, "BT-21-Lot") or prvy(l, "DL-Title-Lot")
        lots[lot_id] = {
            "cast_nazov": cast_nazov,
            "cpv": cpv,
            "druh": prvy(l, "BT-23-Lot") or proc_druh,
            "nuts": prvy(l, "BT-5071-Lot") or proc_nuts,
            "predpokladana_hodnota": cislo(prvy(l, "BT-27-Lot_value")),
            "mena": prvy(l, "BT-27-Lot_currency"),
            "trvanie_mesiace": mesiace(prvy(l, "BT-36-Lot_value"), prvy(l, "BT-36-Lot_measure")),
            "zaciatok": datum(prvy(l, "BT-536-Lot")),
            "koniec": datum(prvy(l, "BT-537-Lot")),
            "lehota_ponuk": lehota(prvy(l, "BT-131(d)-Lot"), prvy(l, "BT-131(t)-Lot")),
            "sektor": sektor(cpv, f"{spolocne['nazov'] or ''} {cast_nazov or ''}"),
        }
    if not lots:
        # formulár bez častí — celý postup ako jedna časť
        lots[""] = {
            "cast_nazov": None, "cpv": proc_cpv, "druh": proc_druh, "nuts": proc_nuts,
            "predpokladana_hodnota": cislo(prvy(vsetko, "BT-27-Procedure_value")),
            "mena": prvy(vsetko, "BT-27-Procedure_currency"),
            "trvanie_mesiace": None, "zaciatok": None, "koniec": None, "lehota_ponuk": None,
            "sektor": sektor(proc_cpv, spolocne["nazov"] or ""),
        }

    if druh in ("sutaz", "predbezne"):
        riadky = []
        for lot_id, lot in lots.items():
            riadky.append({
                **spolocne, "typ": druh, "cast_id": lot_id,
                "cast_nazov": lot["cast_nazov"], "cpv": lot["cpv"], "sektor": lot["sektor"],
                "druh": lot["druh"], "nuts": lot["nuts"],
                "predpokladana_hodnota": lot["predpokladana_hodnota"], "mena": lot["mena"],
                "lehota_ponuk": lot["lehota_ponuk"], "trvanie_mesiace": lot["trvanie_mesiace"],
            })
        return druh, riadky

    # ── výsledok ─────────────────────────────────────────────────────────
    tpas = dict(_s_id(najdi(koren, "GR-TenderingParty_panel"), "TPA"))
    tenders = dict(_s_id(najdi(koren, "GR-LotTender_panel"), "TEN"))
    contracts = _s_id(najdi(koren, "GR-SettledContract_panel"), "CON")
    con_by_id = dict(contracts)
    con_by_tender = {}
    for cid, cl in contracts:
        for t in cl.get("BT-3202-Contract", []):
            con_by_tender.setdefault(t, cl)

    riadky = []
    for lr_uzol in najdi(koren, "GR-LotResult_panel"):
        lr = listy(lr_uzol)
        if prvy(lr, "BT-142-LotResult") != "selec-w":
            continue
        lot_id = prvy(lr, "BT-13713-LotResult") or next(iter(lots))
        lot = lots.get(lot_id) or lots.get(next(iter(lots)))

        pocet_ponuk = None
        for sub in najdi(lr_uzol.get("components"), "GR-LotResult-ReceivedSubmissions_panel"):
            sl = listy(sub)
            if prvy(sl, "BT-760-LotResult") == "tenders":
                pocet_ponuk = int(cislo(prvy(sl, "BT-759-LotResult")) or 0)

        ten_ids = lr.get("OPT-320-LotResult", [])
        if not ten_ids:
            # Národný formulár "Oznámenie o výsledku …" (bez D24) odkaz na
            # víťaznú ponuku nemá — ponuky sú zoradené cez BT-171 (poradie),
            # víťaz je poradie 1. Odmerané: 81 z 254 víťazných častí.
            ponuky = [(tid, t) for tid, t in tenders.items()
                      if prvy(t, "BT-13714-Tender", lot_id) == lot_id]
            prve = [tid for tid, t in ponuky if prvy(t, "BT-171-Tender") == "1"]
            ten_ids = prve or ([ponuky[0][0]] if len(ponuky) == 1 else [])
        for ten_id in ten_ids or [None]:
            ten = tenders.get(ten_id, {})
            hodnota = cislo(prvy(ten, "BT-720-Tender_value")) or cislo(prvy(lr, "BT-710-LotResult_value"))
            mena = prvy(ten, "BT-720-Tender_currency") or prvy(lr, "BT-710-LotResult_currency") or lot["mena"]
            con = con_by_tender.get(ten_id)
            if con is None:
                con_ids = lr.get("OPT-315-LotResult", [])
                con = con_by_id.get(con_ids[0]) if con_ids else None
            if con is None and len(contracts) == 1:
                con = contracts[0][1]      # jediná zmluva vo formulári
            con = con or {}
            podpisane = datum(prvy(con, "BT-145-Contract"))

            koniec, odhad = lot["koniec"], False
            if not koniec and podpisane and lot["trvanie_mesiace"]:
                zaciatok = lot["zaciatok"] or podpisane
                koniec, odhad = pridaj_mesiace(zaciatok, lot["trvanie_mesiace"]), True

            tpa = tpas.get(prvy(ten, "OPT-310-Tender"), {})
            vitazi = tpa.get("OPT-300-Tenderer", [])
            for org_id in vitazi or [None]:
                org = orgs.get(org_id, {})
                ico = prvy(org, "BT-501-Organization-Company-CIN") or ""
                if ico == UVO_ICO:   # poistka: ÚVO je len poskytovateľ služby
                    continue
                if not ico and not prvy(org, "BT-500-Organization-Company"):
                    continue         # víťaz sa nedá určiť — radšej nič než prázdny riadok
                riadky.append({
                    **spolocne, "cast_id": lot_id,
                    "cast_nazov": lot["cast_nazov"], "cpv": lot["cpv"], "sektor": lot["sektor"],
                    "druh": lot["druh"], "nuts": lot["nuts"],
                    "vitaz_ico": ico, "vitaz_nazov": prvy(org, "BT-500-Organization-Company"),
                    "hodnota": hodnota, "mena": mena,
                    "predpokladana_hodnota": lot["predpokladana_hodnota"],
                    "pocet_ponuk": pocet_ponuk,
                    "podpisane": podpisane,
                    "trvanie_mesiace": lot["trvanie_mesiace"],
                    "koniec": koniec, "koniec_odhad": odhad,
                    "zmluva_cislo": prvy(con, "BT-150-Contract"),
                    "crz_url": prvy(con, "BT-151-Contract"),
                })
    return druh, _bez_duplicit(riadky, ("oznamenie_id", "cast_id", "vitaz_ico"))


def _bez_duplicit(riadky, kluc):
    """Upsert padne, keď dávka obsahuje ten istý kľúč dvakrát."""
    videne, out = set(), []
    for r in riadky:
        k = tuple(r.get(x) for x in kluc)
        if k in videne:
            continue
        videne.add(k)
        out.append(r)
    return out


def rozober_cislo(data, vestnik):
    """Celé číslo Vestníka -> (vysledky, vyzvy, statistika)."""
    publikovane = datum(data.get("bulletinPublishDate"))
    vysledky, vyzvy = [], []
    st = {"oznameni": 0, "preskocenych": 0, "oprav_a_inych": 0}
    for polozka in data.get("bulletinItemList") or []:
        st["oznameni"] += 1
        try:
            formular = json.loads(polozka.get("itemData") or "")
        except (ValueError, TypeError):
            st["preskocenych"] += 1      # XML alebo poškodené
            continue
        try:
            druh, riadky = rozober(formular, vestnik, publikovane)
        except Exception as e:           # jeden zlý formulár nesmie zhodiť celé číslo
            log.warning("Vestník %s, formulár %s: %s", vestnik, formular.get("id"), e)
            st["preskocenych"] += 1
            continue
        if druh is None:
            st["oprav_a_inych"] += 1
        elif druh == "vysledok":
            vysledky.extend(riadky)
        else:
            vyzvy.extend(riadky)
    vysledky = _bez_duplicit(vysledky, ("oznamenie_id", "cast_id", "vitaz_ico"))
    vyzvy = _bez_duplicit(vyzvy, ("oznamenie_id", "cast_id"))
    return vysledky, vyzvy, st


# ══════════════════════════════════════════════════════════════════════════
#  Katalóg a sťahovanie
# ══════════════════════════════════════════════════════════════════════════

def _session():
    s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    return s


def zoznam_cisel(sess, od_rok):
    """[{vestnik, rok, cislo, url, dataset_id}] zoradené od najstaršieho."""
    najdene = {}
    for strana in range(1, 60):
        telo = {
            "language": "sk", "page": strana, "pageSize": 100, "query": "Vestník",
            "orderBy": "created", "filters": {"publishers": [UVO_VYDAVATEL]},
            "requiredFacets": [],
        }
        r = sess.post(f"{KATALOG}/datasets/search", json=telo, timeout=60)
        r.raise_for_status()
        polozky = r.json().get("items") or []
        if not polozky:
            break
        stare = 0
        for d in polozky:
            m = NAZOV_CISLA.match(d.get("name") or "")
            if not m:
                continue
            c, rok = int(m.group(1)), int(m.group(2))
            if rok < od_rok:
                stare += 1
                continue
            dist = (d.get("distributions") or [{}])[0]
            url = dist.get("downloadUrl") or dist.get("accessUrl")
            if url:
                najdene[f"{c}/{rok}"] = {"vestnik": f"{c}/{rok}", "rok": rok, "cislo": c,
                                         "url": url, "dataset_id": d.get("id")}
        # zoradené od najnovšieho — keď je celá strana staršia, ďalej netreba
        if stare == len(polozky):
            break
    return sorted(najdene.values(), key=lambda x: (x["rok"], x["cislo"]))


def stiahni(sess, url):
    for pokus in range(3):
        try:
            r = sess.get(url, timeout=180)
            r.raise_for_status()
            # Katalóg posiela súbor ako `text/csv` BEZ charsetu, takže
            # requests by ho dekódoval ako ISO-8859-1 (r.text / r.json())
            # a z "zabezpečenie" by bolo "zabezpeÄ\x8denie" — odmerané na
            # prvom behu v GitHub Actions 25. 9. 2026. Súbor je UTF-8.
            return json.loads(r.content.decode("utf-8-sig"))
        except (requests.RequestException, ValueError) as e:
            if pokus == 2:
                raise
            log.warning("Sťahovanie zlyhalo (%s), skúšam znova: %s", e, url)
            time.sleep(10 * (pokus + 1))


# ══════════════════════════════════════════════════════════════════════════
#  Zápis
# ══════════════════════════════════════════════════════════════════════════

def _upsert(sb, tabulka, riadky, konflikt):
    for i in range(0, len(riadky), DAVKA):
        sb.table(tabulka).upsert(riadky[i:i + DAVKA], on_conflict=konflikt).execute()


def uloz(sb, cislo_info, vysledky, vyzvy, st, publikovany):
    _upsert(sb, "uvo_vysledky", vysledky, "oznamenie_id,cast_id,vitaz_ico")
    _upsert(sb, "uvo_vyzvy", vyzvy, "oznamenie_id,cast_id")
    # checkpoint až po úspešnom zápise riadkov
    sb.table("uvo_vestniky").upsert({
        "vestnik": cislo_info["vestnik"], "rok": cislo_info["rok"], "cislo": cislo_info["cislo"],
        "publikovany": publikovany, "dataset_id": cislo_info["dataset_id"],
        "oznameni": st["oznameni"], "vysledkov": len(vysledky), "vyziev": len(vyzvy),
        "preskocenych": st["preskocenych"], "spracovany_at": "now()",
    }, on_conflict="vestnik").execute()


def spracovane(sb):
    out, od = set(), 0
    while True:
        r = sb.table("uvo_vestniky").select("vestnik").range(od, od + 999).execute()
        out.update(x["vestnik"] for x in r.data)
        if len(r.data) < 1000:
            return out
        od += 1000


def _vystup(**kv):
    cesta = os.environ.get("GITHUB_OUTPUT")
    if cesta:
        with open(cesta, "a") as f:
            for k, v in kv.items():
                f.write(f"{k}={v}\n")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--od-rok", type=int, default=2025)
    ap.add_argument("--limit", type=int, default=400, help="max. čísel v jednom behu")
    ap.add_argument("--vestnik", help="spracovať len toto číslo, napr. 193/2026")
    ap.add_argument("--znova", action="store_true", help="aj už spracované čísla")
    ap.add_argument("--nasucho", action="store_true", help="nič nezapísať")
    a = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    start = time.monotonic()
    sess = _session()

    sb = None
    hotove = set()
    if not a.nasucho:
        from store import klient
        sb = klient()
        hotove = spracovane(sb)

    cisla = zoznam_cisel(sess, a.od_rok)
    log.info("V katalógu %d čísel od roku %d, spracovaných %d.", len(cisla), a.od_rok, len(hotove))
    if a.vestnik:
        cisla = [c for c in cisla if c["vestnik"] == a.vestnik]
    elif not a.znova:
        cisla = [c for c in cisla if c["vestnik"] not in hotove]

    spolu = {"cisel": 0, "vysledkov": 0, "vyziev": 0, "preskocenych": 0, "oznameni": 0,
             "s_vitazom_ico": 0, "s_koncom": 0, "so_sektorom": 0}
    zostava = False
    for i, c in enumerate(cisla):
        if i >= a.limit or (time.monotonic() - start) / 60 > TIME_BUDGET_MIN:
            zostava = True
            break
        data = stiahni(sess, c["url"])
        vysledky, vyzvy, st = rozober_cislo(data, c["vestnik"])
        publikovany = datum(data.get("bulletinPublishDate"))
        spolu["cisel"] += 1
        spolu["vysledkov"] += len(vysledky)
        spolu["vyziev"] += len(vyzvy)
        spolu["preskocenych"] += st["preskocenych"]
        spolu["oznameni"] += st["oznameni"]
        spolu["s_vitazom_ico"] += sum(1 for r in vysledky if r["vitaz_ico"])
        spolu["s_koncom"] += sum(1 for r in vysledky if r["koniec"])
        spolu["so_sektorom"] += sum(1 for r in vysledky + vyzvy if r["sektor"])
        log.info("Vestník %s: %d oznámení, %d výsledkov, %d výziev, %d preskočených",
                 c["vestnik"], st["oznameni"], len(vysledky), len(vyzvy), st["preskocenych"])
        if a.nasucho and spolu["cisel"] == 1:
            for r in vysledky[:3]:
                log.info("  ukážka výsledku: %s", {k: r[k] for k in (
                    "obstaravatel_nazov", "nazov", "cast_id", "vitaz_nazov", "vitaz_ico",
                    "hodnota", "podpisane", "trvanie_mesiace", "koniec", "sektor")})
            for r in vyzvy[:2]:
                log.info("  ukážka výzvy: %s", {k: r[k] for k in (
                    "typ", "obstaravatel_nazov", "nazov", "cast_id", "cpv", "sektor",
                    "predpokladana_hodnota", "lehota_ponuk")})
        if not a.nasucho:
            uloz(sb, c, vysledky, vyzvy, st, publikovany)

    log.info("HOTOVO %s: %s, zostáva: %s", "(nasucho)" if a.nasucho else "", spolu, zostava)
    _vystup(spracovanych=spolu["cisel"], zostava="true" if zostava else "false")
    return 0


if __name__ == "__main__":
    sys.exit(main())
