"""Oficialny register obci (Statisticky urad SR, DATAcube) -> mesto/kraj.

Zdroj su dva JSON-stat vypisy v data/: `register_nuts4_raw.json` (hierarchia
SR -> oblast -> kraj -> okres, kody NUTS) a `register_obce_raw.json`
(vsetky obce SR). Kod obce ma tvar "SK" + 4-znakovy kod okresu (NUTS4, moze
obsahovat aj pismeno, napr. "031A") + 6-ciferny kod samotnej obce. Kraj aj
okres sa teda odvodia priamo z kodu, bez hadania:

    kod obce:  SK 0106 504556
    okres:     SK0106      -> "Okres Malacky"      (nuts4[kod[:6]])
    kraj:      SK010       -> "Bratislavský kraj"   (nuts4[kod[:5]])

DOVOD, PRECO TOTO VZNIKLO: doterajsi zoznam v regiony.OKRESY ma len 122
okresnych a velkych miest. Male obce, ktore v nom nie su, sa doteraz museli
spoliehat na naucenu mapu PSC prefixov (regiony.nauc_psc) alebo ostali bez
kraja — 17 % zaznamov, odmerane v metodike z 10. 9. 2026. Tento register
pridava zvysok Slovenska (~2890 obci) rovnakym mechanizmom.

OVERENE PRI NAPLNENI (17. 9. 2026): kuratorovany zoznam OKRESY sedel
s registrom na 100 % (0 konfliktov na 125 prekryvajucich sa nazvoch).
Register pridava dalsich cca 2600 jednoznacnych nazvov.

AMBIGUITA. 83 z 2811 normalizovanych nazvov (2,9 %) patri viacerym obciam
v roznych krajoch naraz (napr. "Rohoznik" je aj v Bratislavskom aj
v Presovskom kraji). Take nazvy sa VYNECHAVAJU — rovnaky princip, aky uz
regiony.py pouziva pri PSC prefixoch: radsej prazdna hodnota nez zle
priradeny kraj.

AGREGATY. Kody "SK_CAP" (Bratislava ako celok, agregat okresov I az V)
a "SK0422_0425" (zluceny statisticky celok) nemaju tvar kodu jednotlivej
obce a preskakuju sa - nesedia na vzor SK+4+6 znakov.

VYKON: rozsirenie MESTO_KRAJ z 125 na ~2730 poloziek predlzi _V_NAZVE regex,
ale odmerane vyhladavanie ostava pod 35 mikrosekund na volanie (~30x
pomalsie nez povodnych 125 slov, ale stale zanedbatelne oproti casovemu
rozpoctu pipeline v minutach).
"""
import json
import re
import unicodedata
from pathlib import Path

_DATA = Path(__file__).parent / "data"
_KOD = re.compile(r"^SK([0-9A-Z]{4})(\d{6})$")


def _norm(t) -> str:
    nfkd = unicodedata.normalize("NFKD", str(t or ""))
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


def _nacitaj_surovo(cesta_nuts4, cesta_obce):
    """Spolocny nacitavaci krok pre nacitaj() aj nacitaj_s_okresom().

    Vrati {normalizovany_nazov: {(spravny_nazov, kraj, okres), ...}} —
    volajuci si sam rozhodne, na akej urovni (nazov,kraj) vs (nazov,kraj,okres)
    posudzuje jednoznacnost (vid komentare pri oboch funkciach nizsie).
    """
    cesta_nuts4 = Path(cesta_nuts4) if cesta_nuts4 else (_DATA / "register_nuts4_raw.json")
    cesta_obce = Path(cesta_obce) if cesta_obce else (_DATA / "register_obce_raw.json")
    try:
        nuts4 = json.loads(cesta_nuts4.read_text(encoding="utf-8"))["category"]["label"]
        obce = json.loads(cesta_obce.read_text(encoding="utf-8"))["category"]["label"]
    except (OSError, KeyError, json.JSONDecodeError):
        return {}

    kandidati = {}   # normalizovany nazov -> {(spravny_nazov, kraj, okres), ...}
    for kod, nazov in obce.items():
        m = _KOD.match(kod)
        if not m:
            continue                      # SK_CAP a podobne agregaty
        okres_kod = "SK" + m.group(1)     # napr. "SK0106" -> "Okres Malacky"
        kraj = nuts4.get(okres_kod[:5])   # napr. "SK010" -> "Bratislavský kraj"
        okres = nuts4.get(okres_kod)
        if not kraj:
            continue
        kandidati.setdefault(_norm(nazov), set()).add((nazov, kraj, okres))
    return kandidati


def nacitaj(cesta_nuts4=None, cesta_obce=None) -> dict:
    """Vrati {normalizovany_nazov: (spravny_nazov, kraj)} pre JEDNOZNACNE obce.

    Chybajuce alebo necitatelne subory NIE SU chyba behu — vratia prazdny
    slovnik. Register je rozsirenie kuratorovaneho zoznamu, nie zavislost,
    na ktorej by mal beh pipeline stat alebo padat.
    """
    kandidati = _nacitaj_surovo(cesta_nuts4, cesta_obce)
    # Jednoznacne = presne jedna dvojica (nazov, kraj) pre dany normalizovany
    # kluc. Rovnaky normalizovany nazov vo viacerych krajoch sa vynecha.
    # (Okres sa tu zamerne zahadzuje — signatura aj sprava tejto funkcie
    # ostava nezmenena, existujuci volajuci regiony.py na tom stoji.)
    vysledok = {}
    for n, s in kandidati.items():
        dvojice = {(nazov, kraj) for nazov, kraj, _okres in s}
        if len(dvojice) == 1:
            vysledok[n] = next(iter(dvojice))
    return vysledok


def nacitaj_s_okresom(cesta_nuts4=None, cesta_obce=None) -> dict:
    """Ako nacitaj(), ale vracia aj okres: {norm_nazov: (spravny_nazov, kraj, okres)}.

    Pouziva pipeline/alerty.py na parovanie "susednych" obci (rovnaky okres) —
    vid dovod v hlavicke toho suboru, preco (zatial) len okres, nie aj
    velkost obce. Jednoznacnost sa tu posudzuje na urovni (nazov,kraj,okres),
    teda PRISNEJSIE nez v nacitaj() — nazov, ktory nacitaj() este povazuje
    za jednoznacny (rovnaky kraj), ale patri dvom roznym okresom toho kraja,
    sa tu vynecha. Rovnaky princip ako inde v tomto module: radsej prazdna
    hodnota nez zle priradeny okres.
    """
    kandidati = _nacitaj_surovo(cesta_nuts4, cesta_obce)
    return {n: next(iter(s)) for n, s in kandidati.items() if len(s) == 1}
