import posli_eurofondy_alert as a
from posli_email import _obal


def _r(i, url="https://www.uvo.gov.sk/vyhladavanie/detail/1"):
    return {"itms_id": i, "obstaravatel_nazov": "Obec Hraň", "nazov": "ČOV a kanalizácia", "vyhlasene_nazov": "ČOV Hraň",
            "predpokladana_hodnota": 5100000, "kraj": "Košický kraj", "vyhlasene_url": url,
            "vyhlasene_lehota": "2026-12-02T10:00:00+00:00"}


def test_obsah_a_odkazy():
    ob = a.obsah([_r(1), _r(2, url="https://zly.sk/x")])
    html = _obal(ob["titulok"], ob["uvod"], ob["bloky"], ob["cta_text"], ob["cta_url"], ob["odhlasenie"])
    assert "2 súťaží" in ob["titulok"] and "2. 12. 2026" in html and "zly.sk" not in html


def test_max_10_v_emaili():
    ob = a.obsah([_r(i) for i in range(13)])
    assert len(ob["bloky"]) == 11 and "+ 3" in ob["bloky"][-1]["titul"]
