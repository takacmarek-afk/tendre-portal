"""Potvrdzovaci e-mail (double opt-in) pre odber prehladov pre obce.

Audit 5.10.2026, V1 + migracia supabase/63_audit_5_10_bezpecnost.sql, oddiel 4:
novy riadok v odber_obce je potvrdeny=false a ma `token`. Tyzdenny e-mail
(posli_email.py) a alerty (alerty.py) citaju len potvrdeny=true, takze
adresa dostane prehlady az po kliknuti na odkaz z TOHTO e-mailu.

CO SA POSIELA
  Kazdemu riadku odber_obce, ktory ma:
    - potvrdeny = false,
    - potvrdzovaci_email_at IS NULL (este nedostal potvrdzovaci e-mail),
    - created_at mladsie nez 3 dni (starsie neposielame — clovek uz davno
      zabudol a e-mail by posobil ako spam),
  najviac MAX_NA_BEH (200) e-mailov na jeden beh (najstarsie prve).
  Po USPESNOM odoslani sa nastavi potvrdzovaci_email_at = now(). Pri chybe
  odoslania sa riadok neoznaci a zopakuje sa pri dalsom behu (az kym nie je
  riadok starsi nez 3 dni).

ODKAZ
  https://predtendrom.sk/odber-obce?t=<token>&akcia=potvrdit
  (stranka odber-obce vola RPC potvrd_odber_obce(token)).

Netyka sa adries v tabulke kampan_obce (kampan starostom) — tie maju
vlastny tok a vlastne odhlasovanie.

Spustenie:
    python posli_potvrdenie_odberu.py                # naozaj posle
    python posli_potvrdenie_odberu.py --nasucho      # nic neposle, len vypise
    python posli_potvrdenie_odberu.py --komu ja@x.sk # posle len na tuto adresu (test)

Potrebne premenne (rovnake ako posli_email.py, ziadne nove):
    SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, RESEND_API_KEY

PRVE SPUSTENIE VZDY NASUCHO.
"""
import argparse
import logging
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone

from supabase import create_client

from posli_email import (ODOSIELATEL, PAUZA_S, _obal, posli,  # noqa: F401
                         odkaz_odberu_obce)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)-7s %(name)-9s %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("potvrdenie-odberu")

EMAIL_RE = re.compile(r"[^@\s,;<>\"]+@[^@\s,;<>\"]+\.[A-Za-z]{2,}")

MAX_NA_BEH = 200       # najviac tolko e-mailov na jeden beh
MAX_VEK_DNI = 3        # starsie riadky uz nepotvrdzujeme

PREDMET = "Potvrďte odber prehľadov pre obce — PredTendrom.sk"


def _platny_email(e) -> bool:
    return bool(e) and bool(EMAIL_RE.fullmatch(str(e).strip()))


def _odkaz(token) -> "str | None":
    return odkaz_odberu_obce(token, "potvrdit")


def _obsah(odkaz) -> dict:
    return {
        "titulok": "Potvrďte odber prehľadov pre obce",
        "uvod": ("Dobrý deň, niekto (pravdepodobne Vy) zadal túto adresu na "
                 "predtendrom.sk/obce, aby dostával prehľad, aké peniaze môže "
                 "obec získať. Ak ste to boli Vy, potvrďte odber kliknutím "
                 "na tlačidlo nižšie."),
        "bloky": [],
        "cta_text": "Potvrdiť odber",
        "cta_url": odkaz,
        "odhlasenie": ("Ak ste to nezadali Vy, nič nerobte — e-maily Vám "
                       "posielať nebudeme."),
    }


def _text(odkaz) -> str:
    """Textova (plain) verzia e-mailu."""
    return ("Dobrý deň,\n\n"
            "niekto (pravdepodobne Vy) zadal túto adresu na "
            "predtendrom.sk/obce, aby dostával prehľad, aké peniaze môže obec "
            "získať.\n\n"
            f"Ak ste to boli Vy, potvrďte odber: {odkaz}\n\n"
            "Ak nie, nič nerobte — e-maily Vám posielať nebudeme.\n\n"
            "PredTendrom.sk\n")


def vyber_riadky(sb, teraz, limit=MAX_NA_BEH) -> list:
    """Riadky odber_obce, ktorym treba poslat potvrdzovaci e-mail."""
    hranica = (teraz - timedelta(days=MAX_VEK_DNI)).isoformat()
    return (sb.table("odber_obce")
              .select("id, email, token, created_at")
              .eq("potvrdeny", False)
              .is_("potvrdzovaci_email_at", "null")
              .gte("created_at", hranica)
              .order("created_at", desc=False)
              .limit(limit)
              .execute().data or [])


def posli_potvrdenia(sb, kluc, nasucho, obmedz_na=None, teraz=None) -> tuple:
    """Vrati (poslane, zlyhane, preskocene)."""
    teraz = teraz or datetime.now(timezone.utc)
    riadky = vyber_riadky(sb, teraz)
    log.info("Cakajucich potvrdzovacich e-mailov: %s%s",
             len(riadky), "  [NASUCHO]" if nasucho else "")

    poslane = zlyhane = preskocene = 0
    for r in riadky:
        komu = (r.get("email") or "").strip()
        odkaz = _odkaz(r.get("token"))
        if not _platny_email(komu) or not odkaz:
            log.warning("odber_obce %s: neplatny e-mail alebo chyba token, "
                        "preskakujem.", r.get("id"))
            preskocene += 1
            continue
        if obmedz_na and komu.lower() != obmedz_na.lower():
            continue

        obsah = _obsah(odkaz)
        html = _obal(obsah["titulok"], obsah["uvod"], obsah["bloky"],
                     obsah["cta_text"], obsah["cta_url"], obsah["odhlasenie"])

        if posli(kluc, komu, PREDMET, html, nasucho, text=_text(odkaz)):
            poslane += 1
            if not nasucho:
                try:
                    sb.table("odber_obce").update(
                        {"potvrdzovaci_email_at": datetime.now(timezone.utc).isoformat()}
                    ).eq("id", r["id"]).execute()
                except Exception as e:
                    # Horsie nez nezapisat je poslat to iste este raz, ale
                    # zhodit beh kvoli tomu nema zmysel.
                    log.warning("odber_obce %s: potvrdzovaci_email_at sa "
                                "nezapisal (%s)", r.get("id"), e)
        else:
            # Neoznacujeme — zopakuje sa pri dalsom behu.
            zlyhane += 1
        time.sleep(PAUZA_S)
    return poslane, zlyhane, preskocene


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nasucho", action="store_true",
                    help="nic neposle, len vypise co by poslal")
    ap.add_argument("--komu", help="posle len na tuto adresu (test)")
    args = ap.parse_args()

    if args.komu is not None:
        args.komu = args.komu.strip()
        if not _platny_email(args.komu):
            log.error("--komu nie je platna e-mailova adresa. Nepokracujem.")
            return 1

    url = os.getenv("SUPABASE_URL")
    servis = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    kluc = os.getenv("RESEND_API_KEY")
    if not (url and servis):
        log.error("Chyba SUPABASE_URL alebo SUPABASE_SERVICE_ROLE_KEY.")
        return 1
    if not kluc and not args.nasucho:
        log.error("Chyba RESEND_API_KEY. Spusti s --nasucho, alebo ho priprav "
                  "v GitHub Secrets (uz tam je pre posli_email.py).")
        return 1

    sb = create_client(url, servis)

    try:
        poslane, zlyhane, preskocene = posli_potvrdenia(
            sb, kluc, args.nasucho, args.komu)
    except Exception as e:
        log.error("Nacitanie odber_obce zlyhalo: %s", e)
        return 1

    log.info("Hotovo%s: poslanych %s, zlyhanych %s, preskocenych %s.",
             "  [NASUCHO]" if args.nasucho else "", poslane, zlyhane, preskocene)
    if zlyhane and not poslane:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
