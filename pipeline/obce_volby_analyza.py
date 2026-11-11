"""Analyza pred kampanou pre obce (11. 11. 2026). LEN CITANIE, nic nezapise.

1. Stiahne zvolenych starostov 2022 a 2026 (SU SR, volby.py) a pre kazdu obec
   urci: novy starosta / staronovy (ta ista osoba) / bez vysledku 2026.
2. Spoji to s kontaktmi kampane (kampan_obce_kontakty) a s udajmi, ktore
   kampan v e-maili pouzije (poradca, konciaca zakazka z Vestnika, konciaca
   zmluva z CRZ, dotacia) - rovnako ako kampan_obce.zostav.
3. Vypise len SUHRNNE POCTY (logy su verejne), ziadne mena ani adresy.

    python obce_volby_analyza.py
"""
import logging
import sys
from collections import Counter, defaultdict
from datetime import date

import requests

from kampan_obce import SEGMENTY, _vsetky, ico_kluc, nacitaj_data
from volby import TABULKY, _norm, rozober, stiahni

log = logging.getLogger("obce_volby_analyza")


def starostovia(sess, rok):
    out = {}
    for tab in TABULKY:
        url, text = stiahni(sess, rok, tab)
        if text is None:
            log.warning("%s: 404", url)
            continue
        for r in rozober(text, rok, url):
            out.setdefault(r["kod_obce"], r)
    return out


def osoba(r):
    return (_norm(r.get("meno")), _norm(r.get("priezvisko")))


def typ_starostu(kod, s22, s26):
    if kod not in s26:
        return "bez_vysledku_2026"
    if kod not in s22:
        return "novy"            # obec bez volieb 2022 alebo novy kod
    return "staronovy" if osoba(s22[kod]) == osoba(s26[kod]) else "novy"


def segment(d):
    for s in SEGMENTY:
        if d.get(s):
            return s
    return None


def tab(nadpis, pocty, riadky, stlpce):
    print(f"\n== {nadpis}")
    print(f"{'':28s}" + "".join(f"{c:>12s}" for c in stlpce) + f"{'spolu':>10s}")
    for r in riadky:
        hod = [pocty.get((r, c), 0) for c in stlpce]
        print(f"{str(r)[:28]:28s}" + "".join(f"{h:12d}" for h in hod) + f"{sum(hod):10d}")
    sucty = [sum(pocty.get((r, c), 0) for r in riadky) for c in stlpce]
    print(f"{'spolu':28s}" + "".join(f"{h:12d}" for h in sucty) + f"{sum(sucty):10d}")


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from config import USER_AGENT
    sess = requests.Session()
    sess.headers["User-Agent"] = USER_AGENT
    s22, s26 = starostovia(sess, 2022), starostovia(sess, 2026)
    print(f"Zvoleni starostovia/primatori: 2022 = {len(s22)}, 2026 = {len(s26)}")
    if not s26:
        print("Vysledky 2026 este nie su zverejnene.")
        return 1

    vsetky = set(s22) | set(s26)
    typy = Counter(typ_starostu(k, s22, s26) for k in vsetky)
    print("Vsetky obce podla starostu:", dict(typy))
    po_krajoch = Counter()
    for k in vsetky:
        kraj = (s26.get(k) or s22.get(k) or {}).get("kraj") or "?"
        po_krajoch[(kraj, typ_starostu(k, s22, s26))] += 1
    kraje = sorted({k for k, _ in po_krajoch})
    stlpce_typ = ["novy", "staronovy", "bez_vysledku_2026"]
    tab("Vsetky obce SR: kraj x starosta", po_krajoch, kraje, stlpce_typ)

    from store import klient
    sb = klient()
    kontakty = _vsetky(sb, "kampan_obce_kontakty", "ico,kraj,kod_obce,stav,odhlasene_at")
    ucty = {ico_kluc(r["ico"]) for r in _vsetky(sb, "obce_ucty", "ico") if r.get("ico")}
    print(f"\nKontakty kampane: {len(kontakty)}; podla stavu:",
          dict(Counter(k["stav"] for k in kontakty)),
          f"; bez kodu obce: {sum(1 for k in kontakty if not k.get('kod_obce'))}",
          f"; odhlasene: {sum(1 for k in kontakty if k.get('odhlasene_at'))}",
          f"; uz maju ucet: {sum(1 for k in kontakty if ico_kluc(k['ico']) in ucty)}")

    pouzitelne = [k for k in kontakty if k["stav"] in ("ok", "na_kontrolu") and not k.get("odhlasene_at")
                  and ico_kluc(k["ico"]) not in ucty]
    data = nacitaj_data(sb, [k["ico"] for k in pouzitelne], date.today())

    seg_typ, stav_typ, kraj_ok, druhy = Counter(), Counter(), Counter(), Counter()
    for k in pouzitelne:
        kod = k.get("kod_obce")
        t = typ_starostu(kod, s22, s26) if kod else "nezname_meno"
        d = data.get(k["ico"], {})
        seg = segment(d) or "nic_konkretne"
        stav_typ[(k["stav"], t)] += 1
        if k["stav"] == "ok":
            seg_typ[(seg, t)] += 1
            if seg != "nic_konkretne":
                kraj_ok[(k.get("kraj") or "?", t)] += 1
            for s in SEGMENTY:
                if d.get(s):
                    druhy[(s, t)] += 1
    stlpce = ["novy", "staronovy", "bez_vysledku_2026", "nezname_meno"]
    tab("Kontakty (bez odhlasenych a uctov): stav adresy x starosta", stav_typ, ["ok", "na_kontrolu"], stlpce)
    tab("Adresa ok: hlavny dovod e-mailu (segment) x starosta", seg_typ,
        list(SEGMENTY) + ["nic_konkretne"], stlpce)
    tab("Adresa ok: obce, ktore maju dany udaj (aj viac naraz)", druhy, list(SEGMENTY), stlpce)
    tab("Vlna 1 (adresa ok + konkretny obsah): kraj x starosta", kraj_ok,
        sorted({k for k, _ in kraj_ok}), stlpce)

    vlna1 = sum(v for (s, _), v in seg_typ.items() if s != "nic_konkretne")
    print(f"\nVLNA 1 dnes: {vlna1} obci (adresa ok, nie odhlasene, bez uctu, s konkretnym obsahom).")
    print(f"Na kontrolu este: {sum(v for (s, _), v in stav_typ.items() if s == 'na_kontrolu')} obci.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
