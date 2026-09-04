"""Textova klasifikacia zmluv do sektorov.

CRZ neobsahuje CPV kody — su tam len `subject` a `subject_description` ako
volny text. Tato vrstva je nahrada za pole, ktore v datach neexistuje.

SKLONOVANIE
-----------
Slovencina sklonuje aj uprostred spojeni. "Strazna sluzba" nie je "strazn sluzb"
za sebou — medzi zakladmi su koncovky. Preto:

  * jednoslovny zaklad     -> obycajne hladanie podretazca ("strech" v "strechy")
  * viacslovne spojenie    -> regularny vyraz, ktory medzi slovami pripusti
                              lubovolnu koncovku ("strazn__ sluzb__")

Vzory sa prekladaju raz pri nacitani modulu, nie pri kazdej zmluve.
"""
import re
import unicodedata

from config import SEKTORY, PRAH_SKORE, NEGATIVNE, VAHA_NEGATIVNA

SEKTOR_DOTACIE = "DOTACIE_NFP"


def bez_diakritiky(text) -> str:
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", str(text))
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def _priprav(vyraz: str):
    """Vrati bud retazec (rychle hladanie podretazca), alebo prelozeny regex.

    Jednoslovny zaklad staci hladat ako podretazec — "strech" najde "strechy".
    Viacslovne spojenie potrebuje regex, lebo koncovka je medzi slovami:
    "strazn sluzb" musi najst "strazna sluzba" aj "straznej sluzby".
    """
    if " " not in vyraz:
        return vyraz
    casti = [re.escape(c) for c in vyraz.split()]
    return re.compile(r"\b" + r"\w*\s+".join(casti) + r"\w*")


def _sedi(vzor, text: str) -> bool:
    return vzor in text if isinstance(vzor, str) else bool(vzor.search(text))


# Predpripravene vzory. Robi sa to raz, nie pri kazdom zazname.
_NEGATIVNE = [_priprav(s) for s in NEGATIVNE]
_SEKTORY = {
    nazov: [(vaha, [_priprav(s) for s in slova])
            for vaha, slova in cfg["kluc"].items()]
    for nazov, cfg in SEKTORY.items()
}


def _skoruj(text: str, vynechaj=()):
    """Vrati (sektor|None, skore) pre uz normalizovany text."""
    penalta = sum(VAHA_NEGATIVNA for v in _NEGATIVNE if _sedi(v, text))

    najlepsi, najskore = None, 0
    for nazov, urovne in _SEKTORY.items():
        if nazov in vynechaj:
            continue
        skore = penalta
        for vaha, vzory in urovne:
            for v in vzory:
                if _sedi(v, text):
                    skore += vaha
        if skore > najskore:
            najlepsi, najskore = nazov, skore

    return (najlepsi, najskore) if najskore >= PRAH_SKORE else (None, najskore)


def klasifikuj(subject, popis):
    """Hlavna klasifikacia. Vrati (sektor|None, skore).

    Vylucujuce slova sa odratavaju raz a od vsetkych sektorov rovnako.
    Pri zhode skore vyhrava sektor, ktory je v SEKTORY skor — preto su
    dotacie uplne prve a konkretne remesla pred vseobecnymi stavebnymi pracami.
    """
    text = bez_diakritiky(f"{subject or ''} {popis or ''}")
    if not text.strip():
        return None, 0
    return _skoruj(text)


def klasifikuj_ucel(subject, popis):
    """Na CO je dotacia. Vrati nazov sektora alebo None.

    Pri dotaciach potrebujeme dve informacie: ze ide o dotaciu (to zisti
    klasifikuj) a na aku pracu je urcena (to zisti tato funkcia).
    Preto sa tu sektor dotacii preskakuje — inak by vyhral sam nad sebou.
    """
    text = bez_diakritiky(f"{subject or ''} {popis or ''}")
    if not text.strip():
        return None
    sektor, _ = _skoruj(text, vynechaj=(SEKTOR_DOTACIE,))
    return sektor
