"""Uvitacie e-maily po registracii (plan predaja, sekcia 6; migracia 86).

Pat kratkych e-mailov od Mareka, kazdy s jednym navodom a jednym krokom:

    krok 0   hned po registracii      vybrat odbor a kraj          (video 2)
    krok 1   den 1, ak ma vyber       otvorit jednu zmluvu         (video 3)
    krok 3   den 3                    pozriet zalozku Dodavatelia  (video 4)
    krok 7   den 7, ak nic nesleduje  pridat zmluvu do kalendara   (video 6)
    krok 12  2 dni pred koncom skusky zaplatit (zakladajuca cena)  (video 5)

Kazdy krok ma okno. Ked okno ubehne alebo krok nedava zmysel (uz zaplatil,
uz sleduje zmluvu), zapise sa ako 'vynechane' a nikdy nepride. Jeden
pouzivatel dostane za beh najviac jeden e-mail. Posiela sa cez Resend
(pouzivatel sa sam zaregistroval), odosielatel marek@, odpovede idu Marekovi.

Spustenie:
    python posli_onboarding.py              # naozaj posle
    python posli_onboarding.py --nasucho    # nic neposle, nic nezapise, vypise texty

Premenne: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, RESEND_API_KEY.
"""
import argparse
import html
import logging
import os
import sys
import time
from datetime import date, datetime, timezone

import requests

from posli_email import PAUZA_S, RESEND_URL, _sektor_text, _sklon

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)-7s %(name)-9s %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("onboarding")

ODOSIELATEL = "Marek Takáč <marek@predtendrom.sk>"
ODPOVED = "marek@predtendrom.sk"
WEB = "https://predtendrom.sk"
APP = f"{WEB}/app"
NAVODY = f"{WEB}/navody"
CENNIK = f"{WEB}/cennik"
ODHLASENIE = f"{WEB}/odhlasenie-tipov"
UTM = "utm_source=onboarding&utm_medium=email"

# krok -> (od dna, do dna) od registracie; krok 12 sa riadi koncom skusky
OKNA = {0: (0, 2), 1: (1, 3), 3: (3, 6), 7: (7, 10)}
KROKY = (0, 1, 3, 7, 12)


def _dni(od, teraz) -> float:
    if isinstance(od, str):
        od = datetime.fromisoformat(od.replace("Z", "+00:00"))
    return (teraz - od).total_seconds() / 86400


def na_rade(k: dict, teraz: datetime) -> "tuple[int | None, list[int]]":
    """Vrati (krok na poslanie alebo None, kroky na zapisanie ako vynechane)."""
    poslane = set(k.get("odoslane") or [])
    dni = _dni(k["registrovany_at"], teraz)
    vynechat = []
    for krok in KROKY:
        if krok in poslane:
            continue
        if krok == 12:
            if k.get("zaplatene"):
                vynechat.append(12)
                continue
            koniec = k.get("trial_konci")
            if not koniec or (k.get("plan") or "trial") != "trial":
                continue                      # bez skusky (zatial) nic
            do_konca = -_dni(koniec, teraz)
            if do_konca <= 0.25:
                vynechat.append(12)           # skuska uz skoncila
            elif do_konca <= 2.5:
                return 12, vynechat
            continue
        od, do = OKNA[krok]
        if dni < od:
            continue                          # este nie
        if dni >= do:
            vynechat.append(krok)             # okno ubehlo
            continue
        if krok == 1 and not k.get("ma_vyber"):
            continue                          # pocka, kym si nastavi vyber
        if krok == 7 and (k.get("ma_sledovanie") or k.get("zaplatene")):
            vynechat.append(7)
            continue
        return krok, vynechat
    return None, vynechat


# ── texty ─────────────────────────────────────────────────────────────────

def v_kraji(kraj: str) -> str:
    """'Bratislavský kraj' -> 'v Bratislavskom kraji'."""
    if not kraj:
        return "vo Vašom kraji"
    slovo = kraj.replace(" kraj", "")
    if slovo.endswith(("ý", "y")):
        slovo = slovo[:-1] + "om"
    return f"v {slovo} kraji"


def _datum(v) -> str:
    if not v:
        return ""
    d = v if isinstance(v, date) else date.fromisoformat(str(v)[:10])
    return f"{d.day}. {d.month}. {d.year}"


def _odkaz(cesta: str, krok: int) -> str:
    oddel = "&" if "?" in cesta else "?"
    kotva = ""
    if "#" in cesta:
        cesta, kotva = cesta.split("#", 1)
        kotva = "#" + kotva
    return f"{cesta}{oddel}{UTM}&utm_campaign=den{krok}{kotva}"


def obsah(krok: int, k: dict, miesta: int = 30) -> dict:
    """Predmet, odseky (zoznam retazcov) a odkazy {text: url} pre krok."""
    odbor = _sektor_text(k.get("sektor")) if k.get("sektor") else ""
    kde = v_kraji(k.get("kraj") or "")
    video = lambda n: _odkaz(f"{NAVODY}#video-{n}", krok)  # noqa: E731
    if krok == 0:
        return {
            "predmet": "Váš prehľad je pripravený",
            "odseky": [
                "vitajte v PredTendrom. Aby sme Vám mohli posielať zmluvy, ktoré sa Vás týkajú, "
                "potrebujeme jediné: odbor a kraj.",
                "Nastavíte ich v appke v časti Môj výber za 2 minúty. Ako presne, ukazuje "
                "60-sekundové video:",
                ("Pozrieť video: Nastavte si odbor a kraj", video(2)),
                "Potom Vám raz týždenne pošleme nové končiace zmluvy e-mailom.",
                ("Otvoriť PredTendrom", _odkaz(APP, krok)),
            ],
        }
    if krok == 1:
        n = int(k.get("pocet_zmluv") or 0)
        z = k.get("najblizsia") or {}
        prvy = (f"vo Vašom výbere ({odbor}, {k.get('kraj')}) končí do 12 mesiacov {n} "
                f"{_sklon(n, 'zmluva', 'zmluvy', 'zmlúv')}.")
        if z:
            prvy += f" Jedna z najbližších: {z.get('urad')} – {z.get('predmet')}, končí {_datum(z.get('koniec'))}."
        return {
            "predmet": (f"{n} {_sklon(n, 'zmluva', 'zmluvy', 'zmlúv')} vo Vašom výbere končí do roka"
                        if n else "Ako čítať končiacu zmluvu"),
            "odseky": [
                prvy,
                "Otvorte jednu z nich a kliknite na odkaz do Centrálneho registra zmlúv. Uvidíte "
                "celú zmluvu aj s cenou a viete, či sa oplatí pripravovať. Ako na to:",
                ("Pozrieť video: Ako čítať končiacu zmluvu", video(3)),
            ],
        }
    if krok == 3:
        co = f"{odbor} {kde}" if odbor else "vo Vašom odbore"
        return {
            "predmet": f"Kto vyhráva {co}",
            "odseky": [
                "v záložke Dodávatelia vidíte, ktoré firmy dnes dodávajú úradom "
                + (f"v odbore {odbor} {kde}" if odbor else "vo Vašom odbore a kraji")
                + ", koľkým úradom a za koľko. Je to najrýchlejší spôsob, ako zistiť, s kým "
                "budete súťažiť.",
                ("Pozrieť video (75 sekúnd)", video(4)),
            ],
        }
    if krok == 7:
        return {
            "predmet": "Pridajte si prvú zmluvu do kalendára",
            "odseky": [
                "zmluva sa oplatí sledovať vtedy, keď máte čas sa pripraviť. Pri každej zmluve "
                "je tlačidlo „Pridať do kalendára“ a pripomienka Vám príde 6 mesiacov pred koncom.",
                "Vyberte si jednu zmluvu, na ktorú by ste chceli dať ponuku, a pridajte si ju:",
                ("Pozrieť video: Príprava 6 mesiacov vopred", video(6)),
            ],
        }
    if krok == 12:
        odseky = [f"Vaša skúška PredTendrom končí {_datum(k.get('trial_konci'))}. "
                  "Potom sa týždenný prehľad zastaví."]
        if miesta > 0:
            odseky.append("Ak chcete pokračovať: prvým 30 firmám dávame ročný plán Start za 240 € "
                          "namiesto 340 €, cena platí 2 roky. Pri ročnej platbe zadáte kód "
                          "ZAKLADATEL.")
        else:
            odseky.append("Ak chcete pokračovať, plán Start stojí 34 € mesačne alebo 340 € ročne.")
        odseky += [
            ("Pozrieť plány a ceny", _odkaz(CENNIK, krok)),
            "Ak do 30 dní nebudete spokojní, vrátime celú sumu. Ak nechcete pokračovať, "
            "netreba robiť nič. Pred platbou sa oplatí pozrieť, za koľko robia podobné "
            "zákazky iní:",
            ("Pozrieť video: Za koľko to robia iní", video(5)),
        ]
        return {"predmet": "Skúška končí o 2 dni", "odseky": odseky}
    raise ValueError(f"neznamy krok {krok}")


def zostav(o: dict, token: str) -> "tuple[str, str]":
    """HTML a textova verzia. Vsetky odkazy vedu na predtendrom.sk."""
    odhlas = f"{ODHLASENIE}?t={token}"
    txt, htm = ["Dobrý deň,", ""], ['<p style="margin:0 0 14px;">Dobrý deň,</p>']
    for odsek in o["odseky"]:
        if isinstance(odsek, tuple):
            text, url = odsek
            if not url.startswith(WEB):
                raise ValueError(f"cudzi odkaz {url!r}")
            txt += [f"{text}: {url}", ""]
            htm.append(f'<p style="margin:0 0 14px;"><a href="{html.escape(url)}" '
                       f'style="color:#1a56c4;font-weight:600;">{html.escape(text)}</a></p>')
        else:
            txt += [odsek, ""]
            htm.append(f'<p style="margin:0 0 14px;">{html.escape(odsek)}</p>')
    txt += ["Marek Takáč", "PredTendrom.sk", "",
            "Ak máte otázku, odpovedzte na tento e-mail, číta ho priamo Marek.",
            f"Nechcete tieto tipy? Odhlásiť: {odhlas}",
            "LoveHome s.r.o., Černyševského 40, 851 01 Bratislava, IČO 47 586 362"]
    htm.append('<p style="margin:0 0 14px;">Marek Takáč<br>PredTendrom.sk</p>')
    telo = "\n".join(htm)
    return (f"""<!doctype html><html lang="sk"><body style="margin:0;padding:24px 16px;background:#ffffff;">
<div style="max-width:560px;font:15px/1.6 Arial,sans-serif;color:#0f1a2b;">
{telo}
<p style="margin:24px 0 0;padding-top:12px;border-top:1px solid #e4e8ee;font:12px/1.6 Arial,sans-serif;color:#8a929e;">
Ak máte otázku, odpovedzte na tento e-mail, číta ho priamo Marek.<br>
Nechcete tieto tipy? <a href="{html.escape(odhlas)}" style="color:#8a929e;">Odhlásiť</a>.<br>
LoveHome s.r.o., Černyševského 40, 851 01 Bratislava, IČO 47 586 362</p>
</div></body></html>""", "\n".join(txt))


def posli(kluc, komu, predmet, htm, txt, token, nasucho) -> bool:
    if nasucho:
        log.info("NASUCHO -> %s | %s\n%s", komu, predmet, txt)
        return True
    odhlas = f"{ODHLASENIE}?t={token}"
    try:
        r = requests.post(RESEND_URL, timeout=30,
                          headers={"Authorization": f"Bearer {kluc}",
                                   "Content-Type": "application/json"},
                          json={"from": ODOSIELATEL, "to": [komu], "reply_to": ODPOVED,
                                "subject": predmet, "html": htm, "text": txt,
                                "headers": {"List-Unsubscribe": f"<{odhlas}>"}})
    except requests.RequestException as e:
        log.error("%s: siet zlyhala (%s)", komu, type(e).__name__)
        return False
    if r.status_code in (200, 201):
        return True
    log.error("%s: HTTP %s %s", komu, r.status_code, r.text[:200])
    return False


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--nasucho", action="store_true")
    args = ap.parse_args(argv)

    url, servis = os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    kluc = os.getenv("RESEND_API_KEY")
    if not (url and servis):
        log.error("Chyba SUPABASE_URL alebo SUPABASE_SERVICE_ROLE_KEY.")
        return 1
    if not kluc and not args.nasucho:
        log.error("Chyba RESEND_API_KEY (alebo pouzi --nasucho).")
        return 1

    from supabase import create_client
    sb = create_client(url, servis)
    try:
        kandidati = sb.rpc("onboarding_kandidati", {}).execute().data or []
    except Exception as e:
        log.error("onboarding_kandidati() zlyhalo (spustena migracia 86?): %s", e)
        return 1
    try:
        miesta = int(sb.rpc("zakladajuce_miesta", {}).execute().data or 0)
    except Exception:
        miesta = 0

    teraz = datetime.now(timezone.utc)
    poslane = zlyhane = 0
    for k in kandidati:
        krok, vynechat = na_rade(k, teraz)
        if not args.nasucho:
            for v in vynechat:
                sb.rpc("onboarding_oznac", {"p_user_id": k["user_id"], "p_krok": v,
                                            "p_stav": "vynechane"}).execute()
        if krok is None:
            continue
        o = obsah(krok, k, miesta)
        htm, txt = zostav(o, k["token"])
        if posli(kluc, k["email"], o["predmet"], htm, txt, k["token"], args.nasucho):
            poslane += 1
            if not args.nasucho:
                sb.rpc("onboarding_oznac", {"p_user_id": k["user_id"], "p_krok": krok}).execute()
        else:
            zlyhane += 1
        time.sleep(PAUZA_S)

    log.info("Hotovo%s: kandidatov %d, poslanych %d, zlyhanych %d",
             " [NASUCHO]" if args.nasucho else "", len(kandidati), poslane, zlyhane)
    return 1 if (zlyhane and not poslane) else 0


if __name__ == "__main__":
    sys.exit(main())
