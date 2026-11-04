"""Doplni obce_register: pocet obyvatelov, NRO, MRK, ICO a typ (obec/mesto).

Bezi v GitHub Actions (workflow "Pilot vyzvy"), kde su dosiahnutelne zdroje SU SR
a RPO. Nahradza rucne CSV pre skripty/doplnenie-registra-obci.ts.

ZDROJE
  pocet obyvatelov  DATAcube SU SR, dataset om7102rr (obce, rocne), JSON-stat.
                    Pre kazdu obec berieme NAJVACSIU hodnotu z buniek daneho roka,
                    co je stlpec "spolu" (muzi a zeny su vzdy mensie).
  NRO               zoznam MIRRI SR (19 okresov), stav stranky k 3. 11. 2026:
                    mirri.gov.sk/sekcie/regionalny-rozvoj-2/najmenej-rozvinute-okresy/okresy/
  MRK               Atlas romskych komunit 2019, verejna databaza (xlsx, UV SR)
  ICO               kampan_obce_kontakty (ico + kod_obce), uz v databaze
  typ               RPO (register pravnickych osob SU SR): nazov "Mesto ..." / "Obec ...",
                    len pre obce s ICO

    python obce_demografia.py            # na sucho: vypise statistiku (::notice::)
    python obce_demografia.py --zapis    # zapise do obce_register

Logy su verejne (verejne repo): vypisuju sa LEN pocty a struktura zdrojov,
ziadne kontakty. Hodnoty sa nikdy neprepisu na null; nic sa nemaze.
"""
import argparse
import io
import logging
import re
import sys
import unicodedata

import requests

import store

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("demografia")
UA = {"User-Agent": "tendre-portal/1.0 (open data client)"}
KOD = re.compile(r"^SK0[0-9A-F]{3}(\d{6})$")   # okres moze mat pismeno (SK041A Stara Lubovna)

NRO_OKRESY = [
    "Bardejov", "Gelnica", "Kežmarok", "Košice - okolie", "Levoča", "Lučenec",
    "Medzilaborce", "Michalovce", "Poltár", "Revúca", "Rimavská Sobota", "Rožňava",
    "Sabinov", "Stará Ľubovňa", "Sobrance", "Stropkov", "Svidník", "Trebišov",
    "Vranov nad Topľou",
]
ATLAS_URL = "https://www.romovia.vlada.gov.sk/site/assets/files/1111/ark2019_c_verejna.xlsx"
DATACUBE = "https://data.statistics.sk/api/v2/dataset"
DATASETY = ("om7101rr", "om7102rr")   # om7101rr cituje aj Wikipedia pri obciach


# GitHub zobrazi najviac 10 anotacii na krok: zbierame ich a na konci vypiseme jednu.
SPRAVY = []


def notice(text):
    print(text, flush=True)
    SPRAVY.append(str(text))


def vypis_suhrn():
    print("::notice::" + " || ".join(SPRAVY).replace("\n", " ")[:3900], flush=True)


def norm(s) -> str:
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"^\s*okres\s+", "", s)
    s = re.sub(r"\s*-\s*", "-", s)
    return re.sub(r"\s+", " ", s).strip()


# ── Pocet obyvatelov ─────────────────────────────────────────────────────────
def jsonstat_maxima(data: dict) -> dict:
    """JSON-stat 2.0 dataset -> {6-miestny kod obce: najvacsia hodnota}."""
    ids, sizes = data["id"], data["size"]
    dims = data["dimension"]
    # dimenzia s kodmi obci
    obec_dim = None
    for i, d in enumerate(ids):
        idx = dims[d]["category"]["index"]
        kluce = list(idx.keys()) if isinstance(idx, dict) else list(idx)
        if sum(1 for k in kluce if KOD.match(k)) > min(1000, len(kluce) // 2):
            obec_dim = i
            break
    if obec_dim is None:
        raise ValueError(f"Nenasla sa dimenzia obci. Dimenzie: {ids}")
    idx = dims[ids[obec_dim]]["category"]["index"]
    poradie = sorted(idx, key=idx.get) if isinstance(idx, dict) else list(idx)
    values = data["value"]
    if isinstance(values, dict):
        values = {int(k): v for k, v in values.items()}
        get = values.get
    else:
        get = lambda n: values[n] if n < len(values) else None  # noqa: E731
    # krok pre index obce v plochom poli (row-major)
    krok = 1
    for s in sizes[obec_dim + 1:]:
        krok *= s
    total = 1
    for s in sizes:
        total *= s
    out = {}
    for n in range(total):
        v = get(n)
        if v is None:
            continue
        o = (n // krok) % sizes[obec_dim]
        m = KOD.match(poradie[o])
        if not m:
            continue
        k = m.group(1)
        out[k] = max(out.get(k, 0), int(v))
    return out


WIKIDATA = "https://query.wikidata.org/sparql"
SPARQL = """
SELECT ?lau ?pop ?datum ?typLabel WHERE {
  ?o wdt:P17 wd:Q214 ; wdt:P782 ?lau ; p:P1082 ?st .
  ?st ps:P1082 ?pop . OPTIONAL { ?st pq:P585 ?datum }
  OPTIONAL { ?o wdt:P31 ?typ }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "sk". }
}"""


def wikidata_obyvatelia():
    """Zaloha, ked je DATAcube nedostupny (z GitHub Actions byva): Wikidata.
    Vrati ({kod6: (pocet, rok)}, {kod6: typ}). Pri viacerych udajoch berie najnovsi."""
    r = requests.get(WIKIDATA, params={"query": SPARQL, "format": "json"},
                     headers={**UA, "Accept": "application/sparql-results+json"}, timeout=180)
    r.raise_for_status()
    pocty, typy = {}, {}
    for b in r.json()["results"]["bindings"]:
        lau = re.sub(r"\D", "", b["lau"]["value"])
        if len(lau) < 6:
            continue
        k6 = lau[-6:]
        try:
            pop = int(float(b["pop"]["value"]))
        except ValueError:
            continue
        rok = int(b["datum"]["value"][:4]) if "datum" in b else 0
        if k6 not in pocty or rok > pocty[k6][1]:
            pocty[k6] = (pop, rok)
        t = norm(b.get("typLabel", {}).get("value"))
        if "mestska cast" in t:
            typy[k6] = "mestska_cast"
        elif t.startswith("mesto") and typy.get(k6) != "mestska_cast":
            typy[k6] = "mesto"
    return pocty, typy


def stiahni_obyvatelov():
    """DATAcube SU SR (jeden rychly pokus), inak Wikidata.
    Vrati ({kod6: pocet}, {kod6: rok}, {kod6: typ}, zdroj)."""
    for ds in DATASETY:
        url = f"{DATACUBE}/{ds}/all/2025/all?lang=sk&type=json"
        try:
            r = requests.get(url, headers=UA, timeout=20)
            if r.status_code == 200 and r.text.strip().startswith("{"):
                vysl = jsonstat_maxima(r.json())
                if len(vysl) > 2500:
                    return vysl, {k: 2025 for k in vysl}, {}, f"DATAcube {ds}"
            notice(f"DATAcube {ds}: HTTP {r.status_code}")
        except Exception as e:  # noqa: BLE001
            notice(f"DATAcube {ds}: {type(e).__name__}")
    try:
        pocty, typy = wikidata_obyvatelia()
        notice(f"Wikidata: obci s poctom {len(pocty)}, mesta/mestske casti {len(typy)}, "
               f"roky udajov {sorted({r for _, r in pocty.values()})[-5:]}")
        return ({k: v[0] for k, v in pocty.items()}, {k: v[1] for k, v in pocty.items()}, typy, "Wikidata")
    except Exception as e:  # noqa: BLE001
        notice(f"Wikidata: {type(e).__name__} {str(e)[:100]}")
    return {}, {}, {}, None


# ── MRK (Atlas 2019) ──────────────────────────────────────────────────────────
def stiahni_mrk():
    """Vrati mnozinu 6-miestnych kodov obci z Atlasu, alebo set() pri zlyhani."""
    import pandas as pd
    r = requests.get(ATLAS_URL, headers=UA, timeout=120)
    if r.status_code != 200:
        notice(f"Atlas: HTTP {r.status_code}")
        return set(), set()
    listy = pd.read_excel(io.BytesIO(r.content), sheet_name=None, header=None, dtype=str)
    kody, mena = set(), set()
    if "obce" in listy:   # list 'obce': Kraj, Okres, Obec, Kod obce -> zaloha podla nazvu
        df = listy["obce"]
        for _, row in df.iloc[1:].iterrows():
            mena.add((norm(row[2]), norm(row[1])))
    for nazov, df in listy.items():
        notice(f"Atlas list '{nazov}': {df.shape}, prvy riadok: {[str(x)[:20] for x in df.iloc[0].tolist()[:8]]}")
        for col in df.columns:
            hodnoty = df[col].dropna().astype(str).str.strip()
            k6 = hodnoty[hodnoty.str.fullmatch(r"5\d{5}")]
            if len(k6) > 300:
                kody |= set(k6)
                notice(f"Atlas: stlpec {col} v liste '{nazov}' ma {len(set(k6))} kodov obci")
    return kody, mena


# ── RPO: typ (mesto/obec) podla ICO ────────────────────────────────────────────
def typ_z_rpo(ico: str):
    try:
        r = requests.get("https://api.statistics.sk/rpo/v1/search", params={"identifier": ico},
                         headers=UA, timeout=30)
        if r.status_code != 200:
            return None
        res = (r.json() or {}).get("results") or []
        for z in res:
            for fn in z.get("fullNames") or []:
                v = norm(fn.get("value"))
                if v.startswith("mesto ") or v.startswith("mestska cast"):
                    return "mestska_cast" if v.startswith("mestska cast") else "mesto"
                if v.startswith("obec "):
                    return "obec"
    except requests.RequestException:
        return None
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--zapis", action="store_true")
    ap.add_argument("--bez-rpo", action="store_true")
    a = ap.parse_args()
    sb = store.klient()

    stl = "kod,nazov,kraj,okres,ico,typ,pocet_obyvatelov,nro,mrk"
    register, od = [], 0
    while True:   # PostgREST vracia najviac 1000 riadkov na dotaz
        kus = sb.table("obce_register").select(stl).order("kod").range(od, od + 999).execute().data
        register += kus
        if len(kus) < 1000:
            break
        od += 1000
    notice(f"Register: {len(register)} obci")
    po_kode6 = {KOD.match(r["kod"]).group(1): r for r in register if KOD.match(r["kod"])}

    # ICO z kontaktov kampane (kod_obce = kod registra)
    kontakty, od = [], 0
    while True:
        kus = sb.table("kampan_obce_kontakty").select("ico,kod_obce").order("ico").range(od, od + 999).execute().data
        kontakty += kus
        if len(kus) < 1000:
            break
        od += 1000
    kody_reg = {r["kod"] for r in register}
    tvary = {}
    for k in kontakty:
        kk = str(k.get("kod_obce") or "")
        t = "prazdny" if not kk else ("register" if kk in kody_reg else f"iny dlzka {len(kk)}")
        tvary[t] = tvary.get(t, 0) + 1
    notice(f"Kontakty: {len(kontakty)}, kod_obce: {tvary}")
    # kod_obce moze byt aj 6-miestny kod SU SR
    po6 = {KOD.match(r["kod"]).group(1): r["kod"] for r in register if KOD.match(r["kod"])}
    ico_pre = {}
    for k in kontakty:
        kk = str(k.get("kod_obce") or "")
        kod = kk if kk in kody_reg else po6.get(kk[-6:]) if len(kk) >= 6 else None
        if k.get("ico") and kod:
            ico_pre[kod] = re.sub(r"\D", "", k["ico"]).zfill(8)
    notice(f"ICO z kontaktov: {len(ico_pre)}")

    obyv, roky, typy_wd, zdroj = stiahni_obyvatelov()
    try:
        mrk_kody, mrk_mena = stiahni_mrk()
    except Exception as e:  # noqa: BLE001
        notice(f"Atlas zlyhal: {e}")
        mrk_kody, mrk_mena = set(), set()
    nro = {norm(o) for o in NRO_OKRESY}
    okresy_reg = {norm(r.get("okres")) for r in register}
    notice(f"NRO bez zhody v registri: {sorted(nro - okresy_reg)}; priklad okresov registra: {sorted(okresy_reg)[:6]}")

    zmeny = []
    stat = {"pocet": 0, "nro_true": 0, "mrk_true": 0, "ico": 0, "typ": 0}
    for r in register:
        m = KOD.match(r["kod"])
        if not m:
            continue
        k6 = m.group(1)
        z = dict(r)
        if k6 in obyv:
            z["pocet_obyvatelov"] = obyv[k6]
            if roky.get(k6):
                z["obyvatelia_k"] = f"{roky[k6]}-12-31"
            stat["pocet"] += 1
        z["nro"] = norm(r.get("okres")) in nro
        stat["nro_true"] += z["nro"]
        if mrk_kody:
            z["mrk"] = k6 in mrk_kody or (norm(r["nazov"]), norm(r.get("okres"))) in mrk_mena
            stat["mrk_true"] += z["mrk"]
        if not r.get("ico") and r["kod"] in ico_pre:
            z["ico"] = ico_pre[r["kod"]]
            stat["ico"] += 1
        zmeny.append(z)

    # typ: najprv Wikidata (mesto / mestska cast podla kodu obce), potom RPO podla ICO
    for z in zmeny:
        k6 = KOD.match(z["kod"]).group(1)
        if typy_wd.get(k6) and typy_wd[k6] != z.get("typ"):
            z["typ"] = typy_wd[k6]
            stat["typ"] += 1
    if not a.bez_rpo and typ_z_rpo("00328715") is None:
        notice("RPO nedostupne, typ len z Wikidata")
        a.bez_rpo = True
    if not a.bez_rpo:
        s_ico = [z for z in zmeny if z.get("ico") and (z.get("typ") or "obec") == "obec"]
        for z in s_ico:
            t = typ_z_rpo(z["ico"])
            if t and t != z.get("typ"):
                z["typ"] = t
                stat["typ"] += 1
        notice(f"RPO: preverenych {len(s_ico)} obci, typ zmeneny {stat['typ']} (mesta, mestske casti)")

    notice(f"Zdroj obyvatelov: {zdroj}")
    notice("Statistika: " + ", ".join(f"{k} {v}" for k, v in stat.items()) + f" | NRO okresov v registri: "
           f"{len({norm(z.get('okres')) for z in zmeny if z['nro']})}/19")
    if len(obyv) < 2500:
        notice("POZOR: pocty obyvatelov sa nepodarilo nacitat (menej ako 2500 obci), stlpec sa nemeni")

    if not a.zapis:
        notice("Na sucho, nic sa nezapisalo.")
        return 0
    stlpce = ("kod", "nazov", "kraj", "okres", "ico", "typ", "pocet_obyvatelov", "obyvatelia_k", "nro", "mrk")
    riadky = [{k: z.get(k) for k in stlpce} for z in zmeny]
    for i in range(0, len(riadky), 500):
        sb.table("obce_register").upsert(riadky[i:i + 500], on_conflict="kod").execute()
    notice(f"Zapisane: {len(riadky)} obci")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        vypis_suhrn()
