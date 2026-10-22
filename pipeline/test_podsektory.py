"""Podsektory (audit 22. 10. 2026): nakup cistiacich prostriedkov a drogerie
patri do UPRATOVANIE_TOVAR, kamery a EPS/EZS do OSTRAHA_TECHNIKA; sluzby
ostavaju v materskom sektore. Nazvy su skutocne zmluvy z portalu.
Spustenie: python test_podsektory.py
"""
from classify import klasifikuj, prekvalifikuj_podsektory

PRIPADY = [
    ("Rámcová dohoda č. 2023/522 – čistiace prostriedky", "UPRATOVANIE_TOVAR"),
    ("Dodávka čistiacich a hygienických potrieb", "UPRATOVANIE_TOVAR"),
    ("Rámcová kúpna zmluva č. 3/2025 na dodávku čistiacich potrieb a spotrebného materiálu na upratovanie", "UPRATOVANIE_TOVAR"),
    ("čistiace a hyg.potreby", "UPRATOVANIE_TOVAR"),
    ("Nákup čistiacich, leštiacich a hygienických prostriedkov", "UPRATOVANIE_TOVAR"),
    ("Zmluva o poskytovaní čistiacich a upratovacích služieb", "UPRATOVANIE"),
    ("RÁMCOVÁ ZMLUVA O POSKYTOVANÍ UPRATOVACÍCH SLUŽIEB", "UPRATOVANIE"),
    ("Zabezpečenie upratovacích služieb vrátane dodávky hygienických potrieb", "UPRATOVANIE"),
    ("Pravidelné upratovanie 3 pavilónov ZŠ", "UPRATOVANIE"),
    ("Deratizácia, dezinfekcia a dezinsekcia objektov UPJŠ v Košiciach", "UPRATOVANIE"),
    ("Kamerové systémy pre objekty MČ", "OSTRAHA_TECHNIKA"),
    ("Zmluva o dielo - pravidelné odborné prehliadky, kontroly, servis a údržba elektrickej požiarnej signalizácie (EPS), elektrického zabezpečovacieho systému (EZS)", "OSTRAHA_TECHNIKA"),
    ("Zmluva o poskytovaní strážnej služby", "OSTRAHA"),
    ("Zmluva o poskytovaní služieb pri fyzickej ochrane majetku a osôb", "OSTRAHA"),
    ("Kúpna zmluva – dodávka", None),
    ("Inštalácia a servis kotla v kotolni ZŠ", "KURENIE_VODA_PLYN"),
    ("Dodávka potravín pre školskú jedáleň", "STRAVOVANIE"),
]

for text, ocak in PRIPADY:
    s, _ = klasifikuj(text, None)
    assert s == ocak, f"{text!r}: {s} != {ocak}"
print(f"OK   klasifikacia ({len(PRIPADY)} pripadov)")

zmeny = prekvalifikuj_podsektory([
    {"id": 1, "sector": "UPRATOVANIE", "subject": "Rámcová dohoda – čistiace prostriedky"},
    {"id": 2, "sector": "UPRATOVANIE", "subject": "Zmluva o poskytovaní upratovacích služieb"},
    {"id": 3, "sector": "OSTRAHA", "subject": "Kamerové systémy pre objekty MČ"},
    {"id": 4, "sector": "STAVEBNE_PRACE", "subject": "Rámcová dohoda – čistiace prostriedky"},
])
assert zmeny == {1: "UPRATOVANIE_TOVAR", 3: "OSTRAHA_TECHNIKA"}, zmeny
print("OK   prekvalifikovanie len z materskeho sektora")
