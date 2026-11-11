"""E-maily obci z ich webov -> kontakty kampane (11. 11. 2026).

Vstup: tabulka obce_web_kontakty (migracia 102), naplnena z Marekovej extrakcie
(Wikidata -> web obce -> uradny e-mail).

1. IČO obce: kampan je postavena na IČO (dotacie, Vestnik, CRZ, odhlasenie).
   Extrakcia ma len kod obce SU SR, preto IČO dohladame z nasich dat: nazvy
   obci v Vestniku, CRZ (dotacie aj zmluvy) -> kod obce (kampan_obce.kod_obce).
   Pri nejednoznacnosti (viac IČO pre jeden kod) obec preskocime.
2. Adresa sa posudi pravidlami kampane (posud_email). Navyse sa prijme adresa
   na tej istej domene ako web obce, ak nevyzera osobne. Vyradime riadky
   s poznamkou "pozor" a adresy, ktore ma viac obci naraz.
3. Zapis: nova obec -> novy kontakt (zdroj 'web'); obec s adresou 'na_kontrolu'
   -> nahradi sa uradnou z webu; obec s 'ok' adresou z Vestnika ostava.

    python obce_web_kontakty.py --nasucho
    python obce_web_kontakty.py

Logy su verejne: len pocty.
"""
import argparse
import logging
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from urllib.parse import urlparse

from kampan_obce import _vsetky, ico_kluc, je_obec, kod_obce, nacitaj_register, posud_email

log = logging.getLogger("obce_web_kontakty")


def domena(url):
    try:
        h = urlparse(url if "://" in url else "http://" + url).hostname or ""
    except ValueError:
        return ""
    return h.lower().removeprefix("www.")


def posud(email, obec, web):
    """-> (stav, dovod) pre adresu z webu obce."""
    email = (email or "").strip().lower()
    stav, dovod = posud_email(email, "Obec " + obec)
    if stav == "ok" or stav == "vylucene":
        return stav, dovod
    ed, wd = email.split("@")[-1], domena(web or "")
    if wd and (ed == wd or ed.endswith("." + wd)) and dovod != "vyzera ako osobna adresa":
        return "ok", "adresa na domene webu obce"
    return stav, dovod


def mapa_ico(zdroje, register, kraje):
    """zdroje: [(nazov, ico, kraj)] -> {kod_obce: ico}, len jednoznacne."""
    hlasy = defaultdict(Counter)
    for nazov, ico, kraj in zdroje:
        if not ico or not nazov or not je_obec(nazov):
            continue
        kod = kod_obce(nazov, kraj, register)
        if kod:
            hlasy[kod][ico_kluc(ico)] += 1
    out = {}
    for kod, c in hlasy.items():
        (ico, n), *dalsie = c.most_common()
        if not dalsie or n >= 3 * dalsie[0][1]:      # jasna vacsina
            out[kod] = ico.zfill(8)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--nasucho", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    from store import klient
    sb = klient()
    register, kraje = nacitaj_register()

    web = _vsetky(sb, "obce_web_kontakty", "kod_obce,obec,okres,email,web,zdroj_url,poznamka")
    kontakty = {r["ico"]: r for r in _vsetky(sb, "kampan_obce_kontakty", "ico,kod_obce,stav,zdroj")}
    log.info("Extrakcia: %d obci, s e-mailom %d; kontaktov kampane %d.",
             len(web), sum(1 for w in web if w.get("email")), len(kontakty))

    zdroje = []
    kod_z_kontaktov = {k["kod_obce"]: ico for ico, k in kontakty.items() if k.get("kod_obce")}
    for t, n, i, nuts in (("uvo_vysledky", "obstaravatel_nazov", "obstaravatel_ico", "nuts"),
                          ("uvo_vyzvy", "obstaravatel_nazov", "obstaravatel_ico", "nuts")):
        for r in _vsetky(sb, t, f"{n},{i},{nuts}", lambda q: q.ilike(n, "obec %")):
            zdroje.append((r[n], r[i], kraje.get((r.get(nuts) or "")[:5])))
        for r in _vsetky(sb, t, f"{n},{i},{nuts}", lambda q: q.ilike(n, "mesto %")):
            zdroje.append((r[n], r[i], kraje.get((r.get(nuts) or "")[:5])))
    for r in _vsetky(sb, "subsidies", "prijimatel,prijimatel_ico"):
        zdroje.append((r["prijimatel"], r["prijimatel_ico"], None))
    for pref in ("Obec %", "Mesto %"):
        for r in _vsetky(sb, "opportunities", "authority_name,authority_cin",
                         lambda q: q.ilike("authority_name", pref)):
            zdroje.append((r["authority_name"], r["authority_cin"], None))
    ico_podla_kodu = {**mapa_ico(zdroje, register, kraje), **kod_z_kontaktov}
    log.info("IČO dohladane pre %d kodov obci.", len(ico_podla_kodu))

    pocet_email = Counter((w.get("email") or "").strip().lower() for w in web if w.get("email"))
    pocty = Counter()
    vlozit, nahradit = [], []
    teraz = datetime.now(timezone.utc).isoformat()
    for w in web:
        email = (w.get("email") or "").strip().lower()
        if not email:
            pocty["bez e-mailu"] += 1
            continue
        if (w.get("poznamka") or "").startswith("pozor"):
            pocty["vyradene: pozor (rovnaky web ako ina obec)"] += 1
            continue
        if pocet_email[email] > 1:
            pocty["vyradene: rovnaka adresa pri viacerych obciach"] += 1
            continue
        stav, dovod = posud(email, w["obec"], w.get("web"))
        if stav != "ok":
            pocty[f"vyradene: {dovod}"] += 1
            continue
        ico = ico_podla_kodu.get(w["kod_obce"])
        if not ico:
            pocty["ok, ale bez IČO (nevieme spojit s datami)"] += 1
            continue
        k = kontakty.get(ico) or kontakty.get(ico.lstrip("0"))
        zaznam = {"email": email, "stav": "ok", "dovod": dovod, "zdroj": "web",
                  "zdroj_url": w.get("zdroj_url") or w.get("web"), "zdroj_datum": date.today().isoformat(),
                  "kod_obce": w["kod_obce"]}
        if not k:
            vlozit.append({"ico": ico, "obec": "Obec " + w["obec"] if not w["obec"].lower().startswith(("obec", "mesto")) else w["obec"],
                           "kraj": None, **zaznam})
            pocty["nova obec v kampani"] += 1
        elif k["stav"] == "ok":
            pocty["uz mame uradnu adresu (ostava)"] += 1
        elif k["stav"] == "vylucene":
            pocty["rucne vylucena (ostava)"] += 1
        else:
            nahradit.append((k["ico"], {**zaznam, "upravene_at": teraz}))
            pocty["nahradi adresu na kontrolu"] += 1
    for kluc, n in sorted(pocty.items(), key=lambda x: -x[1]):
        log.info("  %-50s %5d", kluc, n)

    # kraj noveho kontaktu z registra (kod obce -> kraj)
    kraj_kodu = {kod: kr for zoz in register.values() for kod, kr in zoz}
    for v in vlozit:
        v["kraj"] = kraj_kodu.get(v["kod_obce"])
    if a.nasucho:
        log.info("NASUCHO — nic nezapisane. Vlozit %d, nahradit %d.", len(vlozit), len(nahradit))
        return 0
    for i in range(0, len(vlozit), 500):
        sb.table("kampan_obce_kontakty").insert(vlozit[i:i + 500]).execute()
    for ico, z in nahradit:
        sb.table("kampan_obce_kontakty").update(z).eq("ico", ico).execute()
    log.info("Zapisane: %d novych, %d nahradenych.", len(vlozit), len(nahradit))
    return 0


if __name__ == "__main__":
    sys.exit(main())
