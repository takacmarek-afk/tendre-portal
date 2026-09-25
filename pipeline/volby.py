"""Zvoleni starostovia a primatori z otvorenych dat volieb (SU SR).

Spustenie:
    python volby.py --rok 2022 --nasucho   # overenie formatu, nic nezapise
    python volby.py --rok 2026             # po zverejneni vysledkov volieb

ZDROJ: Statisticky urad SR zverejnuje vysledky volieb do organov samospravy
obci ako CSV na volby.statistics.sk/opendata/oso/<rok>/:
    OSO<rok>_SK_tab04d.csv — zvoleni starostovia obci a mestskych casti
    OSO<rok>_SK_tab04x.csv — zvoleni primatori (Bratislava, Kosice)
Kodovanie windows-1250, oddelovac ';', pred hlavickou byva riadok s nazvom
tabulky. Stlpce (2022): Kod kraja;Nazov kraja;Kod uzemneho obvodu;Nazov
uzemneho obvodu;Kod okresu;Nazov okresu;Kod obce;Nazov obce;Meno;Priezvisko;
Politicky subjekt. Stlpce sa hladaju podla nazvu, nie podla poradia —
ak SU v roku 2026 nejaky prida alebo prehodi, parser to prezije.

POSLANCOV (tab06d) ZAMERNE NENACITAVAME. Kampan pise len na uradnu adresu
obce; osobne udaje poslancov nepotrebujeme, tak ich ani neukladame.

KOD OBCE je 6-miestny kod SU SR — ten isty, ktory je na konci kodu obce
v registri (pipeline/data/register_obce_raw.json: SK + okres + 6 cifier).
Cez neho kampan_obce.py paruje starostu s kontaktom obce.

Sietovo: volby.statistics.sk je dosiahnutelny z GitHub Actions
(.github/workflows/kampan-obce.yml, krok "volby").
"""
import argparse
import csv
import io
import logging
import sys

import requests

log = logging.getLogger("volby")

URL = "https://volby.statistics.sk/opendata/oso/{rok}/OSO{rok}_SK_{tab}.csv"
TABULKY = ("tab04d", "tab04x")
DAVKA = 500

# nazov stlpca (normalizovany) -> nas kluc
_STLPCE = {
    "kod obce": "kod_obce", "kod mesta": "kod_obce", "kod mestskej casti": "kod_obce",
    "nazov obce": "obec", "nazov mesta": "obec", "nazov mestskej casti": "obec",
    "nazov okresu": "okres", "nazov kraja": "kraj",
    "meno": "meno", "priezvisko": "priezvisko",
    "titul pred menom": "titul_pred", "tituly pred menom": "titul_pred", "titul": "titul_pred",
    "politicky subjekt": "subjekt",
}


def _norm(t):
    import unicodedata
    nfkd = unicodedata.normalize("NFKD", str(t or ""))
    return " ".join("".join(c for c in nfkd if not unicodedata.combining(c)).lower().split())


def dekoduj(obsah: bytes) -> str:
    """windows-1250 podla dokumentacie SU; keby prislo UTF-8 (s BOM alebo bez),
    nerozbit diakritiku."""
    if obsah.startswith(b"\xef\xbb\xbf"):
        return obsah[3:].decode("utf-8")
    try:
        return obsah.decode("utf-8")
    except UnicodeDecodeError:
        return obsah.decode("cp1250")


def rozober(text: str, rok: int, zdroj_url: str = None):
    """CSV text -> zoznam riadkov pre obce_starostovia.

    Hlavicka je prvy riadok, v ktorom je stlpec 'Priezvisko' — riadky nad
    nou (nazov tabulky) sa preskocia. Riadok bez kodu obce alebo bez
    priezviska (napr. obec, kde sa volby nekonali) sa vynecha.
    """
    riadky = list(csv.reader(io.StringIO(text), delimiter=";"))
    hlav_i = next((i for i, r in enumerate(riadky)
                   if any(_norm(x) == "priezvisko" for x in r)), None)
    if hlav_i is None:
        raise ValueError("V CSV chyba hlavicka so stlpcom 'Priezvisko'")
    mapa = {}
    for j, nazov in enumerate(riadky[hlav_i]):
        k = _STLPCE.get(_norm(nazov))
        if k and k not in mapa:
            mapa[k] = j
    for povinny in ("kod_obce", "obec", "priezvisko"):
        if povinny not in mapa:
            raise ValueError(f"V CSV chyba stlpec pre {povinny}: {riadky[hlav_i]}")

    out, videne = [], set()
    for r in riadky[hlav_i + 1:]:
        if not r or len(r) <= max(mapa.values()):
            continue
        z = {k: (r[j].strip() or None) for k, j in mapa.items()}
        kod = "".join(ch for ch in (z.get("kod_obce") or "") if ch.isdigit())
        if not kod or not z.get("priezvisko"):
            continue
        if kod in videne:            # ta ista obec dvakrat — nechame prvy zaznam
            continue
        videne.add(kod)
        out.append({
            "rok": rok, "kod_obce": kod, "obec": z.get("obec"),
            "okres": z.get("okres"), "kraj": z.get("kraj"),
            "meno": z.get("meno"), "priezvisko": z.get("priezvisko"),
            "titul_pred": z.get("titul_pred"), "subjekt": z.get("subjekt"),
            "zdroj_url": zdroj_url,
        })
    return out


def stiahni(sess, rok, tab):
    url = URL.format(rok=rok, tab=tab)
    r = sess.get(url, timeout=60)
    if r.status_code == 404:
        return url, None
    r.raise_for_status()
    return url, dekoduj(r.content)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--rok", type=int, required=True)
    ap.add_argument("--nasucho", action="store_true", help="nic nezapisat")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    from config import USER_AGENT
    sess = requests.Session()
    sess.headers["User-Agent"] = USER_AGENT

    vsetky = []
    for tab in TABULKY:
        url, text = stiahni(sess, a.rok, tab)
        if text is None:
            log.warning("%s zatial neexistuje (404) — SU este nezverejnil vysledky?", url)
            continue
        riadky = rozober(text, a.rok, url)
        log.info("%s: %d zvolenych", url, len(riadky))
        for r in riadky[:3]:
            log.info("  ukazka: %s %s — %s (%s)", r["meno"], r["priezvisko"], r["obec"], r["okres"])
        vsetky.extend(riadky)

    if not vsetky:
        log.error("Ziadne data pre rok %d.", a.rok)
        return 1
    # tab04x moze obsahovat obec, ktora je aj v tab04d — kluc (rok, kod_obce)
    unikatne = {r["kod_obce"]: r for r in vsetky}
    log.info("Spolu %d obci so zvolenym starostom/primatorom.", len(unikatne))
    if a.nasucho:
        log.info("NASUCHO — nic nezapisane.")
        return 0

    from store import klient
    sb = klient()
    riadky = list(unikatne.values())
    for i in range(0, len(riadky), DAVKA):
        sb.table("obce_starostovia").upsert(riadky[i:i + DAVKA], on_conflict="rok,kod_obce").execute()
    log.info("Zapisane do obce_starostovia: %d", len(riadky))
    return 0


if __name__ == "__main__":
    sys.exit(main())
