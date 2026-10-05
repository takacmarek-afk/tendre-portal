"""Testy pre posli_potvrdenie_odberu.py (double opt-in pre odber_obce, V1).

Bez siete a bez skutocnej DB: falosna tabulka, ktora naozaj aplikuje filtre
(eq / is_ / gte / order / limit), takze sa overuje VYBER riadkov, nie len
zavolanie. Spustenie: python test_posli_potvrdenie_odberu.py  (alebo pytest pipeline/)
"""
import sys, os, types
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if "supabase" not in sys.modules:
    try:
        import supabase  # noqa: F401
    except ImportError:
        fake = types.ModuleType("supabase")
        fake.create_client = lambda *a, **k: None
        sys.modules["supabase"] = fake

from datetime import datetime, timedelta, timezone

import posli_potvrdenie_odberu as pp

TERAZ = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)
TOKEN_A = "11111111-1111-4111-8111-111111111111"
TOKEN_B = "22222222-2222-4222-8222-222222222222"


def pred(dni):
    return (TERAZ - timedelta(days=dni)).isoformat()


class _Odpoved:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, tab, riadky):
        self._tab = tab
        self._data = list(riadky)
        self._patch = None
        self._ciel = None

    def select(self, *a, **k):
        return self

    def eq(self, col, val):
        if self._patch is not None:
            self._ciel = (col, val)
        else:
            self._data = [r for r in self._data if r.get(col) == val]
        return self

    def is_(self, col, val):
        if val == "null":
            self._data = [r for r in self._data if r.get(col) is None]
        return self

    def gte(self, col, val):
        self._data = [r for r in self._data if r.get(col) is not None and r[col] >= val]
        return self

    def order(self, col, desc=False):
        self._data.sort(key=lambda r: r[col], reverse=desc)
        return self

    def limit(self, n):
        self._data = self._data[:n]
        return self

    def update(self, patch):
        self._patch = patch
        return self

    def execute(self):
        if self._patch is not None:
            col, val = self._ciel
            for r in self._tab:
                if r.get(col) == val:
                    r.update(self._patch)
            return _Odpoved([])
        return _Odpoved(self._data)


class _Sb:
    def __init__(self, riadky):
        self.riadky = riadky

    def table(self, nazov):
        assert nazov == "odber_obce"
        return _Query(self.riadky, self.riadky)


def _riadok(i, email, token, **kw):
    r = {"id": i, "email": email, "token": token, "potvrdeny": False,
         "potvrdzovaci_email_at": None, "created_at": pred(1)}
    r.update(kw)
    return r


def _bez_spanku():
    pp.PAUZA_S = 0


# ── vyber riadkov ─────────────────────────────────────────────────────────

def test_vyber_len_nepotvrdene_bez_emailu_a_cerstve():
    _bez_spanku()
    sb = _Sb([
        _riadok(1, "ok@obec.sk", TOKEN_A),
        _riadok(2, "uz@obec.sk", TOKEN_B, potvrdzovaci_email_at=pred(1)),
        _riadok(3, "potvrdeny@obec.sk", TOKEN_B, potvrdeny=True),
        _riadok(4, "stary@obec.sk", TOKEN_B, created_at=pred(4)),
    ])
    vybrane = pp.vyber_riadky(sb, TERAZ)
    assert [r["id"] for r in vybrane] == [1]


def test_vyber_ma_limit_200():
    sb = _Sb([_riadok(i, f"a{i}@obec.sk", TOKEN_A) for i in range(250)])
    assert len(pp.vyber_riadky(sb, TERAZ)) == 200
    assert pp.MAX_NA_BEH == 200


# ── odkaz a obsah ─────────────────────────────────────────────────────────

def test_odkaz_ma_token_a_akciu_potvrdit():
    assert pp._odkaz(TOKEN_A) == f"https://predtendrom.sk/odber-obce?t={TOKEN_A}&akcia=potvrdit"
    assert pp._odkaz(None) is None


def test_obsah_html_a_text_maju_odkaz_a_diakritiku():
    odkaz = pp._odkaz(TOKEN_A)
    obsah = pp._obsah(odkaz)
    assert obsah["cta_url"] == odkaz
    assert "pravdepodobne Vy" in obsah["uvod"]
    assert "nič nerobte" in obsah["odhlasenie"]
    text = pp._text(odkaz)
    assert f"potvrďte odber: {odkaz}" in text
    assert "nič nerobte" in text
    assert pp.PREDMET == "Potvrďte odber prehľadov pre obce — PredTendrom.sk"


# ── posielanie ────────────────────────────────────────────────────────────

def test_po_uspechu_nastavi_potvrdzovaci_email_at():
    _bez_spanku()
    riadky = [_riadok(1, "ok@obec.sk", TOKEN_A)]
    poslane = []

    def falosne_posli(kluc, komu, predmet, html, nasucho, text=None):
        poslane.append((komu, predmet, html, text))
        return True

    orig = pp.posli
    pp.posli = falosne_posli
    try:
        p, z, s = pp.posli_potvrdenia(_Sb(riadky), "kluc", False, teraz=TERAZ)
    finally:
        pp.posli = orig
    assert (p, z, s) == (1, 0, 0)
    assert riadky[0]["potvrdzovaci_email_at"] is not None
    komu, predmet, html, text = poslane[0]
    assert komu == "ok@obec.sk"
    assert predmet == pp.PREDMET
    assert f"odber-obce?t={TOKEN_A}&amp;akcia=potvrdit" in html or \
        f"odber-obce?t={TOKEN_A}&akcia=potvrdit" in html
    assert f"?t={TOKEN_A}&akcia=potvrdit" in text


def test_pri_chybe_odoslania_riadok_neoznaci():
    _bez_spanku()
    riadky = [_riadok(1, "chyba@obec.sk", TOKEN_A)]
    orig = pp.posli
    pp.posli = lambda *a, **k: False
    try:
        p, z, s = pp.posli_potvrdenia(_Sb(riadky), "kluc", False, teraz=TERAZ)
    finally:
        pp.posli = orig
    assert (p, z, s) == (0, 1, 0)
    assert riadky[0]["potvrdzovaci_email_at"] is None
    # pri dalsom behu sa vyberie znova
    assert len(pp.vyber_riadky(_Sb(riadky), TERAZ)) == 1


def test_nasucho_nic_nezapise():
    _bez_spanku()
    riadky = [_riadok(1, "ok@obec.sk", TOKEN_A)]
    orig = pp.posli
    pp.posli = lambda *a, **k: True
    try:
        p, z, s = pp.posli_potvrdenia(_Sb(riadky), None, True, teraz=TERAZ)
    finally:
        pp.posli = orig
    assert p == 1
    assert riadky[0]["potvrdzovaci_email_at"] is None


def test_riadok_bez_tokenu_alebo_s_zlym_emailom_sa_preskoci():
    _bez_spanku()
    riadky = [_riadok(1, "ok@obec.sk", None), _riadok(2, "zle", TOKEN_B)]
    volania = []
    orig = pp.posli
    pp.posli = lambda *a, **k: volania.append(a) or True
    try:
        p, z, s = pp.posli_potvrdenia(_Sb(riadky), "kluc", False, teraz=TERAZ)
    finally:
        pp.posli = orig
    assert (p, z, s) == (0, 0, 2)
    assert volania == []


if __name__ == "__main__":
    testy = [f for n, f in list(globals().items())
             if n.startswith("test_") and callable(f)]
    for f in testy:
        f()
        print(f"{f.__name__}: OK")
    print(f"VSETKY TESTY PRESLI ({len(testy)})")
