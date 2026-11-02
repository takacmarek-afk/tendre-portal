"""Zmluvy bez dohladatelnej sutaze (prototyp 2. 11. 2026, migracia 88).

Velke zmluvy z CRZ (`contracts`), ku ktorym vo Vestniku UVO nie je:
  - vysledok s rovnakym ICO uradu aj vitaza, ani
  - vyhlasenie/vysledok toho isteho uradu s podobnym nazvom
    (zhoda slov >= PRAH_PODOBNOSTI) v okne -720 az +45 dni od podpisu,
a zmluva neodkazuje na uvo.gov.sk. Vynechane: dodatky, dotacie/NFP,
najmy, pozicky, zmluvy medzi uradmi a sektorovi obstaravatelia (vodarne,
teplarne, energetika, doprava), ktori maju ine limity.

Limit: stavby >= 600 000 EUR, tovary a sluzby >= 250 000 EUR (s DPH,
konzervativne nad podlimitom). Zmluvy mladsie ako 45 dni su 'predbezne'
(vysledok sutaze moze prist az 30 dni po podpise).

Vystup ide do tabulky zmluvy_bez_sutaze (citat ju smie len admin). Log
obsahuje len pocty — repozitar je verejny a nazvy uradov tam nepatria.

    python bez_sutaze.py [--nasucho] [--mesiacov 20]
"""
import argparse
import logging
import re
import sys
import unicodedata
from datetime import date, datetime, timedelta, timezone

from strankuj import vsetky

log = logging.getLogger("bez_sutaze")

LIMIT_STAVBY = 600_000
LIMIT_OSTATNE = 250_000
PRAH_PODOBNOSTI = 0.34
OKNO_PRED, OKNO_PO = 720, 45
DNI_PREDBEZNE = 45

VYNECHAT_PREDMET = re.compile(
    r"dodat|nfp|nenávratn|dotáci|príspev|zmluva o poskytnutí|o spolupráci|o pôžičk|úver|nájom|nájm"
    r"|kúpna zmluva.*pozem|zámen", re.I)
DODATOK_ZACIATOK = re.compile(r"^\s*(dodatok|dodatek|zmena|amendment)", re.I)
VEREJNY_DODAVATEL = re.compile(
    r"ministerstvo|^mesto |^obec |samosprávny kraj|správa ciest|úrad|štátny podnik|národn"
    r"|slovenská republika|fond", re.I)
SEKTOROVY = re.compile(
    r"vodárensk|vodarensk|teplár|teplar|energet|elektr[áa]r|dopravn[ýy] podnik|plyn|letisk"
    r"|železnic|zeleznic|pošta|posta", re.I)
INHOUSE = re.compile(
    r"technické služby|technicke sluzby|správa|sprava|bytový podnik|mestsk[ýá] podnik|príspevková"
    r"|verejnoprospešné|rozvojové služby", re.I)
STOP = {"zmluva", "zmluvy", "dielo", "diela", "realizaciu", "realizacia", "realizacie", "stavby",
        "stavba", "sluzieb", "poskytovanie", "poskytnutie", "dodavka", "tovaru", "ramcova", "dohoda",
        "predmet", "zakazky", "cast", "mesta", "obce", "kraja"}


def ico(v) -> str:
    cisla = re.sub(r"\D", "", str(v or ""))
    return cisla.zfill(8) if cisla else ""


def slova(text) -> set:
    t = unicodedata.normalize("NFD", (text or "").lower())
    t = "".join(z for z in t if unicodedata.category(z) != "Mn")
    t = re.sub(r"[^a-z0-9 ]", " ", t)
    return {w for w in t.split() if len(w) >= 4 and w not in STOP}


def podobnost(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def nad_limit(z) -> bool:
    cena = float(z.get("price_total") or 0)
    return cena >= (LIMIT_STAVBY if z.get("sector") == "STAVEBNE_PRACE" else LIMIT_OSTATNE)


def je_kandidat(z) -> bool:
    """Zmluva, ktora ma vobec zmysel porovnavat (bez Vestnika)."""
    predmet = f"{z.get('subject') or ''} {z.get('subject_description') or ''}"
    return (z.get("type_id") == 1 and z.get("sector") not in (None, "DOTACIE_NFP")
            and nad_limit(z)
            and not DODATOK_ZACIATOK.search(z.get("subject") or "")
            and not VYNECHAT_PREDMET.search(predmet)
            and not VEREJNY_DODAVATEL.search(z.get("supplier_name") or "")
            and not SEKTOROVY.search(z.get("authority_name") or "")
            and ico(z.get("authority_cin")) and ico(z.get("supplier_cin"))
            and "uvo.gov.sk" not in (z.get("procurement_url") or ""))


def vyhodnot(zmluvy, vysledky, vyzvy, dnes: date):
    """-> zoznam riadkov pre zmluvy_bez_sutaze. Cista funkcia (testy)."""
    pary = {(ico(v.get("obstaravatel_ico")), ico(v.get("vitaz_ico"))) for v in vysledky}
    podla_uradu = {}
    for v in list(vysledky) + list(vyzvy):
        if not v.get("publikovane"):
            continue
        nazov = f"{v.get('nazov') or ''} {v.get('cast_nazov') or ''}"
        podla_uradu.setdefault(ico(v.get("obstaravatel_ico")), []).append(
            (slova(nazov), date.fromisoformat(str(v["publikovane"])[:10])))

    vysledok, videne = [], {}
    for z in sorted(zmluvy, key=lambda z: z["id"]):
        if not je_kandidat(z):
            continue
        a, s = ico(z["authority_cin"]), ico(z["supplier_cin"])
        if (a, s) in pary:
            continue
        podpis = date.fromisoformat(str(z["signed_on"])[:10])
        zs = slova(z.get("subject"))
        najlepsia = 0.0
        for t, d in podla_uradu.get(a, []):
            rozdiel = (podpis - d).days
            if -OKNO_PO <= rozdiel <= OKNO_PRED:
                najlepsia = max(najlepsia, podobnost(zs, t))
        if najlepsia >= PRAH_PODOBNOSTI:
            continue
        kluc = (a, s, round(float(z["price_total"])), (z.get("subject") or "").strip().lower()[:60])
        riadok = {
            "contract_id": z["id"],
            "authority_ico": a, "authority_name": z.get("authority_name"),
            "supplier_ico": s, "supplier_name": z.get("supplier_name"),
            "subject": z.get("subject"), "sector": z.get("sector"),
            "price_total": z.get("price_total"), "signed_on": str(z["signed_on"])[:10],
            "kategoria": "inhouse" if INHOUSE.search(z.get("supplier_name") or "") else "ostatne",
            "podobnost": round(najlepsia, 2),
            "stav": "predbezne" if (dnes - podpis).days < DNI_PREDBEZNE else "potvrdene",
            "duplicita_k": videne.get(kluc),
        }
        videne.setdefault(kluc, z["id"])
        vysledok.append(riadok)
    return vysledok


# ── Overenie cez vyhľadávanie zákaziek na uvo.gov.sk (EVO) ────────────────
# Vestník nemá zákazky s nízkou hodnotou ani výsledky podlimitných súťaží.
# Vyhľadávanie zákaziek na uvo.gov.sk ich má (aj "EVO zákazky"). Ručná
# kontrola 2. 11. 2026: 5 zo 6 nálezov malo zákazku práve tam.
EVO_URL = "https://www.uvo.gov.sk/vyhladavanie/vyhladavanie-zakaziek"
_RIADOK = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
_BUNKA = re.compile(r"<td[^>]*>(.*?)</td>", re.S | re.I)
_TAG = re.compile(r"<[^>]+>")
_PREDPONA_URADU = re.compile(r"^(obec|mesto|mestská časť|mestska cast)\s+", re.I)


def evo_riadky(html_text: str):
    """HTML výsledkov vyhľadávania -> [(nazov zakazky, obstaravatel)]."""
    import html as h
    tbody = html_text.split("<tbody", 1)[-1]
    out = []
    for r in _RIADOK.findall(tbody):
        bunky = [h.unescape(_TAG.sub(" ", b)).strip() for b in _BUNKA.findall(r)]
        if len(bunky) >= 2 and bunky[0]:
            out.append((" ".join(bunky[0].split()), " ".join(bunky[1].split())))
    return out


def evo_dotazy(z) -> list:
    """Dva dotazy: meno uradu (bez 'Obec'/'Mesto') a najvyraznejsie slova predmetu."""
    urad = _PREDPONA_URADU.sub("", (z.get("authority_name") or "").strip())
    urad = " ".join(urad.split()[:3])
    predmet = sorted((w for w in re.split(r"[^\wÀ-ž]+", z.get("subject") or "")
                      if len(w) >= 6 and w.lower() not in STOP), key=len, reverse=True)[:3]
    return [q for q in (urad, " ".join(predmet)) if q]


def evo_vysvetli(z, riadky) -> bool:
    """Je medzi zákazkami na uvo.gov.sk zákazka toho istého úradu s podobným názvom?"""
    zs, us = slova(z.get("subject")), slova(z.get("authority_name"))
    for nazov, obst in riadky:
        if podobnost(us, slova(obst)) >= 0.5 and podobnost(zs, slova(nazov)) >= PRAH_PODOBNOSTI:
            return True
    return False


def over_evo(riadky_vystupu, zmluvy_podla_id, sess, pauza=1.0):
    """Z výstupu vyradí zmluvy, ku ktorým sa zákazka našla na uvo.gov.sk. -> (zostava, vysvetlenych)."""
    import time
    zostava, vysvetlene = [], 0
    for r in riadky_vystupu:
        z = zmluvy_podla_id[r["contract_id"]]
        najdene = []
        for q in evo_dotazy(z):
            try:
                odp = sess.get(EVO_URL, params={"nazovZakazky": q}, timeout=30)
                if odp.ok:
                    najdene += evo_riadky(odp.text)
            except Exception as e:     # výpadok UVO nesmie zastaviť výpočet
                log.warning("uvo.gov.sk vyhľadávanie zlyhalo: %s", type(e).__name__)
            time.sleep(pauza)
        if evo_vysvetli(z, najdene):
            vysvetlene += 1
        else:
            zostava.append(r)
    return zostava, vysvetlene


def suhrn(riadky) -> dict:
    jedinecne = [r for r in riadky if not r["duplicita_k"]]
    return {
        "zmluv": len(jedinecne),
        "mil_eur": round(sum(float(r["price_total"]) for r in jedinecne) / 1e6, 1),
        "inhouse": sum(r["kategoria"] == "inhouse" for r in jedinecne),
        "predbezne": sum(r["stav"] == "predbezne" for r in jedinecne),
        "duplicit": len(riadky) - len(jedinecne),
    }


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s %(message)s",
                        datefmt="%H:%M:%S")
    ap = argparse.ArgumentParser()
    ap.add_argument("--nasucho", action="store_true")
    ap.add_argument("--mesiacov", type=int, default=20)
    a = ap.parse_args(argv)

    import store
    sb = store.klient()
    dnes = date.today()
    od = (dnes - timedelta(days=30 * a.mesiacov)).isoformat()

    zmluvy = vsetky(lambda o, d: sb.table("contracts").select(
        "id,type_id,sector,price_total,signed_on,subject,subject_description,authority_name,"
        "authority_cin,supplier_name,supplier_cin,procurement_url")
        .gte("signed_on", od).gte("price_total", LIMIT_OSTATNE).neq("sector", "DOTACIE_NFP")
        .order("id").range(o, d).execute())
    vysledky = vsetky(lambda o, d: sb.table("uvo_vysledky").select(
        "id,obstaravatel_ico,vitaz_ico,nazov,cast_nazov,publikovane").order("id").range(o, d).execute())
    vyzvy = vsetky(lambda o, d: sb.table("uvo_vyzvy").select(
        "id,obstaravatel_ico,nazov,cast_nazov,publikovane").order("id").range(o, d).execute())
    log.info("Nacitane: zmluv %d, vysledkov %d, vyziev %d", len(zmluvy), len(vysledky), len(vyzvy))

    riadky = vyhodnot(zmluvy, vysledky, vyzvy, dnes)
    import requests
    sess = requests.Session()
    sess.headers["User-Agent"] = "PredTendrom.sk (info@predtendrom.sk)"
    riadky, vysvetlene_evo = over_evo(riadky, {z["id"]: z for z in zmluvy}, sess)
    s = {**suhrn(riadky), "vysvetlene_evo": vysvetlene_evo}
    log.info("Bez dohladatelnej sutaze: %s", s)
    print(f"::notice title=Zmluvy bez sutaze::{s}")
    if a.nasucho:
        return 0

    teraz = datetime.now(timezone.utc).isoformat()
    for i in range(0, len(riadky), 500):
        davka = [{**r, "aktualizovane_at": teraz} for r in riadky[i:i + 500]]
        sb.table("zmluvy_bez_sutaze").upsert(davka, on_conflict="contract_id").execute()
    # Zmluvy, ktore uz kandidatom nie su (napr. dorazil vysledok sutaze), sa
    # nemazu — dostanu stav 'vyriesene', aby ostala rucna kontrola a poznamka.
    aktualne = {r["contract_id"] for r in riadky}
    stare = vsetky(lambda o, d: sb.table("zmluvy_bez_sutaze").select("contract_id,stav")
                   .order("contract_id").range(o, d).execute())
    vyriesene = [r["contract_id"] for r in stare
                 if r["contract_id"] not in aktualne and r["stav"] != "vyriesene"]
    for i in range(0, len(vyriesene), 200):
        sb.table("zmluvy_bez_sutaze").update({"stav": "vyriesene", "aktualizovane_at": teraz}) \
            .in_("contract_id", vyriesene[i:i + 200]).execute()
    log.info("Zapisane %d, vyriesene %d", len(riadky), len(vyriesene))
    return 0


if __name__ == "__main__":
    sys.exit(main())
