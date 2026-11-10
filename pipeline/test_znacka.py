import re

import znacka
import posli_osobny_email as p


def test_podpis_obsahuje_logo_web_a_socialne_siete():
    h = znacka.podpis_html()
    assert znacka.LOGO_URL in h and znacka.FACEBOOK in h and znacka.INSTAGRAM in h
    assert 'alt="PredTendrom.sk"' in h
    t = znacka.podpis_text()
    assert t.startswith("Marek Takáč") and znacka.FACEBOOK in t and znacka.INSTAGRAM in t


def test_osobny_email_nahradi_stary_podpis_a_escapuje():
    text, telo = znacka.osobny_email("Dobrý deň,\n\n<b>x</b> & y\n\nS pozdravom\nMarek Takáč\nPredTendrom.sk\n")
    assert text.count("Marek Takáč") == 1 and "&lt;b&gt;" in telo and "<b>x" not in telo
    assert re.findall(r'<img src="([^"]+)"', telo) == [znacka.LOGO_URL]


def test_osobny_email_ma_text_aj_html():
    predmet, text = p.nacitaj_sablonu("po_skuske")
    m = p.zostav(["a@b.sk"], [], predmet, text, None)
    typy = [c.get_content_type() for c in m.iter_parts()]
    assert typy == ["text/plain", "text/html"]
