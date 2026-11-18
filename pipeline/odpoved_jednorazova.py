"""Jednorazova odpoved na spravu v schranke marek@ (18. 11. 2026).

Adresa nejde do vstupov ani logu (repo je verejne): HASH = SHA-256 adresy
odosielatela, PREDMET = zaciatok predmetu spravy. Odpoved ide ako Re: na
najnovsiu zhodnu spravu za 7 dni, text je v TEXT (bez osobnych udajov).
"""
import email
import hashlib
import imaplib
import os
import smtplib
import ssl
from datetime import date, timedelta
from email.utils import parseaddr

import odpovede as o

TEXT = {
    "podobny": ("Dobrý deň,\n\nďakujeme, radi Vás odhlásime. Vaša žiadosť nám však prišla z Vašej súkromnej "
                "adresy, na ktorú sme nepísali, preto neviem, ktorú adresu mám vyradiť. Prosím, napíšte mi, "
                "na akú e-mailovú adresu Vám od nás správa prišla (napríklad firemnú), a hneď ju vyradím.\n\n"
                "Ďakujem a prepáčte za komplikáciu.\n\nMarek Takáč\nPredTendrom.sk\n"),
}

H = os.environ["HASH"].strip().lower()
PREDMET = os.environ["PREDMET"].strip().lower()
text = TEXT[os.environ["TEXT"]]
heslo = os.environ.get("ZOHO_IMAP_PASSWORD") or os.environ["ZOHO_SMTP_PASSWORD"]
imap = imaplib.IMAP4_SSL(o.IMAP_HOST, 993)
imap.login(o.SCHRANKA, heslo)
imap.select("INBOX", readonly=True)
_, ids = imap.search(None, f'(SINCE "{(date.today() - timedelta(days=7)).strftime("%d-%b-%Y")}")')
ciel = None
for i in (ids[0].split() if ids and ids[0] else []):
    _, d = imap.fetch(i, "(BODY.PEEK[])")
    m = email.message_from_bytes(d[0][1])
    od = parseaddr(m.get("Reply-To") or m.get("From", ""))[1].strip().lower()
    if hashlib.sha256(od.encode()).hexdigest() == H and o._dekoduj(m.get("Subject")).lower().startswith(PREDMET):
        ciel = m
imap.logout()
if not ciel:
    print("::warning title=Odpoved::Sprava sa nenasla.")
    raise SystemExit(1)
r = o.zdvorila_odpoved(ciel, text)
del r["Auto-Submitted"]
with smtplib.SMTP_SSL(o.SMTP_HOST, o.SMTP_PORT, timeout=30, context=ssl.create_default_context()) as s:
    s.login(o.SCHRANKA, heslo)
    odm = s.send_message(r)
print("::notice title=Odpoved::" + ("odoslana" if not odm else "odmietnuta"))
