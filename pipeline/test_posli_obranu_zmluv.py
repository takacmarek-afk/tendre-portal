"""Testy upozornenia na koniec zmluvy sledovanej firmy (bez siete).
Spustenie: python pipeline/test_posli_obranu_zmluv.py"""
import os, sys, types
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if "supabase" not in sys.modules:
    try:
        import supabase  # noqa: F401
    except ImportError:
        fake = types.ModuleType("supabase")
        fake.create_client = lambda *a, **k: None
        sys.modules["supabase"] = fake

import posli_obranu_zmluv as po


class _Rpc:
    def __init__(self, sb, n, p): self.sb, self.n, self.p = sb, n, p
    def execute(self):
        self.sb.volania.append((self.n, self.p))
        class R: pass
        r = R(); r.data = self.sb.riadky if self.n == "obrana_nove_vyzvy" else None
        return r


class _Sb:
    def __init__(self, riadky): self.riadky, self.volania = riadky, []
    def rpc(self, n, p): return _Rpc(self, n, p)


def _beh(riadky, vysledky, nasucho=False):
    global sb
    sb = _Sb(riadky)
    po.PAUZA_S = 0
    po.create_client = lambda *a, **k: sb
    os.environ.update(SUPABASE_URL="u", SUPABASE_SERVICE_ROLE_KEY="k", RESEND_API_KEY="r")
    it = iter(vysledky); odoslane = []
    orig = po.posli
    po.posli = lambda kluc, komu, predmet, html, nas, *a, **k: (odoslane.append((komu, predmet, html)), next(it))[1]
    try:
        kod = po.main(["--nasucho"] if nasucho else [])
    finally:
        po.posli = orig
    return kod, odoslane


def riadok(cid, vid=7, email="a@firma.sk", org="o1", koniec="2026-12-15"):
    return {"org_id": org, "email": email, "contract_id": cid, "vyzva_id": vid,
            "authority_name": "Urad A", "subject": "Upratovanie", "effective_to": koniec,
            "price_total": 40000, "sektor": "UPRATOVANIE", "odhad_vyhlasenia": "2027-01-10",
            "pocet_ponuk_naposledy": 4, "vyzva_nazov": "Upratovacie sluzby 2027",
            "vyzva_lehota": "2026-11-01T10:00:00+00:00", "vyzva_url": "https://example.org"}


def test_obsah_jedna():
    o = po.obsah([riadok(1)])
    assert o["titulok"] == "Úrad vyhlásil súťaž k vašej zmluve"
    z = o["bloky"][0]["zvyraznene"]
    assert "15. 12. 2026" in z and "10. 1. 2027" in z and "4 ponuky" in z
    assert "istotu nemáme" in o["uvod"] and o["cta_url"].startswith("https://predtendrom.sk")


def test_ponuky_sklonovanie():
    assert "1 ponuka" in po._ponuky(1) and "4 ponuky" in po._ponuky(4) and "7 ponúk" in po._ponuky(7)
    assert po._ponuky(None) == ""


def test_obsah_viac_a_dalsie():
    o = po.obsah([riadok(1), riadok(2)], dalsie=3)
    assert "(5)" in o["titulok"] and o["bloky"][-1]["titul"] == "+ 3 ďalších zmlúv"


def test_jeden_email_na_org_a_oznacenie():
    rows = [riadok(1), riadok(2), riadok(1, email="b@firma.sk"), riadok(2, email="b@firma.sk")]
    kod, odoslane = _beh(rows, [True, True])
    assert kod == 0 and sorted(x[0] for x in odoslane) == ["a@firma.sk", "b@firma.sk"]
    v = [x for x in sb.volania if x[0] == "oznac_obrana_alerty"]
    assert len(v) == 1 and sorted(v[0][1]["p_contract_ids"]) == [1, 2] and v[0][1]["p_vyzva_ids"] == [7, 7]


def test_limit_10():
    rows = [riadok(i, koniec=f"2026-12-{i:02d}") for i in range(1, 13)]
    kod, odoslane = _beh(rows, [True])
    v = [x for x in sb.volania if x[0] == "oznac_obrana_alerty"][0]
    assert len(v[1]["p_contract_ids"]) == 10 and "+ 2 ďalších" in odoslane[0][2]


def test_vypadok_neoznaci():
    kod, _ = _beh([riadok(1)], [False])
    assert kod == 1 and not any(x[0] == "oznac_obrana_alerty" for x in sb.volania)


def test_nasucho_neoznaci():
    kod, _ = _beh([riadok(1)], [True], nasucho=True)
    assert kod == 0 and not any(x[0] == "oznac_obrana_alerty" for x in sb.volania)


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_") and callable(f):
            f(); print("OK", n)
