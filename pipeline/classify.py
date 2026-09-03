"""Textova klasifikacia zmluv do sektorov.

CRZ neobsahuje CPV kody — su tam len `subject` a `subject_description` ako
volny text. Tato vrstva je nahrada za pole, ktore v datach neexistuje.
Skutocne CPV kody pribudnu az s vestnikom UVO.
"""
import unicodedata

from config import SEKTORY, PRAH_SKORE, NEGATIVNE, VAHA_NEGATIVNA


def bez_diakritiky(text) -> str:
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", str(text))
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def klasifikuj(subject, popis):
    """Vrati (sektor|None, skore).

    Vylucujuce slova sa odratavaju raz a od vsetkych sektorov rovnako.
    Pri zhode skore vyhrava sektor, ktory je v SEKTORY skor — preto su
    konkretne remesla pred vseobecnymi stavebnymi pracami.
    """
    text = bez_diakritiky(f"{subject or ''} {popis or ''}")
    if not text.strip():
        return None, 0

    penalta = sum(VAHA_NEGATIVNA for s in NEGATIVNE if s in text)

    najlepsi, najskore = None, 0
    for nazov, cfg in SEKTORY.items():
        skore = penalta
        for vaha, slova in cfg["kluc"].items():
            for s in slova:
                if s in text:
                    skore += vaha
        if skore > najskore:
            najlepsi, najskore = nazov, skore

    return (najlepsi, najskore) if najskore >= PRAH_SKORE else (None, najskore)
