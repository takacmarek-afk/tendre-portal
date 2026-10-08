"""Naplni tabulku public.obce_register (migracia 73) vsetkymi obcami SR.

Zdroj: pipeline/data/register_obce_raw.json + register_nuts4_raw.json
(Statisticky urad SR) - rovnake subory ako register_obci.py. Kod obce
"SK" + 4-znakovy okres + 6 cifier urcuje okres aj kraj, nic sa neuhaduje.

    python obce_register.py             # zapise do databazy
    python obce_register.py --nasucho   # len vypise pocet a vzorku

Zapis je upsert podla `kod`, takze sa da pustit opakovane. Premenne:
SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY (vid .github/workflows/obce-register.yml).
"""
import argparse
import json
import logging
import os
import sys
from pathlib import Path

from register_obci import _DATA, _KOD

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)-7s %(name)-9s %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("obce_reg")


def zostav_riadky(cesta_nuts4=None, cesta_obce=None) -> list:
    """Vrati [{kod, nazov, kraj, okres}, ...] pre vsetky obce s platnym kodom.

    Agregaty ("SK_CAP", "SK0422_0425") a obce bez znameho kraja sa preskocia.
    """
    cesta_nuts4 = Path(cesta_nuts4) if cesta_nuts4 else _DATA / "register_nuts4_raw.json"
    cesta_obce = Path(cesta_obce) if cesta_obce else _DATA / "register_obce_raw.json"
    nuts4 = json.loads(cesta_nuts4.read_text(encoding="utf-8"))["category"]["label"]
    obce = json.loads(cesta_obce.read_text(encoding="utf-8"))["category"]["label"]
    riadky = []
    for kod, nazov in obce.items():
        m = _KOD.match(kod)
        if not m:
            continue
        okres_kod = "SK" + m.group(1)
        kraj = nuts4.get(okres_kod[:5])
        if not kraj or not str(nazov).strip():
            continue
        riadky.append({"kod": kod, "nazov": str(nazov).strip(),
                       "kraj": kraj, "okres": nuts4.get(okres_kod)})
    return riadky


def zapis(sb, riadky: list, davka: int = 500) -> int:
    for i in range(0, len(riadky), davka):
        sb.table("obce_register").upsert(riadky[i:i + davka], on_conflict="kod").execute()
    return len(riadky)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--nasucho", action="store_true")
    args = ap.parse_args(argv)
    riadky = zostav_riadky()
    if not riadky:
        log.error("Register obci je prazdny - chybaju subory v pipeline/data?")
        return 1
    log.info("Pripravenych obci: %d (napr. %s)", len(riadky), riadky[0])
    if args.nasucho:
        log.info("Nasucho - nic sa nezapisuje.")
        return 0
    url = os.environ.get("SUPABASE_URL")
    kluc = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not kluc:
        log.error("Chyba SUPABASE_URL alebo SUPABASE_SERVICE_ROLE_KEY.")
        return 2
    from supabase import create_client
    log.info("Zapisanych obci: %d", zapis(create_client(url, kluc), riadky))
    return 0


if __name__ == "__main__":
    sys.exit(main())
