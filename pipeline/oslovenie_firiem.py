"""Oslovenie firiem — tri osobne e-maily dodavatelom verejneho sektora.

Plan a texty: Claude Doc "PredTendrom.sk – plan prvych 50 platiacich firiem",
sekcia 3. Migracia: supabase/84_oslovenie_firiem.sql.
Workflow: .github/workflows/oslovenie-firiem.yml (len rucne spustenie).

KROKY
    python oslovenie_firiem.py kontakty --nasucho      # co by sa zapisalo
    python oslovenie_firiem.py kontakty                # e-maily vitazov z Vestnika UVO
    python oslovenie_firiem.py posli --nasucho --nahlad nahlad.html
    python oslovenie_firiem.py posli --komu ja@x.sk    # 3 testovacie e-maily
    python oslovenie_firiem.py posli --novych 30       # OSTRO
    python oslovenie_firiem.py zastav --ico 12345678   # firma odpovedala

KOMU PISEME (a komu nie) — § 116 ods. 15 zakona c. 452/2021 Z. z.
  Len na ZVEREJNENU adresu: oficialny e-mail vitaza sutaze vo Vestniku UVO
  (pole BT-506), ktory firma sama uviedla ako svoj kontakt. Aj osobne
  adresy (meno.priezvisko@), ktore firma takto zverejnila (rozhodnutie
  23. 10. 2026). Rucne 'vylucene' a 'odpovedal' sa nikdy neprepisuju. Nepiseme firmam, ktore
  uz maju ucet, ani adresam prihlasenym do tyzdenneho prehladu (dali suhlas,
  dostavaju ine e-maily). Odhlasena firma uz nedostane nic.

ODOSIELANIE
  Cez schranku marek@predtendrom.sk v Zoho Mail (SMTP). NIKDY cez Resend:
  jeho Acceptable Use Policy zakazuje "cold outreach" a na tom ucte stoja
  prihlasovacie kody appky.

POISTKY
  - kazdy krok (1, 2, 3) najviac raz na firmu (unique ico+krok), riadok sa
    zapise PRED odoslanim — ked beh spadne, e-mail sa nezopakuje
  - krok 2 najskor 4 dni po kroku 1, krok 3 najskor 5 dni po kroku 2
  - najviac --max e-mailov za den spolu (default 30), 20 s medzi e-mailmi
  - ostro len pondelok az stvrtok, 8:00 az 16:00 nasho casu (--vynutit obide)
  - bez KAMPAN_REPLY_TO sa ostro neposiela: odpovede musia ist Marekovi
  - firma bez konkretnej konciacej zmluvy v odbore a kraji nedostane nic
"""
import argparse
import html
import logging
import os
import re
import sys
import time
import unicodedata
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import kampan_obce as ko   # posli_smtp, zostav_spravu, SMTP nastavenia

log = logging.getLogger("oslovenie")

WEB = "https://predtendrom.sk"
REPLY_TO = os.getenv("KAMPAN_REPLY_TO", "").strip()
PAUZA_S = float(os.getenv("KAMPAN_PAUZA_S", "20"))
BRATISLAVA = ZoneInfo("Europe/Bratislava")
DNI_PO_KROKU = {2: 4, 3: 5}          # krok -> najmenej dni od predosleho kroku
ZACIATOCNA_CENA = "240 €"
BEZNA_CENA = "340 €"

PATICKA_FIRMA = "LoveHome s.r.o., Černyševského 40, 851 01 Bratislava, IČO 47 586 362"

ODBOR = {   # sektor -> (genitiv "v odbore ...", akuzativ "zmluva na ...")
    "UPRATOVANIE": ("upratovania", "upratovanie"),
    "UPRATOVANIE_TOVAR": ("hygienického a čistiaceho tovaru", "hygienický tovar"),
    "OSTRAHA": ("strážnych služieb", "ostrahu"),
    "OSTRAHA_TECHNIKA": ("zabezpečovacej techniky", "zabezpečovaciu techniku"),
    "STRAVOVANIE": ("stravovania", "stravovanie"),
    "ZELEN_ZIMNA_UDRZBA": ("údržby zelene a zimnej údržby", "údržbu zelene"),
}
# Kym nie je video 1 (plan predaja, sekcia 5), odkaz vedie na ukazku bez registracie.
VIDEO_URL = os.getenv("KAMPAN_VIDEO_CESTA", "").strip()

NUTS_KRAJ = {
    "SK010": "Bratislavský kraj", "SK021": "Trnavský kraj", "SK022": "Trenčiansky kraj",
    "SK023": "Nitriansky kraj", "SK031": "Žilinský kraj", "SK032": "Banskobystrický kraj",
    "SK041": "Prešovský kraj", "SK042": "Košický kraj",
}
KRAJ_LOKAL = {
    "Bratislavský kraj": "Bratislavskom kraji", "Trnavský kraj": "Trnavskom kraji",
    "Trenčiansky kraj": "Trenčianskom kraji", "Nitriansky kraj": "Nitrianskom kraji",
    "Žilinský kraj": "Žilinskom kraji", "Banskobystrický kraj": "Banskobystrickom kraji",
    "Prešovský kraj": "Prešovskom kraji", "Košický kraj": "Košickom kraji",
}

_EMAIL = re.compile(r"^[^@\s;,]+@[^@\s;,]+\.[a-z]{2,}$")
_VSEOBECNE = ("info", "office", "obchod", "kontakt", "contact", "sales", "predaj", "sekretariat",
              "recepcia", "firma", "mail", "email", "posta", "objednavky", "zakazky", "tendre",
              "tender", "obstaravanie", "ponuky", "servis", "centrala", "kancelaria", "admin",
              "ekonom", "uctaren", "fakturacia", "hello", "dispecing", "dispecer")
_FREEMAIL = ko._FREEMAIL
_PRAVNE_FORMY = re.compile(r"\b(s\s*\.?\s*r\s*\.?\s*o|spol|a\s*\.?\s*s|k\s*\.?\s*s|v\s*\.?\s*o\s*\.?\s*s"
                           r"|s\s*\.?\s*e|druzstvo|o\s*\.?\s*z|n\s*\.?\s*o)\b\.?", re.IGNORECASE)


# ── pomocne ────────────────────────────────────────────────────────────────

def _norm(t):
    nfkd = unicodedata.normalize("NFKD", str(t or ""))
    return " ".join("".join(c for c in nfkd if not unicodedata.combining(c)).lower().split())


def ico8(ico):
    d = re.sub(r"\D", "", str(ico or ""))
    return d.zfill(8) if d else ""


def kratky_nazov(nazov):
    """'ABC Clean, s. r. o.' -> 'ABC Clean' (do oslovenia v texte)."""
    t = _PRAVNE_FORMY.sub("", str(nazov or "")).strip(" ,.-")
    return re.sub(r"\s{2,}", " ", t) or str(nazov or "").strip()


def mesiac_rok(d):
    mes = ("januári", "februári", "marci", "apríli", "máji", "júni", "júli", "auguste",
           "septembri", "októbri", "novembri", "decembri")
    if isinstance(d, str):
        d = date.fromisoformat(d[:10])
    return f"v {mes[d.month - 1]} {d.year}"


def posud_email(email, firma):
    """-> (stav, dovod).

    Kazda adresa sem prichadza z Vestnika UVO (BT-506): je to kontakt, ktory
    firma sama uviedla ako svoj oficialny kontakt vo verejnom obstaravani.
    Rozhodnutie Mareka 23. 10. 2026: aj osobne adresy (meno.priezvisko@,
    schranka zivnostnika na gmaile), ktore firma takto zverejnila, sa smu
    pouzit (§ 116 ods. 15 z. 452/2021: zverejnene kontaktne udaje PO a FO
    podnikatela). Kazdy e-mail ma odhlasenie a povie, odkial adresu mame.
    """
    e = (email or "").strip().lower()
    if not _EMAIL.match(e):
        return "vylucene", "neplatna adresa"
    lokal, domena = e.split("@", 1)
    zaklad = re.split(r"[._\-+0-9]", lokal)[0]
    if lokal in _VSEOBECNE or zaklad in _VSEOBECNE:
        return "ok", "vseobecna firemna adresa"
    if domena in _FREEMAIL:
        return "ok", "kontakt zverejneny vo Vestniku (verejna schranka)"
    if re.fullmatch(r"[a-z]+[._-][a-z]+", lokal):
        return "ok", "osobny kontakt zverejneny firmou vo Vestniku"
    return "ok", "kontakt zverejneny firmou vo Vestniku"


# ── 1. kontakty z Vestnika UVO ─────────────────────────────────────────────

def kontakty_z_formulara(formular, vestnik, publikovane):
    """Vitazi vysledku sutaze s oficialnym e-mailom (BT-506) -> [riadok]."""
    import uvo
    druh, riadky = uvo.rozober(formular, vestnik, publikovane)
    if druh != "vysledok":
        return []
    koren = formular.get("components") or []
    email_ica = {}
    for _, org in uvo._s_id(uvo.najdi(koren, "GR-Organisations_panel"), "ORG"):
        ico = ico8(uvo.prvy(org, "BT-501-Organization-Company-CIN"))
        e = uvo._email(uvo.prvy(org, "BT-506-Organization-Company"))
        if ico and e:
            email_ica[ico] = e
    out = []
    for r in riadky:
        ico = ico8(r.get("vitaz_ico"))
        e = email_ica.get(ico)
        if not e or ico == ico8(r.get("obstaravatel_ico")):
            continue
        out.append({"ico": ico, "nazov": r.get("vitaz_nazov") or "", "email": e,
                    "segment": r.get("sektor"), "kraj": NUTS_KRAJ.get((r.get("nuts") or "")[:5]),
                    "posledny_urad": r.get("obstaravatel_nazov"), "zdroj_url": r.get("url"),
                    "zdroj_datum": r.get("publikovane")})
    return out


def zluc_kontakty(riadky):
    """Na firmu jeden riadok: najnovsia adresa; segment a kraj podla najcastejsieho vyskytu."""
    podla = {}
    for r in riadky:
        podla.setdefault(r["ico"], []).append(r)
    out = []
    for ico, rr in podla.items():
        rr.sort(key=lambda x: x.get("zdroj_datum") or "", reverse=True)
        naj = dict(rr[0])

        def najcastejsi(k):
            cnt = {}
            for x in rr:
                if x.get(k):
                    cnt[x[k]] = cnt.get(x[k], 0) + 1
            return max(cnt, key=lambda v: (cnt[v], v)) if cnt else None
        naj["segment"] = najcastejsi("segment")
        naj["kraj"] = najcastejsi("kraj") or naj.get("kraj")
        naj["stav"], naj["dovod"] = posud_email(naj["email"], naj["nazov"])
        out.append(naj)
    return out


def doplnit_odbor(sb, kontakty):
    """Odbor firmy podla jej zmluv v CRZ (dodavatelia.hlavny_sektor), nie podla jednej sutaze."""
    ica = [k["ico"] for k in kontakty]
    hlavny = {}
    for i in range(0, len(ica), 200):
        for r in (sb.table("dodavatelia").select("supplier_cin,hlavny_sektor")
                  .in_("supplier_cin", ica[i:i + 200] + [x.lstrip("0") for x in ica[i:i + 200]])
                  .execute().data):
            if r.get("hlavny_sektor"):
                hlavny[ico8(r["supplier_cin"])] = r["hlavny_sektor"]
    for k in kontakty:
        if k["ico"] in hlavny:
            k["segment"] = hlavny[k["ico"]]
    return len(hlavny)


def krok_kontakty(sb, nasucho, od_rok, limit):
    import uvo
    sess = uvo._session()
    cisla = uvo.zoznam_cisel(sess, od_rok)[-limit:]
    log.info("Prechadzam %d cisel Vestnika od roku %d.", len(cisla), od_rok)
    riadky = []
    for c in cisla:
        try:
            data = uvo.stiahni(sess, c["url"])
        except Exception as e:
            log.warning("Vestnik %s preskakujem: %s", c["vestnik"], e)
            continue
        import json
        pub = uvo.datum(data.get("bulletinPublishDate"))
        for p in data.get("bulletinItemList") or []:
            try:
                formular = json.loads(p.get("itemData") or "")
                riadky += kontakty_z_formulara(formular, c["vestnik"], pub)
            except Exception:
                continue
    kontakty = zluc_kontakty(riadky)
    if sb is not None:
        doplnit_odbor(sb, kontakty)
    pocty = {}
    for k in kontakty:
        pocty[k["stav"]] = pocty.get(k["stav"], 0) + 1
    seg = {}
    for k in kontakty:
        if k["stav"] == "ok":
            seg[k["segment"]] = seg.get(k["segment"], 0) + 1
    log.info("Firiem s e-mailom: %d, stavy %s; 'ok' podla sektora %s", len(kontakty), pocty,
             dict(sorted(seg.items(), key=lambda x: -x[1])[:10]))
    if nasucho:
        for k in kontakty[:10]:
            log.info("  %s %s <%s> %s %s %s", k["ico"], k["nazov"], k["email"], k["stav"], k["segment"], k["kraj"])
        log.info("NASUCHO — nic nezapisane.")
        return 0
    # existujuce riadky: stav, ktory Marek zmenil rucne, a odhlasenie sa neprepisuju
    stare = {r["ico"]: r for r in _vsetky(sb, "oslovenie_firiem_kontakty", "ico,stav,dovod,email,odhlasene_at")}
    nove = []
    for k in kontakty:
        s = stare.get(k["ico"])
        riadok = {x: k.get(x) for x in ("ico", "nazov", "email", "segment", "kraj", "posledny_urad",
                                        "zdroj_url", "zdroj_datum")}
        # kazdy riadok davky musi mat rovnake stlpce: chybajuci stav by PostgREST
        # zapisal ako NULL a cela davka by padla (400, not null)
        riadok.update(zdroj="uvo", upravene_at=datetime.now(timezone.utc).isoformat())
        if s is None:
            riadok.update(stav=k["stav"], dovod=k["dovod"])
        elif s["stav"] == "na_kontrolu" or (s["email"] != k["email"] and s["stav"] == "ok"):
            # na_kontrolu a nova adresa sa posudia znova; 'vylucene' a 'odpovedal'
            # (rucne rozhodnutia) a odhlasenie sa nikdy neprepisuju
            riadok.update(stav=k["stav"], dovod=k["dovod"])
        else:
            riadok.update(email=s["email"], stav=s["stav"], dovod=s.get("dovod"))
        nove.append(riadok)
    for i in range(0, len(nove), 200):
        try:
            sb.table("oslovenie_firiem_kontakty").upsert(nove[i:i + 200], on_conflict="ico").execute()
        except Exception as e:     # duplicitny e-mail medzi firmami (zdielana adresa)
            log.warning("Davka %d: %s — skusam po jednom", i, type(e).__name__)
            for r in nove[i:i + 200]:
                try:
                    sb.table("oslovenie_firiem_kontakty").upsert(r, on_conflict="ico").execute()
                except Exception:
                    log.warning("  %s %s preskakujem (adresa uz patri inej firme)", r["ico"], r["email"])
    log.info("Zapisane: %d firiem.", len(nove))
    return 0


# ── 2. hook: skutocne konciace zmluvy v odbore a kraji ──────────────────────

def _vsetky(sb, tabulka, stlpce, filtre=lambda q: q):
    return ko._vsetky(sb, tabulka, stlpce, filtre)


def nacitaj_zmluvy(sb, segmenty, dnes):
    """Konciace zmluvy (opportunities) v segmentoch, 1 az 15 mesiacov dopredu."""
    od, do = (dnes + timedelta(days=30)).isoformat(), (dnes + timedelta(days=450)).isoformat()
    riadky = _vsetky(sb, "opportunities",
                     "contract_id,sector,kraj,authority_name,subject,price_total,effective_to,supplier_name",
                     lambda q: q.in_("sector", list(segmenty)).gte("effective_to", od).lte("effective_to", do))
    # dodavatel podla ICO (aby sme firme neukazovali jej vlastnu zmluvu)
    ica = {}
    ids = [r["contract_id"] for r in riadky]
    for i in range(0, len(ids), 200):
        for c in (sb.table("contracts").select("id,supplier_cin").in_("id", ids[i:i + 200]).execute().data):
            ica[c["id"]] = ico8(c.get("supplier_cin"))
    for r in riadky:
        r["supplier_ico"] = ica.get(r["contract_id"], "")
    return riadky


def hook_pre_firmu(kontakt, zmluvy, dnes):
    """-> {N, top3} alebo None. Zmluvy v segmente a kraji firmy, nie jej vlastne."""
    seg, kraj, ico = kontakt.get("segment"), kontakt.get("kraj"), ico8(kontakt["ico"])
    if not seg or not kraj:
        return None
    rok = (dnes + timedelta(days=365)).isoformat()
    v = [z for z in zmluvy if z["sector"] == seg and z["kraj"] == kraj
         and z["supplier_ico"] != ico and z.get("subject") and z.get("authority_name")]
    n12 = sum(1 for z in v if z["effective_to"] <= rok)
    if not v or n12 < 1:
        return None
    v.sort(key=lambda z: -(float(z.get("price_total") or 0)))
    return {"N": n12, "zmluvy": [{"urad": z["authority_name"], "predmet": _skrat(z["subject"]),
                                   "suma": ko.eur(z.get("price_total")), "koniec": z["effective_to"],
                                   "contract_id": z["contract_id"]} for z in v[:3]]}


def _skrat(t, n=90):
    t = " ".join(str(t or "").split()).rstrip(".")
    return t if len(t) <= n else t[:n - 1].rsplit(" ", 1)[0] + "…"


# ── 3. texty (sekcia 3 planu predaja) ──────────────────────────────────────

def utm(cesta, krok, variant):
    return f"{WEB}{cesta}?utm_source=email&utm_medium=oslovenie&utm_campaign=firmy-k{krok}{variant.lower()}"


def zostav(krok, kontakt, hook, variant):
    """-> {predmet, odstavce} alebo None. Odstavec = str alebo [str | ('a', text, url)]."""
    seg = kontakt["segment"]
    odbor, odbor_kr = ODBOR.get(seg, (seg.lower().replace("_", " "), seg.lower()))
    kraj = kontakt["kraj"]
    kraj_l = KRAJ_LOKAL.get(kraj, kraj)
    z1 = hook["zmluvy"][0]
    n = hook["N"]
    zml = "zmluva" if n == 1 else ("zmluvy" if 2 <= n <= 4 else "zmlúv")
    konci = "končí" if n == 1 or n >= 5 else "končia"
    firma = kratky_nazov(kontakt["nazov"])
    urad_firmy = kontakt.get("posledny_urad")
    suma = f", {z1['suma']}" if z1.get("suma") else ""
    podpis = "S pozdravom\nMarek Takáč\nPredTendrom.sk"
    if krok == 1:
        predmet = (f"Zmluva na {odbor_kr} pre {z1['urad']} končí {mesiac_rok(z1['koniec'])}"
                   if variant == "A" else f"{n} {zml} na {odbor_kr} v {kraj_l} {konci} do roka")
        uvod = (f"vo Vestníku verejného obstarávania som videl, že {firma} pracuje pre {urad_firmy}. "
                if urad_firmy else f"vo Vestníku verejného obstarávania som videl, že {firma} dodáva verejnému sektoru. ")
        return {"predmet": _skrat(predmet, 120), "odstavce": [
            "Dobrý deň,",
            uvod + "Našiel som zmluvu, ktorá by Vás mohla zaujímať:",
            f"{z1['urad']} – {z1['predmet']}{suma}, končí {ko.datum_sk(z1['koniec'])}.",
            f"V odbore {odbor} v {kraj_l} {konci} do 12 mesiacov {n} {zml} úradov. PredTendrom ich "
            "zbiera na jedno miesto a raz týždenne Vám pošle nové, aby ste mali čas pripraviť sa "
            "skôr, než úrad vyhlási súťaž.",
            (["Ako to vyzerá, ukazuje krátke video: ",
              ("a", "predtendrom.sk" + VIDEO_URL, utm(VIDEO_URL, 1, variant))] if VIDEO_URL else
             ["Ako to vyzerá, uvidíte bez registrácie na ",
              ("a", "predtendrom.sk", utm("/", 1, variant)),
              " – stačí zadať odbor a kraj."]),
            podpis]}
    if krok == 2:
        dalsie = hook["zmluvy"][1:3]
        if not dalsie:
            dalsie = hook["zmluvy"][:1]
        riadky = "\n".join(f"• {z['urad']} – {z['predmet']}, končí {ko.datum_sk(z['koniec'])}" for z in dalsie)
        predmet = (f"Ďalšie zmluvy na {odbor_kr} v {kraj_l}" if variant == "A"
                   else f"Zmluvy na {odbor_kr}, ktoré končia v {kraj_l}")
        return {"predmet": _skrat(predmet, 120), "odstavce": [
            "Dobrý deň,",
            "nadväzujem na môj e-mail. Nie každá zmluva sa Vás týka, preto posielam ďalšie z Vášho kraja:",
            riadky,
            ["Všetky si môžete pozrieť bez registrácie: na ",
             ("a", "predtendrom.sk", utm("/", 2, variant)),
             " zadajte odbor a kraj a hneď uvidíte končiace zmluvy."],
            "Ak to pre Vás nie je, odpíšte „Nie“ a už nenapíšem.",
            "Marek Takáč"]}
    if krok == 3:
        predmet = f"Posledný e-mail o zmluvách na {odbor_kr}" if variant == "A" \
            else f"Kedy pripraviť ponuku pre {z1['urad']}?"
        return {"predmet": _skrat(predmet, 120), "odstavce": [
            "Dobrý deň,",
            f"pošlem už len jeden tip. Ak úrad zmluvu na {odbor_kr} obstaráva znova, súťaž zvyčajne vyhlási "
            "niekoľko mesiacov pred jej koncom. Kto má referencie, ceny a kapacity pripravené vopred, má výhodu.",
            f"PredTendrom môžete vyskúšať 14 dní zadarmo, bez platobnej karty. Prvým 30 firmám dávame "
            f"ročný plán za {ZACIATOCNA_CENA} namiesto {BEZNA_CENA}.",
            [("a", "Vyskúšať 14 dní zadarmo", utm("/prihlasenie", 3, variant))],
            "Ďakujem za Váš čas.\nMarek Takáč"]}
    return None


def odhlasenie_url(token):
    return f"{WEB}/odhlasenie-firmy.html?t={token}"


def vyrenderuj(sprava, token):
    """-> (text, html). Escapuje sa vsetko okrem nasich vlastnych odkazov. Bez sledovacich pixelov."""
    odhl = odhlasenie_url(token)
    txt, htm = [], []
    for o in sprava["odstavce"]:
        casti = o if isinstance(o, list) else [o]
        t, h = [], []
        for c in casti:
            if isinstance(c, tuple):
                _, text, url = c
                if not url.startswith(WEB + "/"):
                    raise ValueError(f"Odkaz musi viest na predtendrom.sk: {url}")
                t.append(f"{text} ({url})")
                h.append(f'<a href="{html.escape(url)}" style="color:#1a56c4;">{html.escape(text)}</a>')
            else:
                t.append(c)
                h.append(html.escape(c).replace("\n", "<br>"))
        txt.append("".join(t))
        htm.append('<p style="margin:0 0 14px;">' + "".join(h) + "</p>")
    paticka = ("Píšem Vám na verejne uvedenú firemnú adresu z Vestníka verejného obstarávania. "
               "Ak už nechcete dostávať žiadne správy, odhláste sa tu: ")
    text = ("\n\n".join(txt) + f"\n\n--\n{paticka}{odhl}\nalebo odpovedzte „Odhlásiť“.\n"
            f"{PATICKA_FIRMA}. Zásady: {WEB}/ochrana-osobnych-udajov")
    telo = ('<!doctype html><html lang="sk"><body style="margin:0;padding:16px;'
            'font:15px/1.6 Arial,sans-serif;color:#0f1a2b;background:#ffffff;">'
            '<div style="max-width:580px;">' + "".join(htm)
            + '<p style="margin:24px 0 0;padding-top:12px;border-top:1px solid #e4e8ee;'
              'font-size:12px;line-height:1.6;color:#8a929e;">'
            + html.escape(paticka) + f'<a href="{html.escape(odhl)}" style="color:#8a929e;">odhlásiť</a>'
            " alebo odpovedzte „Odhlásiť“.<br>" + html.escape(PATICKA_FIRMA)
            + f'. <a href="{WEB}/ochrana-osobnych-udajov" style="color:#8a929e;">Zásady ochrany údajov</a></p>'
            "</div></body></html>")
    return text, telo


# ── 4. kto je na rade ──────────────────────────────────────────────────────

def variant_pre(ico):
    return "A" if int(ico8(ico) or "0") % 2 == 0 else "B"


def na_rade(kontakty, odoslane, segmenty, vylucene_ica, vylucene_emaily, dnes, novych):
    """-> [(kontakt, krok)] — najprv nadvazujuce kroky, potom novi (najviac `novych`)."""
    podla = {}
    for o in odoslane:
        if o["stav"] != "chyba":
            podla.setdefault(o["ico"], {})[o["krok"]] = date.fromisoformat(o["odoslane_at"][:10])
    pokracuju, novi = [], []
    for k in kontakty:
        ico = k["ico"]
        if (k["stav"] != "ok" or k.get("odhlasene_at") or ico8(ico) in vylucene_ica
                or (k["email"] or "").lower() in vylucene_emaily):
            continue
        kroky = podla.get(ico, {})
        if not kroky:
            if k.get("segment") in segmenty:
                novi.append((k, 1))
            continue
        posledny = max(kroky)
        if posledny >= 3:
            continue
        dalsi = posledny + 1
        if dnes >= kroky[posledny] + timedelta(days=DNI_PO_KROKU[dalsi]):
            pokracuju.append((k, dalsi))
    return pokracuju + novi[:max(0, novych)]


def smie_ostro(teraz, vynutit):
    if vynutit:
        return None
    if teraz.weekday() > 3:
        return "posielame len pondelok az stvrtok"
    if not 8 <= teraz.hour < 16:
        return "posielame len medzi 8:00 a 16:00"
    return None


def uloz_nahlad(cesta, spravy):
    bloky = []
    for s in spravy:
        bloky.append(
            "<section style='border:1px solid #ccd;border-radius:8px;margin:18px 0;padding:14px;'>"
            f"<div style='font:12px monospace;color:#556;'>komu: {html.escape(s['email'])} | krok {s['krok']}"
            f" | variant {s['variant']} | {html.escape(s['nazov'])} (IČO {s['ico']}) | "
            f"{html.escape(s['segment'] or '')}, {html.escape(s['kraj'] or '')}</div>"
            f"<div style='font:600 15px Arial;margin:6px 0 10px;'>Predmet: {html.escape(s['predmet'])}</div>"
            f"<iframe style='width:100%;height:560px;border:0;' srcdoc=\"{html.escape(s['html'])}\"></iframe>"
            "</section>")
    from pathlib import Path
    Path(cesta).write_text(
        "<!doctype html><meta charset='utf-8'><title>Náhľad oslovenia firiem</title>"
        "<body style='font:14px Arial;max-width:760px;margin:20px auto;'>"
        f"<h1>Náhľad: {len(spravy)} e-mailov</h1>" + "".join(bloky), encoding="utf-8")


def krok_posli(sb, a):
    teraz = datetime.fromisoformat(a.teraz) if a.teraz else datetime.now(BRATISLAVA)
    dnes = teraz.date()
    segmenty = [s.strip().upper() for s in a.segmenty.split(",") if s.strip()]
    ostro = not a.nasucho and not a.komu
    if ostro:
        prekazka = smie_ostro(teraz, a.vynutit)
        if prekazka:
            log.error("Ostro neposielam: %s. (Nasucho a --komu funguju vzdy.)", prekazka)
            return 1
        if not REPLY_TO:
            log.error("Chyba KAMPAN_REPLY_TO — odpovede firiem by nedosli Marekovi. Neposielam.")
            return 1
    heslo = os.getenv("ZOHO_SMTP_PASSWORD")
    if not a.nasucho and not heslo:
        log.error("Chyba ZOHO_SMTP_PASSWORD (heslo aplikacie pre %s).", ko.SMTP_USER)
        return 1

    kontakty = _vsetky(sb, "oslovenie_firiem_kontakty",
                       "ico,nazov,email,stav,segment,kraj,posledny_urad,token,odhlasene_at")
    odoslane = _vsetky(sb, "oslovenie_firiem_odoslane", "ico,krok,stav,odoslane_at")
    vylucene_ica = {ico8(r["ico"]) for r in _vsetky(sb, "organizations", "ico") if r.get("ico")}
    vylucene_emaily = {(r.get("email") or "").lower() for r in _vsetky(sb, "odber_firmy", "email")}
    rad = na_rade(kontakty, odoslane, segmenty, vylucene_ica, vylucene_emaily, dnes, a.novych)
    zmluvy = nacitaj_zmluvy(sb, {k["segment"] for k, _ in rad if k.get("segment")} or set(segmenty), dnes)

    spravy = []
    for k, krok in rad:
        hook = hook_pre_firmu(k, zmluvy, dnes)
        if not hook:
            continue
        variant = variant_pre(k["ico"])
        s = zostav(krok, k, hook, variant)
        if not s:
            continue
        text, telo = vyrenderuj(s, k["token"])
        spravy.append({**s, "krok": krok, "variant": variant, "ico": k["ico"], "nazov": k["nazov"],
                       "email": k["email"], "token": k["token"], "segment": k.get("segment"),
                       "kraj": k.get("kraj"), "hook": hook["zmluvy"][0], "text": text, "html": telo})

    dnes_odoslane = sum(1 for o in odoslane if o["stav"] != "chyba" and o["odoslane_at"][:10] == dnes.isoformat())
    kapacita = max(0, a.max - dnes_odoslane)
    davka = spravy[:kapacita]
    pocty = {}
    for s in spravy:
        pocty[f"krok{s['krok']}"] = pocty.get(f"krok{s['krok']}", 0) + 1
    log.info("Kontaktov %d (ok %d), na rade %d, s konkretnou zmluvou %d %s; dnes uz %d, limit %d.",
             len(kontakty), sum(1 for k in kontakty if k["stav"] == "ok"), len(rad), len(spravy), pocty,
             dnes_odoslane, a.max)
    if a.nahlad:
        uloz_nahlad(a.nahlad, davka if ostro else spravy)
        log.info("Nahlad: %s", a.nahlad)
    for s in spravy[:5]:
        log.info("  krok %d %s -> %s | %s", s["krok"], s["ico"], s["email"], s["predmet"])

    if a.nasucho:
        log.info("NASUCHO — nic neposlane, nic nezapisane. Dnes by islo %d.", len(davka))
        return 0
    if a.komu:
        for s in spravy[:a.test_pocet]:
            rid, chyba = ko.posli_smtp(heslo, a.komu, "[TEST] " + s["predmet"], s["text"], s["html"],
                                       s["token"], _odhlasenie=odhlasenie_url(s["token"]))
            log.info("TEST krok %d %s -> %s: %s", s["krok"], s["ico"], a.komu, chyba or "odoslane")
            time.sleep(min(PAUZA_S, 3))
        return 0

    log.info("OSTRO: posielam %d.", len(davka))
    ok = chyby = 0
    for s in davka:
        try:
            ins = sb.table("oslovenie_firiem_odoslane").insert({
                "ico": s["ico"], "krok": s["krok"], "variant": s["variant"], "email": s["email"],
                "predmet": s["predmet"], "hook": s["hook"]}).execute()
        except Exception as e:      # unique (ico, krok) — uz odoslane inym behom
            log.warning("%s krok %d: preskakujem, uz je v evidencii (%s)", s["ico"], s["krok"], type(e).__name__)
            continue
        rid_riadku = ins.data[0]["id"]
        rid, chyba = ko.posli_smtp(heslo, s["email"], s["predmet"], s["text"], s["html"], s["token"],
                                   _odhlasenie=odhlasenie_url(s["token"]))
        sb.table("oslovenie_firiem_odoslane").update(
            {"stav": "odoslane", "message_id": rid} if rid else {"stav": "chyba", "chyba": chyba}
        ).eq("id", rid_riadku).execute()
        if rid:
            ok += 1
        else:
            chyby += 1
            log.error("%s %s: %s", s["ico"], s["email"], chyba)
            if "prihlasenie" in (chyba or ""):
                log.error("Zle heslo alebo zablokovany SMTP — koncim, aby sa neplytvalo pokusmi.")
                break
        time.sleep(PAUZA_S)
    log.info("HOTOVO: odoslane %d, chyby %d.", ok, chyby)
    return 0 if not chyby else 2


def krok_zastav(sb, ica, stav):
    for ico in ica:
        r = (sb.table("oslovenie_firiem_kontakty").update({"stav": stav, "upravene_at": "now()"})
             .eq("ico", ico8(ico)).execute())
        log.info("%s -> %s (%s)", ico8(ico), stav, "ok" if r.data else "nenajdene")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="krok", required=True)
    k = sub.add_parser("kontakty")
    k.add_argument("--nasucho", action="store_true")
    k.add_argument("--od-rok", type=int, default=2025)
    k.add_argument("--limit", type=int, default=1000, help="najviac cisel Vestnika (najnovsie)")
    p = sub.add_parser("posli")
    p.add_argument("--segmenty", default="UPRATOVANIE,OSTRAHA")
    p.add_argument("--novych", type=int, default=0, help="kolko novych firiem dnes zacat (krok 1)")
    p.add_argument("--nasucho", action="store_true")
    p.add_argument("--komu", help="poslat par testovacich e-mailov len na tuto adresu")
    p.add_argument("--test-pocet", type=int, default=3)
    p.add_argument("--max", type=int, default=30, help="max. e-mailov za den spolu")
    p.add_argument("--nahlad", help="subor s HTML nahladom")
    p.add_argument("--vynutit", action="store_true", help="obist den v tyzdni a hodinu")
    p.add_argument("--teraz", help="YYYY-MM-DDTHH:MM, len na testy")
    z = sub.add_parser("zastav")
    z.add_argument("--ico", required=True, help="ICO oddelene ciarkou")
    z.add_argument("--stav", default="odpovedal", choices=("odpovedal", "vylucene", "ok"))
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    from store import klient
    sb = klient()
    if a.krok == "kontakty":
        return krok_kontakty(sb, a.nasucho, a.od_rok, a.limit)
    if a.krok == "zastav":
        return krok_zastav(sb, [x for x in a.ico.split(",") if x.strip()], a.stav)
    if a.novych and not a.nasucho and not a.komu and not segmenty_ok(a.segmenty):
        log.error("Neznamy segment: %s", a.segmenty)
        return 1
    return krok_posli(sb, a)


def segmenty_ok(s):
    return all(x.strip().upper() in ODBOR for x in s.split(",") if x.strip())


if __name__ == "__main__":
    sys.exit(main())
