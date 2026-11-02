"""Testy pre bez_sutaze.py (cista logika, bez databazy)."""
from datetime import date

import bez_sutaze as b

DNES = date(2026, 11, 2)


def z(id_, **k):
    d = {"id": id_, "type_id": 1, "sector": "STAVEBNE_PRACE", "price_total": 1_000_000,
         "signed_on": "2026-05-01", "subject": "Rekonštrukcia chodníkov Hlavná ulica",
         "authority_name": "Obec Test", "authority_cin": "00123456", "supplier_name": "Stavby s.r.o.",
         "supplier_cin": "36000001", "procurement_url": ""}
    d.update(k)
    return d


def test_bez_oznamenia_je_nalez():
    r = b.vyhodnot([z(1)], [], [], DNES)
    assert len(r) == 1 and r[0]["stav"] == "potvrdene" and r[0]["kategoria"] == "ostatne"


def test_par_ico_vo_vestniku_nie_je_nalez():
    v = [{"obstaravatel_ico": "123456", "vitaz_ico": "36 000 001", "nazov": "iné", "publikovane": "2025-01-01"}]
    assert b.vyhodnot([z(1)], v, [], DNES) == []


def test_podobny_nazov_vyzvy_nie_je_nalez():
    vy = [{"obstaravatel_ico": "00123456", "nazov": "Rekonštrukcia chodníkov na Hlavnej ulici",
           "publikovane": "2026-02-01"}]
    assert b.vyhodnot([z(1)], [], vy, DNES) == []


def test_vyzva_mimo_okna_sa_neratá():
    vy = [{"obstaravatel_ico": "00123456", "nazov": "Rekonštrukcia chodníkov Hlavná",
           "publikovane": "2023-01-01"}]
    assert len(b.vyhodnot([z(1)], [], vy, DNES)) == 1


def test_pod_limitom_dodatok_dotacia_sektorovy():
    assert b.vyhodnot([z(1, price_total=500_000)], [], [], DNES) == []          # stavba pod 600k
    assert len(b.vyhodnot([z(1, sector="UPRATOVANIE", price_total=300_000)], [], [], DNES)) == 1
    assert b.vyhodnot([z(1, subject="Dodatok č. 3 k zmluve")], [], [], DNES) == []
    assert b.vyhodnot([z(1, sector="DOTACIE_NFP")], [], [], DNES) == []
    assert b.vyhodnot([z(1, authority_name="Bratislavská vodárenská spoločnosť")], [], [], DNES) == []
    assert b.vyhodnot([z(1, procurement_url="https://www.uvo.gov.sk/x")], [], [], DNES) == []
    assert b.vyhodnot([z(1, supplier_name="Ministerstvo dopravy SR")], [], [], DNES) == []


def test_inhouse_predbezne_a_duplicita():
    r = b.vyhodnot([z(2, supplier_name="Technické služby mesta Test", signed_on="2026-10-20"),
                    z(3, supplier_name="Technické služby mesta Test", signed_on="2026-10-20")], [], [], DNES)
    assert r[0]["kategoria"] == "inhouse" and r[0]["stav"] == "predbezne"
    assert r[0]["duplicita_k"] is None and r[1]["duplicita_k"] == 2
    s = b.suhrn(r)
    assert s["zmluv"] == 1 and s["duplicit"] == 1 and s["inhouse"] == 1


HTML = """<table><thead><tr><th>Názov</th></tr></thead><tbody>
<tr><td><a href="/x/547453">Obecný úrad a kultúrny dom s. č. 42 - prestavba a prístavba</a></td><td>Obec Zemianske Sady</td><td></td><td></td><td>22.12.2025</td><td>EVO</td></tr>
<tr><td>Dodanie technológie pre zberný dvor</td><td>Obec Zemianske Sady</td></tr>
</tbody></table>"""


def test_evo_riadky_a_vysvetlenie():
    r = b.evo_riadky(HTML)
    assert r[0] == ("Obecný úrad a kultúrny dom s. č. 42 - prestavba a prístavba", "Obec Zemianske Sady")
    zz = z(9, authority_name="Obec Zemianske Sady", subject="Zmluva o dielo - Obecný úrad a kultúrny dom s. č. 42")
    assert b.evo_vysvetli(zz, r)
    assert not b.evo_vysvetli(z(9, authority_name="Obec Iná"), r)
    assert b.evo_dotazy(zz)[0] == "Zemianske Sady"


def test_over_evo_vyradi_najdene():
    class Odp:
        ok = True
        text = HTML
    class Sess:
        def get(self, *a, **k):
            return Odp()
    zz = z(9, authority_name="Obec Zemianske Sady", subject="Obecný úrad a kultúrny dom s. č. 42")
    zostava, n = b.over_evo([{"contract_id": 9}, {"contract_id": 1}], {9: zz, 1: z(1)}, Sess(), pauza=0)
    assert n == 1 and [r["contract_id"] for r in zostava] == [1]
