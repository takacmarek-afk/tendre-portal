"""Test sablon SEO podstranok (generuj_zmluvy_podstranky.py, generuj_obce_podstranky.py).

Overuje (audit 5.10.2026, C5 + U25): sklonovanie poctu v meta description,
vynechanie vety "spolu" ked chyba suma, canonical/odkazy/sitemap BEZ .html
a slovensky format datumu.

Spustenie:  python test_generuj_podstranky.py
"""
import os
import re
import tempfile

import generuj_obce_podstranky as obce
import generuj_zmluvy_podstranky as zmluvy


def agregat(pocet, objem, teaser=()):
    return {"kraj": "Trenčiansky kraj", "pocet": pocet, "objem_eur": objem,
            "najblizsi_koniec": None, "teaser": list(teaser)}


SEK = zmluvy.SEKTORY_SEO["OSTRAHA"]

# 1. Meta description: sklonovanie, chybajuca suma, nula
p1 = zmluvy._popis_stranky(agregat(1, None), SEK, "trenčianskom")
assert p1.startswith("1 zmluva na ostrahu v trenčianskom kraji sa blíži ku koncu."), p1
assert "—" not in p1.split("Prehľad,")[0] and "spolu" not in p1, p1
p2 = zmluvy._popis_stranky(agregat(2, 247697.0), SEK, "košickom")
assert p2.startswith("2 zmluvy na ostrahu v košickom kraji sa blížia ku koncu, spolu 247 697 €."), p2
p5 = zmluvy._popis_stranky(agregat(5, 636267.0), SEK, "žilinskom")
assert p5.startswith("5 zmlúv na ostrahu v žilinskom kraji sa blíži ku koncu, spolu 636 267 €."), p5
p0 = zmluvy._popis_stranky(agregat(0, None), SEK, "nitrianskom")
assert p0.startswith("V nitrianskom kraji sa momentálne neblíži ku koncu žiadna zmluva"), p0
print("OK: meta description (1 / 2-4 / 5+ / 0, chybajuca suma)")

# 2. Datum a tvary
assert obce._datum("2026-09-23") == "23. 9. 2026"
assert obce._tvar(1, "a", "b", "c") == "a" and obce._tvar(3, "a", "b", "c") == "b"
assert obce._tvar(0, "a", "b", "c") == "c" and obce._tvar(11, "a", "b", "c") == "c"
print("OK: datum a tvar")

# 3. Cela stranka: "+ N dalsich", CTA, canonical bez .html, absolutne odkazy
teaser = [{"authority_name": "Škola <b>x</b>", "price_total": None, "mesiac_konca": "auguste 2027"}] * 3
for pocet, ocakavane in ((4, "ďalšia zmluva"), (5, "ďalšie zmluvy"), (9, "ďalších zmlúv")):
    h = zmluvy._vygeneruj_stranku("OSTRAHA", agregat(pocet, 1000.0, teaser))
    assert f"+ {pocet - 3} {ocakavane}" in h, (pocet, ocakavane)
    assert "Zobraziť všetky (14 dní zadarmo, bez karty)" in h
    assert 'href="https://predtendrom.sk/konciace-zmluvy/ostraha/trenciansky"' in h
    assert 'og:url" content="https://predtendrom.sk/konciace-zmluvy/ostraha/trenciansky"' in h
    assert ".html" not in re.sub(r"consent-analytics\.js|config\.js", "", h)
    assert "&lt;b&gt;" in h and "<b>x</b>" not in h  # escapovanie hodnot z DB
print("OK: stranka (skloňovanie '+ N dalsich', CTA, canonical, escapovanie)")

# 4. Index a sitemap
with tempfile.TemporaryDirectory() as tmp:
    zmluvy.SITEMAP_CESTA = os.path.join(tmp, "sitemap-zmluvy.xml")
    zmluvy._zapis_sitemap([("ostraha", "trenciansky")])
    xml = open(zmluvy.SITEMAP_CESTA, encoding="utf-8").read()
    assert ".html" not in xml
    assert "https://predtendrom.sk/konciace-zmluvy/ostraha/</loc>" in xml
    assert "https://predtendrom.sk/konciace-zmluvy/ostraha/trenciansky</loc>" in xml
    os.makedirs(os.path.join(tmp, "obce"))
    obce._zapis_sitemap([{"kraj": "Košický kraj"}], os.path.join(tmp, "obce"))
    xml = open(os.path.join(tmp, "sitemap.xml"), encoding="utf-8").read()
    assert ".html" not in xml and "trh" not in xml
    assert "https://predtendrom.sk/</loc>" in xml and "https://predtendrom.sk/obce/kraj-kosicky</loc>" in xml
print("OK: sitemap bez .html, bez trh")

# 5. Rozsirenie sektorov (5.10.2026): slugy, nadpisy, velke pismeno v title
assert {v["slug"] for v in zmluvy.SEKTORY_SEO.values()} == {
    "upratovanie", "stravovanie", "ostraha", "stavebne-prace", "it-technika"}
for kluc, titul, slug in (("IT_TECHNIKA", "Končiace zmluvy — IT služby a výpočtová technika v trenčianskom kraji | PredTendrom.sk", "it-technika"),
                          ("STAVEBNE_PRACE", "Končiace zmluvy — Stavebné práce v trenčianskom kraji | PredTendrom.sk", "stavebne-prace")):
    h = zmluvy._vygeneruj_stranku(kluc, agregat(7, 50000.0, teaser))
    assert f"<title>{titul}</title>" in h, (kluc, re.search(r"<title>.*?</title>", h).group(0))
    assert f'href="https://predtendrom.sk/konciace-zmluvy/{slug}/trenciansky"' in h
    assert "It služby" not in h
print("OK: nove sektory (title, canonical)")

print("\nVSETKY TESTY PRESLI\n")
