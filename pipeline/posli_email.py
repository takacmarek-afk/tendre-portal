"""Tyzdenny e-mail. Pre dodavatelov aj pre obce.

Spustenie:
    python posli_email.py                # naozaj posle
    python posli_email.py --nasucho      # nic neposle, len vypise co by poslal
    python posli_email.py --komu ja@x.sk # posle len na tuto adresu (test)

Potrebne premenne:
    SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY   — ako zvysok pipeline
    RESEND_API_KEY                            — novy, treba pridat do Secrets
    ODOSIELATEL   (nepovinne, default "PredTendrom.sk <noreply@predtendrom.sk>")

PRVE SPUSTENIE VZDY NASUCHO. Hromadny e-mail sa neda vratit a prvy dojem
sa neda poslat druhy raz.

CO SA POSIELA
  Dodavatelom: co je NOVE od ich posledneho e-mailu v ich sektore a kraji.
  Obciam:      ktore programy prave teraz rozdavaju peniaze obciam.

CO SA NEPOSIELA
  Prazdny e-mail. Ked pre cloveka nic nove nie je, radsej nepride nic —
  tyzdenny e-mail "tento tyzden nic" je najrychlejsia cesta k odhlaseniu.
"""
import argparse
import logging
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone

import requests
from supabase import create_client

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)-7s %(name)-9s %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("email")

RESEND_URL = "https://api.resend.com/emails"
ODOSIELATEL = os.getenv("ODOSIELATEL",
                        "PredTendrom.sk <noreply@predtendrom.sk>")
ODKAZ_APP = "https://predtendrom.sk/app.html"
ODKAZ_OBCE = "https://predtendrom.sk/obce.html"

# Resend na free plane zvlada 2 e-maily za sekundu. Drzim sa pod tym.
PAUZA_S = 0.6

MAX_POLOZIEK = 8        # viac nez tolko do e-mailu nedavam, nikto to necita
DNI_SPAT = 7            # ked odberatel nema zaznam o poslednom e-maile


# ── HTML ────────────────────────────────────────────────────────────────────

def _bezpecne(t):
    """Escapovanie. Do e-mailu ide obsah z databazy, teda z CRZ — cudzi text."""
    return (str(t if t is not None else "")
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def _eur(v):
    try:
        n = float(v)
    except (TypeError, ValueError):
        return "neuvedená"
    if n <= 0:
        return "neuvedená"
    return f"{n:,.0f}".replace(",", " ") + " €"


def _obal(titulok, uvod, bloky, cta_text, cta_url, odhlasenie):
    """Jednoduchy a spolahlivy e-mail. Ziadne stlpce, ziadne obrazky.

    Tabulkovy layout a inline styly su tu zamerne: Outlook a Gmail ignoruju
    <style> v hlavicke aj vacsinu moderneho CSS. Co vyzera stroho, to dojde
    vsade rovnako.

    ESCAPUJE SA TU, NIE U VOLAJUCEHO. Prvy raz som to mal naopak a test
    ukazal, ze `titulok` a `uvod` islo do HTML surove — volajuci ich totiz
    neescapoval, lebo to bol "nas vlastny text". Dnes by to nikto nezneuzil,
    ale je to presne ten tvar chyby, ktora vybuchne az ked niekto neskor
    do titulku posle nazov zakazky z registra. Funkcia je preto bezpecna
    sama od seba a volajuci si nic pamatat nemusi.
    """
    t = _bezpecne
    casti = []
    for b in bloky:
        zvyr = b.get("zvyraznene")
        casti.append(f"""
        <tr><td style="padding:14px 0;border-bottom:1px solid #e4e8ee;">
          <div style="font:600 15px/1.4 Arial,sans-serif;color:#0f1a2b;">{t(b.get('titul'))}</div>
          <div style="font:14px/1.5 Arial,sans-serif;color:#5a6472;margin-top:4px;">{t(b.get('popis'))}</div>
          {f'<div style="font:600 14px/1.4 Arial,sans-serif;color:#1a56c4;margin-top:6px;">{t(zvyr)}</div>' if zvyr else ''}
        </td></tr>""")

    titulok, uvod = t(titulok), t(uvod)
    cta_text, odhlasenie = t(cta_text), t(odhlasenie)
    # URL nechavam bez escapovania textu, ale beriem len vlastne odkazy.
    # Ziadna hodnota z databazy sa sem nedostane.
    if not str(cta_url).startswith("https://predtendrom.sk"):
        raise ValueError(f"Odkaz v e-maile musi viest na predtendrom.sk, dostal som {cta_url!r}")

    return f"""<!doctype html>
<html lang="sk"><body style="margin:0;padding:0;background:#f5f6f8;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f5f6f8;">
<tr><td align="center" style="padding:24px 12px;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
         style="max-width:560px;background:#ffffff;border:1px solid #e4e8ee;border-radius:8px;">
    <tr><td style="padding:22px 24px 0;">
      <div style="font:700 17px/1.2 Arial,sans-serif;color:#0f1a2b;">
        PredTendrom<span style="color:#1a56c4;">.sk</span></div>
    </td></tr>
    <tr><td style="padding:16px 24px 0;">
      <div style="font:700 20px/1.3 Arial,sans-serif;color:#0f1a2b;">{titulok}</div>
      <div style="font:14px/1.6 Arial,sans-serif;color:#5a6472;margin-top:8px;">{uvod}</div>
    </td></tr>
    <tr><td style="padding:6px 24px 0;">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0">{''.join(casti)}</table>
    </td></tr>
    <tr><td style="padding:22px 24px;">
      <a href="{cta_url}" style="display:inline-block;background:#0f1a2b;color:#ffffff;
         font:600 15px/1 Arial,sans-serif;text-decoration:none;padding:13px 22px;border-radius:6px;">
        {cta_text}</a>
    </td></tr>
    <tr><td style="padding:0 24px 22px;">
      <div style="font:12px/1.6 Arial,sans-serif;color:#8a929e;border-top:1px solid #e4e8ee;padding-top:14px;">
        Údaje pochádzajú z Centrálneho registra zmlúv a zo služby Slovensko.Digital.
        Majú informatívny charakter, pred rozhodnutím si ich overte v zdroji.<br><br>
        {odhlasenie}<br>
        LoveHome s.r.o., Černyševského 40, 851 01 Bratislava, IČO 47 586 362
      </div>
    </td></tr>
  </table>
</td></tr></table></body></html>"""


# ── DODAVATELIA ─────────────────────────────────────────────────────────────

def pre_dodavatela(sb, o, dnes):
    """Co je nove v jeho sektore a kraji od posledneho e-mailu."""
    od = o.get("posledny_email")
    if od:
        od = str(od)[:10]
    else:
        od = (dnes - timedelta(days=DNI_SPAT)).isoformat()

    q = (sb.table("opportunities")
           .select("subject, authority_name, mesto, kraj, price_total, "
                   "effective_to, odhad_vyhlasenia, sector, dni_do_konca")
           .gte("first_seen_at", od)
           .gte("dni_do_konca", 90)
           .order("odhad_vyhlasenia", desc=False)
           .limit(MAX_POLOZIEK))
    if o.get("sektor"):
        q = q.eq("sector", o["sektor"])
    if o.get("kraj"):
        q = q.eq("kraj", o["kraj"])

    try:
        zmluvy = q.execute().data or []
    except Exception as e:
        log.warning("Dopyt na prilezitosti zlyhal pre %s: %s",
                    o.get("email"), e)
        return None

    if not zmluvy:
        return None

    bloky = []
    for z in zmluvy:
        kde = ", ".join(x for x in (z.get("mesto"), z.get("kraj")) if x)
        bloky.append({
            "titul": (z.get("subject") or "")[:140],
            "popis": ((z.get("authority_name") or "")
                      + (f" · {kde}" if kde else "")),
            "zvyraznene": (f"{_eur(z.get('price_total'))} · zmluva končí "
                           f"{z.get('effective_to') or '—'}"),
        })

    kde_text = o.get("kraj") or "celom Slovensku"
    co_text = o.get("sektor") or "vašich sektoroch"
    return {
        "titulok": f"{len(zmluvy)} nových príležitostí",
        "uvod": (f"Od posledného e-mailu pribudlo v {co_text} "
                 f"({kde_text}) toto. Pri každej zákazke zostáva "
                 f"aspoň 90 dní do konca zmluvy, takže je na čo sa pripraviť."),
        "bloky": bloky,
        "cta_text": "Otvoriť portál",
        "cta_url": ODKAZ_APP,
        "odhlasenie": ('Filtre a odhlásenie nájdete v portáli po prihlásení, '
                       'v paneli „Nech vám to chodí samo".'),
    }


# ── OBCE ────────────────────────────────────────────────────────────────────

def pre_obec(sb, o, dnes):
    """Ktore programy prave teraz rozdavaju peniaze obciam."""
    try:
        programy = (sb.table("aktivne_programy")
                      .select("poskytovatel, zmluv_30d, zmluv_90d, obci_90d, "
                              "objem_90d, median_dotacie, posledna_zmluva")
                      .order("objem_90d", desc=True)
                      .limit(MAX_POLOZIEK).execute().data or [])
    except Exception as e:
        log.warning("Dopyt na aktivne programy zlyhal: %s", e)
        return None

    if not programy:
        return None

    bloky = []
    for p in programy:
        bloky.append({
            "titul": p.get("poskytovatel"),
            "popis": (f"Za 90 dní podpísal {p.get('zmluv_90d') or 0} zmlúv "
                      f"s {p.get('obci_90d') or 0} obcami"
                      f" · naposledy {p.get('posledna_zmluva') or '—'}"),
            "zvyraznene": (f"Rozdelil {_eur(p.get('objem_90d'))}, "
                           f"typicky {_eur(p.get('median_dotacie'))} na obec"),
        })

    return {
        "titulok": "Kto práve teraz rozdáva peniaze obciam",
        "uvod": ("Toto nie je zoznam výziev, je to niečo istejšie: "
                 "poskytovatelia, ktorí za posledné tri mesiace naozaj "
                 "podpísali zmluvy s obcami. Ak niektorý rozdáva na to, "
                 "čo potrebujete, má zmysel obrátiť sa priamo na neho."),
        "bloky": bloky,
        "cta_text": "Pozrieť podrobnosti a sprostredkovateľov",
        "cta_url": ODKAZ_OBCE,
        "odhlasenie": ('Odhlásiť sa môžete odpoveďou na tento e-mail '
                       'so slovom „odhlásiť".'),
    }


# ── ODOSIELANIE ─────────────────────────────────────────────────────────────

def posli(kluc, komu, predmet, html, nasucho):
    if nasucho:
        log.info("NASUCHO -> %s | %s | %s znakov HTML", komu, predmet, len(html))
        return True
    try:
        r = requests.post(RESEND_URL, timeout=30,
                          headers={"Authorization": f"Bearer {kluc}",
                                   "Content-Type": "application/json"},
                          json={"from": ODOSIELATEL, "to": [komu],
                                "subject": predmet, "html": html})
    except requests.RequestException as e:
        log.error("%s: siet zlyhala (%s)", komu, type(e).__name__)
        return False

    if r.status_code in (200, 201):
        return True
    # 422 byva neplatna adresa, 429 prekroceny limit. Ani jedno nema
    # zhodit cely beh — ostatni odberatelia za to nemozu.
    log.error("%s: HTTP %s %s", komu, r.status_code, r.text[:200])
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nasucho", action="store_true",
                    help="nic neposle, len vypise co by poslal")
    ap.add_argument("--komu", help="posle len na tuto adresu (test)")
    args = ap.parse_args()

    url = os.getenv("SUPABASE_URL")
    servis = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    kluc = os.getenv("RESEND_API_KEY")
    if not (url and servis):
        log.error("Chyba SUPABASE_URL alebo SUPABASE_SERVICE_ROLE_KEY.")
        return 1
    if not kluc and not args.nasucho:
        log.error("Chyba RESEND_API_KEY. Pridaj ho do GitHub Secrets, "
                  "alebo spusti s --nasucho.")
        return 1

    sb = create_client(url, servis)
    dnes = date.today()

    odberatelia = []
    try:
        odberatelia += [dict(x, _typ="dodavatel") for x in
                        (sb.table("odber").select("*").eq("chce_email", True)
                           .execute().data or [])]
    except Exception as e:
        log.warning("Tabulka odber sa necitala: %s", e)
    try:
        odberatelia += [dict(x, _typ="obec") for x in
                        (sb.table("odber_obce").select("*")
                           .eq("potvrdeny", True).execute().data or [])]
    except Exception as e:
        log.warning("Tabulka odber_obce sa necitala: %s", e)

    if args.komu:
        odberatelia = [o for o in odberatelia
                       if (o.get("email") or "").lower() == args.komu.lower()]
        if not odberatelia:
            # Test na adresu, ktora v databaze nie je: posleme obecny prehlad.
            odberatelia = [{"email": args.komu, "_typ": "obec",
                            "sektor": None, "kraj": None}]

    log.info("Odberatelov: %s (dodavatelia %s, obce %s)%s",
             len(odberatelia),
             sum(1 for o in odberatelia if o["_typ"] == "dodavatel"),
             sum(1 for o in odberatelia if o["_typ"] == "obec"),
             "  [NASUCHO]" if args.nasucho else "")
    if not odberatelia:
        log.info("Niet komu posielat. Koniec.")
        return 0

    poslane = preskocene = zlyhane = 0
    for o in odberatelia:
        komu = (o.get("email") or "").strip()
        if not komu or "@" not in komu:
            preskocene += 1
            continue

        obsah = (pre_obec(sb, o, dnes) if o["_typ"] == "obec"
                 else pre_dodavatela(sb, o, dnes))
        if not obsah:
            # Zamerne neposielam prazdny e-mail.
            log.info("%s: nic nove, neposielam", komu)
            preskocene += 1
            continue

        html = _obal(obsah["titulok"], obsah["uvod"], obsah["bloky"],
                     obsah["cta_text"], obsah["cta_url"], obsah["odhlasenie"])
        predmet = f"PredTendrom.sk — {obsah['titulok']}"

        if posli(kluc, komu, predmet, html, args.nasucho):
            poslane += 1
            if not args.nasucho:
                tab = "odber_obce" if o["_typ"] == "obec" else "odber"
                try:
                    sb.table(tab).update(
                        {"posledny_email": datetime.now(timezone.utc).isoformat()}
                    ).eq("email", komu).execute()
                except Exception as e:
                    # Horsie nez nezapisat je poslat to iste o tyzden znova,
                    # ale zhodit beh kvoli tomu nema zmysel.
                    log.warning("%s: posledny_email sa nezapisal (%s)", komu, e)
        else:
            zlyhane += 1
        time.sleep(PAUZA_S)

    log.info("Hotovo: poslanych %s, preskocenych %s, zlyhanych %s",
             poslane, preskocene, zlyhane)
    if zlyhane and not poslane:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
