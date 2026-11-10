"""Upozornenie: pripravovane obstaravanie z eurofondov urad prave vyhlasil (10. 11. 2026).

Pouzivatel so skuskou alebo platenym pristupom, ktoreho vyber (odbory a kraje)
obsahuje obstaravanie, dostane e-mail s odkazom na sutaz vo Vestniku a lehotou.
Kazde obstaravanie kazdemu najviac raz (eurofondy_alerty_odoslane, migracia 99).

    python posli_eurofondy_alert.py --nasucho   # nic neposle, len vypise pocty
    python posli_eurofondy_alert.py             # posle

Premenne: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, RESEND_API_KEY.
"""
import argparse
import logging
import os
import re
import sys
import time
from collections import OrderedDict

from supabase import create_client

from posli_email import PAUZA_S, _datum_sk, _eur, _obal, posli

log = logging.getLogger("eurofondy_alert")
ODKAZ_APP = "https://predtendrom.sk/app"
MAX_V_EMAILI = 10
URL_RE = re.compile(r"^https://(www\.)?(uvo\.gov\.sk|ted\.europa\.eu)/")


def obsah(riadky):
    n = len(riadky)
    bloky = []
    for r in riadky[:MAX_V_EMAILI]:
        hodnota = _eur(r.get("predpokladana_hodnota"))
        url = r.get("vyhlasene_url") if URL_RE.match(str(r.get("vyhlasene_url") or "")) else "https://www.uvo.gov.sk/"
        lehota = f"ponuky do {_datum_sk(r['vyhlasene_lehota'])}" if r.get("vyhlasene_lehota") else "lehotu nájdete vo Vestníku"
        bloky.append({
            "titul": f"{r.get('obstaravatel_nazov') or '—'} — {lehota}",
            "popis": (r.get("vyhlasene_nazov") or r.get("nazov") or "")[:200]
                     + (f" · predpokladaná hodnota {hodnota}" if hodnota else "") + f" · {r.get('kraj') or ''}",
            "zvyraznene": f"Súťaž vo Vestníku: {url}",
        })
    if n > MAX_V_EMAILI:
        bloky.append({"titul": f"+ {n - MAX_V_EMAILI} ďalších", "popis": "Nájdete ich v aplikácii."})
    return {
        "titulok": ("Vyhlásili súťaž z eurofondov, ktorú ste mohli čakať" if n == 1
                    else f"Vyhlásili {n} súťaží z eurofondov vo Vašom výbere"),
        "uvod": ("Tieto obstarávania mali úrady v projektoch z eurofondov ako pripravované. "
                 "Teraz ich vyhlásili vo Vestníku verejného obstarávania, môžete podať ponuku."),
        "bloky": bloky,
        "cta_text": "Otvoriť PredTendrom",
        "cta_url": ODKAZ_APP,
        "odhlasenie": ("Tento e-mail Vám prišiel, lebo vo svojom výbere v PredTendrom.sk sledujete tento "
                       "odbor a kraj. Výber zmeníte v aplikácii (Moje nastavenie). Otázky: info@predtendrom.sk."),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--nasucho", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s")
    kluc = os.getenv("RESEND_API_KEY")
    if not kluc and not a.nasucho:
        log.error("Chyba RESEND_API_KEY (alebo pouzi --nasucho).")
        return 1
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
    riadky = sb.rpc("eurofondy_vyhlasene_alerty", {"p_dni": 7}).execute().data or []
    podla = OrderedDict()
    for r in riadky:
        podla.setdefault((r["user_id"], r["email"]), []).append(r)
    poslane = zlyhane = 0
    for (uid, email), rr in podla.items():
        rr.sort(key=lambda r: str(r.get("vyhlasene_lehota") or "9999"))
        ob = obsah(rr)
        html = _obal(ob["titulok"], ob["uvod"], ob["bloky"], ob["cta_text"], ob["cta_url"], ob["odhlasenie"])
        if posli(kluc, email, f"PredTendrom.sk — {ob['titulok']}", html, a.nasucho):
            poslane += 1
            if not a.nasucho:
                sb.table("eurofondy_alerty_odoslane").upsert(
                    [{"user_id": uid, "itms_id": r["itms_id"]} for r in rr],
                    on_conflict="user_id,itms_id").execute()
        else:
            zlyhane += 1
        time.sleep(PAUZA_S)
    log.info("Hotovo%s: pouzivatelov %d, poslanych %d, zlyhanych %d",
             " [NASUCHO]" if a.nasucho else "", len(podla), poslane, zlyhane)
    return 1 if (zlyhane and not poslane) else 0


if __name__ == "__main__":
    sys.exit(main())
