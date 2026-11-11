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
    # overene 10. 11. 2026: kontroluju auth.uid() alebo tajny token v tele
    "odober_clena_firmy", "onboarding_odhlas", "oslovenie_firiem_odhlas", "over_servisny_token",
    "oznac_servis_prevzaty", "potvrd_odber_firmy", "potvrd_odber_obce", "pozvi_clena", "prijmi_obec_pozvanku",
    "prijmi_pozvanku", "uloz_semafor", "uprav_kontakt_obce", "uprav_kontakt_poradcu", "vytvor_pozvanku",
    "zaloz_organizaciu", "zaloz_poradcu_profil",
    "prijmi_pilot",   # 11. 11. 2026: chraneny tajnym tokenom pozvanky (migracia 104)
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
            # zaznamy s datumom v buducnosti (preklep v zdroji, napr. podpisane 16. 11.)
            # by zakryli vypadok, preto len do zajtrajska
            r = (sb.table(tab).select(stl).not_.is_(stl, "null").lte(stl, (dnes + timedelta(days=1)).isoformat())
                 .order(stl, desc=True).limit(1).execute().data)
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


def planovac(repo=None, token=None, _get=None, teraz=None):
    """Cloudflare planovac (cloudflare/planovac) spusta dopyty-email kazdych 15 minut.
    -> text problemu alebo ''. Bez tokenu (lokalny beh) sa nekontroluje."""
    repo, token = repo or os.getenv("GITHUB_REPOSITORY"), token or os.getenv("GITHUB_TOKEN")
    if not (repo and token):
        return ""
    if _get is None:
        import requests
        _get = requests.get
    try:
        r = _get(f"https://api.github.com/repos/{repo}/actions/workflows/dopyty-email.yml/runs",
                 params={"per_page": 1, "event": "workflow_dispatch"}, timeout=30,
                 headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
        behy = r.json().get("workflow_runs") or []
    except Exception as e:
        return f"stav plánovača sa nepodarilo zistiť ({type(e).__name__})"
    if not behy:
        return "plánovač zatiaľ nespustil žiadnu úlohu"
    posledny = datetime.fromisoformat(behy[0]["created_at"].replace("Z", "+00:00"))
    hodin = ((teraz or datetime.now(timezone.utc)) - posledny).total_seconds() / 3600
    return f"posledné spustenie pred {hodin:.0f} h (má bežať každých 15 minút)" if hodin > 3 else ""


def sprava(vysledky, nove, planovac_problem=""):
    zle = [v for v in vysledky if v[4]]
    if not zle and not nove and not planovac_problem:
        return None
    riadky = [f"- {z}: {p} (limit {l} dní). {o}." for z, _, l, o, p in zle]
    if planovac_problem:
        riadky.append(f"- Plánovač úloh (Cloudflare Worker predtendrom-planovac): {planovac_problem}. "
                      "Skontrolovať v Cloudflare (Workers → predtendrom-planovac → Logs) a či GitHub token "
                      "GH_TOKEN nevypršal.")
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
    pl = planovac()
    print(f"Plánovač: {pl or 'OK'}")
    s = sprava(v, nove, pl)
    if s:
        print(f"::warning title=Zdravie dát::{s[1].splitlines()[2] if len(s[1].splitlines()) > 2 else s[0]}")
        if not a.nasucho:
            posli(os.environ["ZOHO_SMTP_PASSWORD"], *s)
            print("Upozornenie poslané na info@.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
