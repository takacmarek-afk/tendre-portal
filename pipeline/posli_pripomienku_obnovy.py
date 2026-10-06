"""Pripomienka obnovy predplatneho (vlna 83, migracia 68).

Platba cez Stripe je JEDNORAZOVA (Checkout mode "payment"), predplatne sa
neobnovuje automaticky a po `obdobie_konci` sa pristup zatvori
(public.ma_aktivny_pristup()). Preto 7 dni pred koncom posleme vlastnikovi
firmy e-mail s odkazom na platbu. Pre jeden koniec obdobia len raz
(subscriptions.pripomienka_obnovy_za) — po predlzeni sa koniec posunie
a dalsia pripomienka pride pre novy koniec.

Spustenie:
    python posli_pripomienku_obnovy.py              # naozaj posle
    python posli_pripomienku_obnovy.py --nasucho    # nic neposle, len vypise

Premenne: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, RESEND_API_KEY.
"""
import argparse
import logging
import os
import sys
import time
from datetime import datetime, timezone

from supabase import create_client

from posli_email import PAUZA_S, _obal, posli  # noqa: F401

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)-7s %(name)-9s %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("obnova")

ODKAZ_APP = "https://predtendrom.sk/app"
PLANY = {"start": "Start", "growth": "Growth", "team": "Team",
         "poradca": "Poradca", "pro": "Pro"}


def _datum_sk(iso) -> str:
    """'2026-11-06T10:00:00+00:00' -> '6. 11. 2026' (slovensky, bez nul)."""
    try:
        d = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return str(iso)
    return f"{d.day}. {d.month}. {d.year}"


def obsah(plan: str, obdobie_konci) -> dict:
    nazov = PLANY.get(plan, plan or "")
    datum = _datum_sk(obdobie_konci)
    return {
        "titulok": "Vaše predplatné čoskoro končí",
        "uvod": (f"Plán {nazov} máte zaplatený do {datum}. Predplatné sa "
                 f"neobnovuje automaticky — po tomto dni sa prístup do "
                 f"aplikácie zatvorí, kým ho nepredĺžite."),
        "bloky": [{
            "titul": f"Plán {nazov} · platí do {datum}",
            "popis": ("Predĺženie sa pripočíta k zostávajúcemu času, nič "
                      "z už zaplatenej doby nepríde nazmar. Platí sa kartou "
                      "cez Stripe, v aplikácii cez tlačidlo Predplatné."),
        }],
        "cta_text": "Predĺžiť predplatné",
        "cta_url": ODKAZ_APP,
        "odhlasenie": ("Tento e-mail vám prišiel, lebo ste vlastníkom firmy "
                       "s platným predplatným PredTendrom.sk. Otázky: "
                       "info@predtendrom.sk."),
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
        riadky = sb.rpc("pripomienky_obnovy", {}).execute().data or []
    except Exception as e:
        log.error("pripomienky_obnovy() zlyhalo: %s", e)
        return 1

    poslane = zlyhane = 0
    for r in riadky:
        o = obsah(r.get("plan"), r.get("obdobie_konci"))
        html = _obal(o["titulok"], o["uvod"], o["bloky"], o["cta_text"],
                     o["cta_url"], o["odhlasenie"])
        predmet = f"PredTendrom.sk — {o['titulok']}"
        if posli(kluc, r["email"], predmet, html, args.nasucho):
            poslane += 1
            if not args.nasucho:
                try:
                    sb.rpc("oznac_pripomienku_obnovy",
                           {"p_org_id": r["org_id"],
                            "p_obdobie_konci": r["obdobie_konci"]}).execute()
                except Exception as e:
                    # Neoznacene = pri dalsom behu pride e-mail znova; lepsie
                    # nez zabudnut. Dopad: najviac jeden duplicitny e-mail.
                    log.warning("Oznacenie pripomienky zlyhalo (%s)", e)
        else:
            zlyhane += 1
        time.sleep(PAUZA_S)

    log.info("Hotovo%s: poslanych %s, zlyhanych %s",
             "  [NASUCHO]" if args.nasucho else "", poslane, zlyhane)
    return 1 if (zlyhane and not poslane) else 0


if __name__ == "__main__":
    sys.exit(main())
