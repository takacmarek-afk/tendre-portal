"""E-mailove upozornenia pri dopytoch obci (zistenie Mareka, 28.9.2026).

Dva smery, oba na zaklade novych stlpcov z migracie 54_dopyty_notifikacie.sql:
  1. Novy OTVORENY dopyt -> e-mail vsetkym aktivnym poradcom, ktori posobia
     v jeho kraji (alebo maju kraje_posobenia prazdne = vsade), alebo ked
     dopyt sam nema kraj.
  2. Nova reakcia poradcu na dopyt -> e-mail obci, ktora dopyt vypisala.

Spustenie:
    python posli_dopyt_email.py                # naozaj posle
    python posli_dopyt_email.py --nasucho      # nic neposle, len vypise

Potrebne premenne (rovnake ako uz existujuci posli_email.py, ziadne nove):
    SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, RESEND_API_KEY

Preco samostatny skript a nie sucast posli_email.py: iny rytmus behu (co
najcastejsie, viz .github/workflows/dopyty-email.yml, oproti tyzdennemu/
dennemu digestu) a iny typ udalosti (jednorazova akcia, nie periodicky
suhrn) — zamerne oddelene, nech sa nepomiesaju dve rozne veci s dvoma
roznymi rytmami v jednom subore.
"""
import argparse
import logging
import os
import re
import sys
import time

from supabase import create_client

from posli_email import ODOSIELATEL, PAUZA_S, _obal, _bezpecne, posli  # noqa: F401

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)-7s %(name)-9s %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("dopyt-email")

ODKAZ_TRH = "https://predtendrom.sk/trh.html"

EMAIL_RE = re.compile(r"[^@\s,;<>\"]+@[^@\s,;<>\"]+\.[A-Za-z]{2,}")

# Rovnake popisky ako TERMIN_POPIS/ROZPOCET_POPIS v public/trh.html (P3.3,
# migracia 55_dopyt_kontakt_a_sablony.sql) — pri zmene tam zmenit aj tu.
TERMIN_POPIS = {
    "co_najskor": "co najskor", "do_1_mesiaca": "do 1 mesiaca",
    "do_3_mesiacov": "do 3 mesiacov", "neviem": "neviem / flexibilne",
}
ROZPOCET_POPIS = {
    "do_5000": "do 5 000 eur", "5000_20000": "5 000 - 20 000 eur",
    "20000_100000": "20 000 - 100 000 eur", "nad_100000": "nad 100 000 eur",
    "neviem": "neviem",
}


def _detaily_dopytu(dopyt) -> str:
    """'Termin: ... . Rozpocet: ...' — len tie casti, ktore su vyplnene."""
    casti = []
    if dopyt.get("termin"):
        casti.append("Termin: " + TERMIN_POPIS.get(dopyt["termin"], dopyt["termin"]))
    if dopyt.get("rozpocet"):
        casti.append("Rozpocet: " + ROZPOCET_POPIS.get(dopyt["rozpocet"], dopyt["rozpocet"]))
    return " · ".join(casti)


def _platny_email(e) -> bool:
    return bool(e) and bool(EMAIL_RE.fullmatch(str(e).strip()))


# ── SMER 1: NOVY DOPYT -> PORADCOVIA ────────────────────────────────────────

def _poradcovia_pre_dopyt(sb, dopyt) -> list:
    """Aktivni poradcovia, ktorym dopyt sedi krajom (alebo dopyt/poradca
    kraj neriesi). kraje_posobenia je pole — prazdne pole zamerne znamena
    "vsade" (rovnaky vzor ako zaloz_poradcu_profil, default '{}')."""
    try:
        vsetci = (sb.table("poradcovia_profily")
                    .select("kontakt_email, nazov, kraje_posobenia")
                    .eq("aktivny", True).execute().data or [])
    except Exception as e:
        log.warning("Tabulka poradcovia_profily sa necitala: %s", e)
        return []

    kraj = dopyt.get("kraj")
    if not kraj:
        return vsetci
    return [p for p in vsetci
            if not p.get("kraje_posobenia") or kraj in p["kraje_posobenia"]]


def _obsah_pre_poradcu(dopyt) -> dict:
    typ_text = {"zmluva": "Koncici sa zmluva", "dotacia": "Dotacia", "ine": "Ine"}.get(
        dopyt.get("typ"), "Vseobecny dopyt")
    kde = dopyt.get("kraj") or "kraj neuvedeny"
    popis = dopyt.get("popis") or ""
    detaily = _detaily_dopytu(dopyt)
    if detaily:
        popis = f"{popis} ({detaily})" if popis else detaily
    return {
        "titulok": f"Novy dopyt: {dopyt.get('obec_nazov') or 'obec'}",
        "uvod": (f"{dopyt.get('obec_nazov') or 'Obec'} ({kde}) prave vypisala "
                 f"novy dopyt na Trhu dopytov. Reagovat moze najviac 5 firiem, "
                 f"takze cim skor, tym lepsie."),
        "bloky": [{
            "titul": dopyt.get("nazov") or "(bez nazvu)",
            "popis": popis,
            "zvyraznene": typ_text,
        }],
        "cta_text": "Otvorit Trh dopytov",
        "cta_url": ODKAZ_TRH,
        "odhlasenie": ("Tento e-mail suvisi s vasim profilom poradcu na "
                       "Trhu dopytov. Profil mozete kedykolvek upravit "
                       "alebo deaktivovat po prihlaseni na trh.html."),
    }


def posli_poradcom(sb, kluc, nasucho, obmedz_na=None) -> tuple:
    dopyty = (sb.table("dopyty")
                .select("id, obec_nazov, kraj, typ, nazov, popis, stav, termin, rozpocet")
                .eq("poradcovia_notifikovani", False)
                .execute().data or [])
    poslane = zlyhane = 0
    for d in dopyty:
        if d.get("stav") != "otvoreny":
            # Uzavrety skor, nez sme stihli notifikovat - nema zmysel
            # lakat poradcov na nieco, co uz nie je otvorene. Napriek
            # tomu oznacime ako "notifikovane", nech to neskusame znova.
            log.info("Dopyt %s je uz uzavrety, notifikaciu preskakujem.", d["id"])
        else:
            adresati = _poradcovia_pre_dopyt(sb, d)
            obsah = _obsah_pre_poradcu(d)
            html = _obal(obsah["titulok"], obsah["uvod"], obsah["bloky"],
                         obsah["cta_text"], obsah["cta_url"], obsah["odhlasenie"])
            predmet = f"PredTendrom.sk — {obsah['titulok']}"
            for p in adresati:
                komu = (p.get("kontakt_email") or "").strip()
                if not _platny_email(komu):
                    continue
                if obmedz_na and komu.lower() != obmedz_na.lower():
                    continue
                if posli(kluc, komu, predmet, html, nasucho):
                    poslane += 1
                else:
                    zlyhane += 1
                time.sleep(PAUZA_S)

        if not nasucho:
            try:
                sb.table("dopyty").update(
                    {"poradcovia_notifikovani": True}).eq("id", d["id"]).execute()
            except Exception as e:
                log.warning("Dopyt %s: oznacenie ako notifikovany zlyhalo (%s)",
                           d["id"], e)
    return poslane, zlyhane


# ── SMER 2: NOVA REAKCIA -> OBEC ────────────────────────────────────────────

def _obsah_pre_obec(dopyt_nazov, poradca, sprava) -> dict:
    kontakt_bity = [x for x in (poradca.get("kontakt_email"),
                                poradca.get("kontakt_telefon")) if x]
    return {
        "titulok": "Firma reagovala na váš dopyt",
        "uvod": (f'{poradca.get("nazov") or "Poradca"} reagoval(a) na váš '
                 f'dopyt „{dopyt_nazov}".'),
        "bloky": [{
            "titul": poradca.get("nazov") or "Poradca",
            "popis": (sprava or "")[:400],
            "zvyraznene": " · ".join(kontakt_bity) if kontakt_bity else None,
        }],
        "cta_text": "Zobraziť v Trhu dopytov",
        "cta_url": ODKAZ_TRH,
        "odhlasenie": ("Tento e-mail súvisí s dopytom, ktorý ste vypísali "
                       "na Trhu dopytov."),
    }


def posli_obciam(sb, kluc, nasucho, obmedz_na=None) -> tuple:
    reakcie = (sb.table("reakcie")
                 .select("id, dopyt_id, poradca_id, sprava")
                 .eq("obec_notifikovana", False)
                 .execute().data or [])
    poslane = zlyhane = 0
    for r in reakcie:
        try:
            dopyt = (sb.table("dopyty").select("nazov, obec_id")
                       .eq("id", r["dopyt_id"]).limit(1).execute().data or [None])[0]
            poradca = (sb.table("poradcovia_profily")
                         .select("nazov, kontakt_email, kontakt_telefon")
                         .eq("id", r["poradca_id"]).limit(1).execute().data or [None])[0]
            obec = ((sb.table("obce_ucty").select("kontakt_email")
                       .eq("id", dopyt["obec_id"]).limit(1).execute().data or [None])[0]
                    if dopyt else None)
        except Exception as e:
            log.warning("Reakcia %s: dopyt sa nedalo dopocitat (%s)", r["id"], e)
            dopyt = poradca = obec = None

        komu = (obec or {}).get("kontakt_email", "").strip() if obec else ""
        if _platny_email(komu) and dopyt and poradca and not (
                obmedz_na and komu.lower() != obmedz_na.lower()):
            obsah = _obsah_pre_obec(dopyt.get("nazov") or "dopyt", poradca, r.get("sprava"))
            html = _obal(obsah["titulok"], obsah["uvod"], obsah["bloky"],
                         obsah["cta_text"], obsah["cta_url"], obsah["odhlasenie"])
            predmet = f"PredTendrom.sk — {obsah['titulok']}"
            if posli(kluc, komu, predmet, html, nasucho):
                poslane += 1
            else:
                zlyhane += 1
            time.sleep(PAUZA_S)
        else:
            log.info("Reakcia %s: obec bez pouzitelneho kontakt_email, "
                     "notifikaciu preskakujem.", r["id"])

        if not nasucho:
            try:
                sb.table("reakcie").update(
                    {"obec_notifikovana": True}).eq("id", r["id"]).execute()
            except Exception as e:
                log.warning("Reakcia %s: oznacenie ako notifikovana zlyhalo (%s)",
                           r["id"], e)
    return poslane, zlyhane


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nasucho", action="store_true",
                    help="nic neposle, len vypise co by poslal")
    ap.add_argument("--komu", help="posle len na tuto adresu (test)")
    args = ap.parse_args()

    if args.komu is not None:
        args.komu = args.komu.strip()
        if not _platny_email(args.komu):
            log.error("--komu nie je platna e-mailova adresa. Nepokracujem.")
            return 1

    url = os.getenv("SUPABASE_URL")
    servis = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    kluc = os.getenv("RESEND_API_KEY")
    if not (url and servis):
        log.error("Chyba SUPABASE_URL alebo SUPABASE_SERVICE_ROLE_KEY.")
        return 1
    if not kluc and not args.nasucho:
        log.error("Chyba RESEND_API_KEY. Spusti s --nasucho, alebo ho priprav "
                  "v GitHub Secrets (uz tam je pre posli_email.py).")
        return 1

    sb = create_client(url, servis)

    p_poslane, p_zlyhane = posli_poradcom(sb, kluc, args.nasucho, args.komu)
    o_poslane, o_zlyhane = posli_obciam(sb, kluc, args.nasucho, args.komu)

    log.info("Hotovo%s: poradcom poslanych %s (zlyhanych %s), "
             "obciam poslanych %s (zlyhanych %s)",
             "  [NASUCHO]" if args.nasucho else "",
             p_poslane, p_zlyhane, o_poslane, o_zlyhane)
    if (p_zlyhane or o_zlyhane) and not (p_poslane or o_poslane):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
