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
