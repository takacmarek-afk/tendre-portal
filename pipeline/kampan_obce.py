"""Kampan pre obce po volbach 2026 — personalizovane e-maily obciam.

Plan a texty: Claude Doc "Kampan pre obce po volbach 2026" (projekt
PredTendrom.sk). Migracia: supabase/48_kampan_obce.sql.
Workflow: .github/workflows/kampan-obce.yml (len rucne spustenie).

KROKY
    python kampan_obce.py kontakty --nasucho   # co by sa zapisalo
    python kampan_obce.py kontakty             # zapise kontakty z Vestnika UVO
    python kampan_obce.py posli --vlna vlna1 --nasucho --nahlad nahlad.html
    python kampan_obce.py posli --vlna vlna1 --komu ja@x.sk   # 3 testovacie
    python kampan_obce.py posli --vlna vlna1 --max 50         # OSTRO

KOMU PISEME (a komu nie)
  Len na ZVEREJNENU uradnu adresu obce (pravnicka osoba) — vynimka zo
  suhlasu na priamy marketing podla zakona 452/2021. Poslancom nepiseme.
  Adresa sa pouzije len so stavom 'ok' (vseobecna adresa typu podatelna@,
  obec@ alebo adresa na domene obce). Osobne adresy (meno.priezvisko@) a
  adresy na cudzej domene (externy obstaravatel, ktory vyplnil oznamenie
  za obec) dostanu 'na_kontrolu' a bez rucneho schvalenia sa nepouziju.
  Odhlasena obec uz nedostane nic. Obec, ktora uz ma ucet, nedostane nic.

POISTKY
  - nikomu dvakrat v tej istej vlne (unique ico+vlna, riadok sa zapise
    PRED odoslanim — ked beh spadne uprostred, e-mail sa nezopakuje)
  - ostro len od datumu vlny a len v utorok az stvrtok (--vynutit to obide)
  - najviac --max e-mailov za den spolu za vsetky vlny (default 50)
  - bez KAMPAN_REPLY_TO sa ostro neposiela: odpovede musia ist Marekovi
  - obec, o ktorej nemame nic konkretne, nedostane nic
"""
import argparse
import html
import json
import logging
import os
import re
import sys
import time
import unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

log = logging.getLogger("kampan")

RESEND_URL = "https://api.resend.com/emails"
ODOSIELATEL = os.getenv("KAMPAN_OD", "Marek Takáč z PredTendrom.sk <marek@predtendrom.sk>")
REPLY_TO = os.getenv("KAMPAN_REPLY_TO", "").strip()
TELEFON = os.getenv("KAMPAN_TELEFON", "").strip()
ROK_VOLIEB = int(os.getenv("KAMPAN_ROK_VOLIEB", "2026"))
WEB = "https://predtendrom.sk"
PAUZA_S = 0.6            # Resend free plan: max 2 e-maily za sekundu

VLNY = {
    "vlna1": date(2026, 11, 24),   # po ustanovujucich zastupitelstvach
    "vlna2": date(2027, 1, 7),     # po sviatkoch
}
DNI_MEDZI_VLNAMI = 14
SEGMENTY = ("poradca", "uvo", "crz", "dotacie")   # poradie = priorita

_JE_OBEC = re.compile(r"^\s*(obec|mesto|mestsk[aá]\s+[cč]as[tť])\s+", re.IGNORECASE)
_EMAIL = re.compile(r"^[^@\s;,]+@[^@\s;,]+\.[a-z]{2,}$")

# Vseobecne uradne adresy — lokalna cast (pred @) alebo jej zaciatok.
_VSEOBECNE = ("podatelna", "obec", "obecnyurad", "obecny.urad", "obecny_urad", "ou", "urad",
              "mesto", "mestskyurad", "mestsky.urad", "msu", "mu", "starosta", "starostka",
              "primator", "primatorka", "info", "sekretariat", "kancelaria", "prednosta",
              "matrika", "ekonom", "uctaren", "obstaravanie", "vo", "mcu", "miestnyurad")
_FREEMAIL = ("gmail.com", "azet.sk", "zoznam.sk", "centrum.sk", "post.sk", "pobox.sk",
             "atlas.sk", "orangemail.sk", "stonline.sk", "szm.sk", "seznam.cz", "yahoo.com",
             "hotmail.com", "outlook.com", "outlook.sk")


# ── pomocne ────────────────────────────────────────────────────────────────

def _norm(t):
    nfkd = unicodedata.normalize("NFKD", str(t or ""))
    return " ".join("".join(c for c in nfkd if not unicodedata.combining(c)).lower().split())


def _kompakt(t):
    return re.sub(r"[^a-z0-9]", "", _norm(t))


def bez_prefixu(nazov):
    """'Obec Dolná Streda' -> 'Dolná Streda'; 'Mestská časť Bratislava-Petržalka' -> 'Bratislava-Petržalka'."""
    return _JE_OBEC.sub("", str(nazov or "")).strip(" ,")


def je_obec(nazov):
    return bool(_JE_OBEC.match(str(nazov or "")))


def je_mesto(nazov):
    return _norm(nazov).startswith("mesto ")


def eur(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f <= 0:
        return None
    return f"{f:,.0f}".replace(",", " ") + " €"


def datum_sk(d):
    if not d:
        return None
    if isinstance(d, str):
        d = date.fromisoformat(d[:10])
    return f"{d.day}. {d.month}. {d.year}"


# ── 1. klasifikacia adresy ─────────────────────────────────────────────────

def posud_email(email, obec_nazov):
    """-> (stav, dovod). 'ok' len pre vseobecnu uradnu adresu alebo adresu
    na domene obce, ktora nevyzera osobne."""
    email = (email or "").strip().lower()
    if not _EMAIL.match(email):
        return "vylucene", "neplatna adresa"
    lokal, domena = email.split("@", 1)
    obec_k = _kompakt(bez_prefixu(obec_nazov))
    tokeny = [t for t in re.split(r"[._\-]", lokal) if t]
    # kratke slova (ou, mu, vo) len ako cely token — inak by "vojtech.kral@"
    # vyzeralo ako vseobecna adresa
    vseobecna = any(t in _VSEOBECNE for t in tokeny) \
        or any(len(v) >= 5 and lokal.startswith(v) for v in _VSEOBECNE)
    # nazov obce kratsi ako 4 znaky by sa nahodne nasiel aj v cudzom texte
    obec_ok = len(obec_k) >= 4
    obec_v_lokal = obec_ok and obec_k in _kompakt(lokal)
    obec_v_domene = obec_ok and obec_k in _kompakt(domena.rsplit(".", 1)[0])
    # meno.priezvisko@ (dva a viac cisto pismenovych tokenov, ziadny vseobecny,
    # ani nazov obce) = osobna adresa zamestnanca
    osobna = (len(tokeny) >= 2 and all(t.isalpha() for t in tokeny)
              and not vseobecna and not obec_v_lokal)

    # Poradie pravidiel vychadza z realnych dat (25. 9. 2026, 1 019 obci):
    # vyse tretiny adries patri externym obstaravatelom (cvo.sk, tenders.sk,
    # mpprofit.sk, ...), ktori pisu klient@, info@, obstaravanie@ na svojej
    # domene. Obce na hostingu (lekosonline.sk, orava.sk) maju v adrese
    # nazov obce. Na verejnej schranke (gmail, azet) vseobecne slovo
    # nestaci — "obstaravanie.xy@gmail.com" moze byt aj agentura.
    if osobna:
        return "na_kontrolu", "vyzera ako osobna adresa"
    if obec_v_lokal:
        return "ok", "nazov obce v adrese"
    if domena in _FREEMAIL:
        return "na_kontrolu", "verejna schranka bez nazvu obce"
    if vseobecna and obec_v_domene:
        return "ok", "vseobecna adresa na domene obce"
    if obec_v_domene:
        return "na_kontrolu", "adresa na domene obce, ale moze byt osobna"
    if vseobecna:
        return "na_kontrolu", "vseobecna adresa, ale domena nesedi s obcou"
    return "na_kontrolu", "domena nesedi s obcou (externy obstaravatel?)"


# ── 2. register obci: nazov (+kraj) -> kod obce SU SR ─────────────────────

def nacitaj_register(data_dir=None):
    """-> (podla_nazvu: {kompakt: [(kod6, kraj), ...]}, kraj_nuts: {SK0xx: nazov kraja})."""
    d = Path(data_dir) if data_dir else Path(__file__).parent / "data"
    try:
        nuts4 = json.loads((d / "register_nuts4_raw.json").read_text(encoding="utf-8"))["category"]["label"]
        obce = json.loads((d / "register_obce_raw.json").read_text(encoding="utf-8"))["category"]["label"]
    except (OSError, KeyError, json.JSONDecodeError):
        return {}, {}
    podla = {}
    for kod, nazov in obce.items():
        m = re.match(r"^SK([0-9A-Z]{4})(\d{6})$", kod)
        if not m:
            continue
        kraj = nuts4.get(("SK" + m.group(1))[:5])
        # kompaktny kluc: register pise "Bratislava - Staré Mesto", Vestnik
        # "Mestská časť Bratislava-Staré Mesto"
        podla.setdefault(_kompakt(nazov), []).append((m.group(2), kraj))
    kraje = {k: v for k, v in nuts4.items() if len(k) == 5}
    return podla, kraje


def kod_obce(nazov, kraj, register):
    """Jednoznacny kod obce podla nazvu, pri zhode nazvov rozhodne kraj.
    Radsej None nez zly kod (zly kod = zle meno starostu v e-maili)."""
    kandidati = register.get(_kompakt(bez_prefixu(nazov)), [])
    if len(kandidati) == 1:
        return kandidati[0][0]
    if kraj:
        v_kraji = [k for k, kr in kandidati if kr == kraj]
        if len(v_kraji) == 1:
            return v_kraji[0]
    return None


# ── 3. kontakty z Vestnika UVO ─────────────────────────────────────────────

def vyber_kontakty(riadky, register, kraje):
    """riadky z uvo_vysledky/uvo_vyzvy (obstaravatel_ico, _nazov, _email,
    nuts, url, publikovane) -> {ico: kontakt}. Na jednu obec jedna adresa:
    najprv 'ok', potom najnovsie zverejnena."""
    kandidati = {}
    for r in riadky:
        ico = (r.get("obstaravatel_ico") or "").strip()
        nazov = r.get("obstaravatel_nazov")
        email = (r.get("obstaravatel_email") or "").strip().lower()
        if not ico or not email or not je_obec(nazov):
            continue
        stav, dovod = posud_email(email, nazov)
        if stav == "vylucene":
            continue
        kraj = kraje.get((r.get("nuts") or "")[:5])
        kandidati.setdefault(ico, []).append({
            "ico": ico, "obec": nazov.strip(), "kraj": kraj, "email": email,
            "stav": stav, "dovod": dovod, "zdroj": "uvo",
            "zdroj_url": r.get("url"), "zdroj_datum": r.get("publikovane"),
        })
    out = {}
    for ico, zoz in kandidati.items():
        zoz.sort(key=lambda k: (k["stav"] == "ok", k["zdroj_datum"] or ""), reverse=True)
        k = dict(zoz[0])
        # kraj z miesta plnenia moze byt pri jednej zakazke iny; zober najcastejsi
        kraje_obce = [z["kraj"] for z in zoz if z["kraj"]]
        k["kraj"] = max(set(kraje_obce), key=kraje_obce.count) if kraje_obce else None
        k["kod_obce"] = kod_obce(k["obec"], k["kraj"], register)
        out[ico] = k
    return out


def _vsetky(sb, tabulka, stlpce, filtre=lambda q: q):
    out, od = [], 0
    while True:
        r = filtre(sb.table(tabulka).select(stlpce)).range(od, od + 999).execute()
        out.extend(r.data)
        if len(r.data) < 1000:
            return out
        od += 1000


def krok_kontakty(sb, nasucho):
    register, kraje = nacitaj_register()
    stlpce = "obstaravatel_ico,obstaravatel_nazov,obstaravatel_email,nuts,url,publikovane"
    riadky = []
    for t in ("uvo_vysledky", "uvo_vyzvy"):
        riadky += _vsetky(sb, t, stlpce, lambda q: q.not_.is_("obstaravatel_email", "null"))
    nove = vyber_kontakty(riadky, register, kraje)
    existujuce = {r["ico"]: r for r in _vsetky(sb, "kampan_obce_kontakty",
                                                "ico,email,stav,zdroj,zdroj_datum")}
    vlozit, upravit = [], []
    for ico, k in nove.items():
        e = existujuce.get(ico)
        if not e:
            vlozit.append(k)
        elif (e["zdroj"] == "uvo" and e["stav"] != "vylucene" and e["email"] != k["email"]
              and (k["zdroj_datum"] or "") > (e.get("zdroj_datum") or "")):
            upravit.append(k)       # novsia adresa z UVO; rucne kontakty nechavame
    pocty = {s: sum(1 for k in nove.values() if k["stav"] == s) for s in ("ok", "na_kontrolu")}
    log.info("Obce s e-mailom vo Vestniku: %d (ok %d, na kontrolu %d), s kodom obce %d. "
             "Nove %d, aktualizovat %d.", len(nove), pocty["ok"], pocty["na_kontrolu"],
             sum(1 for k in nove.values() if k["kod_obce"]), len(vlozit), len(upravit))
    for k in list(nove.values())[:8]:
        log.info("  ukazka: %s | %s | %s (%s)", k["obec"], k["email"], k["stav"], k["dovod"])
    if nasucho:
        log.info("NASUCHO — nic nezapisane.")
        return 0
    for i in range(0, len(vlozit), 500):
        sb.table("kampan_obce_kontakty").insert(vlozit[i:i + 500]).execute()
    for k in upravit:
        sb.table("kampan_obce_kontakty").update({
            **{x: k[x] for x in ("email", "stav", "dovod", "zdroj_url", "zdroj_datum", "kraj")},
            "upravene_at": datetime.now(timezone.utc).isoformat(),
        }).eq("ico", k["ico"]).execute()
    log.info("Zapisane: %d novych, %d aktualizovanych.", len(vlozit), len(upravit))
    return 0


# ── 4. texty ───────────────────────────────────────────────────────────────

def oslovenie(obec_nazov, starosta):
    """'Dobrý deň, pán starosta Novák,' / 'pani primátorka Nováková,' / 'Dobrý deň,'."""
    if not starosta or not starosta.get("priezvisko"):
        return "Dobrý deň,"
    priezvisko = starosta["priezvisko"].strip().title() if starosta["priezvisko"].isupper() \
        else starosta["priezvisko"].strip()
    z = je_zena(priezvisko)
    if je_mesto(obec_nazov):
        funkcia = "pani primátorka" if z else "pán primátor"
    else:
        funkcia = "pani starostka" if z else "pán starosta"
    return f"Dobrý deň, {funkcia} {priezvisko},"


def je_zena(priezvisko):
    """Slovenske zenske priezviska: -ová a pridavne mena na -á (Malá, Horská).
    Muzske priezviska na dlhe -á takmer neexistuju (Baťa, Straka maju kratke -a)."""
    p = (priezvisko or "").strip().lower()
    return p.endswith("ová") or p.endswith("á")


def kraj_lokal(kraj):
    """'Trnavský kraj' -> 'Trnavskom kraji', 'Trenčiansky kraj' -> 'Trenčianskom kraji'."""
    k = (kraj or "").strip()
    return k[:-len("ý kraj")] + "om kraji" if k.endswith(("ý kraj", "y kraj")) else k


def utm(cesta, vlna, segment):
    return f"{WEB}/{cesta}?utm_source=email&utm_medium=obce&utm_campaign={vlna}-{segment}"


def zostav(vlna, kontakt, starosta, data):
    """-> dict(segment, predmet, odstavce[list[str|tuple]]) alebo None.

    Odstavec je text, alebo zoznam casti, kde ('odkaz', text, url) je odkaz.
    Ked pre obec nemame konkretny udaj, veta vypadne; ked nemame nic,
    obec nedostane nic.
    """
    obec = bez_prefixu(kontakt["obec"])
    podpis = "S pozdravom\nMarek Takáč, PredTendrom.sk" + (f"\n{TELEFON}" if TELEFON else "")
    uvod = oslovenie(kontakt["obec"], starosta)

    if vlna == "vlna2":
        predmet_zmluvy = (data.get("uvo") or data.get("crz") or {}).get("predmet")
        veta = ("ak obec v roku 2027 plánuje žiadať o dotáciu alebo "
                + (f"znova obstarávať zákazku „{predmet_zmluvy.rstrip('.')}“, " if predmet_zmluvy
                   else "niečo obstarávať, ")
                + "na ")
        return {
            "segment": "followup",
            "predmet": f"{obec}: dotácie a obstarávanie na rok 2027",
            "odstavce": [
                uvod,
                [veta, ("odkaz", "predtendrom.sk/obce", utm("obce.html", vlna, "followup")),
                 " je prehľad, kto práve rozdáva peniaze obciam, a na ",
                 ("odkaz", "predtendrom.sk/trh", utm("trh.html", vlna, "followup")),
                 " môžete nájsť poradcu. Obe sú pre obce zadarmo."],
                "Ak to pre vás nie je aktuálne, stačí odpísať a viac vám nebudem písať.",
                podpis,
            ],
        }

    seg = next((s for s in SEGMENTY if data.get(s)), None)
    if not seg:
        return None
    d = data[seg]
    obce_link = ("odkaz", "predtendrom.sk/obce", utm("obce.html", vlna, seg))
    trh_link = ("odkaz", "predtendrom.sk/trh", utm("trh.html", vlna, seg))

    if seg == "poradca":
        kedy = datum_sk(d.get("najate"))
        return {"segment": seg,
                "predmet": f"{obec}: žiadosť o dotáciu — čo príde potom",
                "odstavce": [
                    uvod,
                    "blahoželám k zvoleniu. V Centrálnom registri zmlúv vidíme, že obec má"
                    + (f" od {kedy}" if kedy else "")
                    + f" zmluvu s firmou {d['sprostredkovatel']} na prípravu žiadosti o dotáciu."
                    " Keď dotácia príde, obec bude musieť vybrať dodávateľa — a na to je dobré"
                    " byť pripravený včas.",
                    ["Na ", trh_link, " môžete vypísať, s čím budete potrebovať pomôcť, a ozvú sa"
                     " vám poradcovia so skúsenosťami s obdobnými projektmi. Pre obce je to zadarmo."],
                    podpis]}

    if seg in ("uvo", "crz"):
        suma = eur(d.get("hodnota"))
        koniec = datum_sk(d.get("koniec"))
        if seg == "uvo":
            fakt = (f"{d['predmet'].rstrip('.')} — súťaž vyhrala firma {d['dodavatel']}"
                    + (f" za {suma}" if suma else "")
                    + (f", zmluva končí {koniec}." if koniec else "."))
            zdroj = "Z Vestníka verejného obstarávania vidíme napríklad:"
        else:
            fakt = (f"{d['predmet'].rstrip('.')} — dodávateľ {d['dodavatel']}"
                    + (f", {suma}" if suma else "")
                    + (f", zmluva končí {koniec}." if koniec else "."))
            zdroj = "Z Centrálneho registra zmlúv vidíme napríklad:"
        return {"segment": seg,
                "predmet": f"{obec}: čo má obec podpísané a kedy to končí",
                "odstavce": [
                    uvod,
                    "blahoželám k zvoleniu. Prvé týždne v úrade sú hlavne o tom zistiť, čo obec má"
                    " podpísané a kedy to končí. S tým vám vieme pomôcť hneď.",
                    f"{zdroj} {fakt} Ak ju chcete znova obstarávať, príprava zvyčajne trvá"
                    " 3 až 6 mesiacov.",
                    ["Prehľad zmlúv a dotácií pre obce"
                     + (f" v {kraj_lokal(kontakt['kraj'])}" if kontakt.get("kraj") else "")
                     + " je zadarmo a bez registrácie: ", obce_link],
                    ["Ak by ste na obstarávanie alebo žiadosť o dotáciu potrebovali pomoc, na ",
                     trh_link, " môžete vypísať, s čím potrebujete pomôcť, a ozvú sa vám poradcovia."
                     " Aj to je pre obce zadarmo."],
                    podpis]}

    # dotacie
    suma = eur(d.get("suma"))
    pocet = d.get("pocet") or 0
    slovo = "dotáciu" if pocet == 1 else ("dotácie" if 2 <= pocet <= 4 else "dotácií")
    return {"segment": seg,
            "predmet": f"{obec} a dotácie: kto práve rozdáva peniaze obciam",
            "odstavce": [
                uvod,
                f"blahoželám k zvoleniu. Podľa Centrálneho registra zmlúv obec {obec} dostala"
                f" {pocet} {slovo}" + (f" v celkovej sume {suma}" if suma else "") + ".",
                ["Kto práve rozdáva peniaze obciam a na čo, uvidíte zadarmo a bez registrácie na ",
                 obce_link, "."],
                podpis]}


def _odhlasenie_url(token):
    return f"{WEB}/odhlasenie-obce.html?t={token}"


def vyrenderuj(sprava, token):
    """-> (text, html). Escapuje sa vsetko okrem nasich vlastnych odkazov."""
    odhl = _odhlasenie_url(token)
    txt_casti, html_casti = [], []
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
        txt_casti.append("".join(t))
        html_casti.append("<p style=\"margin:0 0 14px;\">" + "".join(h) + "</p>")
    paticka = ("Tento e-mail sme poslali na zverejnenú úradnú adresu obce. "
               "Ak nechcete dostávať ďalšie, odhláste sa tu: ")
    text = "\n\n".join(txt_casti) + f"\n\n--\n{paticka}{odhl}\n" \
        "LoveHome s.r.o., Černyševského 40, 851 01 Bratislava, IČO 47 586 362"
    telo = (
        '<!doctype html><html lang="sk"><body style="margin:0;padding:16px;'
        'font:15px/1.6 Arial,sans-serif;color:#0f1a2b;background:#ffffff;">'
        '<div style="max-width:580px;">' + "".join(html_casti)
        + '<p style="margin:24px 0 0;padding-top:12px;border-top:1px solid #e4e8ee;'
          'font-size:12px;line-height:1.6;color:#8a929e;">'
        + html.escape(paticka) + f'<a href="{html.escape(odhl)}" style="color:#8a929e;">odhlásiť</a>.<br>'
        "LoveHome s.r.o., Černyševského 40, 851 01 Bratislava, IČO 47 586 362</p>"
        "</div></body></html>")
    return text, telo


# ── 5. data pre obce ───────────────────────────────────────────────────────

def _po_davkach(zoznam, n=100):
    for i in range(0, len(zoznam), n):
        yield zoznam[i:i + n]


def nacitaj_data(sb, ica, dnes):
    """-> {ico: {segment: udaje}} pre vsetky segmenty naraz (davky po 100 ICO)."""
    out = {i: {} for i in ica}
    dnes_s = dnes.isoformat()
    for davka in _po_davkach(list(ica)):
        for r in (sb.table("obce_ziadatelia").select("obec_ico,sprostredkovatel,najate")
                  .in_("obec_ico", davka).order("najate", desc=True).execute().data):
            if r.get("sprostredkovatel"):
                out[r["obec_ico"]].setdefault("poradca", r)
        for r in (sb.table("uvo_vysledky")
                  .select("obstaravatel_ico,nazov,cast_nazov,vitaz_nazov,hodnota,mena,koniec")
                  .in_("obstaravatel_ico", davka).gte("koniec", dnes_s)
                  .not_.is_("vitaz_nazov", "null").order("koniec").execute().data):
            if (r.get("mena") or "EUR") != "EUR":
                continue
            out[r["obstaravatel_ico"]].setdefault("uvo", {
                "predmet": r.get("cast_nazov") or r.get("nazov"),
                "dodavatel": r["vitaz_nazov"], "hodnota": r.get("hodnota"), "koniec": r["koniec"]})
        for r in (sb.table("opportunities")
                  .select("authority_cin,subject,supplier_name,price_total,effective_to")
                  .in_("authority_cin", davka).gte("effective_to", dnes_s)
                  .order("effective_to").execute().data):
            if r.get("subject") and r.get("supplier_name"):
                out[r["authority_cin"]].setdefault("crz", {
                    "predmet": r["subject"], "dodavatel": r["supplier_name"],
                    "hodnota": r.get("price_total"), "koniec": r["effective_to"]})
        sumy = {}
        for r in (sb.table("subsidies").select("prijimatel_ico,suma")
                  .in_("prijimatel_ico", davka).execute().data):
            s = sumy.setdefault(r["prijimatel_ico"], {"pocet": 0, "suma": 0.0})
            s["pocet"] += 1
            try:
                s["suma"] += float(r.get("suma") or 0)
            except (TypeError, ValueError):
                pass
        for ico, s in sumy.items():
            out[ico]["dotacie"] = s
    return out


def vyber_prijemcov(kontakty, odoslane, ucty_ica, vlna, dnes):
    """Kontakty, ktorym sa v tejto vlne smie pisat.
    odoslane: [{ico, vlna, stav, odoslane_at}]"""
    uz_vlna = {o["ico"] for o in odoslane if o["vlna"] == vlna}
    vlna1_ok = {o["ico"]: o["odoslane_at"] for o in odoslane
                if o["vlna"] == "vlna1" and o["stav"] == "odoslane"}
    out = []
    for k in kontakty:
        if k["stav"] != "ok" or k.get("odhlasene_at") or k["ico"] in uz_vlna or k["ico"] in ucty_ica:
            continue
        if vlna == "vlna2":
            kedy = vlna1_ok.get(k["ico"])
            if not kedy or date.fromisoformat(kedy[:10]) > dnes - timedelta(days=DNI_MEDZI_VLNAMI):
                continue
        out.append(k)
    return out


def smie_ostro(vlna, dnes, vynutit):
    if vynutit:
        return None
    if dnes < VLNY[vlna]:
        return f"{vlna} sa smie posielat az od {datum_sk(VLNY[vlna])}"
    if dnes.weekday() not in (1, 2, 3):
        return "posielame len v utorok az stvrtok"
    return None


def posli_resend(kluc, komu, predmet, text, telo, token):
    hlavicky = {"List-Unsubscribe": f"<{_odhlasenie_url(token)}>"
                + (f", <mailto:{REPLY_TO}?subject=odhlasit>" if REPLY_TO else "")}
    payload = {"from": ODOSIELATEL, "to": [komu], "subject": predmet,
               "text": text, "html": telo, "headers": hlavicky}
    if REPLY_TO:
        payload["reply_to"] = REPLY_TO
    try:
        r = requests.post(RESEND_URL, timeout=30, json=payload,
                          headers={"Authorization": f"Bearer {kluc}"})
    except requests.RequestException as e:
        return None, f"siet: {type(e).__name__}"
    if r.status_code in (200, 201):
        return (r.json() or {}).get("id") or "ok", None
    return None, f"HTTP {r.status_code} {r.text[:200]}"


def uloz_nahlad(cesta, spravy):
    bloky = []
    for s in spravy:
        bloky.append(
            f"<section style='border:1px solid #ccd;border-radius:8px;margin:18px 0;padding:14px;'>"
            f"<div style='font:12px monospace;color:#556;'>komu: {html.escape(s['email'])} | "
            f"segment: {s['segment']} | IČO {s['ico']} | starosta: {html.escape(s['starosta'] or '—')}</div>"
            f"<div style='font:600 15px Arial;margin:6px 0 10px;'>Predmet: {html.escape(s['predmet'])}</div>"
            f"<iframe style='width:100%;height:520px;border:0;' srcdoc=\"{html.escape(s['html'])}\"></iframe>"
            "</section>")
    Path(cesta).write_text(
        "<!doctype html><meta charset='utf-8'><title>Náhľad kampane</title>"
        f"<body style='font:14px Arial;max-width:760px;margin:20px auto;'>"
        f"<h1>Náhľad: {len(spravy)} e-mailov</h1>" + "".join(bloky), encoding="utf-8")


def krok_posli(sb, a):
    dnes = date.fromisoformat(a.dnes) if a.dnes else date.today()
    ostro = not a.nasucho and not a.komu
    if ostro:
        prekazka = smie_ostro(a.vlna, dnes, a.vynutit)
        if prekazka:
            log.error("Ostro neposielam: %s. (Nasucho a --komu funguju vzdy.)", prekazka)
            return 1
        if not REPLY_TO:
            log.error("Chyba KAMPAN_REPLY_TO — odpovede obci by nedosli Marekovi. Neposielam.")
            return 1
    kluc = os.getenv("RESEND_API_KEY")
    if not a.nasucho and not kluc:
        log.error("Chyba RESEND_API_KEY.")
        return 1

    kontakty = _vsetky(sb, "kampan_obce_kontakty",
                       "ico,obec,kraj,kod_obce,email,stav,token,odhlasene_at")
    odoslane = _vsetky(sb, "kampan_obce_odoslane", "ico,vlna,stav,odoslane_at")
    ucty_ica = {r["ico"] for r in _vsetky(sb, "obce_ucty", "ico") if r.get("ico")}
    prijemcovia = vyber_prijemcov(kontakty, odoslane, ucty_ica, a.vlna, dnes)
    starostovia = {r["kod_obce"]: r for r in _vsetky(
        sb, "obce_starostovia", "kod_obce,meno,priezvisko",
        lambda q: q.eq("rok", ROK_VOLIEB))}
    data = nacitaj_data(sb, [k["ico"] for k in prijemcovia], dnes)

    spravy = []
    for k in prijemcovia:
        starosta = starostovia.get(k.get("kod_obce"))
        s = zostav(a.vlna, k, starosta, data.get(k["ico"], {}))
        if not s:
            continue
        text, telo = vyrenderuj(s, k["token"])
        spravy.append({**s, "ico": k["ico"], "email": k["email"], "token": k["token"],
                       "starosta": (f"{starosta.get('meno') or ''} {starosta['priezvisko']}".strip()
                                    if starosta else None),
                       "text": text, "html": telo})
    # najsilnejsi dovod ozvat sa ide prvy
    poradie = {s: i for i, s in enumerate(SEGMENTY + ("followup",))}
    spravy.sort(key=lambda s: poradie[s["segment"]])

    pocty = {}
    for s in spravy:
        pocty[s["segment"]] = pocty.get(s["segment"], 0) + 1
    log.info("%s: kontaktov %d, smie sa pisat %d, s konkretnym obsahom %d %s; so starostom %d.",
             a.vlna, len(kontakty), len(prijemcovia), len(spravy), pocty,
             sum(1 for s in spravy if s["starosta"]))

    dnes_odoslane = sum(1 for o in odoslane if o["stav"] != "chyba"
                        and o["odoslane_at"][:10] == dnes.isoformat())
    kapacita = max(0, a.max - dnes_odoslane) if ostro else a.max
    davka = spravy[:kapacita] if ostro else spravy
    if a.nahlad:
        uloz_nahlad(a.nahlad, davka if ostro else spravy)
        log.info("Nahlad: %s", a.nahlad)
    for s in spravy[:5]:
        log.info("  %s -> %s | %s", s["segment"], s["email"], s["predmet"])

    if a.nasucho:
        log.info("NASUCHO — nic neposlane, nic nezapisane. Dnes by islo %d (limit %d, dnes uz %d).",
                 min(len(spravy), max(0, a.max - dnes_odoslane)), a.max, dnes_odoslane)
        return 0

    if a.komu:
        for s in spravy[:a.test_pocet]:
            rid, chyba = posli_resend(kluc, a.komu, "[TEST] " + s["predmet"], s["text"], s["html"], s["token"])
            log.info("TEST %s -> %s: %s", s["ico"], a.komu, chyba or rid)
            time.sleep(PAUZA_S)
        return 0

    log.info("OSTRO: posielam %d (dnes uz %d, limit %d).", len(davka), dnes_odoslane, a.max)
    ok = chyby = 0
    for s in davka:
        # zapis PRED odoslanim: ak beh spadne, obec nedostane e-mail dvakrat
        try:
            ins = sb.table("kampan_obce_odoslane").insert({
                "ico": s["ico"], "vlna": a.vlna, "segment": s["segment"],
                "email": s["email"], "predmet": s["predmet"]}).execute()
        except Exception as e:      # unique (ico, vlna) — uz odoslane inym behom
            log.warning("%s: preskakujem, uz je v evidencii (%s)", s["ico"], type(e).__name__)
            continue
        rid_riadku = ins.data[0]["id"]
        rid, chyba = posli_resend(kluc, s["email"], s["predmet"], s["text"], s["html"], s["token"])
        sb.table("kampan_obce_odoslane").update(
            {"stav": "odoslane", "resend_id": rid} if rid else {"stav": "chyba", "chyba": chyba}
        ).eq("id", rid_riadku).execute()
        if rid:
            ok += 1
        else:
            chyby += 1
            log.error("%s %s: %s", s["ico"], s["email"], chyba)
        time.sleep(PAUZA_S)
    log.info("HOTOVO: odoslane %d, chyby %d.", ok, chyby)
    return 0 if not chyby else 2


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="krok", required=True)
    k = sub.add_parser("kontakty")
    k.add_argument("--nasucho", action="store_true")
    p = sub.add_parser("posli")
    p.add_argument("--vlna", choices=sorted(VLNY), required=True)
    p.add_argument("--nasucho", action="store_true")
    p.add_argument("--komu", help="poslat par testovacich e-mailov len na tuto adresu")
    p.add_argument("--test-pocet", type=int, default=3)
    p.add_argument("--max", type=int, default=50, help="max. e-mailov za den")
    p.add_argument("--nahlad", help="subor s HTML nahladom vsetkych e-mailov")
    p.add_argument("--vynutit", action="store_true", help="obist datum vlny a den v tyzdni")
    p.add_argument("--dnes", help="YYYY-MM-DD, len na testy")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    from store import klient
    sb = klient()
    if a.krok == "kontakty":
        return krok_kontakty(sb, a.nasucho)
    return krok_posli(sb, a)


if __name__ == "__main__":
    sys.exit(main())
