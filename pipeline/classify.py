"""Textova klasifikacia zmluv do sektorov (CRZ nema CPV kody)."""
import unicodedata
from config import SEKTORY, PRAH_SKORE


def bez_diakritiky(text) -> str:
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", str(text))
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def klasifikuj(subject, popis):
    """Vrati (sektor|None, skore)."""
    text = bez_diakritiky(f"{subject or ''} {popis or ''}")
    if not text.strip():
        return None, 0
    najlepsi, najskore = None, 0
    for nazov, cfg in SEKTORY.items():
        skore = 0
        for vaha, slova in cfg["kluc"].items():
            for s in slova:
                if s in text:
                    skore += vaha
        if skore > najskore:
            najlepsi, najskore = nazov, skore
    return (najlepsi, najskore) if najskore >= PRAH_SKORE else (None, najskore)
