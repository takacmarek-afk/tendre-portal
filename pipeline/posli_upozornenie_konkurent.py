"""Upozornenie "sledovanej firme konci zmluva" (vlna 93, migracia 77).

Organizacie s planom Growth+ si sleduju firmy podla ICO (tabulka
sledovane_ico). Tento skript posle vlastnikovi/adminovi e-mail, ked sledovanej
firme (dodavatelovi v CRZ) v najblizsich ~180 dnoch konci zmluva za aspon
5 000 EUR. Kazda zmluva sa kazdej organizacii posle najviac raz
(sledovane_alerty_odoslane). Jeden e-mail obsahuje najviac 10 zmlúv, zvysok
pride pri dalsom behu.

Spustenie:
    python posli_upozornenie_konkurent.py              # naozaj posle
    python posli_upozornenie_konkurent.py --nasucho    # nic neposle, len vypise

Premenne: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, RESEND_API_KEY.
"""
import argparse
import logging
import os
import sys
import time
from collections import OrderedDict

from supabase import create_client

from posli_email import PAUZA_S, _datum_sk, _eur, _obal, posli  # noqa: F401

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)-7s %(name)-9s %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("konkurent")

ODKAZ_APP = "https://predtendrom.sk/app"
MAX_V_EMAILI = 10


def obsah(riadky: list, dalsie: int = 0) -> dict:
    """riadky = zmluvy (uz zoradene podla konca), dalsie = kolko ich nevojde."""
    n = len(riadky) + dalsie
    prva = riadky[0]
    firmy = list(OrderedDict.fromkeys(r.get("nazov_firmy") or r.get("ico") for r in riadky))
    bloky = []
    for r in riadky:
        zvyr = f"Hodnota zmluvy {_eur(r.get('price_total'))}"
        if r.get("odhad_vyhlasenia"):
            zvyr += f" · odhad vyhlásenia tendra {_datum_sk(r['odhad_vyhlasenia'])}"
        bloky.append({
            "titul": f"{r.get('nazov_firmy') or r.get('ico')} — zmluva končí {_datum_sk(r.get('effective_to'))}",
            "popis": f"{r.get('authority_name') or ''}: {r.get('subject') or ''}",
            "zvyraznene": zvyr,
        })
    if dalsie > 0:
        bloky.append({"titul": f"+ {dalsie} ďalších zmlúv", "popis": "Zobrazia sa v ďalšom upozornení."})
    return {
        "titulok": (f"{prva.get('nazov_firmy') or prva.get('ico')}: končí zmluva"
                    if n == 1 else f"Sledovaným firmám končia zmluvy ({n})"),
        "uvod": ("U firiem, ktoré sledujete, sa blíži koniec "
                 + ("jednej zmluvy" if n == 1 else f"{n} zmlúv")
                 + ". Ak úrad zmluvu nepredĺži, zvyčajne vyhlási nové obstarávanie."),
        "bloky": bloky,
        "cta_text": "Otvoriť sledované firmy",
        "cta_url": ODKAZ_APP,
        "odhlasenie": ("Tento e-mail vám prišiel, lebo sledujete firmy podľa IČO "
                       "v pláne Growth alebo Team. Sledovanie môžete kedykoľvek "
                       "zrušiť v aplikácii (Dodávatelia / Sledované firmy). "
                       "Otázky: info@predtendrom.sk."),
        "firmy": firmy,
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
        riadky = sb.rpc("sledovane_konciace_alerty", {"p_dni": 180}).execute().data or []
    except Exception as e:
        log.error("sledovane_konciace_alerty() zlyhalo: %s", e)
        return 1

    # org_id -> {"prijemcovia": [e-maily], "zmluvy": {contract_id: riadok}}
    orgy: "OrderedDict[str, dict]" = OrderedDict()
    for r in riadky:
        o = orgy.setdefault(r["org_id"], {"prijemcovia": OrderedDict(), "zmluvy": OrderedDict()})
        o["prijemcovia"][r["email"]] = True
        o["zmluvy"].setdefault(r["contract_id"], r)

    poslane = zlyhane = 0
    for org_id, o in orgy.items():
        zmluvy = sorted(o["zmluvy"].values(), key=lambda r: (str(r.get("effective_to")), r["contract_id"]))
        davka, dalsie = zmluvy[:MAX_V_EMAILI], max(0, len(zmluvy) - MAX_V_EMAILI)
        ob = obsah(davka, dalsie)
        html = _obal(ob["titulok"], ob["uvod"], ob["bloky"], ob["cta_text"], ob["cta_url"], ob["odhlasenie"])
        predmet = f"PredTendrom.sk — {ob['titulok']}"
        aspon_jeden = False
        for email in o["prijemcovia"]:
            if posli(kluc, email, predmet, html, args.nasucho):
                poslane += 1
                aspon_jeden = True
            else:
                zlyhane += 1
            time.sleep(PAUZA_S)
        if aspon_jeden and not args.nasucho:
            try:
                sb.rpc("oznac_sledovane_alerty", {
                    "p_org_id": org_id,
                    "p_ico": [str(r.get("ico") or "") for r in davka],
                    "p_contract_ids": [r["contract_id"] for r in davka],
                }).execute()
            except Exception as e:
                # Neoznacene = pri dalsom behu pride e-mail znova; lepsie
                # nez zabudnut. Dopad: najviac jeden duplicitny e-mail.
                log.warning("Oznacenie alertu zlyhalo (%s)", e)

    log.info("Hotovo%s: poslanych %s, zlyhanych %s",
             "  [NASUCHO]" if args.nasucho else "", poslane, zlyhane)
    return 1 if (zlyhane and not poslane) else 0


if __name__ == "__main__":
    sys.exit(main())
