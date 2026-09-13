"""Test naucenej mapy PSC -> kraj a doplnenia kraja malym obciam.

Spustenie:  python test_psc.py
"""
import pandas as pd

import regiony
import subsidies


def hlavicka(t):
    print("\n" + "=" * 66)
    print(t)
    print("=" * 66)


# ── Vstupne data ───────────────────────────────────────────────────────────
# Kosicke PSC 040/044, zilinske 010/029, presovske 060.
# Mesta v OKRESY su: Kosice, Zilina, Poprad. Obce Zdana, Rabca, Gerlachov nie.
zmluvy = pd.DataFrame([
    # znama adresa -> sluzi na naucenie mapy
    {"authority_cin": "00691135", "authority_name": "Mesto Košice",
     "authority_address": "Trieda SNP 48/A, 040 11 Košice"},
    {"authority_cin": "00691135", "authority_name": "Mesto Košice",
     "authority_address": "Trieda SNP 48/A, 040 11 Košice"},
    {"authority_cin": "00691135", "authority_name": "Mesto Košice",
     "authority_address": "Trieda SNP 48/A, 040 11 Košice"},
    {"authority_cin": "00321796", "authority_name": "Mesto Žilina",
     "authority_address": "Námestie obetí komunizmu 1, 011 31 Žilina"},
    {"authority_cin": "00321796", "authority_name": "Mesto Žilina",
     "authority_address": "Námestie obetí komunizmu 1, 011 31 Žilina"},
    {"authority_cin": "00321796", "authority_name": "Mesto Žilina",
     "authority_address": "Námestie obetí komunizmu 1, 011 31 Žilina"},
    {"authority_cin": "00326470", "authority_name": "Mesto Poprad",
     "authority_address": "Nábrežie Jána Pavla II. 2802/3, 058 01 Poprad"},
    {"authority_cin": "00326470", "authority_name": "Mesto Poprad",
     "authority_address": "Nábrežie Jána Pavla II. 2802/3, 058 01 Poprad"},
    {"authority_cin": "00326470", "authority_name": "Mesto Poprad",
     "authority_address": "Nábrežie Jána Pavla II. 2802/3, 058 01 Poprad"},
    # Namestovo ma PSC 029 01 — rovnaky trojciferny prefix ako Rabca 029 44.
    # Prave takto sa male obce chytia na presnej urovni: nie cez svoje
    # okresne mesto, ale cez ktorekolvek ZNAME mesto s tym istym prefixom.
    {"authority_cin": "00314676", "authority_name": "Mesto Námestovo",
     "authority_address": "Cyrila a Metoda 329/6, 029 01 Námestovo"},
    {"authority_cin": "00314676", "authority_name": "Mesto Námestovo",
     "authority_address": "Cyrila a Metoda 329/6, 029 01 Námestovo"},
    {"authority_cin": "00314676", "authority_name": "Mesto Námestovo",
     "authority_address": "Cyrila a Metoda 329/6, 029 01 Námestovo"},
    # male obce ako obstaravatelia -> adresu im vieme dohladat podla ICO
    {"authority_cin": "00324795", "authority_name": "Obec Ždaňa",
     "authority_address": "Jarmočná 118/4, 044 11 Ždaňa"},
    {"authority_cin": "00314731", "authority_name": "Obec Rabča",
     "authority_address": "Hlavná 426/238, 029 44 Rabča"},
    # ta ista obec s preklepom v adrese, ale len raz -> nesmie vyhrat
    {"authority_cin": "00314731", "authority_name": "Obec Rabča",
     "authority_address": "Hlavna 1, 029 44 Rabca"},
    {"authority_cin": "00314731", "authority_name": "Obec Rabča",
     "authority_address": "Hlavná 426/238, 029 44 Rabča"},
    # prefix s jednou jedinou vzorkou -> prah ho musi zahodit
    {"authority_cin": "99999999", "authority_name": "Mesto Trnava",
     "authority_address": "Hlavná 1, 917 01 Trnava"},
])

hlavicka("1. Naucenie mapy PSC -> kraj")
pocet = regiony.nauc_psc(zmluvy["authority_address"])
print(f"prijatych prefixov: {pocet}")
for k, v in sorted(regiony.PSC_KRAJ.items()):
    print(f"   {k} -> {v}")

assert regiony.PSC_KRAJ.get("040") == "Košický kraj", "Kosice 040"
assert regiony.PSC_KRAJ.get("011") == "Žilinský kraj", "Zilina 011"
assert regiony.PSC_KRAJ.get("058") == "Prešovský kraj", "Poprad 058"
assert regiony.PSC_KRAJ.get("029") == "Žilinský kraj", "Namestovo 029"
assert "917" not in regiony.PSC_KRAJ, "prefix s 1 vzorkou sa nesmie prijat"
print("OK: prah na pocet vzoriek drzi, znama mesta sa naucili")

hlavicka("2. Kraj z PSC pre obec, ktora v zozname miest nie je")
# POZOR NA TENTO ROZDIEL — prve co som tu mal, bolo zle.
# Zdana ma PSC 044, Kosice 040. Trojciferny prefix obce sa teda
# s prefixom okresneho mesta NEZHODUJE a 3-ciferna mapa ju nechyti.
# Zachranit ju musi dvojciferna uroven (04x -> Kosicky), a to len ak
# je jednoznacna. Preto testujem obe urovne oddelene.
print("3-ciferne prefixy:", sorted(regiony.PSC_KRAJ))
print("2-ciferne prefixy:", sorted(regiony.PSC2_KRAJ))
print("Košice (040 11) cez 3c:", regiony.z_psc("040 11"))
print("Ždaňa  (044 11) cez 2c:", regiony.z_psc("044 11"))
print("Rabča  (029 44) cez 2c:", regiony.z_psc("029 44"))
print("Trnava (917 01) neznamy:", regiony.z_psc("917 01"))

assert regiony.z_psc("040 11") == "Košický kraj", "presny prefix mesta"
assert regiony.z_psc("044 11") == "Košický kraj", \
    "Zdanu ma zachranit dvojciferna uroven 04x"
assert regiony.z_psc("029 44") == "Žilinský kraj", \
    "Rabcu ma zachranit dvojciferna uroven 02x"
assert regiony.z_psc("917 01") is None, "prefix s jednou vzorkou zostane prazdny"
print("OK: dvojciferna uroven dopina obce, jednorazovy prefix sa zahodil")

hlavicka("2b. Sporny dvojciferny prefix sa musi zahodit")
# 05x je v skutocnosti aj Presovsky (Poprad 058) aj Kosicky (Spisska Nova
# Ves 052). Taky prefix nesmieme prijat ani na dvojcifernej urovni.
sporne = pd.Series([
    "Nábrežie 1, 058 01 Poprad", "Nábrežie 1, 058 01 Poprad",
    "Nábrežie 1, 058 01 Poprad",
    "Radničné námestie 4, 052 01 Spišská Nová Ves",
    "Radničné námestie 4, 052 01 Spišská Nová Ves",
    "Radničné námestie 4, 052 01 Spišská Nová Ves",
])
regiony.nauc_psc(sporne)
print("2-ciferne po spornom vstupe:", sorted(regiony.PSC2_KRAJ))
assert "05" not in regiony.PSC2_KRAJ, \
    "05x je aj Presovsky aj Kosicky, prijat sa nesmie"
print("OK: poistka na cistotu drzi")

# vratime naucenu mapu z realistickeho vstupu
regiony.nauc_psc(zmluvy["authority_address"])

hlavicka("3. Mapa ICO -> adresa, najcastejsia adresa vyhrava")
adresy = subsidies.adresy_samosprav(zmluvy)
for k, v in sorted(adresy.items()):
    print(f"   {k} -> {v}")
assert adresy["00324795"] == "Jarmočná 118/4, 044 11 Ždaňa"
assert adresy["00314731"] == "Hlavná 426/238, 029 44 Rabča", \
    "preklep s 1 vyskytom nesmie prebit adresu s 2 vyskytmi"
print("OK: drop_duplicates vybral castejsiu adresu, nie poslednu")

hlavicka("4. Doplnenie kraja dotaciam (nazov nesadne, ICO zachrani)")
dot = pd.DataFrame([
    {"prijimatel": "Mesto Košice", "prijimatel_ico": "00691135"},
    {"prijimatel": "Obec Ždaňa", "prijimatel_ico": "00324795"},
    {"prijimatel": "Obec Rabča", "prijimatel_ico": "00314731"},
    {"prijimatel": "Obec Neznáma Diera", "prijimatel_ico": "11112222"},
    {"prijimatel": "Obec Bez Ica", "prijimatel_ico": None},
])
vysl = regiony.doplnit_z_nazvu(dot.copy(), "prijimatel",
                               adresy_podla_ica=adresy,
                               stlpec_ica="prijimatel_ico")
print(vysl[["prijimatel", "mesto", "kraj"]].to_string(index=False))

assert vysl.loc[0, "kraj"] == "Košický kraj", "mesto z nazvu"
assert vysl.loc[1, "kraj"] == "Košický kraj", "Zdana z PSC"
assert vysl.loc[1, "mesto"] == "Ždaňa", "mesto sa ma doplnit z adresy"
assert vysl.loc[2, "kraj"] == "Žilinský kraj", "Rabca z PSC"
assert pd.isna(vysl.loc[3, "kraj"]) or vysl.loc[3, "kraj"] is None, \
    "neznamu obec NEHADAME"
assert pd.isna(vysl.loc[4, "kraj"]) or vysl.loc[4, "kraj"] is None, \
    "bez ICO nemame odkial brat"
print("OK: 3 z 5 doplnene, zvysne dve zostali prazdne a nehadalo sa")

hlavicka("5. Bez naucenia sa nic nesmie zmenit (spatna kompatibilita)")
regiony.PSC_KRAJ.clear()
regiony.PSC2_KRAJ.clear()
vysl2 = regiony.doplnit_z_nazvu(dot.copy(), "prijimatel",
                                adresy_podla_ica=adresy,
                                stlpec_ica="prijimatel_ico")
# Zdana ma teraz mesto z adresy, ale kraj nie — mapa je prazdna.
assert vysl2.loc[1, "kraj"] is None or pd.isna(vysl2.loc[1, "kraj"])
print("OK: prazdna mapa = chovanie ako pred zmenou")

hlavicka("6. Stary podpis bez mapy musi dalej fungovat")
vysl3 = regiony.doplnit_z_nazvu(dot.copy(), "prijimatel")
assert vysl3.loc[0, "kraj"] == "Košický kraj"
print("OK")

print("\nVSETKY TESTY PRESLI\n")
