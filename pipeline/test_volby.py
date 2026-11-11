from volby import rozober

CSV_2022 = ("Zvolení starostovia\nKód kraja;Názov kraja;Kód okresu;Názov okresu;Kód obce;Názov obce;Meno;Priezvisko;Politický subjekt\n"
            "1;Bratislavský kraj;101;Bratislava I;528595;Bratislava - Staré Mesto;Zuzana;Aufrichtová;NEKA\n")
CSV_2026 = ('"Kód kraja","Názov kraja","Kód okresu","Názov okresu","Kód obce","Názov obce","Meno","Priezvisko","Politický subjekt"\n'
            '1,"Bratislavský kraj",101,"Bratislava I",528595,"Bratislava - Staré Mesto","Matej","Vagač","PS, SaS"\n')
CSV_2026_MESTA = '"Kód mesta","Názov mesta","Meno","Priezvisko","Politický subjekt"\n582000,"Bratislava","Matúš","Vallo","X"\n'


def test_2022_bodkociarka():
    r = rozober(CSV_2022, 2022)
    assert r[0]["kod_obce"] == "528595" and r[0]["priezvisko"] == "Aufrichtová"


def test_2026_ciarka_uvodzovky():
    r = rozober(CSV_2026, 2026)
    assert r[0]["kod_obce"] == "528595" and r[0]["meno"] == "Matej" and r[0]["subjekt"] == "PS, SaS"
    assert r[0]["kraj"] == "Bratislavský kraj"


def test_2026_mesta():
    r = rozober(CSV_2026_MESTA, 2026)
    assert r[0]["kod_obce"] == "582000" and r[0]["obec"] == "Bratislava"
