"""Tyzdenny prehlad konciacich zmluv pre firmy po potvrdeni odberu (migracia 81).

Kto si na uvodnej stranke vyziadal prehlad (double opt-in) a potvrdil ho odkazom,
dostane 4 e-maily (hned, den 4, den 10, den 21) a potom raz za 7 dni tri dalsie
konciace zmluvy z jeho vyberu (odbor + kraj), najviac 30 e-mailov spolu.
Obsah e-mailov: uvodny prehlad, co konciaca zmluva znamena a co nie, ako sa
pripravit, pozvanka na 14-dnovu skusku. Ziadne tvrdenie o predpovedi tendrov.

Pri kazdom e-maile je odhlasovaci odkaz (aj v hlavicke List-Unsubscribe).
Kto sa odhlasi, nikdy nedostane dalsi e-mail (riadok ostava ako zoznam odhlasenych).

Spustenie:
    python posli_odber_firmy.py              # naozaj posle
    python posli_odber_firmy.py --nasucho    # nic neposle, len vypise
    python posli_odber_firmy.py --max 20     # strop e-mailov na beh (default 40)

Premenne: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, RESEND_API_KEY.
"""
import argparse
import logging
import os
import re
import sys
import time

from supabase import create_client

from posli_email import PAUZA_S, _obal, _sektor_text, _sklon, posli  # noqa: F401

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)-7s %(name)-9s %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("odber-firmy")

ODKAZ_ODBER = "https://predtendrom.sk/odber-firmy"
ODKAZ_SKUSKA = "https://predtendrom.sk/prihlasenie.html"
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
CRZ_RE = re.compile(r"^https://www\.crz\.gov\.sk/zmluva/\d+/?$")
MAX_NA_BEH = 40


def odkaz_odhlasenia(token) -> "str | None":
    t = str(token or "")
    return f"{ODKAZ_ODBER}?t={t}&akcia=odhlasit" if UUID_RE.match(t) else None


def _datum(iso) -> str:
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", str(iso or ""))
    return f"{int(m.group(3))}. {int(m.group(2))}. {m.group(1)}" if m else ""


def _eur(n) -> str:
    try:
        return f"{int(round(float(n))):,}".replace(",", " ") + " €"
    except (TypeError, ValueError):
        return ""


def _crz(url) -> str:
    return url if CRZ_RE.match(str(url or "")) else "https://www.crz.gov.sk/"


def bloky_zmluv(d) -> list:
    bloky = []
    for z in ((d or {}).get("zoznam") or []):
        cena = _eur(z.get("cena"))
        popis = f"{z.get('predmet') or ''}" + (f" · {cena}" if cena else "")
        bloky.append({
            "titul": f"{z.get('urad') or '—'} — končí {_datum(z.get('koniec'))}",
            "popis": popis,
            "zvyraznene": f"Zmluva v registri: {_crz(z.get('odkaz'))}",
        })
    return bloky


KROKY_POSTUP = [
    {"titul": "1. Prečítajte si pôvodnú zmluvu",
     "popis": "V registri nájdete predmet, cenu, dobu trvania a to, či zmluva počíta s predĺžením. "
              "Odkaz je pri každej zmluve v našich prehľadoch."},
    {"titul": "2. Pozrite sa na úrad",
     "popis": "Čo kupuje a ako často vyhlasuje obstarávania, nájdete vo Vestníku verejného obstarávania."},
    {"titul": "3. Pripravte referencie",
     "popis": "Pri výbere dodávateľa sa zvyčajne pýta zoznam podobných zákaziek za posledné roky. "
              "Mať ho hotový šetrí čas."},
    {"titul": "4. Ozvite sa včas, no vecne",
     "popis": "Pri menších zákazkách si úrady niekedy pýtajú cenové ponuky priamo. "
              "Pomôže, ak vás už poznajú, no nič nie je zaručené."},
]


def obsah(n: int, r: dict, d) -> "dict | None":
    """E-mail c. n (1 = prvy) pre riadok r. `d` = vysledok odber_firmy_zmluvy.
    None = tento e-mail sa neposle (tyzdenny prehlad bez zmluv)."""
    odbor = _sektor_text(r.get("sektor")) or "váš odbor"
    kde = r.get("kraj") or "celé Slovensko"
    vyber = f"{odbor}, {kde}"
    celkom = int((d or {}).get("celkom") or 0)
    bloky = bloky_zmluv(d)
    pocet = f"{celkom} {_sklon(celkom, 'zmluva', 'zmluvy', 'zmlúv')}"
    odhl = ("Tento e-mail vám prišiel, lebo ste na predtendrom.sk požiadali o týždenný prehľad "
            f"končiacich zmlúv (odbor: {odbor}, {kde}) a súhlas ste potvrdili. "
            "Prehľad môžete kedykoľvek zrušiť odkazom nižšie alebo odpoveďou slovom Odhlásiť. "
            "Otázky: info@predtendrom.sk.")
    zakl = {"cta_text": "Pozrieť všetky zmluvy z výberu", "cta_url": ODKAZ_SKUSKA, "odhlasenie": odhl}

    if n == 1:
        uvod = (f"Ďakujeme za potvrdenie. V tomto výbere ({vyber}) končí v nasledujúcich 12 mesiacoch {pocet}. Tri z nich:"
                if celkom > 0 else
                f"Ďakujeme za potvrdenie. Pre výber ({vyber}) teraz nemáme žiadnu zmluvu, ktorá končí "
                "v najbližších 12 mesiacoch. Keď sa nejaká objaví, pošleme vám ju.")
        return dict(zakl, predmet=f"Váš prehľad končiacich zmlúv: {vyber}",
                    titulok=f"Končiace zmluvy: {vyber}", uvod=uvod, bloky=bloky)
    if n == 2:
        uvod = ("Zmluva, ktorá sa končí, ešte neznamená súťaž. Úrad ju môže predĺžiť dodatkom, zadať nákup "
                "bez súťaže alebo vyhlásiť nové obstarávanie. Čo urobí, vopred nevieme a nesľubujeme. "
                "Dátum konca je však verejný údaj, ktorý sa oplatí sledovať. Ďalšie tri zmluvy z vášho výberu:"
                if bloky else
                "Zmluva, ktorá sa končí, ešte neznamená súťaž. Úrad ju môže predĺžiť dodatkom, zadať nákup "
                "bez súťaže alebo vyhlásiť nové obstarávanie. Čo urobí, vopred nevieme a nesľubujeme. "
                "Dátum konca je však verejný údaj, ktorý sa oplatí sledovať.")
        return dict(zakl, predmet="Čo končiaca zmluva znamená, a čo nie",
                    titulok="Končiaca zmluva nie je tender", uvod=uvod, bloky=bloky)
    if n == 3:
        return dict(zakl, predmet="Ako sa pripraviť na zmluvu, ktorá úradu končí",
                    titulok="Štyri kroky, kým sa úrad ozve",
                    uvod="Nie je to návod na výhru, len praktické kroky, ktoré sa oplatí mať hotové vopred.",
                    bloky=KROKY_POSTUP, cta_text="Pozrieť zmluvy zo svojho výberu")
    if n == 4:
        uvod = (f"V odbore {odbor} ({kde}) končí v najbližších 12 mesiacoch {pocet}. Tri z nich ukazujeme nižšie. "
                "V 14-dňovej skúške bez platobnej karty uvidíte všetky, so sumami a dodávateľmi, a môžete si "
                "nastaviť e-mailový prehľad." if celkom > 0 else
                "V 14-dňovej skúške bez platobnej karty uvidíte všetky končiace zmluvy zo svojho výberu "
                "so sumami a dodávateľmi a môžete si nastaviť e-mailový prehľad.")
        return dict(zakl, predmet=f"Všetky končiace zmluvy: {vyber}", titulok="Chcete vidieť všetky?",
                    uvod=uvod, bloky=bloky, cta_text="Vyskúšať 14 dní zadarmo")
    # n >= 5: tyzdenny prehlad; bez zmluv sa neposiela
    if not bloky:
        return None
    return dict(zakl, predmet=f"Týždenný prehľad: {vyber}", titulok="Tri ďalšie končiace zmluvy",
                uvod=f"V tomto výbere ({vyber}) končí v najbližších 12 mesiacoch {pocet}. Tri z nich:",
                bloky=bloky)


def text_verzia(o: dict, odkaz_odhl: str) -> str:
    casti = [o["titulok"], "", o["uvod"], ""]
    for b in o["bloky"]:
        casti += [b["titul"], b.get("popis", "")] + ([b["zvyraznene"]] if b.get("zvyraznene") else []) + [""]
    casti += [f"{o['cta_text']}: {o['cta_url']}", "", o["odhlasenie"], f"Odhlásiť: {odkaz_odhl}",
              "LoveHome s.r.o., Černyševského 40, 851 01 Bratislava, IČO 47 586 362"]
    return "\n".join(casti)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--nasucho", action="store_true")
    ap.add_argument("--max", type=int, default=int(os.getenv("ODBER_FIRMY_MAX", MAX_NA_BEH)))
    args = ap.parse_args(argv)

    url = os.getenv("SUPABASE_URL")
    servis = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    kluc = os.getenv("RESEND_API_KEY")
    if not (url and servis):
        log.error("Chyba SUPABASE_URL alebo SUPABASE_SERVICE_ROLE_KEY.")
        return 1
    if not kluc and not args.nasucho:
        log.error("Chyba RESEND_API_KEY (alebo pouzi --nasucho).")
        return 1

    sb = create_client(url, servis)
    try:
        # V rezime --nasucho sa riadky nezabera: nic nemenime, len vypiseme.
        riadky = sb.rpc("odber_firmy_na_odoslanie", {"p_max": max(1, args.max),
                                                     "p_zaber": not args.nasucho}).execute().data or []
    except Exception as e:
        log.error("odber_firmy_na_odoslanie() zlyhalo: %s", e)
        return 1

    poslane = zlyhane = preskocene = 0
    for r in riadky:
        n = int(r.get("krok") or 0) + 1
        odkaz = odkaz_odhlasenia(r.get("token"))
        if not odkaz:
            log.warning("Riadok %s ma neplatny token, preskakujem.", r.get("id"))
            preskocene += 1
            continue
        d = None
        if n != 3:
            try:
                d = sb.rpc("odber_firmy_zmluvy", {"p_sektor": r.get("sektor"), "p_kraj": r.get("kraj"),
                                                   "p_posun": n - 1}).execute().data
            except Exception as e:
                log.error("odber_firmy_zmluvy() zlyhalo pre riadok %s: %s", r.get("id"), e)
                zlyhane += 1
                continue
        o = obsah(n, r, d)
        if o is None:
            # Tyzdenny prehlad bez zmluv: neposielame, ale posunieme krok a termin.
            preskocene += 1
            if not args.nasucho:
                try:
                    sb.rpc("odber_firmy_oznac", {"p_id": r["id"], "p_krok": n}).execute()
                except Exception as e:
                    log.warning("Oznacenie riadku %s zlyhalo (%s)", r.get("id"), e)
            continue
        html = _obal(o["titulok"], o["uvod"], o["bloky"], o["cta_text"], o["cta_url"],
                     o["odhlasenie"], odhlasovaci_odkaz=odkaz)
        predmet = f"PredTendrom.sk — {o['predmet']}"
        if posli(kluc, r["email"], predmet, html, args.nasucho,
                 text=text_verzia(o, odkaz), odhlasit_url=odkaz):
            poslane += 1
            if not args.nasucho:
                try:
                    sb.rpc("odber_firmy_oznac", {"p_id": r["id"], "p_krok": n}).execute()
                except Exception as e:
                    # Neoznacene = po 2 hodinach (zabratie riadku) pride e-mail znova;
                    # dopad: najviac jeden duplicitny e-mail.
                    log.warning("Oznacenie e-mailu zlyhalo (%s)", e)
        else:
            zlyhane += 1
        time.sleep(PAUZA_S)

    log.info("Hotovo%s: poslanych %s, zlyhanych %s, preskocenych %s",
             "  [NASUCHO]" if args.nasucho else "", poslane, zlyhane, preskocene)
    return 1 if (zlyhane and not poslane) else 0


if __name__ == "__main__":
    sys.exit(main())
