"""Strazca limitu e-mailov cez Resend (10. 11. 2026).

Resend Free: 100 e-mailov za den a 3 000 za mesiac. Cez Resend idu e-maily
pouzivatelom (prehlady, onboarding, upozornenia), nie studene e-maily (Zoho).
Skript denne spocita odoslane e-maily za poslednych 24 hodin a 30 dni
(Resend API /emails) a ked je ktorykolvek pocet aspon na 70 % limitu, posle
Marekovi upozornenie na info@predtendrom.sk cez Zoho (nie cez Resend, ten
moze byt prave plny).

    python limit_emailov.py --nasucho   # len vypise pocty
    python limit_emailov.py

Premenne: RESEND_API_KEY, ZOHO_SMTP_PASSWORD.
"""
import argparse
import os
import smtplib
import ssl
import sys
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

import requests

LIMIT_DEN, LIMIT_MESIAC = 100, 3000
PRAH = 0.7
KOMU = "info@predtendrom.sk"
OD = "PredTendrom.sk <marek@predtendrom.sk>"
MAX_STRAN = 40   # 40 x 100 = 4 000 > mesacny limit


def _cas(t):
    return datetime.fromisoformat(str(t).replace(" ", "T").replace("Z", "+00:00")[:32])


def spocitaj(kluc, teraz=None, _get=requests.get):
    """-> (za 24 h, za 30 dni). Strankuje Resend /emails od najnovsich."""
    teraz = teraz or datetime.now(timezone.utc)
    den, mesiac = teraz - timedelta(hours=24), teraz - timedelta(days=30)
    n24 = n30 = 0
    po = None
    for _ in range(MAX_STRAN):
        params = {"limit": 100}
        if po:
            params["after"] = po
        r = _get("https://api.resend.com/emails", params=params, timeout=30,
                 headers={"Authorization": f"Bearer {kluc}"})
        r.raise_for_status()
        d = r.json()
        data = d.get("data") or []
        for e in data:
            c = _cas(e["created_at"])
            if c.tzinfo is None:
                c = c.replace(tzinfo=timezone.utc)
            if c >= mesiac:
                n30 += 1
                if c >= den:
                    n24 += 1
            else:
                return n24, n30
        if not d.get("has_more") or not data:
            break
        po = data[-1]["id"]
    return n24, n30


def z_hlaviciek(kluc, _post=requests.post, _get=requests.get):
    """-> (za den, za mesiac) alebo None. Kluc s pravom len na posielanie nesmie
    citat zoznam e-mailov, ale Resend vracia spotrebu v hlavickach odpovede
    (x-resend-daily-quota, x-resend-monthly-quota). Skusime /usage, potom
    neplatny POST /emails bez prijemcu (nic sa neposle, vrati 422)."""
    h = {"Authorization": f"Bearer {kluc}"}
    for r in (lambda: _get("https://api.resend.com/usage", headers=h, timeout=30),
              lambda: _post("https://api.resend.com/emails", headers=h, json={}, timeout=30)):
        try:
            odp = r()
        except requests.RequestException:
            continue
        if odp.status_code == 200 and "usage" in odp.url:
            try:
                e = odp.json()["emails"]
                return int(e["daily"]["used"]), int(e["monthly"]["used"])
            except (KeyError, TypeError, ValueError):
                pass
        d, m = odp.headers.get("x-resend-daily-quota"), odp.headers.get("x-resend-monthly-quota")
        if m is not None:
            return int(d or 0), int(m)
    return None


def sprava(n24, n30):
    """-> (predmet, text) alebo None, ak sme pod prahom."""
    if n24 < PRAH * LIMIT_DEN and n30 < PRAH * LIMIT_MESIAC:
        return None
    return ("PredTendrom: blížime sa k limitu e-mailov (Resend)",
            f"Za posledných 24 hodín odišlo {n24} e-mailov z denného limitu {LIMIT_DEN} "
            f"a za 30 dní {n30} z mesačného limitu {LIMIT_MESIAC} (bezplatný plán Resend).\n\n"
            "Po prekročení limitu Resend ďalšie e-maily používateľom neodošle (prehľady, upozornenia, "
            "e-maily počas skúšky). Riešenie: v Resend (resend.com, Settings, Billing) prejsť na plán Pro "
            "(asi 20 USD mesačne, 50 000 e-mailov). Nič iné netreba meniť.\n\n"
            "Studených e-mailov sa to netýka, tie idú cez Zoho.\n\n-- automatická kontrola PredTendrom.sk")


def posli(heslo, predmet, text):
    m = EmailMessage()
    m["From"], m["To"], m["Subject"] = OD, KOMU, predmet
    m["Date"], m["Message-ID"] = formatdate(localtime=True), make_msgid(domain="predtendrom.sk")
    m["Auto-Submitted"] = "auto-generated"
    m.set_content(text)
    with smtplib.SMTP_SSL("smtp.zoho.eu", 465, timeout=30, context=ssl.create_default_context()) as s:
        s.login("marek@predtendrom.sk", heslo)
        s.send_message(m)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--nasucho", action="store_true")
    a = ap.parse_args(argv)
    kluc = os.environ["RESEND_API_KEY"]
    try:
        n24, n30 = spocitaj(kluc)
    except requests.HTTPError:
        z = z_hlaviciek(kluc)
        if z is None:
            print("::warning title=Limit e-mailov::Resend nevratil spotrebu (kluc len na posielanie).")
            return 0
        n24, n30 = z
    print(f"Resend: za 24 h {n24}/{LIMIT_DEN}, za 30 dni {n30}/{LIMIT_MESIAC}")
    print(f"::notice title=Limit e-mailov::24 h {n24}/{LIMIT_DEN}, 30 dni {n30}/{LIMIT_MESIAC}")
    s = sprava(n24, n30)
    if s and not a.nasucho:
        posli(os.environ["ZOHO_SMTP_PASSWORD"], *s)
        print("Upozornenie poslane.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
