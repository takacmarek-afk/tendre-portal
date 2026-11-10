"""Dopocita sektor a kraj obstaravaniam z eurofondov (tabulka itms_vo, migracia 97).

sektor: rovnaka klasifikacia nazvu ako pri zmluvach z CRZ (classify.klasifikuj).
kraj:   obec sidla obstaravatela -> znamy okres/mesto (regiony), inak register
        obci (jednoznacny nazov), inak nazov obstaravatela ("Mesto Presov").
Do logu len pocty.
"""
import logging
import os
import sys
from collections import Counter, defaultdict

import classify
import regiony
from classify import SEKTOR_DOTACIE
from strankuj import vsetky

log = logging.getLogger("itms")


def kraj_pre(obec, nazov, obce_mapa):
    k = regiony._hladaj(obec or "")[1] if obec else None
    if k:
        return k
    if obec:
        kraje = obce_mapa.get(regiony._norm(obec))
        if kraje and len(kraje) == 1:
            return next(iter(kraje))
    return regiony.z_nazvu(nazov)[1]


def sektor_pre(nazov):
    s, _ = classify.klasifikuj(nazov, None)
    return None if s == SEKTOR_DOTACIE else s


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    from supabase import create_client
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
    obce_mapa = defaultdict(set)
    for o in vsetky(lambda a, b: sb.table("obce_register").select("nazov,kraj").order("kod").range(a, b).execute()):
        obce_mapa[regiony._norm(o["nazov"])].add(o["kraj"])
    riadky = vsetky(lambda a, b: sb.table("itms_vo")
                    .select("id,nazov,obstaravatel_nazov,obstaravatel_obec,sektor,kraj,stav")
                    .order("id").range(a, b).execute())
    zmeny = []
    for r in riadky:
        s = r.get("sektor") or sektor_pre(r.get("nazov"))
        k = r.get("kraj") or kraj_pre(r.get("obstaravatel_obec"), r.get("obstaravatel_nazov"), obce_mapa)
        if s != r.get("sektor") or k != r.get("kraj"):
            zmeny.append({"id": r["id"], "sektor": s, "kraj": k})
    # upsert len troch stlpcov: PostgREST pri konflikte prepise len ich
    for i in range(0, len(zmeny), 500):
        sb.table("itms_vo").upsert(zmeny[i:i + 500], on_conflict="id").execute()
    prip = [r for r in riadky if r.get("stav") == "Pripravované"]
    hotove = {z["id"]: z for z in zmeny}
    sek = Counter((hotove.get(r["id"], r).get("sektor")) for r in prip)
    kr = Counter((hotove.get(r["id"], r).get("kraj")) for r in prip)
    suhrn = [f"Riadkov {len(riadky)}, zmenenych {len(zmeny)}; pripravovanych {len(prip)}",
             "Pripravovane podla sektora: " + ", ".join(f"{k} {v}" for k, v in sek.most_common(18)),
             "Pripravovane podla kraja: " + ", ".join(f"{k} {v}" for k, v in kr.most_common(10))]
    print("\n".join(suhrn))
    print("::notice title=ITMS::" + "%0A".join(suhrn))
    return 0


if __name__ == "__main__":
    sys.exit(main())
