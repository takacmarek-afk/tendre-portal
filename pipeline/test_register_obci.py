"""Test register_obci.nacitaj_s_okresom() — pridane vo vlne FOMO alertov
(pipeline/alerty.py), ktora potrebuje okres, nie len kraj. nacitaj() uz
ma nepriame pokrytie cez test_psc.py (regiony.MESTO_KRAJ), toto su
priame testy na novu funkciu a na to, ze existujuce nacitaj() sa
refaktorovanim nezmenilo.

Spustenie:  python test_register_obci.py
"""
import register_obci


def hlavicka(t):
    print("\n" + "=" * 66)
    print(t)
    print("=" * 66)


hlavicka("nacitaj_s_okresom() vracia (nazov, kraj, okres) pre znamu obec")
d = register_obci.nacitaj_s_okresom()
assert d, "register sa nenacital (chybaju data subory?)"
nazov, kraj, okres = d["malacky"]
assert nazov == "Malacky", nazov
assert kraj == "Bratislavský kraj", kraj
assert okres == "Okres Malacky", okres
print("OK:", d["malacky"])

hlavicka("nacitaj() a nacitaj_s_okresom() sa zhoduju na (nazov, kraj) "
          "pre kazdy spolocny kluc")
d1 = register_obci.nacitaj()
d2 = register_obci.nacitaj_s_okresom()
assert len(d1) > 2000 and len(d2) > 2000, (len(d1), len(d2))
nezhody = [k for k, v in d2.items() if k in d1 and d1[k] != (v[0], v[1])]
assert not nezhody, nezhody
print(f"OK: {len(d1)} vs {len(d2)} zaznamov, 0 nezhod na {len(d2)} spolocnych kluchov")

hlavicka("nacitaj_s_okresom() je prisnejsia alebo rovnaka ako nacitaj() "
          "(nikdy nevrati viac nez nacitaj())")
assert len(d2) <= len(d1), (len(d2), len(d1))
print(f"OK: {len(d2)} <= {len(d1)}")

hlavicka("Chybajuci/neexistujuci subor -> prazdny slovnik, nie vynimka")
prazdny = register_obci.nacitaj_s_okresom(
    cesta_nuts4="/neexistuje/x.json", cesta_obce="/neexistuje/y.json")
assert prazdny == {}, prazdny
print("OK: {}")

print("\nVsetky testy prebehli.")
