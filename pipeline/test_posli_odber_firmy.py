"""Testy prehladu konciacich zmluv pre firmy (bez siete). Spustenie: python pipeline/test_posli_odber_firmy.py"""
import os, sys, types
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if "supabase" not in sys.modules:
    try:
        import supabase  # noqa: F401
    except ImportError:
        fake = types.ModuleType("supabase")
        fake.create_client = lambda *a, **k: None
        sys.modules["supabase"] = fake

import posli_odber_firmy as pf

TOKEN = "123e4567-e89b-12d3-a456-426614174000"
D = {"celkom": 14, "zoznam": [
    {"urad": "Mesto Žilina", "predmet": "Upratovanie budov", "koniec": "2026-12-31", "cena": 120000,
     "odkaz": "https://www.crz.gov.sk/zmluva/123/"},
    {"urad": "Nemocnica <b>X</b>", "predmet": "Stráženie", "koniec": "2027-01-15", "cena": None,
     "odkaz": "https://evil.example/x"}]}
R = {"id": 7, "email": "a@firma.sk", "token": TOKEN, "sektor": "UPRATOVANIE", "kraj": "Žilinský kraj", "krok": 0}


class _Rpc:
    def __init__(self, sb, n, p): self.sb, self.n, self.p = sb, n, p
    def execute(self):
        self.sb.volania.append((self.n, self.p))
        if self.n == "odber_firmy_zmluvy" and self.sb.zlyha_zmluvy:
            raise RuntimeError("boom")
        class Res: pass
        r = Res()
        r.data = {"odber_firmy_na_odoslanie": self.sb.riadky, "odber_firmy_zmluvy": self.sb.zmluvy}.get(self.n)
        return r


class _Sb:
    def __init__(self, riadky, zmluvy=D, zlyha_zmluvy=False):
        self.riadky, self.zmluvy, self.zlyha_zmluvy, self.volania = riadky, zmluvy, zlyha_zmluvy, []
    def rpc(self, n, p): return _Rpc(self, n, p)


def _beh(riadky, vysledky, nasucho=False, zmluvy=D, zlyha_zmluvy=False):
    global sb
    sb = _Sb(riadky, zmluvy, zlyha_zmluvy)
    pf.PAUZA_S = 0
    pf.create_client = lambda *a, **k: sb
    os.environ.update(SUPABASE_URL="u", SUPABASE_SERVICE_ROLE_KEY="k", RESEND_API_KEY="r")
    it = iter(vysledky); odoslane = []
    orig = pf.posli
    def fake(kluc, komu, predmet, html, nas, text=None, odhlasit_url=None):
        odoslane.append((komu, predmet, html, text, odhlasit_url)); return next(it)
    pf.posli = fake
    try:
        kod = pf.main(["--nasucho"] if nasucho else [])
    finally:
        pf.posli = orig
    return kod, odoslane


def test_obsah_prvy_email():
    o = pf.obsah(1, R, D)
    assert "Žilinský kraj" in o["predmet"] and "14 zmlúv" in o["uvod"]
    assert o["bloky"][0]["titul"].endswith("31. 12. 2026")
    assert "120 000 €" in o["bloky"][0]["popis"]
    assert o["bloky"][0]["zvyraznene"].endswith("/zmluva/123/")
    # odkaz mimo crz.gov.sk sa nahradi domovskou strankou registra
    assert o["bloky"][1]["zvyraznene"].endswith("https://www.crz.gov.sk/")


def test_ziadna_predpoved_a_slub():
    for n in (1, 2, 3, 4, 5):
        o = pf.obsah(n, R, D)
        t = (o["predmet"] + o["titulok"] + o["uvod"] + " ".join(b["titul"] + b["popis"] for b in o["bloky"])).lower()
        for zle in ("garantuj", "vyhráte", "2 roky", "predpovedáme", "istá zákazka", "zaručujeme"):
            assert zle not in t, (n, zle)
        assert o["cta_url"].startswith("https://predtendrom.sk")
        assert "Odhlásiť" in o["odhlasenie"] or "zrušiť" in o["odhlasenie"]


def test_email_3_bez_zmluv_a_4_kroky():
    o = pf.obsah(3, R, None)
    assert len(o["bloky"]) == 4


def test_tyzdenny_bez_zmluv_sa_neposle():
    assert pf.obsah(5, R, {"celkom": 0, "zoznam": []}) is None
    assert pf.obsah(1, R, {"celkom": 0, "zoznam": []}) is not None


def test_odkaz_odhlasenia():
    assert pf.odkaz_odhlasenia(TOKEN) == f"https://predtendrom.sk/odber-firmy?t={TOKEN}&akcia=odhlasit"
    assert pf.odkaz_odhlasenia("x' or 1=1") is None and pf.odkaz_odhlasenia(None) is None


def test_poslanie_a_oznacenie():
    kod, odoslane = _beh([R], [True])
    assert kod == 0 and len(odoslane) == 1 and odoslane[0][0] == "a@firma.sk"
    assert odoslane[0][4].endswith("akcia=odhlasit") and "&lt;b&gt;" in odoslane[0][2]  # HTML sa escapuje
    assert ("odber_firmy_oznac", {"p_id": 7, "p_krok": 1}) in sb.volania
    assert ("odber_firmy_na_odoslanie", {"p_max": 40, "p_zaber": True}) in sb.volania


def test_krok_3_nevola_zmluvy():
    kod, odoslane = _beh([dict(R, krok=2)], [True])
    assert kod == 0 and not any(v[0] == "odber_firmy_zmluvy" for v in sb.volania)
    assert ("odber_firmy_oznac", {"p_id": 7, "p_krok": 3}) in sb.volania


def test_vypadok_neoznaci():
    kod, _ = _beh([R], [False])
    assert kod == 1 and not any(v[0] == "odber_firmy_oznac" for v in sb.volania)


def test_nasucho_nezabera_ani_neoznaci():
    kod, odoslane = _beh([R], [True], nasucho=True)
    assert kod == 0 and not any(v[0] == "odber_firmy_oznac" for v in sb.volania)
    assert ("odber_firmy_na_odoslanie", {"p_max": 40, "p_zaber": False}) in sb.volania


def test_neplatny_token_sa_preskoci():
    kod, odoslane = _beh([dict(R, token="zly")], [True])
    assert kod == 0 and odoslane == []


def test_tyzdenny_bez_zmluv_posunie_krok():
    kod, odoslane = _beh([dict(R, krok=4)], [], zmluvy={"celkom": 0, "zoznam": []})
    assert kod == 0 and odoslane == [] and ("odber_firmy_oznac", {"p_id": 7, "p_krok": 5}) in sb.volania


def test_vypadok_zmluv_neposle():
    kod, odoslane = _beh([R], [True], zlyha_zmluvy=True)
    assert kod == 1 and odoslane == []


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_") and callable(f):
            f(); print("OK", n)
