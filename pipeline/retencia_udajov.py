"""Retencia udajov (vlna 85, migracia 71): tyzdenne mazanie starych zaznamov.

Spusta ho workflow .github/workflows/retencia.yml (nedelne rano) cez
service_role. Zavola RPC public.retencia_udajov() a vypise pocty zmazanych
riadkov. Nic dalsie nerobi.

    python retencia_udajov.py             # naozaj zmaze
    python retencia_udajov.py --nasucho   # nic nezmaze, len ohlasi, co by sa volalo

Premenne: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY.
"""
import argparse
import logging
import os
import sys

from supabase import create_client

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)-7s %(name)-9s %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("retencia")


def spusti(sb, nasucho: bool = False) -> dict:
    if nasucho:
        log.info("Nasucho: volal by sa public.retencia_udajov(), nic sa nemaze.")
        return {}
    res = sb.rpc("retencia_udajov").execute()
    data = res.data or {}
    for kluc, pocet in sorted(data.items()):
        log.info("%-26s zmazanych: %s", kluc, pocet)
    return data


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--nasucho", action="store_true")
    args = ap.parse_args(argv)
    url = os.environ.get("SUPABASE_URL")
    kluc = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not kluc:
        log.error("Chyba SUPABASE_URL alebo SUPABASE_SERVICE_ROLE_KEY.")
        return 2
    spusti(create_client(url, kluc), args.nasucho)
    return 0


if __name__ == "__main__":
    sys.exit(main())
