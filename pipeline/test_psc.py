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
    # Este dve kosicke mesta s inym trojcifernym prefixom. Az tri RÔZNE
    # mesta zhodne na kraji otvoria dvojcifernu uroven 04x — a prave tou
    # sa potom chyti Zdana (044), ktorej vlastny prefix nepoznam.
    {"authority_cin": "00324451", "authority_name": "Mesto Moldava nad Bodvou",
     "authority_address": "Školská 2, 045 01 Moldava nad Bodvou"},
    {"authority_cin": "00328308", "authority_name": "Mesto Rožňava",
     "authority_address": "Šafárikova 29, 048 01 Rožňava"},
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
# Jedno mesto na trojcifernom prefixe UZ STACI a je to zamer: taky prefix
# pokryva obvykle jeden okres, takze jedna znama Trnava je dobry dokaz.
# Prah na pocet zmluv tu uz nie je, lebo hlasuju mesta — a Trnava je jedna
# bez ohladu na to, kolko ma zmluv.
assert regiony.PSC_KRAJ.get("917") == "Trnavský kraj", "Trnava 917"
print("OK: znama mesta sa naucili, jedno mesto na 3-cif. prefixe staci")

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
    "Zdanu ma zachranit dvojciferna uroven 04x (tri kosicke mesta)"
assert regiony.z_psc("029 44") == "Žilinský kraj", \
    "Rabca ma rovnaky trojciferny prefix ako Namestovo"
assert "02" not in regiony.PSC2_KRAJ, \
    "dvojciferny prefix 02 ma len jedno mesto a prijat sa nesmie"
print("OK: 3-cif. chyta presne, 2-cif. len ked su aspon tri zhodne mesta")

hlavicka("2a. UKECANE MESTO NESMIE PREHLASOVAT SUSEDA")
# Toto je regresny test na skutocnu chybu z 13. 9. 2026.
# Prefix 925 zdielaju Sladkovicovo (okres Galanta, Trnavsky kraj) a obce
# okolo Sale (Nitriansky kraj). Sladkovicovo ma v CRZ mnohonasobne viac
# zmluv. Kym sa hlasy vazili poctom zmluv, prefix vysiel ako Trnavsky
# a Obec Kralova nad Vahom skoncila v zlom kraji.
# Ked hlasuje kazde mesto raz, spor je vidiet a prefix sa zahodi.
ukecane = pd.Series(
    ["Hlavná 1, 925 21 Sereď"] * 40 +          # Trnavsky, 40 zmluv
    ["Hlavná 2, 925 91 Šaľa"] * 2              # Nitriansky, 2 zmluvy
)
regiony.nauc_psc(ukecane)
print("3-ciferne po ukecanom vstupe:", sorted(regiony.PSC_KRAJ))
print("kraj pre 925:", regiony.z_psc("925 91"))
assert "925" not in regiony.PSC_KRAJ, (
    "prefix 925 ma dve mesta v dvoch krajoch a musi sa zahodit, "
    "aj ked jedno z nich ma dvadsatkrat viac zmluv")
print("OK: pomer zmluv 40:2 prefix NEPREVAZIL, spor rozhodol")

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


hlavicka("7. NaN v adrese nesmie skoncit ako mesto 'nan'")
# Toto NEBOL hypoteticky pripad. Obec Smrdaky mala 16. 9. 2026 v zalozke
# ziadatelov v zobrazeni mesta napisane doslova "nan": pandas dal do
# chybajucej adresy float("nan"), `not float("nan")` je False, takze
# povodna podmienka NaN prepustila a str(nan) == "nan" preposol do DB.
import math
for zla in (float("nan"), None, "", "   ", "nan", "None", "NULL"):
    m, p, k = regiony.rozober_adresu(zla)
    assert m is None and p is None and k is None, \
        f"z {zla!r} vypadlo mesto {m!r}"
print("OK: NaN, None, prazdny retazec ani text 'nan' mesto nevyrobia")

# A to iste cez cely df, lebo tam to naozaj zlyhalo.
df_nan = pd.DataFrame([
    {"authority_address": float("nan"), "authority_name": "Obec Smrdáky"},
    {"authority_address": "Smrdáky 181, 906 03 Smrdáky",
     "authority_name": "Obec Smrdáky"},
])
v7 = regiony.doplnit(df_nan.copy())
assert v7.loc[0, "mesto"] is None or pd.isna(v7.loc[0, "mesto"]), \
    f"mesto z NaN adresy je {v7.loc[0, 'mesto']!r}"
assert v7.loc[1, "mesto"] == "Smrdáky", v7.loc[1, "mesto"]
print("OK: aj cez doplnit(df) — z NaN prazdno, z adresy 'Smrdáky'")

hlavicka("8. Znacka cisla domu nesmie zostat v nazve mesta")
# Na stranke bolo "Rakovice č" — _CISLO_DOMU odstranilo cislo, zostalo
# "Rakovice č." a strip(" ,.-") uz len odsekol tecku.
pripady = {
    # Skutocna adresa Obce Rakovice z CRZ. PSC je tu na KONCI, takze
    # mesto sa berie z casti PRED nim — a presne tato vetva bola zla.
    "Rakovice č. 42, 922 08": "Rakovice",
    "Rakovice č. 8, 922 08 Rakovice č. 8": "Rakovice",
    "Hlavná č. 12, 900 01 Neznáma č. 12": "Neznáma",
    "Neznáma cislo 4, 900 01 Neznáma cislo 4": "Neznáma",
    "Neznáma 15, 900 01 Neznáma 15": "Neznáma",
    # Nazov, ktory sam obsahuje slovo na 'c', sa nesmie okresat.
    "Hlavná 1, 900 01 Nová Ves": "Nová Ves",
}
for adresa, ocakavane in pripady.items():
    m, p, k = regiony.rozober_adresu(adresa)
    assert m == ocakavane, f"{adresa!r} -> {m!r}, cakal som {ocakavane!r}"
    print(f"  {adresa[:46]:46} -> {m}")
print("OK: znacka cisla sa odstranuje, nazov obce zostava cely")


hlavicka("9. Pri uceni mapy PSC musi pole mesta nazvom ZACINAT")
# Toto je oprava chyby odmeranej v behu #43. Diagnostika ukazala, ze
# prefix 080 (Presov) sa zahodil preto, ze niekto hlasoval "Bratislava",
# a prefix 082 preto, ze niekto hlasoval "Trstena". Take hlasy vznikaju
# substringovou zhodou v poli, ktore nazvom mesta nie je.
regiony.PSC_KRAJ.clear()
regiony.PSC2_KRAJ.clear()

adresy_s_smetim = [
    # Styri ciste adresy z Presovskeho kraja, prefix 082.
    "Hlavná 1, 082 21 Veľký Šariš",
    "Nám. 2, 082 71 Lipany",
    "Hlavná 3, 082 22 Šarišské Michaľany",   # neznama obec, nehlasuje
    "Ulica 4, 080 01 Prešov",
    "Ulica 5, 082 12 Kapušany",              # neznama obec, nehlasuje
    # A jedna, ktorej pole mesta OBSAHUJE cudzi nazov, ale nie je nim.
    # Presne takto vznikol hlas "Bratislava" pri prefixe 080.
    "Sklad 9, 082 33 Prevádzka Bratislava - juh",
]
regiony.nauc_psc(adresy_s_smetim)
assert regiony.PSC_KRAJ.get("082") == "Prešovský kraj", \
    f"082 malo vyjst Presovsky, vyslo {regiony.PSC_KRAJ.get('082')!r}"
print("OK: 082 -> Prešovský kraj; cudzi nazov v poli mesta uz nehlasuje")

# Kontrola, ze sprisnenie hlasy len ODOBERA. Ked su dva ROZNE zname
# mesta z roznych krajov na tom istom prefixe, spor ma zostat sporom
# a prefix sa ma dalej zahodit.
regiony.PSC_KRAJ.clear()
regiony.nauc_psc([
    "A 1, 053 04 Spišské Podhradie",   # Presovsky
    "B 2, 053 61 Spišské Vlachy",      # Kosicky
])
assert "053" not in regiony.PSC_KRAJ, \
    "skutocna hranica kraja sa NESMIE prijat"
print("OK: 053 je naozaj hranica dvoch krajov a zostava zahodene")

# A pri POUZITI mapy ma hladanie zostat volne — substringova zhoda
# tam pomaha a nic nekazi.
m, p, k = regiony.rozober_adresu("Ulica 1, 040 01 Košice - Staré Mesto")
assert k == "Košický kraj" and m == "Košice", (m, k)
print("OK: pri pouziti zostava volne hladanie — 'Košice - Staré Mesto' sadne")

# A TOTO je rozdiel medzi "zacina nazvom" a "je cele nazvom". Prvy pokus
# vyzadoval cele pole a "Kosice - Stare Mesto" tym prestalo hlasovat —
# prijatych prefixov ubylo zo 172 na 156 a na produkte to bolo HORSIE.
# Mestska cast teda hlasovat MUSI.
regiony.PSC_KRAJ.clear()
regiony.PSC2_KRAJ.clear()
regiony.nauc_psc(["Ulica 1, 040 11 Košice - Západ"])
assert regiony.PSC_KRAJ.get("040") == "Košický kraj", \
    "mestska cast musi hlasovat, inak stracame viac nez ziskavame"
print("OK: 'Košice - Západ' hlasuje (zacina nazvom mesta)")

# ...ale nazov zahrabany vnutri pola hlasovat NESMIE. Presne tento tvar
# zabil prefix 080 (Presov) hlasom za Bratislavu.
regiony.PSC_KRAJ.clear()
regiony.nauc_psc(["Sklad 9, 080 05 Prevádzka Bratislava - juh"])
assert "080" not in regiony.PSC_KRAJ, \
    "zahrabany nazov mesta NESMIE hlasovat"
print("OK: 'Prevádzka Bratislava - juh' nehlasuje (nazov je vnutri)")

print("\nVSETKY TESTY PRESLI\n")
