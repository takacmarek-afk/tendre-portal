"""Pokus o automaticky zber OTVORENYCH VYZIEV pre obce.

Zamerne sa to vola "pokus". Stav overeny 16. 9. 2026:

  opendata.itms2014.sk  — vracia HTTP 403 na KAZDEJ ceste, aj na Swagger.
                          Moze to byt blokovanie konkretnej IP, takze
                          z bezca GitHub Actions to fungovat MOZE.
                          Zistime az prvym behom.
  eurofondy.gov.sk      — WordPress REST API odpoveda (HTTP 200), ale vyzvy
                          tam nie su samostatny typ obsahu. Su to bezne
                          clanky, takze z toho ide zmes clankov a vyziev
                          a treba to filtrovat podla textu.
  data.gov.sk           — CKAN API, standardne a strojove. Katalog datasetov,
                          nie zoznam vyziev, ale da sa tam najst odkaz.

PRAVIDLO PRE CELY MODUL: kazdy zdroj je vo vlastnom try. Ked zlyha, zapise
sa warning a ide sa dalej. Ziadny zdroj nesmie zhodit beh — vrstva aktivnych
programov z CRZ funguje aj bez vyziev a je to ta, na ktoru sa da spolahnut.

CO SEM NEPATRI: obchadzanie blokovania. Ked zdroj vrati 403, je to odpoved,
nie prekazka. Nezkusame ine IP, proxy ani archivy.
"""
import logging
import re
from datetime import date, datetime

import requests

log = logging.getLogger("vyzvy")

CASOVY_LIMIT = 25          # sekund na jeden zdroj
MAX_Z_ZDROJA = 60          # viac nez tolko riadkov z jedneho zdroja neberieme

USER_AGENT = "PredTendrom.sk/1.0 (verejne zakazky, kontakt info@predtendrom.sk)"

# Slova, ktore v nazve clanku naznacuju vyzvu. Bez nich by z WordPressu
# prisli aj tlacove spravy a pozvanky na konferencie.
_JE_VYZVA = re.compile(
    r"\bv[yý]zv\w*|\bdopytov\w*|nen[aá]vratn\w*\s+finan[cč]n|\bNFP\b"
    r"|[zž]iadost\w*\s+o\s+(poskytnutie|nen[aá]vratn)",
    re.IGNORECASE)

# Slova, ktore naznacuju, ze je to pre obce a mesta.
_PRE_OBCE = re.compile(
    r"\bobec\w*|\bobc[ei]\b|\bmest\w*|samospr[aá]v\w*|\bVUC\b|\bkraj\w*"
    r"|z[aá]kladn\w*\s+[sš]kol|matersk\w*\s+[sš]kol|obecn\w*",
    re.IGNORECASE)


def _prazdny():
    return []


def _riadok(nazov, poskytovatel, url, zdroj, uzavretie=None, popis=None,
            pre_obce=None):
    """Jeden normalizovany zaznam. Vsetky zdroje musia vratit tento tvar."""
    return {
        "nazov": (nazov or "").strip()[:400] or None,
        "poskytovatel": (poskytovatel or "").strip()[:200] or None,
        "url": (url or "").strip()[:500] or None,
        "zdroj": zdroj,
        "uzavretie": uzavretie,
        "popis": (popis or "").strip()[:800] or None,
        "pre_obce": pre_obce,
    }


# ── ZDROJ 1: ITMS2014+ OpenData API ────────────────────────────────────────

def z_itms(session) -> list:
    """Oficialne OpenData API k eurofondom. Ku 16. 9. 2026 vracia 403.

    Skusam viac ciest, pretoze dokumentacia sa v case menila a nechcem to
    odpisat len preto, ze jedna cesta uz neexistuje.
    """
    zaklad = "https://opendata.itms2014.sk"
    cesty = ["/v2/vyzvy", "/vyzvy", "/api/v2/vyzvy"]
    for cesta in cesty:
        try:
            r = session.get(zaklad + cesta,
                            params={"page": 1, "count": MAX_Z_ZDROJA},
                            timeout=CASOVY_LIMIT)
        except requests.RequestException as e:
            log.warning("ITMS %s: siet zlyhala (%s)", cesta, type(e).__name__)
            continue

        if r.status_code == 403:
            log.warning("ITMS %s: HTTP 403 — pristup zamietnuty. "
                        "To je odpoved zdroja, neobchadzame ju.", cesta)
            continue
        if r.status_code == 404:
            continue
        if r.status_code != 200:
            log.warning("ITMS %s: HTTP %s", cesta, r.status_code)
            continue

        try:
            data = r.json()
        except ValueError:
            log.warning("ITMS %s: odpoved nie je JSON", cesta)
            continue

        polozky = data if isinstance(data, list) else (
            data.get("items") or data.get("data") or [])
        out = []
        for p in polozky[:MAX_Z_ZDROJA]:
            if not isinstance(p, dict):
                continue
            out.append(_riadok(
                nazov=p.get("nazov") or p.get("name"),
                poskytovatel=(p.get("vyhlasovatel") or p.get("poskytovatel")
                              or p.get("organizacia")),
                url=p.get("url") or p.get("odkaz"),
                zdroj="ITMS2014+",
                uzavretie=p.get("datumUzavretia") or p.get("datum_uzavretia"),
                popis=p.get("popis") or p.get("description"),
            ))
        if out:
            log.info("ITMS %s: %s vyziev", cesta, len(out))
            return out
    log.warning("ITMS: ziadna cesta nevratila data.")
    return _prazdny()


# ── ZDROJ 2: eurofondy.gov.sk, WordPress REST API ──────────────────────────

def z_eurofondy(session) -> list:
    """WordPress REST API na eurofondy.gov.sk.

    Vyzvy nie su samostatny typ obsahu, takze filtrujem clanky podla nazvu.
    Je to hrubsie nez skutocne API, ale je to VEREJNE DOKUMENTOVANE
    rozhranie, ktore ten web sam vystavuje — nie zoskrabavanie HTML.
    """
    url = "https://eurofondy.gov.sk/wp-json/wp/v2/posts"
    try:
        r = session.get(url, params={"per_page": 100, "orderby": "date",
                                     "order": "desc"},
                        timeout=CASOVY_LIMIT)
    except requests.RequestException as e:
        log.warning("Eurofondy: siet zlyhala (%s)", type(e).__name__)
        return _prazdny()

    if r.status_code != 200:
        log.warning("Eurofondy: HTTP %s", r.status_code)
        return _prazdny()

    try:
        clanky = r.json()
    except ValueError:
        log.warning("Eurofondy: odpoved nie je JSON")
        return _prazdny()

    if not isinstance(clanky, list):
        log.warning("Eurofondy: neocakavany tvar odpovede")
        return _prazdny()

    out = []
    for c in clanky:
        if not isinstance(c, dict):
            continue
        nazov = ((c.get("title") or {}).get("rendered") or "")
        nazov = re.sub(r"<[^>]+>", "", nazov)
        nazov = (nazov.replace("&#8211;", "–").replace("&#8217;", "'")
                      .replace("&amp;", "&").replace("&nbsp;", " ").strip())
        if not nazov or not _JE_VYZVA.search(nazov):
            continue
        popis = re.sub(r"<[^>]+>", " ",
                       (c.get("excerpt") or {}).get("rendered") or "")
        popis = re.sub(r"\s+", " ", popis).strip()
        out.append(_riadok(
            nazov=nazov,
            poskytovatel=None,          # v clanku to strukturovane nie je
            url=c.get("link"),
            zdroj="eurofondy.gov.sk",
            uzavretie=None,
            popis=popis,
            pre_obce=bool(_PRE_OBCE.search(nazov + " " + popis)),
        ))
        if len(out) >= MAX_Z_ZDROJA:
            break

    log.info("Eurofondy: %s zaznamov s vyzvou v nazve (z %s clankov)",
             len(out), len(clanky))
    return out


# ── ZDROJ 3: data.gov.sk, CKAN ─────────────────────────────────────────────

def z_datagov(session) -> list:
    """Katalog otvorenych dat. Nie zoznam vyziev, ale odkazy na datasety.

    Berie sa preto, ze ked sa raz nejaky urad rozhodne vyzvy publikovat
    ako otvorene data, objavi sa to tu — a pipeline si to vsimne sama.
    """
    url = "https://data.gov.sk/api/3/action/package_search"
    try:
        r = session.get(url, params={"q": "výzvy dotácie nenávratný príspevok",
                                     "rows": 20},
                        timeout=CASOVY_LIMIT)
    except requests.RequestException as e:
        log.warning("data.gov.sk: siet zlyhala (%s)", type(e).__name__)
        return _prazdny()

    if r.status_code != 200:
        log.warning("data.gov.sk: HTTP %s", r.status_code)
        return _prazdny()

    try:
        data = r.json()
    except ValueError:
        log.warning("data.gov.sk: odpoved nie je JSON")
        return _prazdny()

    vysledky = ((data.get("result") or {}).get("results") or [])
    out = []
    for d in vysledky[:MAX_Z_ZDROJA]:
        if not isinstance(d, dict):
            continue
        nazov = d.get("title") or d.get("name")
        if not nazov:
            continue
        out.append(_riadok(
            nazov=nazov,
            poskytovatel=(d.get("organization") or {}).get("title"),
            url="https://data.gov.sk/dataset/" + str(d.get("name") or ""),
            zdroj="data.gov.sk",
            popis=d.get("notes"),
            pre_obce=None,
        ))
    log.info("data.gov.sk: %s datasetov", len(out))
    return out


# ── SPOLOCNY VSTUP ─────────────────────────────────────────────────────────

def stiahni(dnes: date = None) -> list:
    """Vyskusa vsetky zdroje. Vrati zlucene a odduplikovane zaznamy.

    Nikdy nevyhodi vynimku. Ked nefunguje nic, vrati prazdny zoznam
    a stranka pre obce ukaze len aktivne programy z CRZ — co je aj tak
    ta cast, na ktoru sa da spolahnut.
    """
    dnes = dnes or date.today()
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT,
                            "Accept": "application/json"})

    vsetko = []
    for meno, fn in (("ITMS2014+", z_itms),
                     ("eurofondy.gov.sk", z_eurofondy),
                     ("data.gov.sk", z_datagov)):
        try:
            vsetko.extend(fn(session))
        except Exception as e:                      # zamerne siroke
            log.warning("Zdroj %s spadol (%s: %s) — pokracujem dalej.",
                        meno, type(e).__name__, e)

    # Odduplikovanie podla URL, a ked chyba, podla nazvu.
    videne, out = set(), []
    for v in vsetko:
        kluc = (v.get("url") or "") or (v.get("nazov") or "")
        kluc = kluc.strip().lower()
        if not kluc or kluc in videne:
            continue
        videne.add(kluc)
        v["stiahnute"] = dnes.isoformat()
        out.append(v)

    if not out:
        log.warning("VYZVY: ziadny zdroj nedal pouzitelne data. Stranka pre "
                    "obce ukaze len aktivne programy z CRZ.")
    else:
        log.info("VYZVY: %s zaznamov celkom, z toho oznacenych pre obce %s",
                 len(out), sum(1 for v in out if v.get("pre_obce")))
    return out
