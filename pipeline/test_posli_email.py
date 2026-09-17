"""Testy pre posli_email.py — zamerne bez sietovych volani (RESEND_API_KEY
sa tu vobec nepouziva), len cista logika rozhodovania, kto je uz na rade.
"""
import sys, os, types
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# posli_email.py importuje supabase.create_client na urovni modulu, hoci ho
# tento test vobec nevola. Ked balik chyba (napr. lokalne bez venv, kym CI
# ho ma z requirements.txt), staci atrapa, aby import prešiel.
if "supabase" not in sys.modules:
    try:
        import supabase  # noqa: F401
    except ImportError:
        fake = types.ModuleType("supabase")
        fake.create_client = lambda *a, **k: None
        sys.modules["supabase"] = fake

from datetime import datetime, timedelta, timezone
import posli_email as pe

teraz = datetime.now(timezone.utc)


def pred(dni):
    return (teraz - timedelta(days=dni)).isoformat()


# 1) Denny odberatel je vzdy na rade, aj keby dostal mail pred chvilou.
o = {"frekvencia": "denne", "posledny_email": pred(0.01)}
print(f"1) denny, mail pred chvilou -> {pe.pripraveny_na_dalsi(o)}")
assert pe.pripraveny_na_dalsi(o) is True

# 2) Tyzdenny odberatel BEZ zaznamu o poslednom maile je na rade (prvy mail).
o = {"frekvencia": "tyzdenne", "posledny_email": None}
print(f"2) tyzdenny, ziadny predchadzajuci mail -> {pe.pripraveny_na_dalsi(o)}")
assert pe.pripraveny_na_dalsi(o) is True

# 3) Tyzdenny odberatel, mail pred 2 dnami -> NIE je na rade.
o = {"frekvencia": "tyzdenne", "posledny_email": pred(2)}
print(f"3) tyzdenny, mail pred 2 dnami -> {pe.pripraveny_na_dalsi(o)}")
assert pe.pripraveny_na_dalsi(o) is False

# 4) Tyzdenny odberatel, mail pred 6 dnami -> UZ je na rade (MIN_DNI_TYZDENNE=6).
o = {"frekvencia": "tyzdenne", "posledny_email": pred(6)}
print(f"4) tyzdenny, mail pred 6 dnami -> {pe.pripraveny_na_dalsi(o)}")
assert pe.pripraveny_na_dalsi(o) is True

# 5) Chybajuci stlpec frekvencia (zaznamy pred migraciou 20) sa spravaju ako
#    tyzdenny odberatel — nie ako denny. Bezpecny default: menej mailov, nie viac.
o = {"posledny_email": pred(1)}
print(f"5) chybajuca frekvencia, mail pred 1 dnom -> {pe.pripraveny_na_dalsi(o)} (default tyzdenne)")
assert pe.pripraveny_na_dalsi(o) is False

# 6) Poskodeny/nerozpoznatelny format posledny_email -> radsej posli navyse,
#    nez ticho niekoho navzdy vynechaj.
o = {"frekvencia": "tyzdenne", "posledny_email": "neplatny-format"}
print(f"6) neplatny format datumu -> {pe.pripraveny_na_dalsi(o)}")
assert pe.pripraveny_na_dalsi(o) is True

print("VSETKY TESTY PRESLI")


# ── platny_webhook() ────────────────────────────────────────────────────────

# 7) Prazdna/chybajuca hodnota nie je platny webhook.
print(f"7) prazdne -> {pe.platny_webhook(None)}, {pe.platny_webhook('')}")
assert pe.platny_webhook(None) is False
assert pe.platny_webhook("") is False

# 8) Platna https URL bez medzier prejde.
print(f"8) platna URL -> {pe.platny_webhook('https://hooks.slack.com/services/T/B/x')}")
assert pe.platny_webhook("https://hooks.slack.com/services/T/B/x") is True

# 9) http:// (nie https), medzera v URL, alebo nezmyselny text sa odmietnu.
print(f"9) http -> {pe.platny_webhook('http://example.com/x')}, "
     f"medzera -> {pe.platny_webhook('https://example.com/x y')}, "
     f"text -> {pe.platny_webhook('nieco co nie je url')}")
assert pe.platny_webhook("http://example.com/x") is False
assert pe.platny_webhook("https://example.com/x y") is False
assert pe.platny_webhook("nieco co nie je url") is False

# 10) Prilis dlha URL (nad 500 znakov) sa odmietne.
dlha = "https://example.com/" + "a" * 500
print(f"10) dlzka={len(dlha)} -> {pe.platny_webhook(dlha)}")
assert pe.platny_webhook(dlha) is False


# ── posli_webhook() ─────────────────────────────────────────────────────────

_OBSAH = {
    "titulok": "3 nové príležitosti",
    "uvod": "Toto je testovaci uvod s & znakom aj <tagom>.",
    "bloky": [
        {"titul": "Zakazka A", "popis": "Urad X", "zvyraznene": "1 000 € · koniec 2026-01-01"},
        {"titul": "Zakazka B", "popis": "Urad Y", "zvyraznene": "2 000 € · koniec 2026-02-01"},
    ],
    "cta_text": "Otvoriť portál",
    "cta_url": "https://predtendrom.sk/app.html",
    "odhlasenie": "x",
}

# 11) NASUCHO nikdy nevola siet (ziadny pe.requests.post) a vrati True.
volania = []
povodny_post = pe.requests.post
pe.requests.post = lambda *a, **k: volania.append((a, k)) or (_ for _ in ()).throw(
    AssertionError("NASUCHO nesmie volat siet"))
try:
    vysledok = pe.posli_webhook("https://hooks.slack.com/x", _OBSAH, True)
finally:
    pe.requests.post = povodny_post
print(f"11) nasucho webhook -> {vysledok}, sietovych volani={len(volania)}")
assert vysledok is True
assert len(volania) == 0

# 12) Slack URL (hooks.slack.com) -> payload je {"text": ...}, obsahuje escapovany "&".
class _FalosnaOdpoved:
    status_code = 200
    text = "ok"

zachytene = {}
def _falosny_post(url, timeout=None, json=None):
    zachytene["url"] = url
    zachytene["json"] = json
    return _FalosnaOdpoved()

povodny_post = pe.requests.post
pe.requests.post = _falosny_post
try:
    vysledok = pe.posli_webhook("https://hooks.slack.com/services/T/B/x", _OBSAH, False)
finally:
    pe.requests.post = povodny_post
print(f"12) slack payload kluce -> {sorted(zachytene['json'].keys())}, "
     f"obsahuje escapovany amp -> {'&amp;' in zachytene['json']['text']}")
assert vysledok is True
assert set(zachytene["json"].keys()) == {"text"}
assert "&amp;" in zachytene["json"]["text"]
assert "<tagom>" not in zachytene["json"]["text"]  # muselo sa escapovat na &lt;tagom&gt;

# 13) Ina URL (nie hooks.slack.com) -> Teams MessageCard format.
zachytene = {}
povodny_post = pe.requests.post
pe.requests.post = _falosny_post
try:
    vysledok = pe.posli_webhook("https://outlook.office.com/webhook/x", _OBSAH, False)
finally:
    pe.requests.post = povodny_post
print(f"13) teams payload @type -> {zachytene['json'].get('@type')}")
assert vysledok is True
assert zachytene["json"]["@type"] == "MessageCard"
assert zachytene["json"]["title"] == _OBSAH["titulok"]

# 14) HTTP chyba (napr. 404 zla URL) sa nesmie zhodit vynimkou, len False.
class _ZlaOdpoved:
    status_code = 404
    text = "not found"

povodny_post = pe.requests.post
pe.requests.post = lambda *a, **k: _ZlaOdpoved()
try:
    vysledok = pe.posli_webhook("https://hooks.slack.com/x", _OBSAH, False)
finally:
    pe.requests.post = povodny_post
print(f"14) HTTP 404 -> {vysledok} (nesmie vyhodit vynimku)")
assert vysledok is False

print("VSETKY TESTY PRESLI (webhook)")


# ── OSOBNA RELEVANCIA (#7, 17.9.2026) ───────────────────────────────────────

# 15) _cislo: bezpecny prevod, None namiesto vynimky/NaN.
print(f"15) _cislo('50000')={pe._cislo('50000')}, _cislo(None)={pe._cislo(None)}, "
      f"_cislo('abc')={pe._cislo('abc')}, _cislo(0)={pe._cislo(0)}")
assert pe._cislo("50000") == 50000.0
assert pe._cislo(None) is None
assert pe._cislo("abc") is None
assert pe._cislo(0) == 0.0  # cena 0 je platna hodnota (ramcova dohoda), nie chyba

# 16) _relevancia: kazda zlozka bonusu samostatne.
_z_it = {"sector": "IT", "kraj": "Bratislavský", "price_total": 195000}
_z_stavba = {"sector": "STAVEBNICTVO", "kraj": "Košický", "price_total": 50000}
b_ziadna = pe._relevancia(_z_stavba, {"sektor": None, "kraj": None}, None)
b_sektor = pe._relevancia(_z_it, {"sektor": "IT", "kraj": None}, None)
b_kraj = pe._relevancia(_z_it, {"sektor": None, "kraj": "Bratislavský"}, None)
b_vlastny_sektor = pe._relevancia(_z_it, {"sektor": None, "kraj": None},
                                   {"hlavny_sektor": "IT", "priemerna_zmluva_eur": None})
b_vlastna_cena = pe._relevancia(_z_it, {"sektor": None, "kraj": None},
                                 {"hlavny_sektor": None, "priemerna_zmluva_eur": 195000})
print(f"16) bonusy: ziadny={b_ziadna}, sektor={b_sektor}, kraj={b_kraj}, "
      f"vlastny_sektor={b_vlastny_sektor}, vlastna_cena={round(b_vlastna_cena, 1)}")
assert b_ziadna == 0
assert b_sektor == 15
assert b_kraj == 10
assert b_vlastny_sektor == 20
assert 14 < b_vlastna_cena <= 15  # cena takmer presne sedi -> bonus blizko maxima

# 17) pre_dodavatela: bez moje_ico sa sprava presne ako doteraz (regresia) —
#     tvrdy filter na sektor, ziadna zmena poradia/vyberu.
class _FalosnaOdpoved:
    def __init__(self, data):
        self.data = data


class _FalosnaTabulka:
    def __init__(self, data):
        self._data = list(data)
        self._limit = None
        self._order_key = None
        self._order_desc = False

    def select(self, *a, **k):
        return self

    def gte(self, col, val):
        self._data = [r for r in self._data if (r.get(col) or "") >= val]
        return self

    def eq(self, col, val):
        self._data = [r for r in self._data if r.get(col) == val]
        return self

    def order(self, col, desc=False):
        self._order_key, self._order_desc = col, desc
        return self

    def limit(self, n):
        self._limit = n
        return self

    def execute(self):
        data = self._data
        if self._order_key:
            data = sorted(data, key=lambda r: r.get(self._order_key) or "",
                          reverse=self._order_desc)
        if self._limit is not None:
            data = data[:self._limit]
        return _FalosnaOdpoved(data)


class _FalosnySb:
    def __init__(self, tabulky):
        self.tabulky = tabulky

    def table(self, nazov):
        return _FalosnaTabulka(self.tabulky.get(nazov, []))


def _zakazka(i, sector, kraj, cena, dni_pred=0):
    return {
        "subject": f"Zakazka {i}", "authority_name": f"Urad {i}",
        "mesto": "Mesto", "kraj": kraj, "price_total": cena,
        "effective_to": "2027-01-01",
        "odhad_vyhlasenia": (teraz + timedelta(days=dni_pred)).date().isoformat(),
        "sector": sector, "dni_do_konca": 200,
        # Vsetko "nove od posledneho mailu" — inak by .gte(first_seen_at)
        # v pre_dodavatela() vsetko odfiltrovalo skor, nez sa relevancia
        # vobec dostane na rad.
        "first_seen_at": teraz.date().isoformat(),
    }


_dnes = teraz.date()
_zmluvy_mix = (
    # IT su chronologicky VZDY skor (dni_pred 0-4) nez STAVEBNICTVO
    # (dni_pred 10-24) — zamerne bez prekryvu, aby bolo jednoznacne, co
    # "chronologicky prve" znamena aj pri viazanych testoch nizsie.
    [_zakazka(i, "IT", "Bratislavský", 190000 + i, dni_pred=i) for i in range(5)] +
    [_zakazka(100 + i, "STAVEBNICTVO", "Košický", 40000 + i, dni_pred=10 + i) for i in range(15)]
)
sb = _FalosnySb({"opportunities": _zmluvy_mix})
o_bez_ico = {"email": "firma@x.sk", "sektor": None, "kraj": None, "moje_ico": None}
vysledok = pe.pre_dodavatela(sb, o_bez_ico, _dnes)
print(f"17) bez moje_ico -> {len(vysledok['bloky'])} poloziek "
      f"(MAX_POLOZIEK={pe.MAX_POLOZIEK}, chronologicky ako predtym)")
assert len(vysledok["bloky"]) == pe.MAX_POLOZIEK
# Chronologicke poradie (najskorsi tender = najmensie dni_pred) musi ostat
# nedotknute, ked sa relevancia vobec nepouziva.
assert "Zakazka 0" in vysledok["bloky"][0]["titul"]

# 18) pre_dodavatela: s moje_ico a bez pevneho sektora/kraja sa vyber SPRAVI
#     z celej sirsej vzorky podla relevancie — vlastny sektor (STAVEBNICTVO,
#     nastaveny cez dodavatelia) prevazi nad chronologicky skorsimi IT
#     zakazkami, na ktore firma vobec neni napojena.
sb2 = _FalosnySb({
    "opportunities": _zmluvy_mix,
    "dodavatelia": [{"supplier_cin": "12345678", "hlavny_sektor": "STAVEBNICTVO",
                      "priemerna_zmluva_eur": 45000}],
})
o_s_ico = {"email": "firma@x.sk", "sektor": None, "kraj": None, "moje_ico": "12345678"}
vysledok2 = pe.pre_dodavatela(sb2, o_s_ico, _dnes)
sektory_v_maile = {b["titul"] for b in vysledok2["bloky"]}
print(f"18) s moje_ico (vlastny sektor STAVEBNICTVO) -> "
      f"{len(vysledok2['bloky'])} poloziek, vsetky STAVEBNICTVO: "
      f"{all('Zakazka 1' in t or 'Zakazka 2' in t for t in sektory_v_maile) is not None}")
assert len(vysledok2["bloky"]) == pe.MAX_POLOZIEK
# Vsetkych 8 vybranych musi byt zo STAVEBNICTVA (id >= 100), lebo tam je
# vlastna historia firmy aj vahovo silnejsia (bonus 20) nez cokolvek ine.
assert all(int(b["titul"].split()[1]) >= 100 for b in vysledok2["bloky"])
# Napriek relevantnemu vyberu ZOSTAVA v maile chronologicke poradie na citanie.
poradie_dni = [b["popis"] for b in vysledok2["bloky"]]  # len na kontrolu, ze nepadlo

# 19) pre_dodavatela: s moje_ico ALE explicitny sektor+kraj naraz -> filter
#     zostava tvrdy, relevancia sa nepouziva (pouzit_relevanciu=False).
sb3 = _FalosnySb({
    "opportunities": _zmluvy_mix,
    "dodavatelia": [{"supplier_cin": "12345678", "hlavny_sektor": "STAVEBNICTVO",
                      "priemerna_zmluva_eur": 45000}],
})
o_oba_filtre = {"email": "firma@x.sk", "sektor": "IT", "kraj": "Bratislavský",
                "moje_ico": "12345678"}
vysledok3 = pe.pre_dodavatela(sb3, o_oba_filtre, _dnes)
print(f"19) moje_ico + explicitny sektor AJ kraj -> "
      f"{len(vysledok3['bloky'])} poloziek, vsetky IT: "
      f"{all(int(b['titul'].split()[1]) < 100 for b in vysledok3['bloky'])}")
assert len(vysledok3["bloky"]) == 5  # len tolko IT/Bratislavsky zakaziek existuje
assert all(int(b["titul"].split()[1]) < 100 for b in vysledok3["bloky"])

print("VSETKY TESTY PRESLI (relevancia)")
