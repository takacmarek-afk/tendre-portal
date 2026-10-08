"""Tyzdenny bezplatny prehlad po skonceni skusky/predplatneho (vlna 92, migracia 76).

Organizaciam, ktorym skoncila skuska alebo zaplatene obdobie (najviac 8 tyzdnov
po konci), posle raz za 6 dni e-mail s poctami a tromi ukazkami z ich vyberu
(1 kraj + 1 sektor). Bez sum a bez mien dodavatelov - tie su sucastou planov.
Odhlasenie: odpoved "Stop" na e-mail; Marek nastavi
subscriptions.bezplatny_email_stop = true.

Spustenie:
    python posli_bezplatny_email.py              # naozaj posle
    python posli_bezplatny_email.py --nasucho    # nic neposle, len vypise

Premenne: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, RESEND_API_KEY.
"""
import argparse
import logging
import os
import sys
import time

from supabase import create_client

from posli_email import PAUZA_S, _obal, _sektor_text, _sklon, posli  # noqa: F401

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)-7s %(name)-9s %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("bezplatny")

ODKAZ_APP = "https://predtendrom.sk/app"


def _mesiac(ym) -> str:
    """'2026-11' -> '11/2026'."""
    try:
        r, m = str(ym).split("-")
        return f"{int(m)}/{r}"
    except ValueError:
        return str(ym or "")


def obsah(d: dict) -> dict:
    zmluvy = int(d.get("pocet_zmluv") or 0)
    dotacie = int(d.get("pocet_dotacii") or 0)
    if d.get("nastavene"):
        kde = f"{d.get('kraj')}, {_sektor_text(d.get('sektor'))}"
        uvod = (f"{kde}: do 12 mesiacov končí {zmluvy} "
                f"{_sklon(zmluvy, 'zmluva', 'zmluvy', 'zmlúv')} a {dotacie} "
                f"{_sklon(dotacie, 'dotácia', 'dotácie', 'dotácií')} môže priniesť tender.")
        dalsie = int(d.get("dalsie_v_kraji") or 0)
        if dalsie > 0:
            uvod += f" V ďalších sektoroch tohto kraja končí ďalších {dalsie} zmlúv."
    else:
        uvod = (f"Na Slovensku do 12 mesiacov končí {zmluvy} "
                f"{_sklon(zmluvy, 'zmluva', 'zmluvy', 'zmlúv')} a {dotacie} "
                f"{_sklon(dotacie, 'dotácia', 'dotácie', 'dotácií')} môže priniesť tender. "
                f"Po aktivácii plánu si nastavíte kraj a sektor.")
    bloky = [{"titul": u.get("obstaravatel") or "—",
              "popis": f"{u.get('predmet') or ''} (zmluva končí {_mesiac(u.get('koniec'))})"}
             for u in (d.get("ukazky") or [])]
    return {
        "titulok": "Týždenný prehľad končiacich zmlúv",
        "uvod": uvod + " Sumy, dodávatelia a odkazy na zmluvy sú v plánoch od 34 € mesačne.",
        "bloky": bloky,
        "cta_text": "Otvoriť PredTendrom",
        "cta_url": ODKAZ_APP,
        "odhlasenie": ("Tento e-mail vám prišiel, lebo vaša skúška alebo plán "
                       "PredTendrom.sk nedávno skončili; posielame ho najviac "
                       "8 týždňov. Ak ho nechcete dostávať, odpovedzte na neho "
                       "slovom Stop. Otázky: info@predtendrom.sk."),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--nasucho", action="store_true")
    args = ap.parse_args(argv)

    url = os.getenv("SUPABASE_URL")
    servis = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    kluc = os.getenv("RESEND_API_KEY")
    if not (url and servis):
        log.error("Chyba SUPABASE_URL alebo SUPABASE_SERVICE_ROLE_KEY.")
        return 1
    if not kluc and not args.nasucho:
        log.error("Chyba RESEND_API_KEY (alebo pouzi --nasucho).")
        return 1

    sb = create_client(url, servis)
    try:
        riadky = sb.rpc("bezplatne_emaily", {}).execute().data or []
    except Exception as e:
        log.error("bezplatne_emaily() zlyhalo: %s", e)
        return 1

    poslane = zlyhane = 0
    for r in riadky:
        o = obsah(r.get("obsah") or {})
        html = _obal(o["titulok"], o["uvod"], o["bloky"], o["cta_text"],
                     o["cta_url"], o["odhlasenie"])
        predmet = f"PredTendrom.sk — {o['titulok']}"
        if posli(kluc, r["email"], predmet, html, args.nasucho):
            poslane += 1
            if not args.nasucho:
                try:
                    sb.rpc("oznac_bezplatny_email", {"p_org_id": r["org_id"]}).execute()
                except Exception as e:
                    # Neoznacene = pri dalsom behu pride e-mail znova; lepsie
                    # nez zabudnut. Dopad: najviac jeden duplicitny e-mail.
                    log.warning("Oznacenie e-mailu zlyhalo (%s)", e)
        else:
            zlyhane += 1
        time.sleep(PAUZA_S)

    log.info("Hotovo%s: poslanych %s, zlyhanych %s",
             "  [NASUCHO]" if args.nasucho else "", poslane, zlyhane)
    return 1 if (zlyhane and not poslane) else 0


if __name__ == "__main__":
    sys.exit(main())
