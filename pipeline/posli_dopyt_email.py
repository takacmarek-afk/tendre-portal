"""E-mailove upozornenia pri dopytoch obci (zistenie Mareka, 28.9.2026).

Dva smery, oba na zaklade novych stlpcov z migracie 54_dopyty_notifikacie.sql:
  1. Novy OTVORENY dopyt -> e-mail vsetkym aktivnym poradcom, ktori posobia
     v jeho kraji (alebo maju kraje_posobenia prazdne = vsade), alebo ked
     dopyt sam nema kraj.
  2. Nova reakcia poradcu na dopyt -> e-mail obci, ktora dopyt vypisala.
  (vlna 82, migracia 67) Poradcom sa rozosielaju LEN dopyty overenych obci
  (dopyty.overeny). Dopyt neoverenej obce ide namiesto toho ako upozornenie
  Marekovi (info@predtendrom.sk / NOTIFIKACIA_KOMU) s volanim schval_obec().

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
# (Texty su pre cloveka, preto s diakritikou.)
TERMIN_POPIS = {
    "co_najskor": "čo najskôr", "do_1_mesiaca": "do 1 mesiaca",
    "do_3_mesiacov": "do 3 mesiacov", "neviem": "neviem / flexibilné",
}
ROZPOCET_POPIS = {
    "do_5000": "do 5 000 €", "5000_20000": "5 000 – 20 000 €",
    "20000_100000": "20 000 – 100 000 €", "nad_100000": "nad 100 000 €",
    "neviem": "neviem",
}


def _detaily_dopytu(dopyt) -> str:
    """'Termín: ... · Rozpočet: ...' — len tie casti, ktore su vyplnene."""
    casti = []
    if dopyt.get("termin"):
        casti.append("Termín: " + TERMIN_POPIS.get(dopyt["termin"], dopyt["termin"]))
    if dopyt.get("rozpocet"):
        casti.append("Rozpočet: " + ROZPOCET_POPIS.get(dopyt["rozpocet"], dopyt["rozpocet"]))
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
    typ_text = {"zmluva": "Končiaca zmluva", "dotacia": "Dotácia", "ine": "Iné"}.get(
        dopyt.get("typ"), "Všeobecný dopyt")
    kde = dopyt.get("kraj") or "kraj neuvedený"
    popis = dopyt.get("popis") or ""
    detaily = _detaily_dopytu(dopyt)
    if detaily:
        popis = f"{popis} ({detaily})" if popis else detaily
    return {
        "titulok": f"Nový dopyt: {dopyt.get('obec_nazov') or 'obec'}",
        "uvod": (f"{dopyt.get('obec_nazov') or 'Obec'} ({kde}) práve vypísala "
                 f"nový dopyt na Trhu dopytov. Na tento dopyt môže odpovedať "
                 f"najviac 5 poradcov."),
        "bloky": [{
            "titul": dopyt.get("nazov") or "(bez názvu)",
            "popis": popis,
            "zvyraznene": typ_text,
        }],
        "cta_text": "Otvoriť Trh dopytov",
        "cta_url": ODKAZ_TRH,
        "odhlasenie": ("Tento e-mail súvisí s vaším profilom poradcu na "
                       "Trhu dopytov. Profil môžete kedykoľvek upraviť "
                       "alebo deaktivovať po prihlásení na Trhu dopytov."),
    }


def posli_poradcom(sb, kluc, nasucho, obmedz_na=None) -> tuple:
    dopyty = (sb.table("dopyty")
                .select("id, obec_nazov, kraj, typ, nazov, popis, stav, termin, rozpocet")
                .eq("poradcovia_notifikovani", False)
                .eq("overeny", True)     # A6 (vlna 82): neoverene obce poradcom nerozosielame
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
            pokusov = uspesnych = 0
            for p in adresati:
                komu = (p.get("kontakt_email") or "").strip()
                if not _platny_email(komu):
                    continue
                if obmedz_na and komu.lower() != obmedz_na.lower():
                    continue
                pokusov += 1
                if posli(kluc, komu, predmet, html, nasucho):
                    poslane += 1
                    uspesnych += 1
                else:
                    zlyhane += 1
                time.sleep(PAUZA_S)
            # Audit 6. 10. 2026 (B2): dopyt sa NEOZNACI ako notifikovany,
            # ked islo o test na jednu adresu (--komu), alebo ked sa nepodarilo
            # poslat ani jeden e-mail (vypadok Resendu) — zopakuje sa pri
            # dalsom behu. Pri ciastocnom uspechu sa oznaci (inak by dostali
            # e-mail dvakrat tí, ktorym uz prisiel).
            if obmedz_na or (pokusov and not uspesnych):
                continue

        if not nasucho:
            try:
                sb.table("dopyty").update(
                    {"poradcovia_notifikovani": True}).eq("id", d["id"]).execute()
            except Exception as e:
                log.warning("Dopyt %s: oznacenie ako notifikovany zlyhalo (%s)",
                           d["id"], e)
    return poslane, zlyhane


# ── SMER 0: DOPYT NEOVERENEJ OBCE -> ADMIN (A6, vlna 82) ────────────────────

ADMIN_EMAIL = os.getenv("NOTIFIKACIA_KOMU") or "info@predtendrom.sk"


def _obsah_pre_admina(riadky) -> dict:
    """`riadky`: zoznam (dopyt, obec). Jeden e-mail na vsetky cakajuce."""
    bloky = []
    videne = set()
    for d, o in riadky:
        o = o or {}
        oid = d.get("obec_id")
        if oid in videne:
            continue
        videne.add(oid)
        pocet = sum(1 for dd, _ in riadky if dd.get("obec_id") == oid)
        bloky.append({
            "titul": f"{o.get('nazov') or d.get('obec_nazov') or 'Obec'}"
                     f" (IČO {o.get('ico') or '—'})",
            "popis": (f"Dopyt: {d.get('nazov') or '(bez názvu)'}"
                      + (f" · spolu čakajúcich dopytov: {pocet}" if pocet > 1 else "")
                      + f" · kontakt: {o.get('kontakt_email') or '—'}"
                      + f" · schváliť (Supabase SQL editor): "
                        f"select public.schval_obec('{oid}');"),
            "zvyraznene": "Poradcom sa nezobrazí, kým obec neschválite.",
        })
    return {
        "titulok": "Obec čaká na schválenie",
        "uvod": ("Účet obce, ktorý sa nepodarilo overiť automaticky (e-mail "
                 "účtu nesedí s úradným e-mailom obce z nášho zoznamu), "
                 "zadal dopyt. Skontrolujte, či ide o skutočnú obec; "
                 "prehľad čakajúcich: select * from public.cakajuce_obce();"),
        "bloky": bloky,
        "cta_text": "Otvoriť Trh dopytov",
        "cta_url": ODKAZ_TRH,
        "odhlasenie": "Interné upozornenie pre správcu PredTendrom.sk.",
    }


def upozorni_admina(sb, kluc, nasucho, obmedz_na=None) -> tuple:
    """Dopyty neoverenych obci, o ktorych sme admina este neinformovali.
    Jeden suhrnny e-mail na beh. Oznacuje sa az po uspesnom odoslani."""
    if obmedz_na:
        return 0, 0   # test na jednu adresu sa nesmie dotknut admin upozornenia
    try:
        dopyty = (sb.table("dopyty")
                    .select("id, obec_id, obec_nazov, nazov, stav")
                    .eq("overeny", False)
                    .eq("admin_upozorneny", False)
                    .execute().data or [])
    except Exception as e:
        log.warning("Cakajuce dopyty neoverenych obci sa necitali: %s", e)
        return 0, 0
    dopyty = [d for d in dopyty if d.get("stav") == "otvoreny"]
    if not dopyty:
        return 0, 0

    riadky = []
    for d in dopyty:
        try:
            o = (sb.table("obce_ucty").select("nazov, ico, kontakt_email")
                   .eq("id", d["obec_id"]).limit(1).execute().data or [None])[0]
        except Exception:
            o = None
        riadky.append((d, o))

    obsah = _obsah_pre_admina(riadky)
    html = _obal(obsah["titulok"], obsah["uvod"], obsah["bloky"],
                 obsah["cta_text"], obsah["cta_url"], obsah["odhlasenie"])
    predmet = f"PredTendrom.sk — {obsah['titulok']}"
    ok = posli(kluc, ADMIN_EMAIL, predmet, html, nasucho)
    time.sleep(PAUZA_S)
    if not ok:
        return 0, 1
    if not nasucho:
        for d, _ in riadky:
            try:
                sb.table("dopyty").update(
                    {"admin_upozorneny": True}).eq("id", d["id"]).execute()
            except Exception as e:
                log.warning("Dopyt %s: oznacenie admin_upozorneny zlyhalo (%s)",
                           d["id"], e)
    return 1, 0


# ── SMER 2: NOVA REAKCIA -> OBEC ────────────────────────────────────────────

def _obsah_pre_obec(dopyt_nazov, poradca, sprava) -> dict:
    meno_poradcu = (poradca.get("nazov") or "z Trhu dopytov").strip()
    kontakt_bity = [x for x in (poradca.get("kontakt_email"),
                                poradca.get("kontakt_telefon")) if x]
    return {
        "titulok": "Nová odpoveď na váš dopyt",
        "uvod": (f'Na váš dopyt „{dopyt_nazov}“ odpovedal poradca '
                 f'{meno_poradcu}' + ("" if meno_poradcu.endswith(".") else ".")),
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
                continue   # neoznacit — zopakuje sa pri dalsom behu
            time.sleep(PAUZA_S)
        else:
            if obmedz_na:
                continue   # test na jednu adresu nesmie oznacit cudzie reakcie
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
    a_poslane, a_zlyhane = upozorni_admina(sb, kluc, args.nasucho, args.komu)

    log.info("Hotovo%s: poradcom poslanych %s (zlyhanych %s), "
             "obciam poslanych %s (zlyhanych %s), "
             "upozorneni adminovi %s (zlyhanych %s)",
             "  [NASUCHO]" if args.nasucho else "",
             p_poslane, p_zlyhane, o_poslane, o_zlyhane, a_poslane, a_zlyhane)
    if (p_zlyhane or o_zlyhane or a_zlyhane) and not (p_poslane or o_poslane or a_poslane):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
