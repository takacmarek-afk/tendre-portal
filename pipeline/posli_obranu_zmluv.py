"""Obrana vlastnych zmluv (vlna 94, migracia 78): "urad vyhlasil sutaz".

Organizacii s planom Growth+ posle e-mail, ked urad, ktoremu dodava podla
zmluvy konciacej do 12 mesiacov (dodavatel = ICO organizacie z registracie),
vyhlasil v tom istom sektore sutaz. Je to odhad "mozno nastupca vasej zmluvy",
nie istota. V e-maili je aj pocet ponuk z poslednej sutaze toho uradu v tom
istom sektore a odhadovany termin tendra. Jedna dvojica zmluva + vyzva sa
posle najviac raz (obrana_alerty_odoslane); najviac 10 zmluv v e-maili.

Spustenie:
    python posli_obranu_zmluv.py              # naozaj posle
    python posli_obranu_zmluv.py --nasucho    # nic neposle, len vypise

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
log = logging.getLogger("obrana")

ODKAZ_APP = "https://predtendrom.sk/app"
MAX_V_EMAILI = 10


def _ponuky(n) -> str:
    try:
        n = int(n)
    except (TypeError, ValueError):
        return ""
    if n == 1:
        return "v poslednej súťaži toho úradu v tomto sektore bola 1 ponuka"
    if 2 <= n <= 4:
        return f"v poslednej súťaži toho úradu v tomto sektore boli {n} ponuky"
    return f"v poslednej súťaži toho úradu v tomto sektore bolo {n} ponúk"


def obsah(riadky: list, dalsie: int = 0) -> dict:
    n = len(riadky) + dalsie
    prva = riadky[0]
    bloky = []
    for r in riadky:
        casti = [f"Vaša zmluva končí {_datum_sk(r.get('effective_to'))} ({_eur(r.get('price_total'))})"]
        if r.get("odhad_vyhlasenia"):
            casti.append(f"odhad vyhlásenia tendra {_datum_sk(r['odhad_vyhlasenia'])}")
        pon = _ponuky(r.get("pocet_ponuk_naposledy"))
        if pon:
            casti.append(pon)
        bloky.append({
            "titul": f"{r.get('authority_name') or '—'}: {r.get('vyzva_nazov') or 'nová súťaž'}",
            "popis": f"Vaša zmluva: {r.get('subject') or ''}",
            "zvyraznene": " · ".join(casti),
        })
    if dalsie > 0:
        bloky.append({"titul": f"+ {dalsie} ďalších zmlúv", "popis": "Zobrazia sa v ďalšom upozornení."})
    return {
        "titulok": ("Úrad vyhlásil súťaž k vašej zmluve" if n == 1
                    else f"Úrady vyhlásili súťaže k vašim zmluvám ({n})"),
        "uvod": (f"{prva.get('authority_name') or 'Úrad'} vyhlásil súťaž v rovnakom sektore, "
                 "v ktorom vám končí zmluva. Môže ísť o nástupcu vašej zmluvy, istotu nemáme: "
                 "pozrite si podmienky a lehotu na predloženie ponúk."),
        "bloky": bloky,
        "cta_text": "Otvoriť PredTendrom",
        "cta_url": ODKAZ_APP,
        "odhlasenie": ("Tento e-mail vám prišiel, lebo ste v pláne Growth alebo Team "
                       "a v registri zmlúv máme zmluvu vedenú na IČO vašej organizácie. "
                       "Otázky alebo odhlásenie: info@predtendrom.sk."),
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
        riadky = sb.rpc("obrana_nove_vyzvy", {}).execute().data or []
    except Exception as e:
        log.error("obrana_nove_vyzvy() zlyhalo: %s", e)
        return 1

    orgy: "OrderedDict[str, dict]" = OrderedDict()
    for r in riadky:
        o = orgy.setdefault(r["org_id"], {"prijemcovia": OrderedDict(), "dvojice": OrderedDict()})
        o["prijemcovia"][r["email"]] = True
        o["dvojice"].setdefault((r["contract_id"], r["vyzva_id"]), r)

    poslane = zlyhane = 0
    for org_id, o in orgy.items():
        riad = sorted(o["dvojice"].values(), key=lambda r: (str(r.get("effective_to")), r["contract_id"]))
        davka, dalsie = riad[:MAX_V_EMAILI], max(0, len(riad) - MAX_V_EMAILI)
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
                sb.rpc("oznac_obrana_alerty", {
                    "p_org_id": org_id,
                    "p_contract_ids": [r["contract_id"] for r in davka],
                    "p_vyzva_ids": [r["vyzva_id"] for r in davka],
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
