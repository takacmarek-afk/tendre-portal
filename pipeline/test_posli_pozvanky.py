"""Testy pre posli_pozvanky.py — bez sietovych volani (RESEND_API_KEY sa tu
nepouziva, hoci --nasucho aj tak nikdy nevola siet)."""
import sys, os, types
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Rovnaky dovod ako v test_posli_email.py: supabase.create_client sa importuje
# na urovni modulu (aj v posli_email.py, ktory posli_pozvanky.py importuje),
# hoci ho tieto testy vobec nevolaju naozaj.
if "supabase" not in sys.modules:
    try:
        import supabase  # noqa: F401
    except ImportError:
        fake = types.ModuleType("supabase")
        fake.create_client = lambda *a, **k: None
        sys.modules["supabase"] = fake

from datetime import datetime, timedelta, timezone
import posli_pozvanky as pp

teraz = datetime.now(timezone.utc)


def o_hodin(h):
    return (teraz + timedelta(hours=h)).isoformat()


# ── _pozvanka_html() ─────────────────────────────────────────────────────

# 1) CTA odkaz musi viest na prihlasenie.html s tokenom v query, inak by
#    _obal() rovno vyhodil vynimku (kontroluje predtendrom.sk) — tu
#    overujeme, ze token sa naozaj prenesie, nie len ze prejde kontrola.
html = pp._pozvanka_html("Testovacia s.r.o.", "tok123abc")
print(f"1) token v odkaze -> {'pozvanka=tok123abc' in html}")
assert "https://predtendrom.sk/prihlasenie.html?pozvanka=tok123abc" in html
assert "Testovacia s.r.o." in html

# 2) Nazov firmy s HTML-nebezpecnymi znakmi sa escapuje (organizations.nazov
#    je pouzivatelsky vstup pri zalozeni firmy, nie dovereny CRZ text).
html2 = pp._pozvanka_html('Fi<rma> & "Synovia"', "tok")
print(f"2) escapovane -> {'&lt;rma&gt;' in html2 and '&amp;' in html2}")
assert "<rma>" not in html2
assert "&lt;rma&gt;" in html2
assert "&amp;" in html2

print("VSETKY TESTY PRESLI (_pozvanka_html)")


# ── main(): cely beh nad falosnou databazou ──────────────────────────────

class _FalosnaOdpoved:
    def __init__(self, data):
        self.data = data


class _FalosnyUpdate:
    def __init__(self, vsetky_riadky, patch):
        self._vsetky = vsetky_riadky
        self._patch = patch
        self._col = None
        self._val = None

    def eq(self, col, val):
        self._col, self._val = col, val
        return self

    def execute(self):
        for r in self._vsetky:
            if r.get(self._col) == self._val:
                r.update(self._patch)
        return _FalosnaOdpoved([])


class _FalosnaTabulka:
    def __init__(self, vsetky_riadky):
        self._vsetky = vsetky_riadky  # referencia — update() musi mutovat TOTO
        self._data = list(vsetky_riadky)

    def select(self, *a, **k):
        return self

    def eq(self, col, val):
        self._data = [r for r in self._data if r.get(col) == val]
        return self

    def is_(self, col, val):
        if val == "null":
            self._data = [r for r in self._data if r.get(col) is None]
        else:
            self._data = [r for r in self._data if r.get(col) is not None]
        return self

    def update(self, patch):
        return _FalosnyUpdate(self._vsetky, patch)

    def execute(self):
        return _FalosnaOdpoved(self._data)


class _FalosnySb:
    def __init__(self, invitations):
        self.tabulky = {"invitations": invitations}

    def table(self, nazov):
        return _FalosnaTabulka(self.tabulky[nazov])


def _spusti_main(argv, invitations, monkeypatch):
    """Nahradi create_client aj posli(), spusti main() a vrati (kod, invitations)."""
    sb = _FalosnySb(invitations)
    monkeypatch.setattr(pp, "create_client", lambda *a, **k: sb)
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "sluzobny-kluc")
    monkeypatch.setattr(sys, "argv", ["posli_pozvanky.py"] + argv)
    kod = pp.main()
    return kod, invitations


# Jednoduchy nahrada za pytest monkeypatch (tieto testy nebezia pod pytestom,
# rovnaky vzor ako zvysok pipeline — cisty skript, assert, ziadny framework).
class _Monkeypatch:
    def __init__(self):
        self._povodne = []

    def setattr(self, obj, meno, hodnota):
        self._povodne.append((obj, meno, getattr(obj, meno, None)))
        setattr(obj, meno, hodnota)

    def setenv(self, meno, hodnota):
        self._povodne.append((os.environ, meno, os.environ.get(meno)))
        os.environ[meno] = hodnota

    def vrat_spat(self):
        for obj, meno, hodnota in reversed(self._povodne):
            if obj is os.environ:
                if hodnota is None:
                    os.environ.pop(meno, None)
                else:
                    os.environ[meno] = hodnota
            else:
                setattr(obj, meno, hodnota)


# 3) Bezny beh: jedna platna cakajuca pozvanka, posli() ostava skutocna
#    funkcia (nasucho=True v args, takze ziadna siet) -> nic sa nezapise
#    (sent_at ostava None), lebo --nasucho nikdy nezapisuje do DB.
mp = _Monkeypatch()
riadky = [{
    "id": "inv-1", "org_id": "org-1", "email": "kolega@firma.sk",
    "token": "tok-1", "stav": "cakajuca", "expires_at": o_hodin(24 * 10), "sent_at": None,
    "organizations": {"nazov": "Firma s.r.o."},
}]
kod, riadky = _spusti_main(["--nasucho"], riadky, mp)
print(f"3) nasucho, 1 cakajuca -> kod={kod}, sent_at={riadky[0]['sent_at']}")
assert kod == 0
assert riadky[0]["sent_at"] is None  # nasucho nic nezapisuje
mp.vrat_spat()

# 4) Naostro (bez --nasucho): posli() sa nahradi falosnou funkciou, ktora
#    vzdy vrati True bez akejkolvek siete — overujeme, ze sa POTOM naozaj
#    zapise sent_at na spravny riadok.
mp = _Monkeypatch()
mp.setattr(pp, "posli", lambda kluc, komu, predmet, html, nasucho: True)
riadky = [{
    "id": "inv-2", "org_id": "org-1", "email": "novy@firma.sk",
    "token": "tok-2", "stav": "cakajuca", "expires_at": o_hodin(24 * 10), "sent_at": None,
    "organizations": {"nazov": "Firma s.r.o."},
}]
mp.setenv("RESEND_API_KEY", "test-kluc")
kod, riadky = _spusti_main([], riadky, mp)
print(f"4) naostro, posli()=True -> kod={kod}, sent_at={riadky[0]['sent_at']}")
assert kod == 0
assert riadky[0]["sent_at"] is not None
mp.vrat_spat()

# 5) Vyprsana pozvanka (expires_at v minulosti) sa NEPOSIELA a oznaci sa
#    ako 'vyprsana' — nie ako keby bola uspesne odoslana.
mp = _Monkeypatch()
volania = []
mp.setattr(pp, "posli", lambda kluc, komu, predmet, html, nasucho: volania.append(komu) or True)
riadky = [{
    "id": "inv-3", "org_id": "org-1", "email": "neskoro@firma.sk",
    "token": "tok-3", "stav": "cakajuca", "expires_at": o_hodin(-1), "sent_at": None,
    "organizations": {"nazov": "Firma s.r.o."},
}]
mp.setenv("RESEND_API_KEY", "test-kluc")
kod, riadky = _spusti_main([], riadky, mp)
print(f"5) vyprsana -> kod={kod}, stav={riadky[0]['stav']}, poslane={volania}")
assert kod == 0
assert riadky[0]["stav"] == "vyprsana"
assert riadky[0]["sent_at"] is None
assert volania == []  # posli() sa vobec nezavolalo
mp.vrat_spat()

# 6) Bez ziadnych cakajucich pozvaniek skript nepada, vrati 0.
mp = _Monkeypatch()
kod, _ = _spusti_main(["--nasucho"], [], mp)
print(f"6) prazdny zoznam -> kod={kod}")
assert kod == 0
mp.vrat_spat()

# 7) Chybajuci org nazov (embed sa nepodaril / organizacia zmazana) sa
#    nezhodi beh — pouzije sa zastupny text "vášho tímu" v predmete/obsahu.
mp = _Monkeypatch()
mp.setattr(pp, "posli", lambda kluc, komu, predmet, html, nasucho: True)
riadky = [{
    "id": "inv-4", "org_id": "org-2", "email": "bezfirma@x.sk",
    "token": "tok-4", "stav": "cakajuca", "expires_at": o_hodin(24), "sent_at": None,
    "organizations": None,
}]
mp.setenv("RESEND_API_KEY", "test-kluc")
kod, riadky = _spusti_main([], riadky, mp)
print(f"7) chybajuci nazov firmy -> kod={kod}, sent_at nastavene={riadky[0]['sent_at'] is not None}")
assert kod == 0
assert riadky[0]["sent_at"] is not None
mp.vrat_spat()

print("VSETKY TESTY PRESLI (main)")
