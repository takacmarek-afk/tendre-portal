"""Test obce_register.zostav_riadky() - register vsetkych obci SR.

Spustenie:  python test_obce_register.py
"""
import obce_register


def hlavicka(t):
    print("\n" + "=" * 66)
    print(t)
    print("=" * 66)


riadky = obce_register.zostav_riadky()

hlavicka("Pocet a jedinecnost kodov")
assert 2800 < len(riadky) <= 2930, len(riadky)
kody = [r["kod"] for r in riadky]
assert len(kody) == len(set(kody)), "duplicitne kody"
print(f"OK: {len(riadky)} obci, kody jedinecne")

hlavicka("Agregaty (SK_CAP) sa preskocia")
assert not any(not r["kod"].startswith("SK") or "_" in r["kod"] for r in riadky)
print("OK")

hlavicka("Rovnomenne obce maju rozne kraje (Trnavka)")
trn = {r["kraj"]: r["okres"] for r in riadky if r["nazov"] == "Trnávka"}
assert trn == {"Trnavský kraj": "Okres Dunajská Streda",
               "Košický kraj": "Okres Trebišov"}, trn
print("OK:", trn)

hlavicka("Revucka Lehota")
rl = [r for r in riadky if r["nazov"] == "Revúcka Lehota"]
assert len(rl) == 1 and rl[0]["kraj"] == "Banskobystrický kraj" and rl[0]["okres"] == "Okres Revúca", rl
print("OK:", rl[0])

hlavicka("Kazdy riadok ma nazov, kraj a okres")
assert all(r["nazov"] and r["kraj"] and r["okres"] for r in riadky)
print("OK")

hlavicka("Chybajuci subor -> vynimka (loader nema ticho zapisat nic)")
try:
    obce_register.zostav_riadky("/neexistuje/a.json", "/neexistuje/b.json")
    raise SystemExit("ocakavana vynimka")
except OSError:
    print("OK")

print("\nVsetky testy prebehli.")
