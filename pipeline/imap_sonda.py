"""Sonda: dostaneme sa IMAPom do schranky marek@predtendrom.sk a vidime odpovede
na studene e-maily? Vypisuje LEN pocty a nazvy priecinkov, ziadny obsah ani adresy."""
import email
import imaplib
import os
from datetime import date, timedelta
from email.utils import parseaddr

from supabase import create_client

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
nase = {(r.get("message_id") or "").strip() for r in sb.table("oslovenie_firiem_odoslane")
        .select("message_id").limit(5000).execute().data if r.get("message_id")}
riadky = [f"Nasich odoslanych s Message-ID: {len(nase)}"]
try:
    m = imaplib.IMAP4_SSL("imap.zoho.eu", 993)
    m.login("marek@predtendrom.sk", os.environ["ZOHO_SMTP_PASSWORD"])
    typ, zoznam = m.list()
    priecinky = [z.decode(errors="ignore").split(' "/" ')[-1].strip('"') for z in (zoznam or [])]
    riadky.append("IMAP prihlasenie OK; priecinky: " + ", ".join(priecinky[:15]))
    m.select("INBOX", readonly=True)
    od = (date.today() - timedelta(days=14)).strftime("%d-%b-%Y")
    typ, ids = m.search(None, f'(SINCE "{od}")')
    ids = ids[0].split() if ids and ids[0] else []
    odpovede = adresati = 0
    for i in ids[-300:]:
        typ, d = m.fetch(i, "(BODY.PEEK[HEADER.FIELDS (IN-REPLY-TO REFERENCES TO)])")
        h = email.message_from_bytes(d[0][1])
        ref = " ".join([h.get("In-Reply-To", ""), h.get("References", "")])
        if any(mid and mid in ref for mid in nase):
            odpovede += 1
        if "info@predtendrom.sk" in (h.get("To", "") or "").lower():
            adresati += 1
    riadky.append(f"INBOX 14 dni: {len(ids)} sprav, odpovede na nase e-maily: {odpovede}, adresovane na info@: {adresati}")
    m.logout()
except Exception as e:
    riadky.append(f"IMAP CHYBA: {type(e).__name__}: {str(e)[:150]}")
print("\n".join(riadky))
print("::notice title=IMAP::" + "%0A".join(riadky))
