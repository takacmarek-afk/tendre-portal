"""Testy upozornenia na koniec zmluvy sledovanej firmy (bez siete).
Spustenie: python pipeline/test_posli_upozornenie_konkurent.py"""
import os, sys, types
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if "supabase" not in sys.modules:
    try:
        import supabase  # noqa: F401
    except ImportError:
        fake = types.ModuleType("supabase")
        fake.create_client = lambda *a, **k: None
        sys.modules["supabase"] = fake

import posli_upozornenie_konkurent as pk


class _Rpc:
    def __init__(self, sb, n, p): self.sb, self.n, self.p = sb, n, p
    def execute(self):
        self.sb.volania.append((self.n, self.p))
        class R: pass
        r = R(); r.data = self.sb.riadky if self.n == "sledovane_konciace_alerty" else None
        return r


class _Sb:
    def __init__(self, riadky): self.riadky, self.volania = riadky, []
    def rpc(self, n, p): return _Rpc(self, n, p)


def _beh(riadky, vysledky, nasucho=False):
    global sb
    sb = _Sb(riadky)
    pk.PAUZA_S = 0
    pk.create_client = lambda *a, **k: sb
    os.environ.update(SUPABASE_URL="u", SUPABASE_SERVICE_ROLE_KEY="k", RESEND_API_KEY="r")
    it = iter(vysledky); odoslane = []
    orig = pk.posli
    pk.posli = lambda kluc, komu, predmet, html, nas, *a, **k: (odoslane.append((komu, predmet, html)), next(it))[1]
    try:
        kod = pk.main(["--nasucho"] if nasucho else [])
    finally:
        pk.posli = orig
    return kod, odoslane


def riadok(cid, email="a@firma.sk", org="o1", ico="111", koniec="2026-12-15"):
    return {"org_id": org, "email": email, "ico": ico, "nazov_firmy": "Konkurent A", "contract_id": cid,
            "authority_name": "Urad 1", "subject": "Upratovanie", "effective_to": koniec,
            "price_total": 50000, "kraj": "KrajA", "odhad_vyhlasenia": "2027-02-01"}


def test_obsah_jedna_zmluva():
    o = pk.obsah([riadok(1)])
    assert "Konkurent A: končí zmluva" == o["titulok"]
    assert "15. 12. 2026" in o["bloky"][0]["titul"] and "1. 2. 2027" in o["bloky"][0]["zvyraznene"]
    assert o["cta_url"].startswith("https://predtendrom.sk")


def test_obsah_viac_zmluv_a_dalsie():
    o = pk.obsah([riadok(1), riadok(2)], dalsie=3)
    assert "(5)" in o["titulok"] and o["bloky"][-1]["titul"] == "+ 3 ďalších zmlúv"


def test_jeden_email_na_org_a_oznacenie():
    rows = [riadok(1), riadok(2), riadok(1, email="b@firma.sk"), riadok(2, email="b@firma.sk")]
    kod, odoslane = _beh(rows, [True, True])
    assert kod == 0 and sorted(x[0] for x in odoslane) == ["a@firma.sk", "b@firma.sk"]
    volanie = [v for v in sb.volania if v[0] == "oznac_sledovane_alerty"]
    assert len(volanie) == 1 and sorted(volanie[0][1]["p_contract_ids"]) == [1, 2]


def test_limit_10_v_emaili():
    rows = [riadok(i, koniec=f"2026-12-{i:02d}") for i in range(1, 13)]
    kod, odoslane = _beh(rows, [True])
    volanie = [v for v in sb.volania if v[0] == "oznac_sledovane_alerty"][0]
    assert len(volanie[1]["p_contract_ids"]) == 10 and "+ 2 ďalších" in odoslane[0][2]


def test_vypadok_neoznaci():
    kod, _ = _beh([riadok(1)], [False])
    assert kod == 1 and not any(v[0] == "oznac_sledovane_alerty" for v in sb.volania)


def test_nasucho_neoznaci():
    kod, _ = _beh([riadok(1)], [True], nasucho=True)
    assert kod == 0 and not any(v[0] == "oznac_sledovane_alerty" for v in sb.volania)


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_") and callable(f):
            f(); print("OK", n)
