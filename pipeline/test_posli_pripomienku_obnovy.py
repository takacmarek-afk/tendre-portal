"""Testy pripomienky obnovy (bez siete). Spustenie: PYTHONPATH=pipeline python pipeline/test_posli_pripomienku_obnovy.py"""
import os, sys, types
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if "supabase" not in sys.modules:
    try:
        import supabase  # noqa: F401
    except ImportError:
        fake = types.ModuleType("supabase")
        fake.create_client = lambda *a, **k: None
        sys.modules["supabase"] = fake

import posli_pripomienku_obnovy as po


class _Rpc:
    def __init__(self, sb, n, p): self.sb, self.n, self.p = sb, n, p
    def execute(self):
        self.sb.volania.append((self.n, self.p))
        class R: pass
        r = R(); r.data = self.sb.riadky if self.n == "pripomienky_obnovy" else None
        return r


class _Sb:
    def __init__(self, riadky): self.riadky, self.volania = riadky, []
    def rpc(self, n, p): return _Rpc(self, n, p)


def _beh(riadky, vysledky, nasucho=False):
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


R = {"org_id": "o1", "email": "a@firma.sk", "plan": "growth", "obdobie_konci": "2026-11-06T10:00:00+00:00"}


def test_datum_a_text():
    assert po._datum_sk("2026-11-06T10:00:00+00:00") == "6. 11. 2026"
    o = po.obsah("growth", R["obdobie_konci"])
    assert "Growth" in o["uvod"] and "6. 11. 2026" in o["uvod"] and "neobnovuje automaticky" in o["uvod"]
    assert o["cta_url"].startswith("https://predtendrom.sk")


def test_poslanie_a_oznacenie():
    global sb
    sb = _Sb([R])
    kod, odoslane = _beh([R], [True])
    assert kod == 0 and len(odoslane) == 1 and odoslane[0][0] == "a@firma.sk"
    assert ("oznac_pripomienku_obnovy", {"p_org_id": "o1", "p_obdobie_konci": R["obdobie_konci"]}) in sb.volania


def test_vypadok_neoznaci():
    global sb
    sb = _Sb([R])
    kod, odoslane = _beh([R], [False])
    assert kod == 1 and not any(v[0] == "oznac_pripomienku_obnovy" for v in sb.volania)


def test_nasucho_neoznaci():
    global sb
    sb = _Sb([R])
    kod, _ = _beh([R], [True], nasucho=True)
    assert kod == 0 and not any(v[0] == "oznac_pripomienku_obnovy" for v in sb.volania)


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_") and callable(f):
            f(); print("OK", n)
