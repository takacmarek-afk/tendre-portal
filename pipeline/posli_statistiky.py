"""Tyzdenny e-mail so zhrnutim navstevnosti (tabulka navstevy).

Spustenie:
    python posli_statistiky.py                # naozaj posle
    python posli_statistiky.py --nasucho      # nic neposle, len vypise co by poslal

Potrebne premenne:
    SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY   — ako zvysok pipeline
    RESEND_API_KEY                            — rovnaky kluc ako posli_email.py

KOMU TO CHODI
  Vzdy len na PRIJEMCA nizsie (pevny e-mail zakladatela), nie je to odber
  ani nastavenie, ktore sa da niekde zapnut/vypnut — rovnaky pragmaticky
  pristup ako je_admin() v supabase/27_navstevnost.sql (jediny zakladatel,
  jeden pevny e-mail, menit sa bude az ked pribudne druhy spravca).

PRECO SA TU NEPOUZIVAJU RPC funkcie navstevnost_*()
  Tie su chranene cez je_admin(), ktora kontroluje auth.uid() — funguje
  len v kontexte prihlaseneho uzivatela (JWT z browseru). Tento skript
  bezi s SUPABASE_SERVICE_ROLE_KEY (ziadny auth.uid()), takze cita
  priamo z tabulky navstevy — service_role RLS aj tak obchadza, presne
  ako zvysok pipeline (posli_email.py, posli_pozvanky.py). Agregacia
  (podla stranky/referrera/dna) sa preto robi tu v Pythone.

CO SA NEPOSIELA
  Tyzden bez jedinej navstevy. Zakladatel vie ist do admin panelu
  (app.html, zalozka Statistiky) kedykolvek sam — prazdny e-mail kazdy
  tyzden by bol len sum, nie signal.
"""
import argparse
import logging
import os
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone

from supabase import create_client

# Rovnaky obal a odosielacia funkcia ako tyzdenny e-mail dodavatelom/obciam
# — rovnaky vzhlad, rovnake escapovanie, rovnaka kontrola (odkaz musi viest
# na predtendrom.sk). Skripty su sesterske subory v tom istom priecinku,
# import teda funguje bez balicka.
from posli_email import _obal, posli, RESEND_URL, ODOSIELATEL  # noqa: F401

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)-7s %(name)-9s %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("statistiky")

PRIJEMCA = "takac.marek@gmail.com"
ODKAZ_APP = "https://predtendrom.sk/app.html"
DNI_SPAT = 7
TOP_STRANOK = 5
TOP_REFERREROV = 3


def _priamo(referrer):
    """Rovnake spravanie ako navstevnost_referreri() v SQL: prazdny/None
    referrer je priamy vstup (zaklozka, adresa na priamo), nie chybajuci
    udaj."""
    r = (referrer or "").strip()
    return r if r else "(priamo / bez odkazu)"


def _kluc_sid(n, i):
    """Kluc na rozlisenie unikatnej navstevy. Riadky so session_id (nove
    dáta, supabase/30_navstevnost_unique.sql) sa dedupuju podla neho — jedna
    osoba prekliknuta cez viac stranok v jednej navsteve sa pocita raz.
    Riadky bez neho (stare data spred migracie, alebo zlyhanie
    sessionStorage v prehliadaci) sa pocitaju kazdy zvlast, rovnaky fallback
    ako SQL count(distinct coalesce(session_id, id::text)) v RPC funkciach."""
    sid = n.get("session_id")
    return sid if sid else f"__bez_sid__{i}"


def priprav_zhrnutie(navstevy):
    """navstevy: zoznam riadkov {cesta, referrer, created_at, session_id}.
    Vracia (celkom, top_stranky, top_referreri) — vsetko su UNIKATNE
    navstevy (dedup podla session_id v ramci kazdej skupiny), nie surovy
    pocet pageview riadkov. top_* su zoznamy (nazov, pocet) zoradene
    zostupne."""
    videne_celkom = set()
    podla_stranky = Counter()
    videne_stranky = set()
    podla_referrera = Counter()
    videne_referrera = set()

    for i, n in enumerate(navstevy):
        sid = _kluc_sid(n, i)
        if sid not in videne_celkom:
            videne_celkom.add(sid)

        cesta = n.get("cesta")
        if cesta and (cesta, sid) not in videne_stranky:
            videne_stranky.add((cesta, sid))
            podla_stranky[cesta] += 1

        referrer = _priamo(n.get("referrer"))
        if (referrer, sid) not in videne_referrera:
            videne_referrera.add((referrer, sid))
            podla_referrera[referrer] += 1

    celkom = len(videne_celkom)
    top_stranky = podla_stranky.most_common(TOP_STRANOK)
    top_referreri = podla_referrera.most_common(TOP_REFERREROV)
    return celkom, top_stranky, top_referreri


def _statistiky_html(celkom, top_stranky, top_referreri):
    bloky = [{
        "titul": f"Posledných {DNI_SPAT} dní",
        "popis": "",
        "zvyraznene": f"{celkom} unikátnych návštev",
    }]
    for cesta, pocet in top_stranky:
        bloky.append({"titul": cesta, "popis": "", "zvyraznene": f"{pocet} návštev"})
    if top_referreri:
        najlepsi, pocet_najlepsi = top_referreri[0]
        bloky.append({
            "titul": "Odkiaľ prichádzajú najviac",
            "popis": najlepsi,
            "zvyraznene": f"{pocet_najlepsi} návštev",
        })

    return _obal(
        titulok="Týždenný prehľad návštevnosti",
        uvod=(f"Za posledných {DNI_SPAT} dní zaznamenal PredTendrom.sk "
              f"{celkom} unikátnych návštev (jedna osoba prekliknutá cez "
              f"viac stránok sa počíta raz). Bez cookies, bez sledovania "
              f"jednotlivých návštevníkov naprieč viacerými návštevami."),
        bloky=bloky,
        cta_text="Otvoriť plné štatistiky",
        cta_url=ODKAZ_APP,
        odhlasenie=("Tento prehľad chodí len na tento e-mail — nie je to "
                    "odber, ktorý by sa dal niekde vypnúť."),
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nasucho", action="store_true",
                    help="nic neposle, len vypise co by poslal")
    args = ap.parse_args()

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
    od = (datetime.now(timezone.utc) - timedelta(days=DNI_SPAT)).isoformat()

    try:
        navstevy = (sb.table("navstevy")
                      .select("cesta, referrer, created_at, session_id")
                      .gte("created_at", od)
                      .execute().data or [])
    except Exception as e:
        log.error("Nepodarilo sa nacitat navstevy: %s", e)
        return 1

    celkom, top_stranky, top_referreri = priprav_zhrnutie(navstevy)
    log.info("Unikatnych navstev za poslednych %s dni: %s%s",
             DNI_SPAT, celkom, "  [NASUCHO]" if args.nasucho else "")

    if celkom == 0:
        log.info("Ziadne navstevy, e-mail sa neposiela.")
        return 0

    html = _statistiky_html(celkom, top_stranky, top_referreri)
    predmet = f"Návštevnosť PredTendrom.sk — {celkom} unikátnych návštev za týždeň"

    if posli(kluc, PRIJEMCA, predmet, html, args.nasucho):
        log.info("Hotovo: prehlad poslany na %s.", PRIJEMCA)
        return 0

    log.error("Odoslanie zlyhalo.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
