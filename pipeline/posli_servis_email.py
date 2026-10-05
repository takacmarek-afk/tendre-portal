"""E-mail s odkazom na rychlu registraciu pre schvalene servisne dopyty
(P3.2 C, druha polovica "zo ziadosti o pomoc sa so suhlasom obce automaticky
stane dopyt na trhu").

ROZSAH (Marekovo rozhodnutie 29.9.2026, klikatelne otazky): "Ano, e-mail s
rychlou registraciou." Servisny dopyt (servis.html) musi mat:
  1. suhlas_zverejnit = true (obec zaskrtla pri odoslani formulara),
  2. schvaleny = true (RUCNE nastavene Marekom/mnou v Supabase Studio, po
     precitani volneho textu popis — kontrola pred zverejnenim, viz
     supabase/59_servis_dopyt_prevod.sql).

Tento skript NEVYTVARA verejny dopyt priamo — len posle e-mail s odkazom
na `/prihlasenie.html?servis=<token>&dalej=trh.html`. Samotne vytvorenie
dopytu (vytvor_dopyt) prebehne az na trh.html, hned po tom, co si obec
dokonci registraciu (public/trh.html, zurcitVstupZoServisu()).

CO SA NEPOSIELA DVAKRAT: email_poslany_at sa nastavi po uspesnom odoslani,
skript vzdy vyberie len riadky, kde je este null.

Spustenie:
    python posli_servis_email.py                # naozaj posle
    python posli_servis_email.py --nasucho       # nic neposle, len vypise
    python posli_servis_email.py --komu ja@x.sk  # posle len na tuto adresu (test)

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

from posli_email import ODOSIELATEL, PAUZA_S, _obal, posli  # noqa: F401

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)-7s %(name)-9s %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("servis-email")

ODKAZ_PRIHLASENIE = "https://predtendrom.sk/prihlasenie.html"
EMAIL_RE = re.compile(r"[^@\s,;<>\"]+@[^@\s,;<>\"]+\.[A-Za-z]{2,}")

# Poistka (audit 5.10.2026, K3): schvaleny dopyt starsi nez toto sa uz
# neposiela — stary neodoslany riadok by inak po case mohol "ozit". DB od
# migracie 63 anonymovi nedovoli nastavit `schvaleny`, toto je navyse.
MAX_VEK_DNI = 60


def _platny_email(e) -> bool:
    return bool(e) and bool(EMAIL_RE.fullmatch(str(e).strip()))


def _odkaz(token) -> str:
    """?servis=<token>&dalej=trh.html - rovnaky vzor ako ?pozvanka=<kod>
    z 58_pozvat_kolegu.sql, oba idu cez uz hotovy prihlasovaci flow."""
    return f"{ODKAZ_PRIHLASENIE}?servis={token}&dalej=trh.html"


def _ma_sa_poslat(sd, teraz) -> bool:
    """Poistka: len `schvaleny` je presne True a riadok nie je starsi nez
    MAX_VEK_DNI dni. Chybajuci/necitatelny created_at = neposielat."""
    if sd.get("schvaleny") is not True:
        return False
    try:
        vytvoreny = datetime.fromisoformat(str(sd.get("created_at")).replace("Z", "+00:00"))
    except ValueError:
        return False
    if vytvoreny.tzinfo is None:
        vytvoreny = vytvoreny.replace(tzinfo=timezone.utc)
    return teraz - vytvoreny <= timedelta(days=MAX_VEK_DNI)


def _obsah(sd) -> dict:
    obec = (sd.get("obec") or "").strip()
    od_obce = f" za obec {obec}" if obec else ""
    return {
        "titulok": "Váš dopyt je pripravený na zverejnenie",
        "uvod": (f"Dobrý deň, žiadosť o pomoc, ktorú ste nám poslali{od_obce}, "
                 "sme si prečítali a je pripravená na zverejnenie ako dopyt "
                 "na Trhu dopytov, kde ju uvidia poradcovia vo vašom kraji."),
        "bloky": [{
            "titul": "Dokončite jedným klikom",
            "popis": ("Prihláste sa rovnakým e-mailom, na aký prišla táto "
                      "správa — dopyt sa vytvorí automaticky, nič ďalšie "
                      "vypisovať nemusíte."),
            "zvyraznene": None,
        }],
        "cta_text": "Dokončiť a zverejniť dopyt",
        "cta_url": _odkaz(sd["token"]),
        "odhlasenie": ("Tento e-mail súvisí s vašou vlastnou žiadosťou zo "
                       "servisného formulára. Ak ste ju neposielali vy, "
                       "odpovedzte na tento e-mail."),
    }


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
    teraz = datetime.now(timezone.utc)

    riadky = (sb.table("servisne_dopyty")
                .select("id, obec, kontakt_email, token, schvaleny, created_at")
                .eq("suhlas_zverejnit", True)
                .eq("schvaleny", True)
                .gte("created_at", (teraz - timedelta(days=MAX_VEK_DNI)).isoformat())
                .is_("email_poslany_at", "null")
                .is_("prevzaty_at", "null")
                .execute().data or [])

    poslane = zlyhane = preskocene = 0
    for sd in riadky:
        if not _ma_sa_poslat(sd, teraz):
            log.info("Servisny dopyt %s: neschvaleny alebo starsi nez %s dni, "
                     "preskakujem.", sd["id"], MAX_VEK_DNI)
            preskocene += 1
            continue
        komu = (sd.get("kontakt_email") or "").strip()
        if not _platny_email(komu):
            log.warning("Servisny dopyt %s: neplatny kontakt_email, preskakujem.", sd["id"])
            preskocene += 1
            continue
        if args.komu and komu.lower() != args.komu.lower():
            continue

        obsah = _obsah(sd)
        html = _obal(obsah["titulok"], obsah["uvod"], obsah["bloky"],
                     obsah["cta_text"], obsah["cta_url"], obsah["odhlasenie"])
        predmet = "PredTendrom.sk — Váš dopyt je pripravený na zverejnenie"

        if posli(kluc, komu, predmet, html, args.nasucho):
            poslane += 1
            if not args.nasucho:
                try:
                    sb.table("servisne_dopyty").update(
                        {"email_poslany_at": datetime.now(timezone.utc).isoformat()}
                    ).eq("id", sd["id"]).execute()
                except Exception as e:
                    log.warning("Servisny dopyt %s: oznacenie email_poslany_at "
                               "zlyhalo (%s)", sd["id"], e)
        else:
            zlyhane += 1
        time.sleep(PAUZA_S)

    log.info("Hotovo%s: poslanych %s, zlyhanych %s, preskocenych %s.",
             "  [NASUCHO]" if args.nasucho else "", poslane, zlyhane, preskocene)
    if zlyhane and not poslane:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
