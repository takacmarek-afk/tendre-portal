"""Mesacny e-mail o obci pre existujuce ucty na Trhu dopytov (P3.2 B).

Zo zadania (claude/predtendrom-p3-cesta-pre-starostov-zadanie.md, persona B
"stronovy starosta"): "Mesacny osobny e-mail o obci bez nutnosti prihlasenia:
co je nove pre obce jeho velkosti, ktore programy prave platia, ktore
zmluvy obce sa bliza ku koncu."

ROZSAH (Marekovo rozhodnutie 29.9.2026, cez klikatelne otazky v chate):
LEN OBCE S EXISTUJUCIM UCTOM (obce_ucty.kontakt_email) — samostatny zoznam
oficialnych e-mailov vsetkych obci na Slovensku dnes nemame. Ak sa taky
zoznam neskor zozenie, tento skript sa rozsiri, nie nahradi.

BEZ "OBCE VASEJ VELKOSTI" — rovnake zistenie ako pri cenovom benchmarku
(pozri migraciu 57 a starosta.html): spolahlivy zdroj poctu obyvatelov
obci nemame, preto sa velkost v texte vobec nespomina.

CO SA POSIELA (za KONKRETNU obec z jej obce_ucty.nazov/kraj, rovnaky zdroj
pravdy ako prvych_100_dni_suhrn RPC z 53_prvych_100_dni.sql — ziadna
duplicita logiky):
  1. Kolko zmluv obce sa v najblizsich 12 mesiacoch konci (pocet + sucet).
  2. Kolko dotacii obci este bezi (pocet + sucet).
  3. Kto prave teraz rozdava peniaze obciam vseobecne (aktivne_programy,
     rovnaky obsah ako v existujucom tyzdennom posli_email.py::pre_obec).

CO SA NEPOSIELA: prazdny e-mail (rovnaka zasada ako v posli_email.py) ani
e-mail castejsie ako raz za ~28 dni (obce_ucty.posledny_mesacny_email).

Spustenie:
    python posli_obec_mesacny_email.py                # naozaj posle
    python posli_obec_mesacny_email.py --nasucho      # nic neposle, len vypise
    python posli_obec_mesacny_email.py --komu ja@x.sk # posle len na tuto adresu (test)

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

from posli_email import (ODOSIELATEL, PAUZA_S, _obal, _eur, posli,  # noqa: F401
                         _popis_programu, _sklon)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)-7s %(name)-9s %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("obec-mesacny-email")

ODKAZ_PRVYCH_100_DNI = "https://predtendrom.sk/prvych-100-dni.html"
EMAIL_RE = re.compile(r"[^@\s,;<>\"]+@[^@\s,;<>\"]+\.[A-Za-z]{2,}")

# Neposielat castejsie nez raz za tolkoto dni — "mesacny" e-mail.
MIN_DNI_MEDZI_EMAILMI = 28
MAX_PROGRAMOV = 3


def _platny_email(e) -> bool:
    return bool(e) and bool(EMAIL_RE.fullmatch(str(e).strip()))


def _ma_sa_poslat(obec, dnes) -> bool:
    posledny = obec.get("posledny_mesacny_email")
    if not posledny:
        return True
    try:
        d = datetime.fromisoformat(str(posledny).replace("Z", "+00:00"))
    except ValueError:
        return True
    return (dnes - d) >= timedelta(days=MIN_DNI_MEDZI_EMAILMI)


def _suhrn_pre_obec(sb, nazov) -> dict | None:
    """Volá rovnaku RPC ako verejna stranka /prvych-100-dni — jeden zdroj
    pravdy pre 'co sa konci' a 'co este bezi', ziadna duplicita logiky."""
    try:
        r = sb.rpc("prvych_100_dni_suhrn", {"p_nazov": nazov}).execute().data
    except Exception as e:
        log.warning("prvych_100_dni_suhrn(%r) zlyhalo: %s", nazov, e)
        return None
    if not r:
        return None
    return r[0] if isinstance(r, list) else r


def _programy(sb) -> list:
    try:
        return (sb.table("aktivne_programy")
                  .select("poskytovatel, zmluv_90d, obci_90d, objem_90d, "
                          "median_dotacie, posledna_zmluva")
                  .order("objem_90d", desc=True)
                  .limit(MAX_PROGRAMOV).execute().data or [])
    except Exception as e:
        log.warning("Dopyt na aktivne_programy zlyhal: %s", e)
        return []


def _obsah(obec, suhrn, programy) -> dict | None:
    bloky = []

    if suhrn and (suhrn.get("pocet_konciacich") or 0) > 0:
        bloky.append({
            "titul": "Zmluvy vašej obce, ktoré sa blížia ku koncu",
            "popis": (f"{suhrn['pocet_konciacich']} "
                      + _sklon(suhrn['pocet_konciacich'], "zmluva sa končí",
                               "zmluvy sa končia", "zmlúv sa končí")
                      + " v najbližších 12 mesiacoch."),
            "zvyraznene": f"Spolu cca {_eur(suhrn.get('objem_konciacich'))}",
        })

    if suhrn and (suhrn.get("pocet_dotacii_bezi") or 0) > 0:
        bloky.append({
            "titul": "Dotácie vašej obce, ktoré ešte bežia",
            "popis": (f"{suhrn['pocet_dotacii_bezi']} "
                      + _sklon(suhrn['pocet_dotacii_bezi'],
                               "dotácia, ktorá ešte beží alebo má otvorené okno na čerpanie.",
                               "dotácie, ktoré ešte bežia alebo majú otvorené okno na čerpanie.",
                               "dotácií, ktoré ešte bežia alebo majú otvorené okno na čerpanie.")),
            "zvyraznene": f"Spolu cca {_eur(suhrn.get('objem_dotacii_bezi'))}",
        })

    for p in programy:
        bloky.append({
            "titul": p.get("poskytovatel"),
            "popis": _popis_programu(p),
            "zvyraznene": (f"Spolu {_eur(p.get('objem_90d'))}, "
                           f"typicky {_eur(p.get('median_dotacie'))} na obec"),
        })

    if not bloky:
        return None

    return {
        "titulok": (f"Novinky pre obec {obec['nazov']}" if obec.get("nazov")
                    else "Novinky pre vašu obec"),
        "uvod": ("Mesačný prehľad — čo sa deje okolo zmlúv a dotácií vašej "
                 "obce, a kto práve teraz rozdáva peniaze obciam všeobecne. "
                 "Presné súčty, žiadne jednotlivé zmluvy — tie nájdete "
                 "vyhľadaním svojej obce na verejnej stránke."),
        "bloky": bloky,
        "cta_text": "Otvoriť prehľad obce",
        "cta_url": ODKAZ_PRVYCH_100_DNI,
        "odhlasenie": ("Tento e-mail dostávate raz mesačne ako súčasť vášho "
                       "účtu na Trhu dopytov. Ak si ho neželáte, odpovedzte "
                       "na tento e-mail slovom „odhlásiť“."),
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
    dnes = datetime.now(timezone.utc)

    obce = (sb.table("obce_ucty")
              .select("id, nazov, kontakt_email, posledny_mesacny_email")
              .execute().data or [])
    programy = _programy(sb)

    poslane = zlyhane = preskocene = 0
    for o in obce:
        komu = (o.get("kontakt_email") or "").strip()
        if not _platny_email(komu):
            preskocene += 1
            continue
        if args.komu and komu.lower() != args.komu.lower():
            continue
        if not _ma_sa_poslat(o, dnes):
            preskocene += 1
            continue

        suhrn = _suhrn_pre_obec(sb, o.get("nazov"))
        obsah = _obsah(o, suhrn, programy)
        if not obsah:
            # Rovnaka zasada ako tyzdenny email: prazdny obsah = neposielat.
            log.info("Obec %s (%s): nic na povedanie, e-mail preskakujem.",
                     o.get("nazov"), o["id"])
            preskocene += 1
            continue

        html = _obal(obsah["titulok"], obsah["uvod"], obsah["bloky"],
                     obsah["cta_text"], obsah["cta_url"], obsah["odhlasenie"])
        predmet = f"PredTendrom.sk — {obsah['titulok']}"

        if posli(kluc, komu, predmet, html, args.nasucho):
            poslane += 1
            if not args.nasucho:
                try:
                    sb.table("obce_ucty").update(
                        {"posledny_mesacny_email": dnes.isoformat()}
                    ).eq("id", o["id"]).execute()
                except Exception as e:
                    log.warning("Obec %s: oznacenie posledny_mesacny_email "
                               "zlyhalo (%s)", o["id"], e)
        else:
            zlyhane += 1
        time.sleep(PAUZA_S)

    log.info("Hotovo%s: poslanych %s, zlyhanych %s, preskocenych %s "
             "(bez kontaktu/uz tento mesiac/nic nove).",
             "  [NASUCHO]" if args.nasucho else "",
             poslane, zlyhane, preskocene)
    if zlyhane and not poslane:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
