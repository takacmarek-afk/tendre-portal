import os

import generuj_eurofondy_podstranky as g


def _r(i, sektor="STAVEBNE_PRACE", kraj="Košický kraj", h=100000):
    return {"id": i, "sektor": sektor, "kraj": kraj, "nazov": f"Rekonštrukcia školy {i}",
            "obstaravatel_nazov": f"Obec {i % 3}", "predpokladana_hodnota": h * i}


def test_agregat_a_len_5_prikladov(tmp_path):
    riadky = [_r(i) for i in range(1, 9)] + [_r(99, sektor="INE"), _r(98, kraj=None)]
    agr = g.agreguj(riadky)
    a = agr[("STAVEBNE_PRACE", "Košický kraj")]
    assert list(agr) == [("STAVEBNE_PRACE", "Košický kraj")]
    assert a["pocet"] == 8 and a["uradov"] == 3 and len(a["priklady"]) == 5
    assert a["priklady"][0]["hodnota"] == 800000
    rob = tmp_path / "robots.txt"; rob.write_text("User-agent: *\n")
    g.vygeneruj(agr, str(tmp_path / "eurofondy"), str(tmp_path / "s.xml"), str(rob))
    html = (tmp_path / "eurofondy" / "stavebne-prace" / "kosicky.html").read_text()
    assert "Rekonštrukcia školy 8" in html and "Rekonštrukcia školy 3" not in html   # 6.-8. riadok nie je v HTML
    assert "+ 3 ďalšie obstarávania" in html and "index,follow" in html
    assert "https://predtendrom.sk/eurofondy/stavebne-prace/kosicky" in html
    assert "/eurofondy/stavebne-prace/kosicky" in (tmp_path / "s.xml").read_text()
    assert "sitemap-eurofondy.xml" in rob.read_text()


def test_malo_obstaravani_noindex(tmp_path):
    agr = g.agreguj([_r(1), _r(2)])
    rob = tmp_path / "r.txt"; rob.write_text("")
    g.vygeneruj(agr, str(tmp_path / "e"), str(tmp_path / "s.xml"), str(rob))
    assert "noindex" in (tmp_path / "e" / "stavebne-prace" / "kosicky.html").read_text()
    assert "kosicky" not in (tmp_path / "s.xml").read_text()


def test_escapuje_nazov():
    agr = g.agreguj([dict(_r(1), nazov="<script>x</script>")])
    html = g._stranka("STAVEBNE_PRACE", "Košický kraj", agr[("STAVEBNE_PRACE", "Košický kraj")], set(agr))
    assert "<script>x" not in html and "&lt;script&gt;" in html


def test_stara_stranka_sa_zmaze(tmp_path):
    rob = tmp_path / "r.txt"; rob.write_text("")
    stara = tmp_path / "e" / "odpad"; stara.mkdir(parents=True); (stara / "kosicky.html").write_text("x")
    g.vygeneruj(g.agreguj([_r(1)]), str(tmp_path / "e"), str(tmp_path / "s.xml"), str(rob))
    assert not (stara / "kosicky.html").exists()
    assert (tmp_path / "e" / "stavebne-prace" / "kosicky.html").exists()


def test_prehlad_odboru_bez_404(tmp_path):
    riadky = [_r(i) for i in range(1, 9)] + [_r(i, kraj="Prešovský kraj") for i in range(20, 23)]
    agr = g.agreguj(riadky)
    rob = tmp_path / "robots.txt"; rob.write_text("")
    g.vygeneruj(agr, str(tmp_path / "e"), str(tmp_path / "s.xml"), str(rob))
    html = (tmp_path / "e" / "stavebne-prace" / "index.html").read_text()
    assert 'href="/eurofondy/stavebne-prace/kosicky"' in html and 'href="/eurofondy/stavebne-prace/presovsky"' in html
    assert "Rekonštrukcia školy 22" in html                    # najvacsie priklady naprieč krajmi
    assert "https://predtendrom.sk/eurofondy/stavebne-prace/" in html
    assert "/eurofondy/stavebne-prace/</loc>" in (tmp_path / "s.xml").read_text()
    assert 'href="/eurofondy/stavebne-prace/"' in (tmp_path / "e" / "index.html").read_text()


def test_suhrn_json(tmp_path):
    import json
    riadky = [_r(i) for i in range(1, 9)] + [_r(i, kraj="Prešovský kraj", h=10) for i in range(20, 23)]
    agr = g.agreguj(riadky)
    rob = tmp_path / "robots.txt"; rob.write_text("")
    g.vygeneruj(agr, str(tmp_path / "e"), str(tmp_path / "s.xml"), str(rob))
    d = json.loads((tmp_path / "e" / "suhrn.json").read_text())
    assert d["pocet"] == 11
    sp = d["sektory"]["STAVEBNE_PRACE"]
    assert sp["slug"] == "stavebne-prace" and sp["pocet"] == 11
    assert sp["kraje"]["Košický kraj"]["slug"] == "kosicky" and len(sp["kraje"]["Košický kraj"]["priklady"]) == 3
    assert d["najvacsie"]["hodnota"] == 800000 and d["najvacsie"]["kraj"] == "Košický kraj"
