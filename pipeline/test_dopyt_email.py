"""Testy pre posli_dopyt_email.py (notifikacie pri dopytoch, 28.9.2026).

Testuje len ciste funkcie a filtrovaciu logiku (bez skutocnej DB/Resend) —
rovnaky princip ako ostatne male testy v pipeline (test_konkurencia.py,
test_obce.py): overit logiku, nie infrastrukturu okolo nej.
Spustenie: python test_dopyt_email.py  (alebo pytest pipeline/)
"""
from posli_dopyt_email import (
    _platny_email,
    _obsah_pre_poradcu,
    _obsah_pre_obec,
    _poradcovia_pre_dopyt,
)


# ── _platny_email ────────────────────────────────────────────────────────

def test_platny_email():
    dobre = ["a@b.sk", "starosta.sena@obec.sk", "x.y+z@firma.co"]
    zle = ["", None, "nieco", "a@b", "a b@c.sk", "@b.sk"]
    for e in dobre:
        assert _platny_email(e), f"malo prejst: {e!r}"
    for e in zle:
        assert not _platny_email(e), f"nemalo prejst: {e!r}"


# ── _obsah_pre_poradcu ──────────────────────────────────────────────────

def test_obsah_pre_poradcu_typy():
    for typ, ocakavany_text in [("zmluva", "Koncici sa zmluva"),
                                 ("dotacia", "Dotacia"),
                                 ("ine", "Ine"),
                                 (None, "Vseobecny dopyt"),
                                 ("neznamy", "Vseobecny dopyt")]:
        d = {"obec_nazov": "Seňa", "kraj": "Košický kraj", "typ": typ,
             "nazov": "Potrebujeme poradcu", "popis": "test"}
        obsah = _obsah_pre_poradcu(d)
        assert obsah["bloky"][0]["zvyraznene"] == ocakavany_text
        assert "Seňa" in obsah["titulok"]
        assert obsah["cta_url"] == "https://predtendrom.sk/trh.html"


def test_obsah_pre_poradcu_bez_kraja():
    d = {"obec_nazov": "Testovacia obec", "kraj": None, "typ": "ine",
         "nazov": "X", "popis": None}
    obsah = _obsah_pre_poradcu(d)
    assert "kraj neuvedeny" in obsah["uvod"]


# ── _obsah_pre_obec ─────────────────────────────────────────────────────

def test_obsah_pre_obec_orezanie_spravy():
    poradca = {"nazov": "Poradca s.r.o.", "kontakt_email": "p@firma.sk",
               "kontakt_telefon": "0900123456"}
    dlha_sprava = "a" * 1000
    obsah = _obsah_pre_obec("Môj dopyt", poradca, dlha_sprava)
    assert len(obsah["bloky"][0]["popis"]) == 400
    assert "p@firma.sk" in obsah["bloky"][0]["zvyraznene"]
    assert "0900123456" in obsah["bloky"][0]["zvyraznene"]
    assert "Môj dopyt" in obsah["uvod"]


def test_obsah_pre_obec_bez_kontaktov():
    poradca = {"nazov": "Poradca"}
    obsah = _obsah_pre_obec("Dopyt", poradca, "sprava")
    assert obsah["bloky"][0]["zvyraznene"] is None


# ── _poradcovia_pre_dopyt (kraj filter) ──────────────────────────────────

class _FakeQuery:
    def __init__(self, data):
        self._data = data

    def select(self, *a, **kw):
        return self

    def eq(self, *a, **kw):
        return self

    def execute(self):
        class R:
            pass
        r = R()
        r.data = self._data
        return r


class _FakeSb:
    def __init__(self, poradcovia):
        self._poradcovia = poradcovia

    def table(self, name):
        assert name == "poradcovia_profily"
        return _FakeQuery(self._poradcovia)


def test_poradcovia_pre_dopyt_filtruje_podla_kraja():
    poradcovia = [
        {"kontakt_email": "vsade@f.sk", "nazov": "Vsade", "kraje_posobenia": []},
        {"kontakt_email": "kosice@f.sk", "nazov": "Kosicky", "kraje_posobenia": ["Košický kraj"]},
        {"kontakt_email": "zilina@f.sk", "nazov": "Zilinsky", "kraje_posobenia": ["Žilinský kraj"]},
    ]
    sb = _FakeSb(poradcovia)

    vybrani = _poradcovia_pre_dopyt(sb, {"kraj": "Košický kraj"})
    emaily = {p["kontakt_email"] for p in vybrani}
    assert emaily == {"vsade@f.sk", "kosice@f.sk"}

    vsetci = _poradcovia_pre_dopyt(sb, {"kraj": None})
    assert len(vsetci) == 3


if __name__ == "__main__":
    for meno, f in list(globals().items()):
        if meno.startswith("test_") and callable(f):
            f()
            print("OK", meno)
