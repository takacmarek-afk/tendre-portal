import os
import tempfile

import generuj_obstaravatelia_podstranky as g


def _o(ico, k12=0, ep=0, kraj="Košický kraj", nazov="Mesto Košice"):
    return {"ico": ico, "nazov": nazov, "kraj": kraj, "konci12": k12, "objem12": 1e6 * k12,
            "ukazky": [{"predmet": f"Upratovanie {i}", "mesiac": "2027-03", "cena": 1e5} for i in range(min(k12, 3))],
            "eurofondy_pocet": ep, "eurofondy_objem": 2e6 if ep else None,
            "eurofondy": [{"nazov": "Rekonštrukcia školy", "hodnota": 2e6}] if ep else []}


def test_prah_a_cesta():
    assert g.ma_stranku(_o("00691135", k12=2, ep=1))
    assert not g.ma_stranku(_o("00691135", k12=2))
    assert not g.ma_stranku(_o("00691135", k12=9, kraj="Neznámy"))
    assert g.cesta(_o("00691135")) == "obstaravatelia/kosicky/mesto-kosice-00691135"


def test_vygeneruj_bez_dodavatela():
    with tempfile.TemporaryDirectory() as d:
        psane = g.vygeneruj([_o("00691135", k12=5, ep=1), _o("11111111", k12=1, nazov="Obec Malá")],
                            vystup_dir=os.path.join(d, "o"), sitemap=os.path.join(d, "s.xml"),
                            robots=os.path.join(d, "r.txt"), dnes="1. 1. 2027")
        assert len(psane) == 1
        t = open(psane[0], encoding="utf-8").read()
        assert "Mesto Košice: končiace zmluvy a pripravované obstarávania" in t
        assert "+ 2 ďalšie zmluvy v aplikácii" in t and "Rekonštrukcia školy" in t
        assert 'href="https://predtendrom.sk/obstaravatelia/kosicky/mesto-kosice-00691135"' in t
        assert "{" not in t.split("<script>")[0]
        idx = open(os.path.join(d, "o", "kosicky", "index.html"), encoding="utf-8").read()
        assert "Obec Malá" not in idx and "v košickom kraji" in idx
        assert "/obstaravatelia/kosicky/mesto-kosice-00691135" in open(os.path.join(d, "s.xml"), encoding="utf-8").read()
