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

VOLITELNE: SLACK/TEAMS
  Ak ma odberatel (len dodavatelia, stlpec odber.webhook_url) vyplneny
  webhook, dostane rovnaky obsah aj tam — ako doplnok k e-mailu, nie
  nahradu. Zlyhanie webhooku nema ovplyvnit odosielanie e-mailu.

VOLITELNE: OSOBNA RELEVANCIA (#7, 17.9.2026)
  Ak ma odberatel vyplnene odber.moje_ico A NEMA naraz nastavene aj sektor
  aj kraj (teda aspon jedna os je "vsetko"), vyber top MAX_POLOZIEK sa
  nerobi len chronologicky, ale podla relevancie — rovnaky princip ako
  v app.html (bodRelevancie): zhoda s explicitne nastavenym sektorom/krajom
  a zhoda s vlastnou historiou firmy (dodavatelia.hlavny_sektor,
  priemerna_zmluva_eur). Explicitne nastaveny sektor/kraj OSTAVA tvrdym
  filtrom — firma, ktora si ho vedome zvolila, nema v e-maile dostat nieco
  ine. Bez moje_ico (dnes vsetci existujuci odberatelia) sa sprava presne
  ako doteraz.
"""
import argparse
import logging
import math
import os
import re
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

# Siria vzorka kandidatov, z ktorej sa VYBERA top MAX_POLOZIEK podla
# relevancie (#7, 17.9.2026) — pouziva sa len ked firma vyplnila moje_ico
# a nema oba filtre (sektor AJ kraj) nastavene naraz (viz pouzit_relevanciu
# v pre_dodavatela). Bez tejto sirsej vzorky by relevancia nemala z coho
# vyberat — dostali by sme len prvych 8 podla odhad_vyhlasenia tak ci tak.
KANDIDATOV_NA_VYBER = 60

# Odkedy beha workflow DENNE (predtym len tyzdenne, viz email.yml), tyzdenny
# odberatel by bez tohto dostaval mail prakticky kazdy den, len co pribudne
# cokolvek nove v jeho sektore/kraji — pre_dodavatela() totiz posiela vzdy,
# ked je "nieco nove od posledneho mailu", bez ohladu na to, ako casto beh
# skutocne bezi. 6, nie 7: rezerva pred tyzdennym cyklom, aby hodinovy posun
# medzi behmi nikdy nevynechal riadny termin.
MIN_DNI_TYZDENNE = 6


# ── HTML ────────────────────────────────────────────────────────────────────

def _bezpecne(t):
    """Escapovanie. Do e-mailu ide obsah z databazy, teda z CRZ — cudzi text."""
    return (str(t if t is not None else "")
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def _cislo_kladne(v) -> bool:
    """Ma zmluva uvedenu kladnu cenu? Cena 0 v CRZ znamena ramcovu dohodu."""
    try:
        return float(v) > 0
    except (TypeError, ValueError):
        return False


def _eur(v):
    if not _cislo_kladne(v):
        return "neuvedená"
    return f"{float(v):,.0f}".replace(",", " ") + " €"


def platny_webhook(url) -> bool:
    """Zakladna kontrola predtym, nez sa nan nieco posle: musi to vyzerat
    ako https URL bez medzier. Nekontroluje dosiahnutelnost — to sa zisti
    az pri samotnom posielani a zlyhanie tam nezhadzuje beh."""
    if not url:
        return False
    url = str(url).strip()
    return bool(re.fullmatch(r"https://\S+", url)) and len(url) <= 500


def _bezpecne_text(t):
    """Escapovanie pre webhook (Slack aj Teams). Rovnaky dovod ako
    _bezpecne(): obsah je z CRZ, cudzi text. Slack pouziva &, <, > na
    odkazy a zmienky, preto ich treba escapovat aj v obycajnom texte."""
    return (str(t if t is not None else "")
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


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

def _cislo(v):
    """Bezpecny prevod na float. None namiesto vynimky aj namiesto 0 —
    0 by v _relevancii znamenalo "cena 0", nie "cena chyba", a to su
    v CRZ dve rozne veci (ramcova dohoda vs. neznamy udaj)."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None  # f == f vylucuje NaN


def _moj_profil(sb, ico):
    """Vlastny profil firmy z uz existujucej `dodavatelia` (hlavny sektor,
    priemerna hodnota zmluvy) — ziadna nova agregacia, rovnaky zdroj ako
    v app.html. Prazdny vysledok (RLS, neznamy ICO) vrati None, nie chybu."""
    try:
        r = (sb.table("dodavatelia")
               .select("hlavny_sektor, priemerna_zmluva_eur")
               .eq("supplier_cin", ico).limit(1).execute().data)
        return r[0] if r else None
    except Exception as e:
        log.warning("Vlastny profil (moje_ico=%s) sa nepodarilo zistit: %s",
                    ico, e)
        return None


def _relevancia(z, o, profil):
    """Rovnaky princip ako bodRelevancie() v app.html (#7, 17.9.2026):
    doplnkovy bonus k tomu, co uz o zakazke vieme, nie novy nezavisly
    vypocet. Vahy su zamerne rovnake ako na webe, aby sa poradie v appke
    a vyber do e-mailu nerozchadzali bez dovodu."""
    b = 0.0
    if o.get("sektor") and z.get("sector") == o["sektor"]:
        b += 15
    if o.get("kraj") and z.get("kraj") == o["kraj"]:
        b += 10
    if profil and profil.get("hlavny_sektor") and z.get("sector") == profil["hlavny_sektor"]:
        b += 20
    vlastna_cena = _cislo(profil.get("priemerna_zmluva_eur")) if profil else None
    cena = _cislo(z.get("price_total"))
    if vlastna_cena and vlastna_cena > 0 and cena and cena > 0:
        b += 15 / (1 + abs(math.log10(cena / vlastna_cena)))
    return b


def pre_dodavatela(sb, o, dnes):
    """Co je nove v jeho sektore a kraji od posledneho e-mailu.

    Ak firma vyplnila vlastne ICO a nema OBA filtre (sektor aj kraj)
    nastavene naraz, vyber top MAX_POLOZIEK sa robi z sirsej vzorky podla
    relevancie namiesto ciste chronologicky — viz _relevancia() a docstring
    modulu. Explicitne nastaveny sektor/kraj zostava tvrdym SQL filtrom aj
    tu, nezavisly na relevancii.
    """
    od = o.get("posledny_email")
    if od:
        od = str(od)[:10]
    else:
        od = (dnes - timedelta(days=DNI_SPAT)).isoformat()

    pouzit_relevanciu = bool(o.get("moje_ico")) and not (o.get("sektor") and o.get("kraj"))
    limit = KANDIDATOV_NA_VYBER if pouzit_relevanciu else MAX_POLOZIEK

    q = (sb.table("opportunities")
           .select("subject, authority_name, mesto, kraj, price_total, "
                   "effective_to, odhad_vyhlasenia, sector, dni_do_konca")
           .gte("first_seen_at", od)
           .gte("dni_do_konca", 90)
           .order("odhad_vyhlasenia", desc=False)
           .limit(limit))
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

    if pouzit_relevanciu and len(zmluvy) > MAX_POLOZIEK:
        profil = _moj_profil(sb, o["moje_ico"])
        zmluvy = sorted(zmluvy, key=lambda z: _relevancia(z, o, profil), reverse=True)
        zmluvy = zmluvy[:MAX_POLOZIEK]
        # Naspat na chronologicke poradie na citanie — relevancia rozhodla
        # LEN o tom, KTORE polozky sa do e-mailu dostanu, nie v akom
        # poradi tam stoja. "Najskorsi tender hore" ostava citatelne aj
        # ked bol vyber urceny inak, nez predtym.
        zmluvy.sort(key=lambda z: z.get("odhad_vyhlasenia") or "9999-99-99")

    bloky = []
    for z in zmluvy:
        kde = ", ".join(x for x in (z.get("mesto"), z.get("kraj")) if x)
        bloky.append({
            "titul": (z.get("subject") or "")[:140],
            "popis": ((z.get("authority_name") or "")
                      + (f" · {kde}" if kde else "")),
            # Cena 0 je v CRZ bezna: znamena ramcovu dohodu, kde sa sutazi
            # o jednotkove ceny, nie o celkovu sumu. Odmerane: 28,8 %
            # prilezitosti. V e-maile s osmimi polozkami by pat riadkov
            # s holym "neuvedena" vyzeralo ako diera v datach — pritom je
            # to informacia. Preto to aj povieme.
            "zvyraznene": (
                (f"{_eur(z.get('price_total'))} · "
                 if _cislo_kladne(z.get("price_total"))
                 else "Rámcová dohoda, súťaží sa o jednotkové ceny · ")
                + f"zmluva končí {z.get('effective_to') or '—'}"),
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


def _nacitaj_pro_org(sb) -> "set | None":
    """Mnozina org_id s Pro pristupom, nacitana naraz (nie RPC na kazdeho
    odberatela zvlast). Rovnaka logika ako public.ma_pro_pre_org() /
    public.ma_pro() v 08_zadarmo.sql a 25_odber_pro_gating.sql — service_role
    v pipeline nema auth.uid(), preto sa pocita tu, nie cez RLS.

    Navratova hodnota None = "vsetci maju Pro" (otvorene obdobie,
    je_zadarmo() vracia true) — zjednodusenie volania na strane volajuceho.
    """
    try:
        zadarmo = sb.rpc("je_zadarmo", {}).execute().data
    except Exception as e:
        log.warning("je_zadarmo() sa nedalo zistit (%s), predpokladam False.", e)
        zadarmo = False
    if zadarmo:
        return None
    try:
        subs = sb.table("subscriptions").select(
            "org_id, plan, stav, trial_konci").execute().data or []
    except Exception as e:
        log.warning("Tabulka subscriptions sa necitala: %s", e)
        return set()
    teraz = datetime.now(timezone.utc)
    pro = set()
    for s in subs:
        if s.get("plan") not in ("trial", "pro"):
            continue
        aktivne = s.get("stav") == "aktivne"
        if not aktivne and s.get("stav") == "trial":
            tc = s.get("trial_konci")
            if tc:
                try:
                    tc_dt = datetime.fromisoformat(str(tc).replace("Z", "+00:00"))
                    aktivne = tc_dt > teraz
                except ValueError:
                    aktivne = False
        if aktivne and s.get("org_id"):
            pro.add(s["org_id"])
    return pro


def pripraveny_na_dalsi(o: dict, ma_pro: bool = True) -> bool:
    """Tyzdenny odberatel je na rade najskor MIN_DNI_TYZDENNE dni po
    predoslom maile. Denny odberatel (alebo ten bez zaznamu frekvencie —
    povodni odberatelia pred migraciou 20 default na 'tyzdenne' v databaze,
    toto je len poistka, ked by stlpec chybal) je na rade vzdy.

    `ma_pro`: denny digest je od migracie 25 vyhoda Growth planu (17.9.2026).
    RLS to zabrani nastavit nanovo bez Pro, ale stary riadok organizacie,
    ktora medzitym prisla o Pro, by service_role kluc (ten RLS obchadza)
    inak poslal dalej — preto sa tu 'denne' bez Pro ticho spravi ako
    'tyzdenne', rovnaky degradacny vzor ako inde v projekte (napr. chybajuce
    moje_ico), nie tvrde zablokovanie odberu.
    """
    frekvencia = o.get("frekvencia") or "tyzdenne"
    if frekvencia == "denne" and not ma_pro:
        frekvencia = "tyzdenne"
    if frekvencia != "tyzdenne":
        return True
    posledny = o.get("posledny_email")
    if not posledny:
        return True
    try:
        posledny_dt = datetime.fromisoformat(str(posledny).replace("Z", "+00:00"))
    except ValueError:
        return True
    return (datetime.now(timezone.utc) - posledny_dt).days >= MIN_DNI_TYZDENNE


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


def posli_webhook(url, obsah, nasucho):
    """Posle rovnaky obsah ako e-mail na Slack alebo Teams incoming webhook.
    Format podla domeny: hooks.slack.com pouziva jednoduchy Slack text
    payload, vsetko ostatne (Teams incoming webhook connector) pouziva
    MessageCard JSON. Doplnkovy kanal -- zlyhanie tu nesmie ovplyvnit
    odosielanie e-mailu ani zhodit cely beh.
    """
    polozky = obsah["bloky"][:MAX_POLOZIEK]
    if "hooks.slack.com" in url:
        riadky = "\n".join(
            f"• *{_bezpecne_text(b['titul'])}* — {_bezpecne_text(b['popis'])}\n"
            f"   {_bezpecne_text(b['zvyraznene'])}"
            for b in polozky
        )
        text = (f"*{_bezpecne_text(obsah['titulok'])}*\n{_bezpecne_text(obsah['uvod'])}"
               f"\n\n{riadky}\n\n<{obsah['cta_url']}|{_bezpecne_text(obsah['cta_text'])}>")
        payload = {"text": text}
    else:
        telo = "\n\n".join(
            f"**{_bezpecne_text(b['titul'])}**  \n{_bezpecne_text(b['popis'])}  \n"
            f"{_bezpecne_text(b['zvyraznene'])}"
            for b in polozky
        )
        payload = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "summary": obsah["titulok"],
            "title": obsah["titulok"],
            "text": (f"{_bezpecne_text(obsah['uvod'])}\n\n{telo}\n\n"
                    f"[{_bezpecne_text(obsah['cta_text'])}]({obsah['cta_url']})"),
        }

    if nasucho:
        log.info("NASUCHO webhook -> %s... | %s znakov", url[:32], len(str(payload)))
        return True
    try:
        r = requests.post(url, timeout=15, json=payload)
    except requests.RequestException as e:
        log.warning("webhook %s...: siet zlyhala (%s)", url[:32], type(e).__name__)
        return False
    if r.status_code in (200, 201, 204):
        return True
    log.warning("webhook %s...: HTTP %s %s", url[:32], r.status_code, r.text[:200])
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nasucho", action="store_true",
                    help="nic neposle, len vypise co by poslal")
    ap.add_argument("--komu", help="posle len na tuto adresu (test)")
    args = ap.parse_args()

    # `--komu` prichadza z rucneho vstupu vo workflowe, takze mu neverim.
    # Nechcem, aby sa cokolvek necakane dostalo do pola "to" v Resende
    # alebo do logu. Adresa musi vypadat ako adresa, inak koniec.
    if args.komu is not None:
        args.komu = args.komu.strip()
        if not re.fullmatch(r"[^@\s,;<>\"]+@[^@\s,;<>\"]+\.[A-Za-z]{2,}",
                            args.komu):
            log.error("--komu nie je platna e-mailova adresa. Nepokracujem.")
            return 1

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
    pro_org = _nacitaj_pro_org(sb)  # None = vsetci (otvorene obdobie)

    def _ma_pro(org_id) -> bool:
        return pro_org is None or (org_id in pro_org)

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

        if (o["_typ"] == "dodavatel"
                and not pripraveny_na_dalsi(o, _ma_pro(o.get("org_id")))):
            preskocene += 1
            continue

        obsah = (pre_obec(sb, o, dnes) if o["_typ"] == "obec"
                 else pre_dodavatela(sb, o, dnes))
        if not obsah:
            # Zamerne neposielam prazdny e-mail.
            log.info("%s: nic nove, neposielam", komu)
            preskocene += 1
            continue

        # Doplnkovy kanal, len dodavatelia (stlpec je na `odber`, nie
        # `odber_obce`), nezavisly od uspechu e-mailu nizsie.
        if (o["_typ"] == "dodavatel" and platny_webhook(o.get("webhook_url"))
                and _ma_pro(o.get("org_id"))):
            posli_webhook(o["webhook_url"], obsah, args.nasucho)

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
