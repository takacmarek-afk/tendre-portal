"""Testy pre alerty.py ("Sused uz stavia") — zamerne bez sietovych volani,
len cista logika: rozpoznanie okresu z nazvu a zostavenie obsahu alertu
(preskoc seba sameho, deduplikacia uz poslaneho).

Spustenie:  python test_alerty.py
"""
import sys, os, types
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Rovnaky dovod a rovnaka atrapa ako v test_posli_email.py — alerty.py
# (cez posli_email.py) importuje supabase.create_client na urovni modulu.
if "supabase" not in sys.modules:
    try:
        import supabase  # noqa: F401
    except ImportError:
        fake = types.ModuleType("supabase")
        fake.create_client = lambda *a, **k: None
        sys.modules["supabase"] = fake

import alerty


def hlavicka(t):
    print("\n" + "=" * 66)
    print(t)
    print("=" * 66)


hlavicka("_obec_a_okres: 'Obec X' prefix ma prednost")
norm, okres = alerty._obec_a_okres("Obec Malacky")
assert norm == "malacky", norm
assert okres == "Okres Malacky", okres
print("OK:", norm, okres)

hlavicka("_obec_a_okres: 'Mesto X' prefix funguje rovnako")
norm, okres = alerty._obec_a_okres("Mesto Piešťany")
assert okres == "Okres Piešťany", okres
print("OK:", norm, okres)

hlavicka("_obec_a_okres: znamy nazov kdekolvek v texte (bez prefixu)")
norm, okres = alerty._obec_a_okres("Základná škola, Malacky")
assert okres == "Okres Malacky", okres
print("OK:", norm, okres)

hlavicka("_obec_a_okres: neznamy/vymysleny nazov -> (None, None)")
norm, okres = alerty._obec_a_okres("Neexistujuca Dedina Zzz123")
assert (norm, okres) == (None, None), (norm, okres)
print("OK: (None, None)")

hlavicka("_obec_a_okres: prazdny/None vstup -> (None, None), nic nespadne")
assert alerty._obec_a_okres(None) == (None, None)
assert alerty._obec_a_okres("") == (None, None)
print("OK")

hlavicka("pre_odberatela: udalost v tom istom okrese sa zaradi")
podla_okresu = {"Okres Malacky": [{
    "contract_id": 1, "obec_norm": "jablonove", "obec_nazov": "Obec Jablonové",
    "poskytovatel": "Ministerstvo XY", "ucel": "Zateplenie škôlky",
    "suma": 50000, "podpisane": "2026-09-01",
}]}
o = {"email": "starosta@malacky.sk", "obec": "Obec Malacky", "kraj": "Bratislavský kraj"}
obsah = alerty.pre_odberatela(None, o, podla_okresu, uz_poslane=set())
assert obsah is not None
assert obsah["bloky"][0]["titul"] == "Obec Jablonové", obsah
assert obsah["_contract_ids"] == [1], obsah
print("OK:", obsah["bloky"][0]["titul"], obsah["bloky"][0]["zvyraznene"])

hlavicka("pre_odberatela: udalost o SEBE SAMOM sa NEZARADI (nie je 'sused')")
podla_okresu_self = {"Okres Malacky": [{
    "contract_id": 2, "obec_norm": "malacky", "obec_nazov": "Obec Malacky",
    "poskytovatel": "Ministerstvo XY", "ucel": "Cesta",
    "suma": 80000, "podpisane": "2026-09-05",
}]}
obsah = alerty.pre_odberatela(None, o, podla_okresu_self, uz_poslane=set())
assert obsah is None, obsah
print("OK: None (vlastna zmluva sa nepocita ako 'sused')")

hlavicka("pre_odberatela: uz poslana udalost sa nezopakuje")
uz_poslane = {("starosta@malacky.sk", 1)}
obsah = alerty.pre_odberatela(None, o, podla_okresu, uz_poslane)
assert obsah is None, obsah
print("OK: None (uz bolo poslane)")

hlavicka("pre_odberatela: iny okres -> ziadna udalost")
o_iny = {"email": "x@y.sk", "obec": "Obec Košice", "kraj": "Košický kraj"}
obsah = alerty.pre_odberatela(None, o_iny, podla_okresu, uz_poslane=set())
assert obsah is None, obsah
print("OK: None (iny okres)")

hlavicka("pre_odberatela: obec sa neda zaradit do okresu -> None, nic nespadne")
o_neznamy = {"email": "x@y.sk", "obec": "Uplne Vymyslena Dedina Qqq"}
obsah = alerty.pre_odberatela(None, o_neznamy, podla_okresu, uz_poslane=set())
assert obsah is None, obsah
print("OK: None")

hlavicka("pre_odberatela: viac udalosti sa oreze na MAX_UDALOSTI")
vela = {"Okres Malacky": [
    {"contract_id": i, "obec_norm": "jablonove", "obec_nazov": "Obec Jablonové",
     "poskytovatel": "M", "ucel": "U", "suma": 1000 * i, "podpisane": "2026-09-01"}
    for i in range(1, 10)
]}
obsah = alerty.pre_odberatela(None, o, vela, uz_poslane=set())
assert len(obsah["bloky"]) == alerty.MAX_UDALOSTI, obsah
assert len(obsah["_contract_ids"]) == alerty.MAX_UDALOSTI
print(f"OK: orezane na {len(obsah['bloky'])} (MAX_UDALOSTI={alerty.MAX_UDALOSTI})")

print("\nVsetky testy prebehli.")
