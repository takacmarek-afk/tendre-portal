"""Spracovanie odpovedi na studene e-maily (10. 11. 2026, schvalil Marek).

Cita schranku marek@predtendrom.sk cez IMAP (Zoho, heslo aplikacie
ZOHO_SMTP_PASSWORD) a kazdu novu spravu za poslednych 21 dni roztriedi:

  nedorucene  vratena sprava (mailer-daemon) -> adresa sa vyradi (stav 'vylucene')
  auto        automaticka odpoved (dovolenka, mimo kancelarie) -> nic, seria ide dalej
  nie         jasne odmietnutie bez otazky -> firma sa vyradi ('odpovedal') a dostane
              jednu zdvorilu vetu
  rucne       vsetko ostatne (otazka, zaujem, nejasne) -> firma sa pozastavi
              ('odpovedal'), NIKDY sa neodpoveda automaticky; odpoveda Marek
  ine         sprava, ktora nie je odpovedou na nase oslovenie -> nic

Pravidlo je zamerne opatrne: pri pochybnosti 'rucne', nie 'nie'.
Do logu (repo je verejne) ide LEN pocet podla typu, ziadne adresy ani obsah.

    python odpovede.py              # nasucho: len roztriedi a vypise pocty
    python odpovede.py --ostro      # zapise stav, posle zdvorile vety
"""
import argparse
import email
import imaplib
import logging
import os
import re
import smtplib
import ssl
import sys
from datetime import date, timedelta
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.utils import formatdate, make_msgid, parseaddr, parsedate_to_datetime

log = logging.getLogger("odpovede")

IMAP_HOST, SMTP_HOST, SMTP_PORT = "imap.zoho.eu", "smtp.zoho.eu", 465
SCHRANKA = "marek@predtendrom.sk"
ODOSIELATEL = "Marek Takáč z PredTendrom.sk <marek@predtendrom.sk>"
DNI = 21
VETA = ("Dobrý deň,\n\nďakujem za odpoveď, ďalej Vás už nebudem kontaktovať.\n\n"
        "Pekný deň,\nMarek Takáč\nzakladateľ PredTendrom.sk | predtendrom.sk\n")

_AUTO_PREDMET = re.compile(r"automatic|automatick|mimo kancel|out of office|autoreply|auto-reply|"
                           r"dovolenk|neprítomn|nepritomn|abwesend|nedostupn", re.I)
_NIE = re.compile(r"nem[aá]me\s+(o\s+\S+\s+)?z[aá]ujem|nem[aá]me\s+z[aá]ujem|nie\s+sme\s+(o\s+\S+\s+)?"
                  r"z[aá]ujem|nezauj[ií]ma|nepotrebujeme|nevyu[zž]ijeme|neposielajte|nekontaktujte|"
                  r"odhl[aá]s|vyra[dď]te|zru[sš]te|unsubscribe|nez[uú][cč]ast[nň]ujeme|"
                  r"nem[aá]me\s+potrebu|nie\s+je\s+pre\s+n[aá]s|nemaj[uú]\s+z[aá]ujem|^\s*nie[.!,]?\s*$",
                  re.I | re.M)
_POZITIVNE = re.compile(r"\?|(?<!ne)zauj[ií]ma\s+n[aá]s|(?<!ne)m[aá]me\s+z[aá]ujem|\bcen[auy]\b|cenov|"
                        r"demo|sk[uú][sš]k|stretn|zavolaj|telefon|kontaktujte\s+ma|viac\s+inform|"
                        r"pozriem|pozrieme|vysk[uú][sš]a", re.I)
_CITACIA = re.compile(r"^(>|-{2,}\s*Original|Od:|From:|Dňa .* nap[ií]sal|On .* wrote|S\s+pozdravom|"
                      r"Sent from|________________)", re.I | re.M)


def _dekoduj(h) -> str:
    try:
        return str(make_header(decode_header(h or "")))
    except Exception:
        return h or ""


def text_spravy(m) -> str:
    """Prvy text/plain (alebo html bez znaciek), len nova cast pred citaciou."""
    casti = m.walk() if m.is_multipart() else [m]
    plain = html = ""
    for c in casti:
        if c.get_content_maintype() != "text" or c.get("Content-Disposition", "").startswith("attachment"):
            continue
        try:
            t = c.get_payload(decode=True).decode(c.get_content_charset() or "utf-8", errors="ignore")
        except Exception:
            continue
        if c.get_content_subtype() == "plain" and not plain:
            plain = t
        elif c.get_content_subtype() == "html" and not html:
            html = re.sub(r"<[^>]+>", " ", re.sub(r"(?is)<(style|script).*?</\1>", " ", t))
    t = plain or html
    k = _CITACIA.search(t)
    return (t[:k.start()] if k else t)[:1500].strip()


def je_nedorucena(m) -> bool:
    od = parseaddr(m.get("From", ""))[1].lower()
    return (od.startswith(("mailer-daemon", "postmaster"))
            or m.get_content_type() == "multipart/report"
            or "undelivered" in _dekoduj(m.get("Subject")).lower())


def nedorucene_adresy(m) -> set:
    """Adresy z vratenej spravy (Final-Recipient / X-Failed-Recipients / text)."""
    out = set()
    for h in m.get_all("X-Failed-Recipients", []) or []:
        out |= {a.strip().lower() for a in h.split(",") if "@" in a}
    for c in m.walk():
        if c.get_content_type() == "message/delivery-status":
            for p in (c.get_payload() or []):
                fr = p.get("Final-Recipient") or p.get("Original-Recipient") or ""
                if "@" in fr:
                    out.add(fr.split(";")[-1].strip().strip("<>").lower())
    if not out:
        t = text_spravy(m) if not m.is_multipart() else " ".join(
            (c.get_payload(decode=True) or b"").decode(errors="ignore")
            for c in m.walk() if c.get_content_maintype() == "text")
        out |= {a.lower() for a in re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", t)
                if not a.lower().endswith(("predtendrom.sk", "zoho.eu", "zohomail.eu"))}
    return out


def roztried(m, text: str) -> str:
    if je_nedorucena(m):
        return "nedorucene"
    if (m.get("Auto-Submitted", "no").lower() not in ("", "no") or m.get("X-Autoreply")
            or m.get("X-Autorespond") or _AUTO_PREDMET.search(_dekoduj(m.get("Subject")))):
        return "auto"
    if _NIE.search(text) and not _POZITIVNE.search(text):
        return "nie"
    return "rucne"


def priradit_ico(m, kontakty_email: dict, kontakty_dom: dict, nase_mid: dict):
    """-> ICO firmy, na ktorej oslovenie sprava odpoveda, alebo None."""
    ref = " ".join([m.get("In-Reply-To", ""), m.get("References", "")])
    for mid, ico in nase_mid.items():
        if mid and mid in ref:
            return ico
    od = parseaddr(m.get("From", ""))[1].lower()
    if od in kontakty_email:
        return kontakty_email[od]
    return kontakty_dom.get(od.rsplit("@", 1)[-1]) if "@" in od else None


def zdvorila_odpoved(m) -> EmailMessage:
    r = EmailMessage()
    r["From"] = ODOSIELATEL
    r["To"] = m.get("Reply-To") or m.get("From")
    predmet = _dekoduj(m.get("Subject")) or ""
    r["Subject"] = predmet if predmet.lower().startswith(("re:", "odp:")) else f"Re: {predmet}"
    if m.get("Message-ID"):
        r["In-Reply-To"] = m["Message-ID"]
        r["References"] = " ".join(x for x in (m.get("References", ""), m["Message-ID"]) if x)
    r["Date"] = formatdate(localtime=True)
    r["Message-ID"] = make_msgid(domain="predtendrom.sk")
    r["Auto-Submitted"] = "auto-replied"
    r.set_content(VETA)
    return r


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--ostro", action="store_true")
    a = ap.parse_args(argv)
    from supabase import create_client
    from strankuj import vsetky
    from oslovenie_firiem import _FREEMAIL, ico8
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
    heslo = os.environ.get("ZOHO_IMAP_PASSWORD") or os.environ["ZOHO_SMTP_PASSWORD"]

    kontakty = vsetky(lambda o, d: sb.table("oslovenie_firiem_kontakty").select("ico,email")
                      .order("ico").range(o, d).execute())
    k_email = {(k["email"] or "").lower(): k["ico"] for k in kontakty if k.get("email")}
    k_dom = {}
    for e, ico in k_email.items():
        dom = e.rsplit("@", 1)[-1]
        if dom not in _FREEMAIL:
            k_dom.setdefault(dom, ico)
    nase = {r["message_id"].strip(): r["ico"] for r in vsetky(
        lambda o, d: sb.table("oslovenie_firiem_odoslane").select("message_id,ico")
        .order("id").range(o, d).execute()) if r.get("message_id")}
    try:
        hotove = {r["message_id"] for r in vsetky(
            lambda o, d: sb.table("oslovenie_odpovede").select("message_id").order("message_id").range(o, d).execute())}
    except Exception:
        if a.ostro:
            raise   # bez tabulky (migracia 96) by sa odpovedalo opakovane
        hotove = set()

    imap = imaplib.IMAP4_SSL(IMAP_HOST, 993)
    imap.login(SCHRANKA, heslo)
    od = (date.today() - timedelta(days=DNI)).strftime("%d-%b-%Y")
    pocty, odpovedi = {}, []
    spravy = []
    for priecinok in ("INBOX", "Spam"):
        if imap.select(priecinok, readonly=True)[0] != "OK":
            continue
        _, ids = imap.search(None, f'(SINCE "{od}")')
        for i in (ids[0].split() if ids and ids[0] else []):
            _, d = imap.fetch(i, "(BODY.PEEK[])")
            spravy.append(d)
    for d in spravy:
        m = email.message_from_bytes(d[0][1])
        mid = (m.get("Message-ID") or "").strip()
        if not mid or mid in hotove:
            continue
        text = "" if je_nedorucena(m) else text_spravy(m)
        typ = roztried(m, text)
        ico = None
        if typ == "nedorucene":
            for adr in nedorucene_adresy(m):
                if adr in k_email:
                    ico = k_email[adr]
                    break
        else:
            ico = priradit_ico(m, k_email, k_dom, nase)
        if not ico:
            typ = "ine"
        pocty[typ] = pocty.get(typ, 0) + 1
        if not a.ostro:
            continue
        poslana = False
        if typ in ("nie", "rucne", "nedorucene"):
            stav = "vylucene" if typ == "nedorucene" else "odpovedal"
            sb.table("oslovenie_firiem_kontakty").update({"stav": stav, "upravene_at": "now()"}).eq("ico", ico8(ico)).execute()
        if typ == "nie":
            odpovedi.append(zdvorila_odpoved(m))
            poslana = True
        try:
            prijate = parsedate_to_datetime(m.get("Date")).isoformat()
        except Exception:
            prijate = None
        sb.table("oslovenie_odpovede").upsert({"message_id": mid, "ico": ico8(ico) if ico else None, "typ": typ,
                                               "odpoved_odoslana": poslana, "prijate_at": prijate}).execute()
    imap.logout()

    poslane = 0
    if odpovedi:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30, context=ssl.create_default_context()) as s:
            s.login(SCHRANKA, heslo)
            for r in odpovedi:
                if not s.send_message(r):
                    poslane += 1
    suhrn = (f"{'OSTRO' if a.ostro else 'NASUCHO'}: nie {pocty.get('nie', 0)} (zdvorila veta {poslane}), "
             f"rucne {pocty.get('rucne', 0)}, auto {pocty.get('auto', 0)}, "
             f"nedorucene {pocty.get('nedorucene', 0)}, ine {pocty.get('ine', 0)}")
    log.info(suhrn)
    print(f"::notice title=Odpovede::{suhrn}")
    if pocty.get("rucne"):
        print(f"::warning title=Odpovede::Na rucnu odpoved caka {pocty['rucne']} sprav (schranka marek@predtendrom.sk).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
