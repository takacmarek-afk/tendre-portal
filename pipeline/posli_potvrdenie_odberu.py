"""Potvrdzovaci e-mail (double opt-in) pre odber prehladov pre obce.

Audit 5.10.2026, V1 + migracia supabase/63_audit_5_10_bezpecnost.sql, oddiel 4:
novy riadok v odber_obce je potvrdeny=false a ma `token`. Tyzdenny e-mail
(posli_email.py) a alerty (alerty.py) citaju len potvrdeny=true, takze
adresa dostane prehlady az po kliknuti na odkaz z TOHTO e-mailu.

CO SA POSIELA
  Kazdemu riadku odber_obce, ktory ma:
    - potvrdeny = false,
    - este nema vycerpane pokusy (najviac 3) a od posledneho pokusu
      uplynulo aspon 10 minut (alebo este nebol ziaden),
    - created_at mladsie nez 3 dni (starsie neposielame — clovek uz davno
      zabudol a e-mail by posobil ako spam),
  najviac MAX_NA_BEH (200) e-mailov na jeden beh (najstarsie prve).
  Riadky sa ZABERAJU atomicky v databaze (RPC zaber_potvrdenie_odberu,
  migracia 65): zaroven sa nastavi potvrdzovaci_email_at a zvysi pocet
  pokusov, takze Edge Function a tento skript nikdy neposlu to iste dvakrat.
  Pri chybe odoslania sa pokus vrati (vrat_potvrdenie_odberu) a zopakuje sa
  pri dalsom behu (az kym nie je riadok starsi nez 3 dni).

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
MAX_POKUSOV = 3        # najviac tolko potvrdzovacich e-mailov na jeden riadok
MEDZERA_MIN = 10       # minimalna pauza medzi dvoma pokusmi pre ten isty riadok

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


def _moze_dostat(r, teraz) -> bool:
    """Rovnake pravidlo ako RPC zaber_potvrdenie_odberu (migracia 65)."""
    if (r.get("potvrdzovaci_pokusy") or 0) >= MAX_POKUSOV:
        return False
    posledny = r.get("potvrdzovaci_email_at")
    if not posledny:
        return True
    try:
        t = datetime.fromisoformat(str(posledny).replace("Z", "+00:00"))
    except ValueError:
        return False
    return t < teraz - timedelta(minutes=MEDZERA_MIN)


def vyber_riadky(sb, teraz, limit=MAX_NA_BEH) -> list:
    """Riadky odber_obce, ktorym by sa dnes poslal potvrdzovaci e-mail.
    Len na vypis (--nasucho); skutocne zabratie robi RPC (zaber_riadky)."""
    hranica = (teraz - timedelta(days=MAX_VEK_DNI)).isoformat()
    riadky = (sb.table("odber_obce")
                .select("id, email, token, created_at, potvrdzovaci_email_at, "
                        "potvrdzovaci_pokusy")
                .eq("potvrdeny", False)
                .gte("created_at", hranica)
                .order("created_at", desc=False)
                .limit(1000)
                .execute().data or [])
    return [r for r in riadky if _moze_dostat(r, teraz)][:limit]


def zaber_riadky(sb, komu=None) -> list:
    """Atomicky zabere riadky na odoslanie (RPC zaber_potvrdenie_odberu).
    Kazdy riadok dostane najviac MAX_POKUSOV pokusov, medzi pokusmi aspon
    MEDZERA_MIN minut; dva sucasne behy nikdy nezoberu ten isty riadok."""
    return sb.rpc("zaber_potvrdenie_odberu", {"p_email": komu}).execute().data or []


def vrat_riadok(sb, riadok_id) -> None:
    try:
        sb.rpc("vrat_potvrdenie_odberu", {"p_id": riadok_id}).execute()
    except Exception as e:
        log.warning("odber_obce %s: vratenie pokusu zlyhalo (%s)", riadok_id, e)


def posli_potvrdenia(sb, kluc, nasucho, obmedz_na=None, teraz=None) -> tuple:
    """Vrati (poslane, zlyhane, preskocene)."""
    teraz = teraz or datetime.now(timezone.utc)
    if nasucho:
        riadky = vyber_riadky(sb, teraz)
    else:
        riadky = zaber_riadky(sb, obmedz_na)
        if len(riadky) > MAX_NA_BEH:
            for r in riadky[MAX_NA_BEH:]:
                vrat_riadok(sb, r.get("id"))
            riadky = riadky[:MAX_NA_BEH]
    log.info("Cakajucich potvrdzovacich e-mailov: %s%s",
             len(riadky), "  [NASUCHO]" if nasucho else "")

    poslane = zlyhane = preskocene = 0
    for r in riadky:
        komu = (r.get("email") or "").strip()
        odkaz = _odkaz(r.get("token"))
        if not _platny_email(komu) or not odkaz:
            log.warning("odber_obce %s: neplatny e-mail alebo chyba token, "
                        "preskakujem.", r.get("id"))
            preskocene += 1   # pokus sa NEVRACIA: riadok nema zmysel opakovat
            continue
        if obmedz_na and komu.lower() != obmedz_na.lower():
            if not nasucho:
                vrat_riadok(sb, r.get("id"))
            continue

        obsah = _obsah(odkaz)
        html = _obal(obsah["titulok"], obsah["uvod"], obsah["bloky"],
                     obsah["cta_text"], obsah["cta_url"], obsah["odhlasenie"])

        if posli(kluc, komu, PREDMET, html, nasucho, text=_text(odkaz)):
            poslane += 1
        else:
            # Pokus sa vrati; zopakuje sa pri dalsom behu (po 10 minutach).
            zlyhane += 1
            if not nasucho:
                vrat_riadok(sb, r.get("id"))
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
