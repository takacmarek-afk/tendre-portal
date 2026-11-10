"""Audit (len citanie, 10. 11. 2026): ktorym firmam odisiel studeny e-mail
o odbore, v ktorom nepodnikaju, a ci pre ne mame spravny odbor s datami.

Vypisuje len IČO, verejny nazov firmy, odbory a pocty. Ziadne e-maily.
"""
import logging
import os
import sys
from collections import Counter
from datetime import date, timedelta

from supabase import create_client

import oslovenie_firiem as of
from strankuj import vsetky

log = logging.getLogger("oprava_audit")


def rozdelenie(sb, ico, od):
    cin = [of.ico8(ico), of.ico8(ico).lstrip("0")]
    r = vsetky(lambda a, b: sb.table("contracts").select("sector").in_("supplier_cin", cin)
               .gte("signed_on", od).order("id").range(a, b).execute())
    return Counter(x.get("sector") for x in r)


def najlepsi(c):
    spolu = sum(c.values())
    for s, n in c.most_common():
        if s and s != "INE" and n >= of.ODBOR_MIN_ZMLUV and n / spolu >= of.ODBOR_MIN_PODIEL:
            return s
    return None


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
    dnes = date.today()
    od5 = (dnes - timedelta(days=1826)).isoformat()
    rok = (dnes + timedelta(days=365)).isoformat()
    odosl = vsetky(lambda a, b: sb.table("oslovenie_firiem_odoslane").select("ico,krok,predmet,stav")
                   .eq("stav", "odoslane").order("id").range(a, b).execute())
    kont = {k["ico"]: k for k in vsetky(lambda a, b: sb.table("oslovenie_firiem_kontakty")
                                         .select("ico,nazov,segment,kraj,stav").order("ico").range(a, b).execute())}
    eu = of.nacitaj_eurofondy(sb, dnes)
    podla = {}
    for o in odosl:
        podla.setdefault(o["ico"], []).append(o)
    vysledok = Counter()
    riadky = []
    for ico, oo in sorted(podla.items()):
        k = kont.get(ico) or {}
        obrana = any(o["krok"] == 1 and (o["predmet"] or "").startswith(("Vaša zmluva", "Kedy ")) for o in oo)
        seg = k.get("segment")
        c = rozdelenie(sb, ico, od5)
        spolu = sum(c.values())
        sedi = (not spolu) or (c.get(seg, 0) >= of.ODBOR_MIN_ZMLUV and c.get(seg, 0) / spolu >= of.ODBOR_MIN_PODIEL)
        if sedi:
            vysledok["odbor sedi"] += 1
            continue
        if obrana and len(oo) == 1:
            vysledok["len obrana (vlastna zmluva), bez chyby"] += 1
            continue
        novy = najlepsi(c)
        n_konc = n_eu = 0
        if novy and k.get("kraj"):
            n_konc = (sb.table("opportunities").select("contract_id", count="exact").eq("sector", novy)
                      .eq("kraj", k["kraj"]).lte("effective_to", rok).limit(1).execute().count or 0)
            n_eu = (eu.get((novy, k["kraj"])) or (0,))[0]
        stav = k.get("stav")
        if stav != "ok":
            kat = f"zle zaradena, kontakt '{stav}' (nepisat)"
        elif not novy:
            kat = "zle zaradena, spravny odbor nejasny (nepisat)"
        elif n_konc + n_eu < 3:
            kat = "zle zaradena, v spravnom odbore malo dat"
        else:
            kat = "KANDIDAT na opravny e-mail"
        vysledok[kat] += 1
        top = ", ".join(f"{s}:{n}" for s, n in c.most_common(3))
        riadky.append(f"{kat[:22]:22} | {ico} {(k.get('nazov') or '')[:40]:40} | {seg} -> {novy} | "
                      f"{k.get('kraj')} | konciace {n_konc}, eurofondy {n_eu} | kroky {sorted(o['krok'] for o in oo)} | CRZ {top}")
    log.info("Firiem s odoslanym e-mailom: %d", len(podla))
    for kat, n in vysledok.most_common():
        log.info("  %-50s %d", kat, n)
    log.info("")
    for r in riadky:
        log.info(r)
    return 0


if __name__ == "__main__":
    sys.exit(main())
