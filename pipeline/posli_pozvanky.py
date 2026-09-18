"""Posle e-mailom cakajuce Team pozvanky (tabulka invitations).

Spustenie:
    python posli_pozvanky.py                # naozaj posle
    python posli_pozvanky.py --nasucho      # nic neposle, len vypise co by poslal

Potrebne premenne:
    SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY   — ako zvysok pipeline
    RESEND_API_KEY                            — rovnaky kluc ako posli_email.py

CO TO ROBI
  Owner v app.html zavola RPC pozvi_clena(email), ktora zapise riadok do
  invitations (stav='cakajuca', sent_at=null). Tento skript pravidelne
  (cron kazdych ~15 minut, .github/workflows/pozvanky.yml) najde take
  riadky, posle e-mail cez Resend a zapise sent_at.

PRECO NEPOSIELAME SUPABASE MAGIC-LINK PRIAMO Z TOHTO SKRIPTU
  Pozvanka len OZNAMI a odkazuje na uz existujuci
  prihlasenie.html?pozvanka=<token> — pozvany tam prejde PRESNE tym istym
  signInWithOtp() flow ako pri beznom prihlaseni. Ziadna admin-API cesta
  do auth systemu navyse, viz komentar v supabase/26_team_pozvanky.sql.

CO SA NEPOSIELA
  Pozvanky bez platneho org_id/email (mal by byt nemozny stav vdaka FK a
  RPC validacii, ale skript to preskakuje ticho, nie padne) a pozvanky,
  ktore uz medzitym vypršali (expires_at < now) — tie len oznaci ako
  'vyprsana' a ide dalej.
"""
import argparse
import logging
import os
import sys
from datetime import datetime, timezone

from supabase import create_client

# Rovnaky obal a odosielacia funkcia ako tyzdenny e-mail — rovnaky vzhlad,
# rovnake escapovanie, rovnaka bezpecnostna kontrola (odkaz musi viest na
# predtendrom.sk). Skripty su sesterske subory v tom istom priecinku,
# import teda funguje bez balicka.
from posli_email import _bezpecne, _obal, posli, RESEND_URL, ODOSIELATEL  # noqa: F401

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)-7s %(name)-9s %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("pozvanky")

ODKAZ_PRIHLASENIE = "https://predtendrom.sk/prihlasenie.html"


def _pozvanka_html(nazov_firmy: str, token: str) -> str:
    """Obsah je zamerne kratky — jedna vec na spravenie, jedno tlacidlo.
    _obal() escapuje nazov_firmy aj tak, ale posiela sa uz orezany a z
    dovereneho zdroja (organizations.nazov, nie cudzi CRZ text)."""
    return _obal(
        titulok="Pozvánka do tímu",
        uvod=(f"Boli ste pozvaní do organizácie „{nazov_firmy}“ na "
              f"PredTendrom.sk. Kliknutím na tlačidlo nižšie sa prihlásite "
              f"(alebo si vytvoríte prístup, ak ešte účet nemáte) a "
              f"pripojíte sa k tímu."),
        bloky=[{
            "titul": nazov_firmy,
            "popis": ("Po prihlásení uvidíte presne to isté, čo zvyšok "
                      "tímu — spoločné sledované firmy aj nastavenia "
                      "odberu."),
        }],
        cta_text="Prijať pozvánku",
        cta_url=f"{ODKAZ_PRIHLASENIE}?pozvanka={token}",
        odhlasenie=("Túto pozvánku ste nečakali? Pokojne ju ignorujte, "
                    "nič sa nestane."),
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nasucho", action="store_true",
                    help="nic neposle, len vypise co by poslal")
    args = ap.parse_args()

    url = os.getenv("SUPABASE_URL")
    servis = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    kluc = os.getenv("RESEND_API_KEY")
    if not (url and servis):
        log.error("Chyba SUPABASE_URL alebo SUPABASE_SERVICE_ROLE_KEY.")
        return 1
    if not kluc and not args.nasucho:
        log.error("Chyba RESEND_API_KEY. Pridaj ho do GitHub Secrets, "
                  "alebo spusti s --nasucho.")
        return 1

    sb = create_client(url, servis)
    teraz = datetime.now(timezone.utc)

    try:
        cakajuce = (sb.table("invitations")
                      .select("id, org_id, email, token, expires_at, "
                              "organizations(nazov)")
                      .eq("stav", "cakajuca")
                      .is_("sent_at", "null")
                      .execute().data or [])
    except Exception as e:
        log.error("Nepodarilo sa nacitat cakajuce pozvanky: %s", e)
        return 1

    log.info("Cakajucich pozvaniek na odoslanie: %s%s",
             len(cakajuce), "  [NASUCHO]" if args.nasucho else "")
    if not cakajuce:
        return 0

    poslane = vyprsane = zlyhane = 0
    for inv in cakajuce:
        email = (inv.get("email") or "").strip()
        token = inv.get("token")
        if not email or "@" not in email or not token:
            zlyhane += 1
            continue

        expires_at = inv.get("expires_at")
        if expires_at and expires_at < teraz.isoformat():
            log.info("%s: pozvanka uz vyprsala, oznacujem", email)
            if not args.nasucho:
                try:
                    sb.table("invitations").update(
                        {"stav": "vyprsana"}
                    ).eq("id", inv["id"]).execute()
                except Exception as e:
                    log.warning("%s: vyprsana sa nepodarilo zapisat (%s)", email, e)
            vyprsane += 1
            continue

        nazov_firmy = ((inv.get("organizations") or {}).get("nazov")
                       or "vášho tímu")
        html = _pozvanka_html(nazov_firmy, token)
        predmet = f"Pozvánka do tímu {nazov_firmy} — PredTendrom.sk"

        if posli(kluc, email, predmet, html, args.nasucho):
            poslane += 1
            if not args.nasucho:
                try:
                    sb.table("invitations").update(
                        {"sent_at": datetime.now(timezone.utc).isoformat()}
                    ).eq("id", inv["id"]).execute()
                except Exception as e:
                    # Horsie ako neoznacit sent_at je poslat to iste znova
                    # o 15 minut, ale zhodit beh kvoli tomu nema zmysel —
                    # dalsi beh to skusi zapisat znova.
                    log.warning("%s: sent_at sa nezapisal (%s)", email, e)
        else:
            zlyhane += 1

    log.info("Hotovo: poslanych %s, vyprsanych %s, zlyhanych %s",
             poslane, vyprsane, zlyhane)
    if zlyhane and not poslane:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
