"""Denna straz cerstvosti dat (audit 10. 11. 2026).

Pre kazdy zdroj zisti datum posledneho zaznamu. Ked je starsi nez limit,
posle Marekovi e-mail na info@predtendrom.sk (cez Zoho) a beh skonci chybou,
aby to bolo vidno aj v GitHube. Zaroven kontroluje, ci anonymny navstevnik
nesmie spustat novu funkciu SECURITY DEFINER mimo zoznamu povolenych.

    python zdravie_dat.py --nasucho     # len vypise
    python zdravie_dat.py

Premenne: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, ZOHO_SMTP_PASSWORD.
"""
import argparse
import os
import smtplib
import ssl
import sys
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

# zdroj -> (tabulka, stlpec, max. vek v dnoch, popis)
ZDROJE = {
    "CRZ zmluvy":   ("contracts", "published_at", 4, "Centrálny register zmlúv (pipeline, pracovné dni)"),
    "Vestník ÚVO":  ("uvo_vestniky", "publikovany", 4, "čísla Vestníka verejného obstarávania"),
    "ITMS21+":      ("itms_sync_log", "koniec", 5, "eurofondy, import z počítača v pondelok a štvrtok"),
    "Dotácie":      ("subsidies", "podpisane", 14, "podpísané dotačné zmluvy"),
}

# Funkcie SECURITY DEFINER, ktore smu volat anonymni navstevnici (verejne alebo
# s vlastnou kontrolou v tele). Nova funkcia mimo zoznamu = upozornenie.
POVOLENE_ANON = {
    "_strop_vkladov", "doterajsi_poradcovia_obce", "hladaj_obec", "itms_import", "je_admin", "je_poradca",
    "kampan_obce_odhlas", "karta_vyzvy", "ma_aktivny_pristup", "ma_pro", "ma_pro_pre_org", "ma_team",
    "moj_obec_id", "moj_poradca_id", "moj_servisny_dopyt", "moj_tim", "moje_org_ids", "moje_pozvanky",
    "moji_kolegovia", "nastav_stav_prilezitosti", "nastavenia_start_limit", "navstevnost_denne",
    "navstevnost_referreri", "navstevnost_stranky", "nazov_obec_pozvanky", "nazov_pozvanky",
    "odhlas_odber_firmy", "odhlas_odber_obce", "odhlas_odber_prehladu", "odober_clena",
    "poradcovia_mojich_dopytov", "prvych_100_dni_suhrn", "verejny_cenovy_median", "vyzvy_signaly_obci",
    "zakladajuce_miesta", "zatvor_dopyt", "zmaz_stav_prilezitosti",
}


def vek_dni(hodnota, dnes):
    if not hodnota:
        return None
    d = datetime.fromisoformat(str(hodnota).replace("Z", "+00:00")[:19]).date() if len(str(hodnota)) > 10 \
        else date.fromisoformat(str(hodnota)[:10])
    return (dnes - d).days


def skontroluj(sb, dnes):
    """-> [(zdroj, vek, limit, popis, problem)]"""
    out = []
    for zdroj, (tab, stl, limit, popis) in ZDROJE.items():
        try:
            r = sb.table(tab).select(stl).not_.is_(stl, "null").order(stl, desc=True).limit(1).execute().data
            vek = vek_dni(r[0][stl], dnes) if r else None
        except Exception as e:
            out.append((zdroj, None, limit, popis, f"chyba dotazu: {type(e).__name__}"))
            continue
        problem = "žiadne dáta" if vek is None else (f"posledný záznam pred {vek} dňami" if vek > limit else "")
        out.append((zdroj, vek, limit, popis, problem))
    return out


def nove_anon_funkcie(sb):
    try:
        mena = sb.rpc("anon_definer_funkcie", {}).execute().data or []
    except Exception:
        return []        # funkcia na kontrolu nemusi existovat; nie je to vypadok dat
    return sorted({m["proname"] if isinstance(m, dict) else m for m in mena} - POVOLENE_ANON)


def sprava(vysledky, nove):
    zle = [v for v in vysledky if v[4]]
    if not zle and not nove:
        return None
    riadky = [f"- {z}: {p} (limit {l} dní). {o}." for z, _, l, o, p in zle]
    if nove:
        riadky.append("- Nové funkcie, ktoré smie spustiť anonymný návštevník: " + ", ".join(nove)
                      + ". Skontrolovať, či nevracajú platené dáta.")
    return ("PredTendrom: problém s dátami",
            "Denná kontrola dát našla problém:\n\n" + "\n".join(riadky)
            + "\n\nPri CRZ a Vestníku: pozrite GitHub Actions, workflow Pipeline a UVO (posledný beh)."
            "\nPri ITMS21+: zapnite počítač v pondelok alebo štvrtok o 16:43, alebo spustite import ručne."
            "\n\n-- automatická kontrola PredTendrom.sk")


def posli(heslo, predmet, text):
    m = EmailMessage()
    m["From"], m["To"], m["Subject"] = "PredTendrom.sk <marek@predtendrom.sk>", "info@predtendrom.sk", predmet
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
    from supabase import create_client
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
    dnes = datetime.now(timezone.utc).date()
    v = skontroluj(sb, dnes)
    nove = nove_anon_funkcie(sb)
    for z, vek, l, _, p in v:
        print(f"{z}: vek {vek} dní (limit {l}) {'PROBLÉM: ' + p if p else 'OK'}")
    if nove:
        print("Nové anonymné funkcie:", ", ".join(nove))
    s = sprava(v, nove)
    if s:
        print(f"::warning title=Zdravie dát::{s[1].splitlines()[2] if len(s[1].splitlines()) > 2 else s[0]}")
        if not a.nasucho:
            posli(os.environ["ZOHO_SMTP_PASSWORD"], *s)
            print("Upozornenie poslané na info@.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
