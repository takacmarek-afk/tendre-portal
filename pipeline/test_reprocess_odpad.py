"""reprocess_odpad: faza A presunie len to, co teraz patri do ODPAD."""
from reprocess_odpad import kandidati_fazy_a


def test_faza_a():
    riadky = [
        {"id": 1, "sector": "UPRATOVANIE", "subject": "Zber a vývoz komunálneho odpadu", "subject_description": ""},
        {"id": 2, "sector": "UPRATOVANIE", "subject": "Upratovanie budovy úradu", "subject_description": ""},
        {"id": 3, "sector": "DOTACIE_NFP", "subject": "Dotácia na zberný dvor - zber odpadu", "subject_description": ""},
        {"id": 4, "sector": "ODPAD", "subject": "Vývoz odpadu", "subject_description": ""},
        {"id": 5, "sector": "KURENIE_VODA_PLYN", "subject": "Rekonštrukcia čistiarne odpadových vôd", "subject_description": ""},
    ]
    z = kandidati_fazy_a(riadky)
    assert set(z) == {1}
    assert z[1][0] == "UPRATOVANIE"
