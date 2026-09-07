"""Sonda: kolko stavebnych zmluv v CRZ ma pouzitelny oceneny vykaz vymer.

Odpoveda na tri otazky, ktore rozhoduju o tom, ci ma cenova inteligencia zmysel:
  N1  aky podiel stavebnych zmluv ma prilohu s rozpoctom
  N3  aky podiel poloziek nesie TSKP kod
      (N2, ceny prehravajucich uchadzacov, sa z CRZ zistit neda — to je UVO)

Berie ID zmluv priamo z nasej databazy, nie z rucneho zoznamu. Spusta sa
z GitHub Actions, takze netreba nic instalovat lokalne.

    python probe_vykazy.py --pocet 250
"""
import io
import re
import csv
import sys
import time
import random
import logging
import argparse
from dataclasses import dataclass, asdict, fields

import requests

import store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("probe")

BASE = "https://www.crz.gov.sk"
# Vlastny User-Agent s kontaktom. CRZ je statna sluzba, nie nase CDN.
UA = {"User-Agent": "predtendrom.sk research probe (info@predtendrom.sk)"}

# Sektory, kde ma zmysel hladat oceneny vykaz vymer
SEKTORY_STAVBA = [
    "STAVEBNE_PRACE", "STRECHY_IZOLACIE", "OKNA_DVERE_POVRCHY",
    "ELEKTROINSTALACIE", "KURENIE_VODA_PLYN",
]

NAZOV_VYKAZ = re.compile(
    r"(v[yý]kaz\s*v[yý]mer|rozpo[čc]et|ocenen|s[uú]pis\s*pr[aá]c|bill\s*of\s*quant)", re.I)
# TSKP: 9 cislic, casto delene — 612 46-1121 aj 612461121
TSKP = re.compile(r"\b\d{3}[\s.-]?\d{2}[\s.-]?\d{4}\b")
MJ = re.compile(r"\b(m2|m3|m|ks|kg|t|bm|hod|s[uú]b|kpl)\b", re.I)
CISLO = re.compile(r"\d{1,3}(?:[\s ]\d{3})*(?:[,.]\d+)?")


@dataclass
class Vysledok:
    zmluva_id: str
    priloha: str
    nazov: str
    typ: str
    bajtov: int
    znakov: int
    tskp_kodov: int
    riadkov_s_cenou: int
    podiel_riadkov_s_tskp: float
    verdikt: str


def _stiahni(url, timeout=60):
    r = requests.get(url, headers=UA, timeout=timeout)
    r.raise_for_status()
    return r.content


def prilohy(zmluva_id):
    html = requests.get(f"{BASE}/zmluva/{zmluva_id}/", headers=UA, timeout=60).text
    najdene = re.findall(
        r'href="(?:https?://[^"]*)?/data/att/([\w.]+?)\.(pdf|xlsx|xls|docx|zip)"[^>]*>(.*?)</a>',
        html, re.I | re.S)
    out = []
    for att_id, ext, label in najdene:
        nazov = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", label)).strip()
        out.append((f"{att_id}.{ext.lower()}", nazov or att_id))
    return out


def _hodnot(text, riadkov, tskp_kodov):
    """Spolocne rozhodnutie pre PDF aj Excel."""
    znakov = len(text.strip())
    podiel = round(tskp_kodov / riadkov, 2) if riadkov else 0.0
    if znakov < 400:
        return znakov, podiel, "SKEN"
    if riadkov < 10:
        return znakov, podiel, "BEZ_CIEN"
    return znakov, podiel, "POUZITELNE" if tskp_kodov >= 5 else "BEZ_TSKP"


def analyzuj_pdf(data):
    import pdfplumber
    casti = []
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page in pdf.pages[:25]:
                casti.append(page.extract_text() or "")
    except Exception as e:
        return 0, 0, 0, 0.0, f"CHYBA:{type(e).__name__}"

    text = "\n".join(casti)
    riadky = sum(1 for l in text.splitlines()
                 if MJ.search(l) and len(CISLO.findall(l)) >= 3)
    tskp = len(set(TSKP.findall(text)))
    znakov, podiel, verdikt = _hodnot(text, riadky, tskp)
    return znakov, tskp, riadky, podiel, verdikt


def analyzuj_xlsx(data):
    import openpyxl
    try:
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as e:
        return 0, 0, 0, 0.0, f"CHYBA:{type(e).__name__}"

    riadky, casti = 0, []
    for ws in wb.worksheets:
        for row in ws.iter_rows(max_row=3000, values_only=True):
            vals = [str(c) for c in row if c is not None]
            if not vals:
                continue
            line = " ".join(vals)
            casti.append(line)
            if sum(1 for c in row if isinstance(c, (int, float))) >= 3 and MJ.search(line):
                riadky += 1
    text = "\n".join(casti)
    tskp = len(set(TSKP.findall(text)))
    # Excel ma text vzdy, takze prah na "sken" nema zmysel
    podiel = round(tskp / riadky, 2) if riadky else 0.0
    verdikt = ("POUZITELNE" if (tskp >= 5 and riadky >= 10)
               else "BEZ_TSKP" if riadky >= 10 else "BEZ_CIEN")
    return len(text), tskp, riadky, podiel, verdikt


def spracuj(zmluva_id):
    try:
        vsetky = prilohy(zmluva_id)
    except Exception as e:
        return [Vysledok(zmluva_id, "", "", "", 0, 0, 0, 0, 0.0,
                         f"CHYBA:{type(e).__name__}")]
    if not vsetky:
        return [Vysledok(zmluva_id, "", "", "", 0, 0, 0, 0, 0.0, "BEZ_PRILOH")]

    # Najprv prilohy, ktore podla nazvu vyzeraju ako rozpocet. Nazvy v CRZ
    # byvaju generické (dokument1.pdf), preto fallback na vsetky.
    kandidati = [(a, n) for a, n in vsetky if NAZOV_VYKAZ.search(n) or NAZOV_VYKAZ.search(a)]
    if not kandidati:
        kandidati = vsetky

    out = []
    for att, nazov in kandidati[:4]:
        try:
            data = _stiahni(f"{BASE}/data/att/{att}")
        except Exception as e:
            out.append(Vysledok(zmluva_id, att, nazov[:60], "", 0, 0, 0, 0, 0.0,
                                f"CHYBA:{type(e).__name__}"))
            continue

        ext = att.rsplit(".", 1)[-1]
        if ext == "pdf":
            znakov, tskp, riadky, podiel, verdikt = analyzuj_pdf(data)
        elif ext in ("xlsx", "xls"):
            znakov, tskp, riadky, podiel, verdikt = analyzuj_xlsx(data)
        else:
            znakov, tskp, riadky, podiel, verdikt = 0, 0, 0, 0.0, "INE"

        out.append(Vysledok(zmluva_id, att, nazov[:60], ext, len(data),
                            znakov, tskp, riadky, podiel, verdikt))
        time.sleep(0.6)   # slusny odstup, CRZ nie je nase CDN
    return out


def vzorka_zmluv(sb, pocet):
    """Nahodna vzorka stavebnych zmluv z nasej databazy."""
    r = (sb.table("contracts")
           .select("id")
           .in_("sector", SEKTORY_STAVBA)
           .gte("price_total", 50000)      # male zmluvy rozpocet nemavaju
           .order("signed_on", desc=True)
           .limit(pocet * 4)
           .execute())
    ids = [str(x["id"]) for x in (r.data or [])]
    random.shuffle(ids)
    return ids[:pocet]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pocet", type=int, default=250)
    args = ap.parse_args()

    sb = store.klient()
    ids = vzorka_zmluv(sb, args.pocet)
    if not ids:
        print("::error::V databaze nie su stavebne zmluvy. Dobehol bootstrap?")
        return 1
    log.info("Vzorka: %s zmluv", len(ids))

    vsetko = []
    for n, zid in enumerate(ids, 1):
        vsetko.extend(spracuj(zid))
        if n % 25 == 0:
            log.info("  %s/%s zmluv, %s priloh", n, len(ids), len(vsetko))

    with open("probe_results.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[x.name for x in fields(Vysledok)])
        w.writeheader()
        for v in vsetko:
            w.writerow(asdict(v))

    # ── SUHRN ─────────────────────────────────────────────────────────────
    poc = {}
    for v in vsetko:
        k = v.verdikt.split(":")[0]
        poc[k] = poc.get(k, 0) + 1
    celkom = len(vsetko) or 1

    print("\n" + "=" * 58)
    print(f"{'verdikt':<16}{'priloh':>8}{'podiel':>10}")
    print("-" * 58)
    for k in sorted(poc, key=lambda x: -poc[x]):
        print(f"{k:<16}{poc[k]:>8}{poc[k]/celkom*100:>9.1f}%")

    ok_zmluvy = {v.zmluva_id for v in vsetko if v.verdikt == "POUZITELNE"}
    n1 = len(ok_zmluvy) / len(ids) * 100
    pouzitelne = [v for v in vsetko if v.verdikt == "POUZITELNE"]
    n3 = (sum(v.podiel_riadkov_s_tskp for v in pouzitelne) / len(pouzitelne) * 100
          if pouzitelne else 0)

    print("-" * 58)
    print(f"N1  zmluv s pouzitelnym vykazom : {len(ok_zmluvy)}/{len(ids)}  ({n1:.0f} %)")
    print(f"N3  priemerny podiel riadkov s TSKP : {n3:.0f} %")
    print("=" * 58)

    if n1 > 30:
        verdikt = "IDE SA. Pokrytie nad 30 %, plna verzia ma zmysel."
    elif n1 >= 10:
        verdikt = "IDE SA OPATRNE. Pokrytie 10-30 %, len na velke zakazky."
    else:
        verdikt = "ZASTAV. Pokrytie pod 10 %, napad na CRZ prilohach nefunguje."
    print(f"\nVERDIKT: {verdikt}")
    print(f"::notice::N1={n1:.0f}% N3={n3:.0f}% priloh={celkom} {verdikt}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
