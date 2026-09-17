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
