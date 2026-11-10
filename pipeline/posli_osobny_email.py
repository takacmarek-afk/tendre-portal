"""Jeden osobny e-mail firme z PredTendrom.sk (schvaluje Marek pri kazdom pouziti).

Adresy sa NIKDY nezadavaju ani nevypisuju (repo aj logy su verejne): skript ich
najde sam podla ICO firmy. Komu = clenovia uctu firmy, kopia = dalsi
pouzivatelia z tej istej e-mailovej domeny bez clenstva (kolegovia, co sa
registrovali, ale nedostali sa dnu).

    python posli_osobny_email.py --ico 12345678 --sablona po_skuske            # nasucho
    python posli_osobny_email.py --ico 12345678 --sablona po_skuske --ostro

Sablona: sablony/<meno>.txt, prvy riadok = predmet, zvysok = text.
Posiela cez Zoho (marek@predtendrom.sk), odpovede idu na KAMPAN_REPLY_TO.
"""
import argparse
import os
import smtplib
import ssl
import sys
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path

SMTP_HOST, SMTP_PORT = "smtp.zoho.eu", 465
SMTP_USER = "marek@predtendrom.sk"
ODOSIELATEL = f"Marek Takáč <{SMTP_USER}>"


def nacitaj_sablonu(meno):
    cesta = Path(__file__).parent / "sablony" / f"{meno}.txt"
    predmet, _, text = cesta.read_text(encoding="utf-8").partition("\n")
    return predmet.strip(), text.strip() + "\n"


def domena(email):
    return email.rsplit("@", 1)[-1].lower()


def adresati(clenovia, vsetci):
    """-> (komu, kopia). clenovia = e-maily clenov firmy, vsetci = [(email, je_clen_niekde)]."""
    komu = sorted({e.lower() for e in clenovia})
    domeny = {domena(e) for e in komu}
    kopia = sorted({e.lower() for e, clen in vsetci
                    if not clen and domena(e) in domeny and e.lower() not in komu})
    return komu, kopia


def zostav(komu, kopia, predmet, text, reply_to):
    m = EmailMessage()
    m["From"] = ODOSIELATEL
    m["To"] = ", ".join(komu)
    if kopia:
        m["Cc"] = ", ".join(kopia)
    if reply_to:
        m["Reply-To"] = reply_to
    m["Subject"] = predmet
    m["Date"] = formatdate(localtime=True)
    m["Message-ID"] = make_msgid(domain="predtendrom.sk")
    m.set_content(text)
    return m


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--ico", required=True)
    p.add_argument("--sablona", required=True)
    p.add_argument("--ostro", action="store_true")
    p.add_argument("--oslovenie", action="store_true",
                   help="adresat = adresa, na ktoru sme firmu oslovili (oslovenie_firiem_kontakty)")
    a = p.parse_args(argv)
    ico = "".join(ch for ch in a.ico if ch.isdigit()).zfill(8)
    predmet, text = nacitaj_sablonu(a.sablona)

    from supabase import create_client
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
    if a.oslovenie:
        k = sb.table("oslovenie_firiem_kontakty").select("email").eq("ico", ico).execute().data
        komu, kopia = ([k[0]["email"].lower()] if k and k[0].get("email") else []), []
        if not komu:
            print(f"::error::Firma {ico} nie je v oslovenych.")
            return 1
        return odosli(a, komu, kopia, predmet, text)
    org = sb.table("organizations").select("id").eq("ico", ico).execute().data
    if not org:
        print(f"::error::Firma s ICO {ico} nema ucet.")
        return 1
    clen_ids = {r["user_id"] for r in sb.table("memberships").select("user_id")
                .in_("org_id", [o["id"] for o in org]).execute().data}
    vsetky_clenstva = {r["user_id"] for r in sb.table("memberships").select("user_id").execute().data}
    pouzivatelia, strana = [], 1
    while True:
        davka = sb.auth.admin.list_users(page=strana, per_page=1000)
        pouzivatelia += davka
        if len(davka) < 1000:
            break
        strana += 1
    clenovia = [u.email for u in pouzivatelia if u.id in clen_ids and u.email]
    vsetci = [(u.email, u.id in vsetky_clenstva) for u in pouzivatelia if u.email]
    komu, kopia = adresati(clenovia, vsetci)
    if not komu:
        print("::error::Firma nema ziadneho clena s e-mailom.")
        return 1
    return odosli(a, komu, kopia, predmet, text)


def odosli(a, komu, kopia, predmet, text):
    print(f"::notice::Sablona '{a.sablona}': komu {len(komu)}, kopia {len(kopia)}, predmet: {predmet}")
    if not a.ostro:
        print("::notice::NASUCHO - nic neodoslane.")
        return 0
    heslo = os.environ.get("ZOHO_SMTP_PASSWORD")
    reply_to = os.environ.get("KAMPAN_REPLY_TO", "").strip()
    if not heslo or not reply_to:
        print("::error::Chyba ZOHO_SMTP_PASSWORD alebo KAMPAN_REPLY_TO.")
        return 1
    m = zostav(komu, kopia, predmet, text, reply_to)
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30, context=ssl.create_default_context()) as s:
        s.login(SMTP_USER, heslo)
        odmietnute = s.send_message(m)
    if odmietnute:
        print(f"::error::Odmietnutych adries: {len(odmietnute)}")
        return 1
    print(f"::notice::ODOSLANE (komu {len(komu)}, kopia {len(kopia)}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
