"""Testy tyzdenneho bezplatneho e-mailu (bez siete). Spustenie: python pipeline/test_posli_bezplatny_email.py"""
import os, sys, types
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if "supabase" not in sys.modules:
    try:
        import supabase  # noqa: F401
    except ImportError:
        fake = types.ModuleType("supabase")
        fake.create_client = lambda *a, **k: None
        sys.modules["supabase"] = fake

import posli_bezplatny_email as pb


class _Rpc:
    def __init__(self, sb, n, p): self.sb, self.n, self.p = sb, n, p
    def execute(self):
        self.sb.volania.append((self.n, self.p))
        class R: pass
        r = R(); r.data = self.sb.riadky if self.n == "bezplatne_emaily" else None
        return r


class _Sb:
    def __init__(self, riadky): self.riadky, self.volania = riadky, []
    def rpc(self, n, p): return _Rpc(self, n, p)


def _beh(riadky, vysledky, nasucho=False):
    global sb
    sb = _Sb(riadky)
    pb.PAUZA_S = 0
    pb.create_client = lambda *a, **k: sb
    os.environ.update(SUPABASE_URL="u", SUPABASE_SERVICE_ROLE_KEY="k", RESEND_API_KEY="r")
    it = iter(vysledky); odoslane = []
    orig = pb.posli
    pb.posli = lambda kluc, komu, predmet, html, nas, *a, **k: (odoslane.append((komu, predmet, html)), next(it))[1]
    try:
        kod = pb.main(["--nasucho"] if nasucho else [])
    finally:
        pb.posli = orig
    return kod, odoslane


OBSAH = {"nastavene": True, "kraj": "Bratislavský kraj", "sektor": "UPRATOVANIE",
         "pocet_zmluv": 79, "pocet_dotacii": 3, "dalsie_v_kraji": 120,
         "ukazky": [{"obstaravatel": "Univerzitná nemocnica", "predmet": "Upratovacie služby", "koniec": "2026-11"}]}
R = {"org_id": "o1", "email": "a@firma.sk", "obsah": OBSAH}


def test_text_bez_sum_a_dodavatelov():
    o = pb.obsah(OBSAH)
    t = o["uvod"] + " ".join(b["titul"] + b["popis"] for b in o["bloky"])
    assert "79 zmlúv" in o["uvod"] and "3 dotácie" in o["uvod"] and "120" in o["uvod"]
    assert "11/2026" in t and "Univerzitná nemocnica" in t
    assert "€ " not in o["bloky"][0]["popis"]
    assert o["cta_url"].startswith("https://predtendrom.sk") and "Stop" in o["odhlasenie"]


def test_bez_nastaveni():
    o = pb.obsah({"nastavene": False, "pocet_zmluv": 1000, "pocet_dotacii": 5, "ukazky": []})
    assert "Na Slovensku" in o["uvod"] and o["bloky"] == []


def test_poslanie_a_oznacenie():
    kod, odoslane = _beh([R], [True])
    assert kod == 0 and len(odoslane) == 1 and odoslane[0][0] == "a@firma.sk"
    assert ("oznac_bezplatny_email", {"p_org_id": "o1"}) in sb.volania


def test_vypadok_neoznaci():
    kod, _ = _beh([R], [False])
    assert kod == 1 and not any(v[0] == "oznac_bezplatny_email" for v in sb.volania)


def test_nasucho_neoznaci():
    kod, _ = _beh([R], [True], nasucho=True)
    assert kod == 0 and not any(v[0] == "oznac_bezplatny_email" for v in sb.volania)


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_") and callable(f):
            f(); print("OK", n)
