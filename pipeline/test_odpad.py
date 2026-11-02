"""Sektor ODPAD (rozhodnutie 2. 11. 2026): co do odpadu patri a co nie."""
from classify import klasifikuj
from uvo import sektor


def _s(predmet):
    return klasifikuj(predmet, "")[0]


def test_odpad_zachyti():
    for p in ["Zmluva o zbere a vývoze komunálneho odpadu",
              "Vývoz a zber odpadu z obce",
              "Odpadové hospodárstvo obce Testovo",
              "Triedený zber a zvoz odpadu",
              "Prevádzka zberného dvora",
              "Vývoz smetí a KUKA nádob",
              "Likvidácia odpadu"]:
        assert _s(p) == "ODPAD", p


def test_odpad_nezachyti_cudzie():
    assert _s("Rekonštrukcia čistiarne odpadových vôd") != "ODPAD"
    assert _s("Vývoz snehu") != "ODPAD"
    assert _s("Zber údajov") != "ODPAD"
    assert _s("Kúpna zmluva - kontajner") != "ODPAD"


def test_cpv_odpad():
    assert sektor("90511000-2", "Zber odpadu") == "ODPAD"
    assert sektor("90910000-9", "Upratovanie") == "UPRATOVANIE"
