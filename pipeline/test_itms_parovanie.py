import itms_parovanie as ip


def _i(nazov, ico="00312345", h=None, zal="2026-01-01"):
    return {"id": 1, "nazov": nazov, "obstaravatel_ico": ico, "predpokladana_hodnota": h, "itms_created_at": zal}


def _v(nazov, ico="312345", pub="2026-06-01", h=None):
    return {"typ": "sutaz", "obstaravatel_ico": ico, "nazov": nazov, "publikovane": pub, "predpokladana_hodnota": h}


def test_rovnaky_nazov_a_ico_sa_sparuje():
    p = ip.paruj([_i("Bystrany – vodovod, kanalizácia a ČOV")], [_v("Bystrany - vodovod, kanalizacia a COV")])
    assert len(p) == 1 and p[0][2] == 1.0


def test_ine_ico_alebo_stara_vyzva_nie():
    assert not ip.paruj([_i("Modernizácia ZŠ Benice")], [_v("Modernizácia základnej školy Benice", ico="999")])
    assert not ip.paruj([_i("Modernizácia ZŠ Benice", zal="2026-06-01")], [_v("Modernizácia ZŠ Benice", pub="2026-01-01")])


def test_dozor_sa_neparuje_so_stavbou():
    assert not ip.paruj([_i("Stavebný dozor na stavbe Aglomerácia Banská Bystrica – kanalizácia")],
                        [_v("Aglomerácia Banská Bystrica - kanalizácia")])


def test_slaba_zhoda_nie():
    assert not ip.paruj([_i("Zberný dvor Dolné Dubové")], [_v("CELOOBECNÁ KANALIZÁCIA DOLNÉ DUBOVÉ")])
