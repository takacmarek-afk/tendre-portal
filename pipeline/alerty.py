"""'Sused uz stavia' — mesacny FOMO alert pre obce (odber_obce).

Spustenie:
    python alerty.py                # naozaj posle
    python alerty.py --nasucho      # nic neposle, len vypise co by poslal
    python alerty.py --komu ja@x.sk # posle len na tuto adresu (test)

Potrebne premenne: rovnake ako posli_email.py
    SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, RESEND_API_KEY

PRVE SPUSTENIE VZDY NASUCHO.

CO TOTO ROBI
Z navrhu rozvoja portalu (dokument "Predtendrom.sk — navrh rozvoja
portalu", sekcia "Prekonanie bariery pasivity"): pasivna obec sa na
portal sama nevrati, treba ju osloviť. Kazdemu prihlasenemu odberatelovi
z odber_obce (potvrdeny=true — realny, uz existujuci opt-in zoznam,
rovnaky, aky pouziva tyzdenny posli_email.py) posle tento skript alert,
KED V JEHO OKRESE INA OBEC NEDAVNO PODPISALA DOTACNU ZMLUVU. Zdroj dat je
`subsidies` (rovnaky, aky uz pouziva obce.aktivne_programy pre agregovany
tyzdenny prehlad) — len tu na urovni JEDNOTLIVYCH udalosti, nie
agregovane podla poskytovatela.

PRECO LEN OKRES, ZATIAL NIE AJ "PODOBNA VELKOST OBCE"
Povodny navrh ("Sused uz stavia") pocital s definiciou "okres + podobny
pocet obyvatelov". Pri implementacii (22.9.2026) som overil dostupne
verejne zdroje pre pocet obyvatelov obci:
  - RPO (Register pravnickych osob) API — len identita (nazov/ICO/adresa),
    ZIADNE pole s poctom obyvatelov ani elektronickou postou.
  - SUSR register organizacii — rovnako len identita.
  - SUSR DATAcube ma tabulku s poctom obyvatelov (om7101rr), ale presne
    kody jej dimenzii (uzemie/rok/pohlavie) sa v tejto vlne nepodarilo
    strojovo zistit bez rucneho skusania v UI — a hadat kody by znamenalo
    riziko TICHO ZLE PRIRADENEHO cisla k obci, presne to, co si tento
    projekt zakazuje ("nikdy nevymyslene").
Namiesto hadania preto v1 pouziva LEN OKRES (register_obci.py, uz
pouzivany a overeny inde v pipeline). Rozsirenie o velkost obce je
pripravene na dalsiu vlnu, ked sa najde spolahlivy, strojovo citatelny
zdroj (RPO/DATAcube presny endpoint, alebo subor, ktory posle Marek).

PRECO SAMOSTATNY SKRIPT, NIE SUCAST posli_email.py
Iny obsah (konkretna susedna udalost, nie agregovany prehlad programov),
iny cyklus (mesacny, nie tyzdenny/denny) a iny zdroj pravdy pre "uz
poslane" (sused_alerty_odoslane, nie odber.posledny_email — ten stlpec
patri vylucne existujucemu tyzdennemu emailu a nesmie sa tu menit).
Rovnaky princip oddelenia, aky ma ruz-financie.yml voci pipeline.yml:
zlyhanie/zmena tu nesmie ovplyvnit uz funkcny beh.

DEDUPLIKACIA
sused_alerty_odoslane (email, contract_id) — kazda dvojica prijemca a
konkretnej zmluvy sa posle najviac raz, navzdy (ziadne expirovanie).
"""
import argparse
import logging
import os
import re
import time
from datetime import date, timedelta

from supabase import create_client

import obce
import regiony
import register_obci
from posli_email import _obal, _eur, posli, ODKAZ_OBCE

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)-7s %(name)-9s %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("alerty")

# Mesacny alert: siroke okno, aby aj obec s menej aktivnym okresom raz za
# cas dostala nieco relevantne. 45, nie presne 30 — rezerva, aby hodinovy
# posun medzi behmi nikdy nevynechal riadny mesiac (rovnaky princip ako
# MIN_DNI_TYZDENNE v posli_email.py).
DNI_OKNO = 45
MAX_UDALOSTI = 3   # kolko susednych zmluv najviac v jednom e-maile

PAUZA_S = 0.6


# ── OKRES Z NAZVU (register_obci.nacitaj_s_okresom() nad rovnakym vzorom
#    vyhladavania, aky pouziva regiony.z_nazvu() pre kraj) ──────────────────

_MESTO_OKRES = {norm: okres for norm, (_nazov, _kraj, okres)
                in register_obci.nacitaj_s_okresom().items()}

_PREFIX_OBEC = re.compile(r"^(?:mesto|obec|mestska cast)\s+(.+)$")


def _obec_a_okres(nazov):
    """Vrati (normalizovany_nazov_obce, okres) z nazvu organizacie, alebo
    (None, None). Rovnaky dvojstupnovy postup ako regiony.z_nazvu() (prefix
    "Obec X"/"Mesto X" ma prednost, potom hladanie znameho nazvu kdekolvek
    v texte), ale nad register_obci.nacitaj_s_okresom() — regiony.MESTO_KRAJ
    okres neobsahuje. Vracia aj normalizovany nazov, aby volajuci vedel
    porovnat "je to ta ista obec ako prijemca" bez druheho hladania.
    """
    if not nazov:
        return None, None
    n = regiony._norm(nazov)

    m = _PREFIX_OBEC.match(n)
    if m:
        kandidat = re.split(r"\s*[-–,]", m.group(1))[0].strip()
        if kandidat in _MESTO_OKRES:
            return kandidat, _MESTO_OKRES[kandidat]

    zhoda = regiony._V_NAZVE.search(n)
    if zhoda and zhoda.group(1) in _MESTO_OKRES:
        return zhoda.group(1), _MESTO_OKRES[zhoda.group(1)]

    return None, None


# ── UDALOSTI ────────────────────────────────────────────────────────────────

def _nacitaj_udalosti(sb, dnes):
    """Nedavno podpisane dotacne zmluvy s obcami, zoskupene podla okresu.

    Vrati {okres: [udalost, ...]}, udalost = {contract_id, obec_norm,
    obec_nazov, poskytovatel, suma, ucel, podpisane}. Rovnake filtre ako
    obce.aktivne_programy(): overeny verejny poskytovatel, prijemca musi
    vyzerat ako obec/mesto, suma nad MIN_SUMA_DOTACIE.
    """
    hranica = (dnes - timedelta(days=DNI_OKNO)).isoformat()
    try:
        riadky = (sb.table("subsidies")
                    .select("contract_id, prijimatel, poskytovatel, ucel, "
                            "suma, podpisane")
                    .gte("podpisane", hranica)
                    .gte("suma", obce.MIN_SUMA_DOTACIE)
                    .order("podpisane", desc=True)
                    .execute().data or [])
    except Exception as e:
        log.error("Dopyt na subsidies zlyhal: %s", e)
        return {}

    podla_okresu = {}
    preskocene_obec = preskocene_poskyt = preskocene_okres = 0
    for r in riadky:
        if not obce._je_obec(r.get("prijimatel")):
            preskocene_obec += 1
            continue
        if not obce.je_verejny_poskytovatel(r.get("poskytovatel")):
            preskocene_poskyt += 1
            continue
        obec_norm, okres = _obec_a_okres(r["prijimatel"])
        if not okres:
            preskocene_okres += 1
            continue
        podla_okresu.setdefault(okres, []).append({
            "contract_id": r["contract_id"],
            "obec_norm": obec_norm,
            "obec_nazov": r["prijimatel"],
            "poskytovatel": r.get("poskytovatel"),
            "ucel": r.get("ucel"),
            "suma": r.get("suma"),
            "podpisane": r.get("podpisane"),
        })

    log.info("Udalosti za poslednych %s dni: %s obci v %s okresoch "
             "(preskocenych: %s nie-obec, %s neoverit. poskytovatel, "
             "%s neznamy okres)",
             DNI_OKNO, sum(len(v) for v in podla_okresu.values()),
             len(podla_okresu), preskocene_obec, preskocene_poskyt,
             preskocene_okres)
    return podla_okresu


def pre_odberatela(sb, o, podla_okresu, uz_poslane):
    """Zostavi obsah alertu pre jedneho odberatela, alebo None (nic nove /
    obec sa neda zaradit do okresu)."""
    obec_norm, okres = _obec_a_okres(o.get("obec"))
    if not okres:
        return None

    kandidati = [u for u in podla_okresu.get(okres, [])
                 if u["obec_norm"] != obec_norm
                 and (o["email"].lower(), u["contract_id"]) not in uz_poslane]
    if not kandidati:
        return None

    vybrane = kandidati[:MAX_UDALOSTI]
    bloky = []
    for u in vybrane:
        popis = f"Poskytovateľ: {u['poskytovatel']}"
        if u.get("ucel"):
            popis += f" · {u['ucel']}"
        bloky.append({
            "titul": u["obec_nazov"],
            "popis": popis,
            "zvyraznene": (f"Získala {_eur(u['suma'])}"
                           f"{' · podpísané ' + u['podpisane'] if u.get('podpisane') else ''}"),
        })

    return {
        "titulok": "Sused už stavia",
        "uvod": ("Obce vo vašom okrese nedávno podpísali dotačné zmluvy. "
                 "Ak je program relevantný aj pre vás, výzva môže byť "
                 "stále otvorená."),
        "bloky": bloky,
        "cta_text": "Pozrieť otvorené výzvy a programy",
        "cta_url": ODKAZ_OBCE,
        "odhlasenie": ('Odhlásiť sa môžete odpoveďou na tento e-mail '
                       'so slovom „odhlásiť".'),
        "_contract_ids": [u["contract_id"] for u in vybrane],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nasucho", action="store_true",
                    help="nic neposle, len vypise co by poslal")
    ap.add_argument("--komu", help="posle len na tuto adresu (test)")
    args = ap.parse_args()

    if args.komu is not None:
        args.komu = args.komu.strip()
        if not re.fullmatch(r"[^@\s,;<>\"]+@[^@\s,;<>\"]+\.[A-Za-z]{2,}",
                            args.komu):
            log.error("--komu nie je platna e-mailova adresa. Nepokracujem.")
            return 1

    url = os.getenv("SUPABASE_URL")
    servis = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    kluc = os.getenv("RESEND_API_KEY")
    if not (url and servis):
        log.error("Chyba SUPABASE_URL alebo SUPABASE_SERVICE_ROLE_KEY.")
        return 1
    if not kluc and not args.nasucho:
        log.error("Chyba RESEND_API_KEY. Pridaj ho do GitHub Secrets, "
                  "alebo spusti s --nasucho.")
        return 1

    sb = create_client(url, servis)
    dnes = date.today()

    try:
        odberatelia = (sb.table("odber_obce").select("email, obec, kraj")
                         .eq("potvrdeny", True).execute().data or [])
    except Exception as e:
        log.error("Tabulka odber_obce sa necitala: %s", e)
        return 1

    if args.komu:
        odberatelia = [o for o in odberatelia
                       if (o.get("email") or "").lower() == args.komu.lower()]
        if not odberatelia:
            log.error("--komu %s nie je v odber_obce (potvrdeny=true). "
                      "Test bez realneho odberatela by nedokazal, ci sa "
                      "obec da zaradit do okresu.", args.komu)
            return 1

    log.info("Odberatelov: %s%s", len(odberatelia),
             "  [NASUCHO]" if args.nasucho else "")
    if not odberatelia:
        log.info("Niet komu posielat. Koniec.")
        return 0

    podla_okresu = _nacitaj_udalosti(sb, dnes)
    if not podla_okresu:
        log.info("Ziadne relevantne udalosti za poslednych %s dni. Koniec.",
                 DNI_OKNO)
        return 0

    try:
        odoslane_rows = (sb.table("sused_alerty_odoslane")
                            .select("email, contract_id").execute().data or [])
    except Exception as e:
        log.error("Tabulka sused_alerty_odoslane sa necitala: %s", e)
        return 1
    uz_poslane = {(r["email"].lower(), r["contract_id"]) for r in odoslane_rows}

    poslane = preskocene = zlyhane = 0
    for o in odberatelia:
        komu = (o.get("email") or "").strip()
        if not komu or "@" not in komu:
            preskocene += 1
            continue

        obsah = pre_odberatela(sb, o, podla_okresu, uz_poslane)
        if not obsah:
            preskocene += 1
            continue

        html = _obal(obsah["titulok"], obsah["uvod"], obsah["bloky"],
                     obsah["cta_text"], obsah["cta_url"], obsah["odhlasenie"])
        predmet = f"PredTendrom.sk — {obsah['titulok']}"

        if posli(kluc, komu, predmet, html, args.nasucho):
            poslane += 1
            if not args.nasucho:
                try:
                    sb.table("sused_alerty_odoslane").insert([
                        {"email": komu, "contract_id": cid}
                        for cid in obsah["_contract_ids"]
                    ]).execute()
                except Exception as e:
                    # Horsie nez nezapisat je poslat to iste znova o mesiac,
                    # ale zhodit beh kvoli tomu nema zmysel.
                    log.warning("%s: sused_alerty_odoslane sa nezapisalo (%s)",
                               komu, e)
        else:
            zlyhane += 1
        time.sleep(PAUZA_S)

    log.info("Hotovo: poslanych %s, preskocenych %s, zlyhanych %s",
             poslane, preskocene, zlyhane)
    if zlyhane and not poslane:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
