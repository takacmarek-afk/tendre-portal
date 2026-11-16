"""Obec odpovie "áno" na e-mail o eurofondoch -> o jej pripravovanom
obstarávaní dáme vedieť firmám z kraja (16. 11. 2026, schválil Marek).

Postup:
  1. odpovede.py rozpozná odpoveď obce (Message-ID, adresa alebo doména
     z kampan_obce_kontakty). Krátke "áno" po e-maile zo segmentu eurofondy
     zapíše súhlas: kampan_obce_odoslane, vlna 'dopyt-ano', stav 'odosiela sa'
     (bez novej tabuľky; unique (ico, vlna) bráni duplicite). Obec dostane
     potvrdzujúcu vetu.
  2. posli_firmam(): pre každý čakajúci súhlas vyberie najviac MAX_FIRIEM
     firiem z rovnakého odboru a kraja (najprv odberatelia týždenného
     prehľadu, potom oslovené firmy so stavom 'ok') a pošle im krátky e-mail
     s kontaktom na obec. Každá firma najviac raz na obec
     (kampan_obce_odoslane, vlna 'dopyt-<ico obce>'). Potom súhlas -> 'odoslane'.

Do logu (repo je verejné) idú len počty, žiadne adresy ani mená.
"""
import logging
import re
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formatdate, make_msgid, parseaddr

log = logging.getLogger("dopyt_obce")

WEB = "https://predtendrom.sk"
SMTP_HOST, SMTP_PORT = "smtp.zoho.eu", 465
SCHRANKA = "marek@predtendrom.sk"
ODOSIELATEL = "Marek Takáč z PredTendrom.sk <marek@predtendrom.sk>"
MAX_FIRIEM = 12
MAX_POLOZIEK = 3
VLNA_SUHLAS = "dopyt-ano"

VETA_OBEC_ANO = (
    "Dobrý deň,\n\nďakujem. Do jedného pracovného dňa dáme o pripravovanom obstarávaní vedieť firmám "
    "z vášho kraja, ktoré takéto zákazky robia. Ozvú sa vám priamo na tento e-mail.\n\n"
    "Pre obec je to zadarmo a k ničomu ju to nezaväzuje. Termín a podmienky súťaže určujete vy.\n\n"
    "S pozdravom\nMarek Takáč\nPredTendrom.sk | predtendrom.sk\n")
VETA_OBEC_NIE = ("Dobrý deň,\n\nďakujem za odpoveď, ďalej vám už nebudem písať.\n\n"
                 "S pozdravom\nMarek Takáč\nPredTendrom.sk\n")

_ICO = re.compile(r"\D")


def ico_kluc(ico):
    return _ICO.sub("", str(ico or "")).lstrip("0")


def varianty(ico):
    k = ico_kluc(ico)
    return sorted({k, k.zfill(8)}) if k else []


def eur(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return ""
    if v <= 0:
        return ""
    return f"{round(v):,}".replace(",", " ") + " €"


def skrat(t, n=110):
    t = " ".join(str(t or "").split()).rstrip(".")
    return t if len(t) <= n else t[:n - 3].rsplit(" ", 1)[0] + "…"


# ── 1. odpovede obcí ───────────────────────────────────────────────────────

def mapy_obci(kontakty, odoslane, freemail):
    """-> (podla_mid, podla_emailu, podla_domeny, segment_vlna1) pre priradenie odpovede k obci."""
    mid, em, dom = {}, {}, {}
    for k in kontakty:
        e = (k.get("email") or "").strip().lower()
        if e:
            em.setdefault(e, k["ico"])
            d = e.rsplit("@", 1)[-1]
            if d not in freemail:
                dom.setdefault(d, k["ico"])
    seg = {}
    for o in odoslane:
        if o.get("resend_id"):
            mid[o["resend_id"].strip()] = o["ico"]
        if o.get("vlna") == "vlna1" and o.get("stav") == "odoslane":
            seg[o["ico"]] = o.get("segment")
    return mid, em, dom, seg


def priradit_obec(m, podla_mid, podla_emailu, podla_domeny):
    ref = " ".join([m.get("In-Reply-To", ""), m.get("References", "")])
    for i, ico in podla_mid.items():
        if i and i in ref:
            return ico
    od = parseaddr(m.get("Reply-To") or m.get("From", ""))[1].lower()
    if od in podla_emailu:
        return podla_emailu[od]
    return podla_domeny.get(od.rsplit("@", 1)[-1]) if "@" in od else None


def zapis_suhlas(sb, ico, email_adr):
    """Súhlas obce -> čakajúci riadok pre posli_firmam. True, ak je nový."""
    if sb.table("kampan_obce_odoslane").select("id").eq("ico", ico).eq("vlna", VLNA_SUHLAS).limit(1).execute().data:
        return False
    sb.table("kampan_obce_odoslane").insert({"ico": ico, "vlna": VLNA_SUHLAS, "segment": "eurofondy",
                                             "email": (email_adr or "").strip().lower(),
                                             "predmet": "suhlas obce", "stav": "odosiela sa"}).execute()
    return True


def odhlas_obec(sb, ico, dovod="odpovedala nie"):
    sb.table("kampan_obce_kontakty").update({"odhlasene_at": "now()", "dovod": dovod,
                                             "upravene_at": "now()"}).eq("ico", ico).execute()


def vyrad_obec(sb, ico):
    sb.table("kampan_obce_kontakty").update({"stav": "vylucene", "dovod": "nedorucene",
                                             "upravene_at": "now()"}).eq("ico", ico).execute()


# ── 2. e-mail firmám ───────────────────────────────────────────────────────

def polozky_obce(sb, ico):
    """Pripravované, ešte nevyhlásené obstarávania obce s odborom a krajom, od najväčšieho."""
    v = varianty(ico)
    if not v:
        return []
    rows = (sb.table("itms_vo").select("nazov,predpokladana_hodnota,sektor,kraj")
            .in_("obstaravatel_ico", v).eq("stav", "Pripravované")
            .is_("vyhlasene_zistene_at", "null").execute().data or [])
    rows = [r for r in rows if r.get("nazov")]
    rows.sort(key=lambda r: -(float(r.get("predpokladana_hodnota") or 0)))
    return rows


def vyber_firmy(polozky, odbery, kontakty, vylucene_emaily, uz_poslane, n=MAX_FIRIEM):
    """-> [(kluc, email, token, typ)] najviac n firiem v odbore a kraji obstarávaní.
    typ 'odber' (odkaz na odhlásenie prehľadu) alebo 'firma' (odhlásenie oslovenia)."""
    ciele = {(p.get("sektor"), p.get("kraj")) for p in polozky if p.get("sektor") and p.get("kraj")}
    sektory = {s for s, _ in ciele}
    out, emaily = [], set(vylucene_emaily)
    for o in odbery:   # odberatelia si o novinky požiadali sami -> prví
        e = (o.get("email") or "").lower()
        if (not e or e in emaily or o.get("odhlaseny_at") or not o.get("potvrdeny")
                or o.get("sektor") not in sektory):
            continue
        if o.get("kraj") and (o["sektor"], o["kraj"]) not in ciele:
            continue
        kluc = f"odber-{o['id']}"
        if kluc in uz_poslane:
            continue
        out.append((kluc, e, o.get("token"), "odber"))
        emaily.add(e)
    for k in kontakty:
        e = (k.get("email") or "").lower()
        if (not e or e in emaily or k.get("stav") != "ok" or k.get("odhlasene_at")
                or (k.get("segment"), k.get("kraj")) not in ciele):
            continue
        kluc = f"firma-{k['ico']}"
        if kluc in uz_poslane:
            continue
        out.append((kluc, e, k.get("token"), "firma"))
        emaily.add(e)
    return out[:n]


def text_firme(obec, kraj, polozky, kontakt_obce, odhlasenie):
    """-> (predmet, text). Len overené údaje z ITMS21+, nič nesľubujeme."""
    hlavna = polozky[0]
    predmet = f"{obec} pripravuje obstarávanie: {skrat(hlavna['nazov'], 70)}"
    riadky = []
    for p in polozky[:MAX_POLOZIEK]:
        suma = eur(p.get("predpokladana_hodnota"))
        riadky.append(f"• {skrat(p['nazov'])}" + (f" – predpokladaná hodnota {suma}" if suma else ""))
    text = (
        "Dobrý deň,\n\n"
        f"obec {obec}" + (f" ({kraj})" if kraj else "") + " pripravuje v projekte z eurofondov "
        + ("obstarávanie, ktoré ešte nie je vyhlásené:\n\n" if len(riadky) == 1
           else "obstarávania, ktoré ešte nie sú vyhlásené:\n\n")
        + "\n".join(riadky) + "\n\n"
        "Obec nám potvrdila, že chce, aby sa o ňom dozvedelo viac firiem z regiónu. "
        f"Ak vás to zaujíma, ozvite sa priamo obecnému úradu: {kontakt_obce}\n\n"
        "Údaje pochádzajú z ITMS21+ (projekty z eurofondov). Termín a podmienky súťaže určuje obec.\n\n"
        "Ak chcete takéto správy z vášho odboru a kraja dostávať každý týždeň, stačí odpísať „áno“. "
        "Je to zadarmo.\n\n"
        "S pozdravom\nMarek Takáč\nPredTendrom.sk | predtendrom.sk\n\n"
        f"Nechcete tieto e-maily? {odhlasenie}\n"
        "LoveHome s.r.o., Černyševského 40, 851 01 Bratislava, IČO 47 586 362\n")
    return predmet, text


def odhlasenie_pre(typ, token):
    t = str(token or "")
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", t):
        return None
    if typ == "odber":
        return f"{WEB}/odber-firmy?t={t}&akcia=odhlasit"
    return f"{WEB}/odhlasenie-firmy.html?t={t}"


def _sprava(komu, predmet, text, odhlasenie):
    m = EmailMessage()
    m["From"] = ODOSIELATEL
    m["To"] = komu
    m["Subject"] = predmet
    m["Date"] = formatdate(localtime=True)
    m["Message-ID"] = make_msgid(domain="predtendrom.sk")
    m["List-Unsubscribe"] = f"<{odhlasenie}>"
    m.set_content(text)
    return m


def posli_firmam(sb, heslo, ostro, _smtp=smtplib.SMTP_SSL):
    """Spracuje čakajúce súhlasy obcí. -> dict s počtami (bez adries)."""
    from strankuj import vsetky
    pocty = {"suhlasy": 0, "firmy": 0, "bez_firiem": 0, "chyby": 0}
    cakajuce = (sb.table("kampan_obce_odoslane").select("id,ico,email")
                .eq("vlna", VLNA_SUHLAS).eq("stav", "odosiela sa").execute().data or [])
    if not cakajuce:
        return pocty
    kontakty_obci = {r["ico"]: r for r in (sb.table("kampan_obce_kontakty").select("ico,obec,kraj,email")
                                           .in_("ico", [c["ico"] for c in cakajuce]).execute().data or [])}
    odbery = vsetky(lambda o, d: sb.table("odber_firmy").select("id,email,sektor,kraj,token,potvrdeny,odhlaseny_at")
                    .order("id").range(o, d).execute())
    firmy = vsetky(lambda o, d: sb.table("oslovenie_firiem_kontakty").select("ico,email,stav,segment,kraj,token,odhlasene_at")
                   .order("ico").range(o, d).execute())
    s = None
    try:
        for c in cakajuce:
            pocty["suhlasy"] += 1
            ko = kontakty_obci.get(c["ico"]) or {}
            obec = re.sub(r"^\s*(obec|mesto)\s+", "", ko.get("obec") or "", flags=re.I) or "Obec"
            polozky = polozky_obce(sb, c["ico"])
            vlna_f = f"dopyt-{ico_kluc(c['ico'])}"
            uz = {r["ico"] for r in (sb.table("kampan_obce_odoslane").select("ico")
                                     .eq("vlna", vlna_f).execute().data or [])}
            vyber = vyber_firmy(polozky, odbery, firmy, set(), uz) if polozky else []
            if not vyber:
                pocty["bez_firiem"] += 1
            kontakt = c.get("email") or ko.get("email") or ""
            for kluc, email_f, token, typ in vyber:
                odhl = odhlasenie_pre(typ, token)
                if not odhl:
                    continue
                predmet, text = text_firme(obec, ko.get("kraj"), polozky, kontakt, odhl)
                if not ostro:
                    pocty["firmy"] += 1
                    continue
                if s is None:
                    s = _smtp(SMTP_HOST, SMTP_PORT, timeout=30, context=ssl.create_default_context())
                    s.login(SCHRANKA, heslo)
                m = _sprava(email_f, predmet, text, odhl)
                try:
                    odmietnute = s.send_message(m)
                    stav, chyba = ("chyba", "odmietnute") if odmietnute else ("odoslane", None)
                except (smtplib.SMTPException, OSError) as e:
                    stav, chyba = "chyba", type(e).__name__
                sb.table("kampan_obce_odoslane").insert({"ico": kluc, "vlna": vlna_f, "segment": "firma",
                                                         "email": email_f, "predmet": predmet, "stav": stav,
                                                         "chyba": chyba, "resend_id": m["Message-ID"]}).execute()
                pocty["firmy" if stav == "odoslane" else "chyby"] += 1
            if ostro:
                sb.table("kampan_obce_odoslane").update({"stav": "odoslane", "predmet": f"suhlas obce, firmam {len(vyber)}"}
                                                        ).eq("id", c["id"]).execute()
    finally:
        if s is not None:
            try:
                s.quit()
            except Exception:
                pass
    return pocty
