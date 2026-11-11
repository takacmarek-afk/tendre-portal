from obce_web_kontakty import mapa_ico, posud


def test_posud():
    assert posud("obec@brusno.sk", "Brusno", "https://www.brusno.sk")[0] == "ok"
    assert posud("info@osobnyudaj.sk", "Čerín", "https://www.cerin.sk")[0] != "ok"
    assert posud("sekretariat@velkechlievany.com", "Veľké Chlievany", "https://velkechlievany.com/")[0] == "ok"
    assert posud("jan.novak@benice.sk", "Benice", "https://www.benice.sk")[0] != "ok"
    assert posud("info@mojweb.sk", "Kocúrany", "https://www.mojweb.sk")[0] == "ok"


def test_mapa_ico_jednoznacne():
    reg = {"brusno": [("508632", "Banskobystrický kraj")]}
    z = [("Obec Brusno", "313211", None)] * 5 + [("Obec Brusno", "999", None)]
    assert mapa_ico(z, reg, {}) == {"508632": "00313211"}
    z2 = [("Obec Brusno", "313211", None), ("Obec Brusno", "999", None)]
    assert mapa_ico(z2, reg, {}) == {}
