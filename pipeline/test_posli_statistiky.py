"""Testy pre posli_statistiky.py — bez sietovych volani."""
import sys, os, types
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Rovnaky dovod ako v test_posli_pozvanky.py: supabase.create_client sa
# importuje na urovni modulu (aj v posli_email.py, ktory tento skript
# importuje), hoci ho tieto testy vobec nevolaju naozaj.
if "supabase" not in sys.modules:
    try:
        import supabase  # noqa: F401
    except ImportError:
        fake = types.ModuleType("supabase")
        fake.create_client = lambda *a, **k: None
        sys.modules["supabase"] = fake

from datetime import datetime, timedelta, timezone
import posli_statistiky as ps

teraz = datetime.now(timezone.utc)


def pred_dnami(d):
    return (teraz - timedelta(days=d)).isoformat()


# ── priprav_zhrnutie() ───────────────────────────────────────────────────

# 1) Zakladne scitanie a triedenie podla poctu, zostupne.
navstevy = (
    [{"cesta": "/index.html", "referrer": None}] * 5
    + [{"cesta": "/cennik.html", "referrer": "https://google.com"}] * 3
    + [{"cesta": "/obce.html", "referrer": "https://google.com"}] * 1
)
celkom, top_stranky, top_referreri = ps.priprav_zhrnutie(navstevy)
print(f"1) celkom={celkom}, top_stranky={top_stranky}, top_referreri={top_referreri}")
assert celkom == 9
assert top_stranky[0] == ("/index.html", 5)
assert top_stranky[1] == ("/cennik.html", 3)
assert top_referreri[0] == ("(priamo / bez odkazu)", 5)
assert top_referreri[1] == ("https://google.com", 4)

# 2) Prazdny/None referrer sa zbalí do "(priamo / bez odkazu)", nie do
#    samostatnych bucketov pre "" a None.
navstevy2 = [
    {"cesta": "/a", "referrer": None},
    {"cesta": "/a", "referrer": ""},
    {"cesta": "/a", "referrer": "   "},
]
_, _, top_referreri2 = ps.priprav_zhrnutie(navstevy2)
print(f"2) referreri={top_referreri2}")
assert top_referreri2 == [("(priamo / bez odkazu)", 3)]

# 3) Obmedzenie na TOP_STRANOK/TOP_REFERREROV aj ked je kandidatov viac.
navstevy3 = [{"cesta": f"/s{i}", "referrer": f"https://r{i}.sk"} for i in range(10)]
celkom3, top_s3, top_r3 = ps.priprav_zhrnutie(navstevy3)
print(f"3) pocet_top_stranok={len(top_s3)}, pocet_top_referrerov={len(top_r3)}")
assert celkom3 == 10
assert len(top_s3) == ps.TOP_STRANOK
assert len(top_r3) == ps.TOP_REFERREROV

# 4) Riadky bez cesty (nemal by nastat, ale skript nesmie spadnut) sa
#    do top_stranky nezapocitaju, do celkoveho poctu ano.
navstevy4 = [{"cesta": None, "referrer": None}, {"cesta": "/x", "referrer": None}]
celkom4, top_s4, _ = ps.priprav_zhrnutie(navstevy4)
print(f"4) celkom={celkom4}, top_stranky={top_s4}")
assert celkom4 == 2
assert top_s4 == [("/x", 1)]

print("VSETKY TESTY PRESLI (priprav_zhrnutie)")


# ── _statistiky_html() ───────────────────────────────────────────────────

# 5) CTA odkaz musi viest na app.html (inak by _obal() vyhodil vynimku),
#    a pocty musia byt v HTML.
html = ps._statistiky_html(12, [("/index.html", 7)], [("(priamo / bez odkazu)", 5)])
print(f"5) cta v odkaze -> {'app.html' in html}, pocty -> {'12 unikátnych návštev' in html}")
assert "https://predtendrom.sk/app.html" in html
assert "12 unikátnych návštev" in html
assert "/index.html" in html

print("VSETKY TESTY PRESLI (_statistiky_html)")


# ── priprav_zhrnutie() — dedup podla session_id (30_navstevnost_unique.sql) ──

# 5b) Jedna osoba (rovnake session_id) prekliknuta cez 3 stranky sa v
#     celkovom counte pocita raz, ale v top_stranky sa ta istá session
#     zaráta do kazdej navstivenej stranky zvlast (to je "navstevnost tejto
#     stranky", nie "celkovy pocet ludi").
navstevy5b = [
    {"cesta": "/index.html", "referrer": None, "session_id": "s1"},
    {"cesta": "/cennik.html", "referrer": None, "session_id": "s1"},
    {"cesta": "/obce.html", "referrer": None, "session_id": "s1"},
]
celkom5b, top_s5b, _ = ps.priprav_zhrnutie(navstevy5b)
print(f"5b) jedna session cez 3 stranky -> celkom={celkom5b}, top_stranky={top_s5b}")
assert celkom5b == 1
assert sorted(top_s5b) == sorted([("/index.html", 1), ("/cennik.html", 1), ("/obce.html", 1)])

# 5c) Rovnaka session, rovnaka stranka viackrat (napr. refresh) sa v
#     top_stranky pre tu stranku pocita tiez len raz.
navstevy5c = [
    {"cesta": "/index.html", "referrer": None, "session_id": "s1"},
    {"cesta": "/index.html", "referrer": None, "session_id": "s1"},
    {"cesta": "/index.html", "referrer": None, "session_id": "s2"},
]
celkom5c, top_s5c, _ = ps.priprav_zhrnutie(navstevy5c)
print(f"5c) opakovane navstevy tej istej stranky -> celkom={celkom5c}, top_stranky={top_s5c}")
assert celkom5c == 2
assert top_s5c == [("/index.html", 2)]

# 5d) Riadky bez session_id (stare data spred migracie) sa pocitaju kazdy
#     zvlast — rovnake spravanie ako predtym (spatna kompatibilita s
#     testom 1 vyssie, ktory tiez nepouziva session_id).
navstevy5d = [
    {"cesta": "/a", "referrer": None},
    {"cesta": "/a", "referrer": None},
]
celkom5d, top_s5d, _ = ps.priprav_zhrnutie(navstevy5d)
print(f"5d) bez session_id -> celkom={celkom5d}, top_stranky={top_s5d}")
assert celkom5d == 2
assert top_s5d == [("/a", 2)]

print("VSETKY TESTY PRESLI (priprav_zhrnutie — dedup)")


# ── main(): cely beh nad falosnou databazou ──────────────────────────────

class _FalosnaOdpoved:
    def __init__(self, data):
        self.data = data


class _FalosnaTabulka:
    def __init__(self, riadky):
        self._data = list(riadky)

    def select(self, *a, **k):
        return self

    def gte(self, col, val):
        self._data = [r for r in self._data if r.get(col, "") >= val]
        return self

    def execute(self):
        return _FalosnaOdpoved(self._data)


class _FalosnySb:
    def __init__(self, navstevy):
        self.tabulky = {"navstevy": navstevy}

    def table(self, nazov):
        return _FalosnaTabulka(self.tabulky[nazov])


class _Monkeypatch:
    """Jednoducha nahrada za pytest monkeypatch, rovnaky vzor ako v
    test_posli_pozvanky.py — tieto testy nebezia pod pytestom."""
    def __init__(self):
        self._povodne = []

    def setattr(self, obj, meno, hodnota):
        self._povodne.append((obj, meno, getattr(obj, meno, None)))
        setattr(obj, meno, hodnota)

    def setenv(self, meno, hodnota):
        self._povodne.append((os.environ, meno, os.environ.get(meno)))
        os.environ[meno] = hodnota

    def delenv(self, meno):
        self._povodne.append((os.environ, meno, os.environ.get(meno)))
        os.environ.pop(meno, None)

    def vrat_spat(self):
        for obj, meno, hodnota in reversed(self._povodne):
            if obj is os.environ:
                if hodnota is None:
                    os.environ.pop(meno, None)
                else:
                    os.environ[meno] = hodnota
            else:
                setattr(obj, meno, hodnota)


def _spusti_main(argv, navstevy, monkeypatch):
    sb = _FalosnySb(navstevy)
    monkeypatch.setattr(ps, "create_client", lambda *a, **k: sb)
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "sluzobny-kluc")
    monkeypatch.setattr(sys, "argv", ["posli_statistiky.py"] + argv)
    kod = ps.main()
    return kod


# 6) Nasucho s navstevami -> kod 0, ziadna siet (posli() to uz sam zaruci,
#    tu len overujeme, ze main() sa cez to prehryzie bez chyby).
mp = _Monkeypatch()
navstevy = [{"cesta": "/index.html", "referrer": None, "created_at": pred_dnami(1)}]
kod = _spusti_main(["--nasucho"], navstevy, mp)
print(f"6) nasucho, 1 navsteva -> kod={kod}")
assert kod == 0
mp.vrat_spat()

# 7) Ziadne navstevy -> e-mail sa neposiela (posli() sa vobec nezavola),
#    ale beh nepada.
mp = _Monkeypatch()
volania = []
mp.setattr(ps, "posli", lambda kluc, komu, predmet, html, nasucho: volania.append(komu) or True)
kod = _spusti_main(["--nasucho"], [], mp)
print(f"7) prazdny zoznam -> kod={kod}, volania={volania}")
assert kod == 0
assert volania == []
mp.vrat_spat()

# 8) Naostro (bez --nasucho): posli() sa nahradi falosnou funkciou, kod 0
#    a prijemca je presne PRIJEMCA (nie je to konfigurovatelny odber).
mp = _Monkeypatch()
volania = []
mp.setattr(ps, "posli", lambda kluc, komu, predmet, html, nasucho: volania.append(komu) or True)
navstevy = [{"cesta": "/cennik.html", "referrer": "https://google.com", "created_at": pred_dnami(2)}]
mp.setenv("RESEND_API_KEY", "test-kluc")
kod = _spusti_main([], navstevy, mp)
print(f"8) naostro -> kod={kod}, komu={volania}")
assert kod == 0
assert volania == [ps.PRIJEMCA]
mp.vrat_spat()

# 9) Chyba SUPABASE_URL/KEY -> kod 1, bez pokusu o cokolvek dalsie.
mp = _Monkeypatch()
mp.delenv("SUPABASE_URL")
mp.delenv("SUPABASE_SERVICE_ROLE_KEY")
mp.setattr(sys, "argv", ["posli_statistiky.py", "--nasucho"])
kod = ps.main()
print(f"9) chybajuce premenne -> kod={kod}")
assert kod == 1
mp.vrat_spat()

# 10) Naostro bez RESEND_API_KEY -> kod 1 (nikdy sa nesmie tvarit, ze to
#     poslal, ked kluc chyba).
mp = _Monkeypatch()
mp.setenv("SUPABASE_URL", "https://x.supabase.co")
mp.setenv("SUPABASE_SERVICE_ROLE_KEY", "sluzobny-kluc")
mp.delenv("RESEND_API_KEY")
mp.setattr(sys, "argv", ["posli_statistiky.py"])
kod = ps.main()
print(f"10) naostro bez RESEND_API_KEY -> kod={kod}")
assert kod == 1
mp.vrat_spat()

print("VSETKY TESTY PRESLI (main)")
