"""Tyzdenny prehlad cisel pre Mareka e-mailom (11. 11. 2026).

Kazdy pondelok: co sa za 7 dni stalo v oslovovani firiem a obci, kto klikol
(podla kroku a textu e-mailu), nove skusky, pilot, platby, dopyty obci
a navstevnost. Posiela cez Zoho na info@predtendrom.sk. Do logu len suhrn.

    python tyzdenny_report.py [--nasucho] [--dni 7]

Premenne: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, ZOHO_SMTP_PASSWORD.
"""
import argparse
import os
import re
import smtplib
import ssl
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

from supabase import create_client

from strankuj import vsetky


def pocet(sb, tabulka, filtre, stlpec="*"):
    try:
        return filtre(sb.table(tabulka).select(stlpec, count="exact")).limit(1).execute().count or 0
    except Exception as e:
        return f"? ({type(e).__name__})"


def zdroj_navstevy(n):
    if n.get("utm_source"):
        return n["utm_source"] + (f"/{n['utm_medium']}" if n.get("utm_medium") else "")
    if n.get("referrer"):
        d = re.sub(r"^https?://([^/]+).*$", r"\1", n["referrer"]).removeprefix("www.").removeprefix("m.")
        if "predtendrom" in d:
            return "(interný)"
        if "google" in d:
            return "google"
        if "facebook" in d:
            return "facebook"
        return d
    return "(priamo)"



def zostav(sb, dni):
    teraz = datetime.now(timezone.utc)
    od = (teraz - timedelta(days=dni)).isoformat()
    r = []

    # ── 1. Lievik ─────────────────────────────────────────────────────────
    nav = vsetky(lambda a, b: sb.table("navstevy")
                 .select("id,cesta,referrer,session_id,utm_source,utm_medium,utm_campaign,created_at")
                 .gte("created_at", od).order("id").range(a, b).execute())
    sess = lambda rows: len({n["session_id"] or n["id"] for n in rows})
    z_emailu_firmy = [n for n in nav if n.get("utm_source") == "email" and n.get("utm_medium") == "oslovenie"]
    z_emailu_obce = [n for n in nav if n.get("utm_source") == "email" and n.get("utm_medium") == "obce"]
    ud = vsetky(lambda a, b: sb.table("udalosti").select("id,nazov,utm_source").gte("created_at", od)
                .order("id").range(a, b).execute())
    udal = Counter(u["nazov"] for u in ud)

    r.append(f"PREDTENDROM.SK — TÝŽDENNÝ PREHĽAD ({(teraz - timedelta(days=dni)):%d. %m.} – {teraz:%d. %m. %Y})")
    r.append("")
    r.append("1. LIEVIK FIRMY")
    r.append(f"   Studené e-maily odoslané:      {pocet(sb, 'oslovenie_firiem_odoslane', lambda q: q.eq('stav', 'odoslane').gte('odoslane_at', od), 'id')}")
    r.append(f"   Návštevy z týchto e-mailov:    {sess(z_emailu_firmy)}")
    r.append(f"   Klik „Vyskúšať“ (celý web):    {udal.get('klik_vyskusat', 0)}")
    r.append(f"   Odoslaný prihlasovací e-mail:  {udal.get('odoslany_prihlasovaci_email', 0)}")
    r.append(f"   Nové firmy (skúška):           {pocet(sb, 'events', lambda q: q.eq('typ', 'org_vytvorena').gte('created_at', od))}")
    r.append(f"   Pilot prijatý:                 {pocet(sb, 'events', lambda q: q.eq('typ', 'pilot_prijaty').gte('created_at', od))}")
    r.append(f"   Platba začatá / zaplatená:     {udal.get('begin_checkout', 0)} / "
             f"{pocet(sb, 'events', lambda q: q.eq('typ', 'platba_prijata').gte('created_at', od))}")
    r.append(f"   Odpovede (aj automatické a nedoručené): {pocet(sb, 'oslovenie_odpovede', lambda q: q.gte('spracovane_at', od), 'message_id')}, "
             f"z toho od človeka: {pocet(sb, 'oslovenie_odpovede', lambda q: q.gte('spracovane_at', od).in_('typ', ['nie', 'rucne', 'ine']), 'message_id')}"
             f" (odhlásené firmy spolu: {pocet(sb, 'oslovenie_firiem_kontakty', lambda q: q.not_.is_('odhlasene_at', 'null'), 'ico')})")

    # kliky podla kampane (krok/variant) — ktory e-mail funguje
    odosl = vsetky(lambda a, b: sb.table("oslovenie_firiem_odoslane").select("id,krok,variant,odoslane_at")
                   .eq("stav", "odoslane").gte("odoslane_at", od).order("id").range(a, b).execute())
    po_kroku = Counter(f"k{o['krok']}{(o.get('variant') or '').lower()}" for o in odosl)
    kliky = defaultdict(set)
    for n in z_emailu_firmy:
        m = re.search(r"k(\d)([ab]?)", n.get("utm_campaign") or "")
        kliky[f"k{m.group(1)}{m.group(2)}" if m else "?"].add(n["session_id"] or n["id"])
    if po_kroku or kliky:
        r.append("   Podľa kroku a variantu (odoslané → návštevy):")
        for k in sorted(set(po_kroku) | set(kliky)):
            r.append(f"     {k:5s} {po_kroku.get(k, 0):4d} → {len(kliky.get(k, ())):3d}")

    # ── 2. Obce ────────────────────────────────────────────────────────────
    r.append("")
    r.append("2. KAMPAŇ PRE OBCE")
    ko = vsetky(lambda a, b: sb.table("kampan_obce_odoslane").select("id,segment,stav,odoslane_at")
                .gte("odoslane_at", od).order("id").range(a, b).execute())
    r.append(f"   Odoslané za týždeň:            {sum(1 for o in ko if o['stav'] == 'odoslane')}"
             f" (chyby {sum(1 for o in ko if o['stav'] == 'chyba')}; spolu od začiatku "
             f"{pocet(sb, 'kampan_obce_odoslane', lambda q: q.eq('stav', 'odoslane'), 'id')})")
    seg = Counter(o["segment"] for o in ko if o["stav"] == "odoslane")
    if seg:
        r.append("   Podľa dôvodu: " + ", ".join(f"{k} {v}" for k, v in seg.most_common()))
    kl_obce = defaultdict(set)
    for n in z_emailu_obce:
        kl_obce[(n.get("utm_campaign") or "?").split("-", 1)[-1]].add(n["session_id"] or n["id"])
    r.append(f"   Návštevy z e-mailov obciam:    {sess(z_emailu_obce)}"
             + (" (" + ", ".join(f"{k} {len(v)}" for k, v in sorted(kl_obce.items(), key=lambda x: -len(x[1]))) + ")" if kl_obce else ""))
    r.append(f"   Odhlásené obce spolu:          {pocet(sb, 'kampan_obce_kontakty', lambda q: q.not_.is_('odhlasene_at', 'null'), 'ico')}")
    r.append(f"   Nové účty obcí:                {pocet(sb, 'obce_ucty', lambda q: q.gte('created_at', od), 'id')}")
    r.append(f"   Nové dopyty obcí:              {pocet(sb, 'dopyty', lambda q: q.gte('created_at', od), 'id')}"
             f" (odpovede firiem/poradcov: {pocet(sb, 'reakcie', lambda q: q.gte('created_at', od), 'id')})")

    # ── 3. Navstevnost ─────────────────────────────────────────────────────
    r.append("")
    r.append("3. NÁVŠTEVNOSŤ WEBU")
    r.append(f"   Návštevy: {sess(nav)} (zobrazení {len(nav)})")
    zdroje = defaultdict(set)
    stranky = defaultdict(set)
    for n in nav:
        zdroje[zdroj_navstevy(n)].add(n["session_id"] or n["id"])
        c = n.get("cesta") or "/"
        c = re.sub(r"^/(eurofondy|konciace-zmluvy|obce)/.*", r"/\1/…", c)
        stranky[c].add(n["session_id"] or n["id"])
    r.append("   Zdroje: " + ", ".join(f"{k} {len(v)}" for k, v in sorted(zdroje.items(), key=lambda x: -len(x[1]))[:10]))
    r.append("   Stránky: " + ", ".join(f"{k} {len(v)}" for k, v in sorted(stranky.items(), key=lambda x: -len(x[1]))[:10]))

    # ── 4. Prevadzka ───────────────────────────────────────────────────────
    r.append("")
    r.append("4. PREVÁDZKA")
    try:
        from zdravie_dat import skontroluj
        for z, vek, limit, _, p in skontroluj(sb, teraz.date()):
            r.append(f"   {z}: posledný záznam pred {vek} dňami" + (f" — PROBLÉM ({p})" if p else " — OK"))
    except Exception as e:
        r.append(f"   Kontrola dát zlyhala: {type(e).__name__}")
    r.append("")
    r.append("-- automatický prehľad PredTendrom.sk (Claude)")
    return "\n".join(r)


def posli(heslo, text):
    m = EmailMessage()
    m["From"], m["To"] = "PredTendrom.sk <marek@predtendrom.sk>", "info@predtendrom.sk"
    m["Subject"] = f"PredTendrom: týždenný prehľad {datetime.now():%d. %m. %Y}"
    m["Date"], m["Message-ID"] = formatdate(localtime=True), make_msgid(domain="predtendrom.sk")
    m["Auto-Submitted"] = "auto-generated"
    m.set_content(text)
    with smtplib.SMTP_SSL("smtp.zoho.eu", 465, timeout=30, context=ssl.create_default_context()) as s:
        s.login("marek@predtendrom.sk", heslo)
        s.send_message(m)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--nasucho", action="store_true")
    ap.add_argument("--dni", type=int, default=7)
    a = ap.parse_args(argv)
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
    text = zostav(sb, a.dni)
    # do verejneho logu len prvy blok (cisla, ziadne mena)
    print("\n".join(l for l in text.splitlines() if not l.startswith("   Stránky")))
    if a.nasucho:
        return 0
    posli(os.environ["ZOHO_SMTP_PASSWORD"], text)
    print("Poslane na info@predtendrom.sk.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
