"""Obohati existujucich dodavatelov o RUZ financny kontext + NACE.

Spustenie:
    python obohat_financie.py                    # dalsia davka (default 150)
    python obohat_financie.py --limit 400
    python obohat_financie.py --force             # aj tie, co uz maju cerstvu kontrolu
    python obohat_financie.py --nasucho            # nic nezapise, len vypise

Potrebne premenne:  SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY (rovnake ako
zvysok pipeline, viz store.py).

CO TO ROBI A PRECO JE SAMOSTATNY SKRIPT
  Pre kazde ICO z tabulky `dodavatelia` (tu uz su len pravnicke osoby -
  viz config.py PRAVNE_FORMY a jej komentar, preco: fyzicke osoby tam
  ZAMERNE nie su, GDPR) zavola RUZ API (pipeline/ruz.py) a zapise vysledok
  do ruz_zaklad / ruz_financie (supabase/35_ruz_financie.sql). NEBEHA
  v ramci main.py — je to vlastny skript s vlastnym GitHub Actions behom
  (.github/workflows/ruz-financie.yml), rovnaky vzor ako
  posli_pozvanky.py/generuj_obce_podstranky.py. Dovod je oddelenie
  zlyhania: ked RUZ API vypadne alebo zmeni tvar odpovede, hlavny denny
  prepocet (zmluvy, prilezitosti, dotacie) o tom nemusi vobec vediet.

  Berie LEN ICO, ktore uz v `dodavatelia` su (dochadza teda z existujucich
  CRZ dodavatelov, nie hromadny narodny import celeho RUZ registra —
  presne rozsah, ktory Marek schvalil).

DAVKOVANIE
  RUZ API nema zdokumentovany rate limit, ale par tisic firiem krat
  niekolko volani na firmu (jednotka + zavierky + vykazy) by aj tak
  jeden beh GitHub Actions nestihol slusne spracovat. Preto:
    - spracuje najprv ICO, ktore este nemaju ziadny zaznam v ruz_zaklad,
      potom najstarsie skontrolovane (checked_at)
    - --limit obmedzuje pocet ICO na jeden beh (opakovanym spustanim sa
      postupne pokryje cela zakladna)
    - uz cerstvo skontrolovane (< PRESKOC_DNI dni) sa bez --force
      preskakuju — RUZ zavierky sa menia radovo raz do roka, nie denne
    - casovy rozpocet (TIME_BUDGET_MIN) zastavi beh predcasne, ked sa
      blizi limit Actions, aby beh dokoncil aspon to, co uz spracoval
"""
import argparse
import calendar
import logging
import os
import sys
import time
from datetime import datetime, timezone

from supabase import create_client

import ruz

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)-7s %(name)-9s %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("obohat_financie")

PRESKOC_DNI = int(os.getenv("RUZ_PRESKOC_DNI", "180"))
TIME_BUDGET_MIN = int(os.getenv("RUZ_TIME_BUDGET_MIN", "40"))


def _posledny_den_mesiaca(rok_mesiac):
    """'2025-12' -> '2025-12-31'. RUZ vracia obdobia len ako YYYY-MM, tu
    treba skutocny posledny den mesiaca, nie natvrdo 28/30 (marec, december
    a pod. by tak prisli o 1-3 dni z obdobia)."""
    if not rok_mesiac:
        return None
    rok, mesiac = (int(x) for x in rok_mesiac.split("-"))
    return f"{rok_mesiac}-{calendar.monthrange(rok, mesiac)[1]:02d}"


_STRANKA_DB = 1000


def _nacitaj_vsetko(dotaz_fn, stranka=_STRANKA_DB):
    """Nacita VSETKY riadky opakovanym .range() (stránkovanie).

    Objavene 22.9.2026: Supabase/PostgREST v predvolenom nastaveni obmedzi
    jeden .select().execute() bez .range()/.limit() na max-rows (tu 1000).
    `_nacitaj_kandidatov` nizsie to pri 2149 riadkoch v `dodavatelia` a
    ziadnom .range() nikdy nezistil - videla sa len prvych 1000 (zoradenych
    podla objem_eur), zvysnych 1149 firiem nebolo mozne NIKDY vybrat ako
    kandidatov, aj ked retazenie behov (.github/workflows/ruz-financie.yml)
    spravne bezalo dalej. `dotaz_fn(start, end)` vrati uz vykonany
    .execute() pre dany .range(start, end).
    """
    vysledok = []
    zaciatok = 0
    while True:
        davka = dotaz_fn(zaciatok, zaciatok + stranka - 1).data or []
        vysledok.extend(davka)
        if len(davka) < stranka:
            break
        zaciatok += stranka
    return vysledok


def _nacitaj_kandidatov(sb, limit, force):
    """ICO z `dodavatelia`, zoradene: bez zaznamu v ruz_zaklad prve, potom
    najstarsie checked_at. Ak force=True, poradie podla checked_at
    (najstarsie/nikdy prve) bez ohladu na PRESKOC_DNI."""
    dodavatelia = _nacitaj_vsetko(
        lambda od, do: sb.table("dodavatelia").select("supplier_cin, objem_eur")
                         .order("objem_eur", desc=True).range(od, do).execute()
    )
    stav = {r["supplier_cin"]: r.get("checked_at")
            for r in _nacitaj_vsetko(
                lambda od, do: sb.table("ruz_zaklad")
                                 .select("supplier_cin, checked_at").range(od, do).execute()
            )}

    teraz = datetime.now(timezone.utc)

    def je_cerstve(checked_at):
        if not checked_at:
            return False
        try:
            dt = datetime.fromisoformat(checked_at.replace("Z", "+00:00"))
        except ValueError:
            return False
        return (teraz - dt).days < PRESKOC_DNI

    kandidati = []
    for d in dodavatelia:
        ico = d["supplier_cin"]
        checked_at = stav.get(ico)
        if not force and je_cerstve(checked_at):
            continue
        # Ziadny zaznam (None) ide pred hocijakym datumom — chceme najprv
        # pokryt firmy, ktore este vobec neboli skontrolovane.
        kluc = (checked_at is not None, checked_at or "")
        kandidati.append((kluc, ico))

    kandidati.sort(key=lambda x: x[0])
    return [ico for _, ico in kandidati[:limit]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=150,
                    help="kolko ICO spracovat v tomto behu (default 150)")
    ap.add_argument("--force", action="store_true",
                    help="skontroluj aj cerstvo skontrolovane ICO")
    ap.add_argument("--nasucho", action="store_true",
                    help="nic nezapise, len vypise co by spravil")
    args = ap.parse_args()

    url = os.getenv("SUPABASE_URL")
    servis = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not (url and servis):
        log.error("Chyba SUPABASE_URL alebo SUPABASE_SERVICE_ROLE_KEY.")
        return 1

    sb = create_client(url, servis)

    try:
        icos = _nacitaj_kandidatov(sb, args.limit, args.force)
    except Exception as e:
        log.error("Nepodarilo sa nacitat zoznam dodavatelov: %s", e)
        return 1

    log.info("Kandidatov na obohatenie: %s%s", len(icos),
              "  [NASUCHO]" if args.nasucho else "")
    if not icos:
        return 0

    zaciatok = time.monotonic()
    spracovanych = so_zaznamom = bez_zaznamu = zlyhanych = 0

    for ico in icos:
        if (time.monotonic() - zaciatok) / 60 > TIME_BUDGET_MIN:
            log.warning("Casovy rozpocet (%s min) vycerpany, koncim. "
                        "Dalsi beh pokracuje zvysnymi ICO.", TIME_BUDGET_MIN)
            break

        try:
            data = ruz.financie_pre_ico(ico)
        except ruz.RuzChyba as e:
            log.warning("ICO %s: %s", ico, e)
            zlyhanych += 1
            continue
        except Exception as e:
            # Nedovolime jednej firme so zvlastnym tvarom dat zhodit cely beh.
            log.warning("ICO %s: neocakavana chyba (%s), preskakujem", ico, e)
            zlyhanych += 1
            continue

        spracovanych += 1
        if data["ma_zaznam"]:
            so_zaznamom += 1
        else:
            bez_zaznamu += 1

        if args.nasucho:
            log.info("ICO %s: ma_zaznam=%s nace=%s roky=%s", ico,
                      data["ma_zaznam"], data["nace_kod"],
                      [r["rok"] for r in data["roky"]])
            continue

        try:
            sb.table("ruz_zaklad").upsert({
                "supplier_cin": ico,
                "ma_zaznam": data["ma_zaznam"],
                "nace_kod": data["nace_kod"],
                "nace_nazov": data["nace_nazov"],
                "pravna_forma": data["pravna_forma"],
                "velkost_organizacie": data["velkost_organizacie"],
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }, on_conflict="supplier_cin").execute()

            if data["roky"]:
                riadky = [{
                    "supplier_cin": ico,
                    "rok": r["rok"],
                    "obdobie_od": r["obdobie_od"] + "-01" if r["obdobie_od"] else None,
                    "obdobie_do": _posledny_den_mesiaca(r["obdobie_do"]),
                    "datum_podania": r["datum_podania"],
                    "obrat": r["obrat"],
                    "vysledok_hospodarenia": r["vysledok_hospodarenia"],
                    "refreshed_at": datetime.now(timezone.utc).isoformat(),
                } for r in data["roky"]]
                sb.table("ruz_financie").upsert(
                    riadky, on_conflict="supplier_cin,rok"
                ).execute()
        except Exception as e:
            log.warning("ICO %s: zapis do DB zlyhal (%s)", ico, e)
            zlyhanych += 1

    log.info("Hotovo: spracovanych %s (so zaznamom %s, bez zaznamu %s), zlyhanych %s",
              spracovanych, so_zaznamom, bez_zaznamu, zlyhanych)

    # Signalizacia pre GitHub Actions (retazenie behov, viz workflow):
    # su este dalsie ICO na spracovanie po tomto behu? Zmysluplne len pre
    # ostry beh — v --nasucho sa nic do ruz_zaklad.checked_at nezapisuje,
    # takze rovnaky dopyt by vratil ten isty zoznam donekonecna a chain by
    # sa nikdy nezastavil.
    zostava = False
    if not args.nasucho:
        try:
            zostava = bool(_nacitaj_kandidatov(sb, limit=1, force=args.force))
        except Exception as e:
            log.warning("Nepodarilo sa overit, ci zostavaju dalsie ICO: %s", e)
    vystup = os.getenv("GITHUB_OUTPUT")
    if vystup:
        with open(vystup, "a", encoding="utf-8") as f:
            f.write(f"zostava={'true' if zostava else 'false'}\n")
            f.write(f"spracovanych={spracovanych}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
