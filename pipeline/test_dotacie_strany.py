"""Test otacania vymenenych stran pri dotaciach.
Spusti: python test_dotacie_strany.py

PRECO EXISTUJE: 16. 9. 2026 bolo v tabulke dotacii 11 riadkov z 3 276,
kde bol PRIJIMATELOM "Ministerstvo financií SR" alebo "Košický samosprávny
kraj" a poskytovatelom obec. Skoda nebola kozmeticka — kraj sa odvodzuje
z nazvu prijimatela, takze tie riadky dostali kraj a mesto SIDLA
POSKYTOVATELA. Dotacia pre Obec Ludovitova (Nitriansky kraj) sa
zakaznikovi zobrazovala ako bratislavska.
"""
from datetime import date
import pandas as pd
import subsidies
from classify import SEKTOR_DOTACIE

MIN_FIN = ("Ministerstvo financií Slovenskej republiky, Štefanovičova 5, "
           "817 82 Bratislava - mestská časť Staré Mesto")


def hlavicka(t):
    print("\n" + "=" * 68 + "\n" + t + "\n" + "=" * 68)


def zmluva(authority, supplier, ico_a="00000001", ico_s="00000002", id_=1):
    """Jeden riadok tak, ako ho vidi subsidies.z_contracts()."""
    return {
        "id": id_, "sector": SEKTOR_DOTACIE, "price_total": 250_000,
        "signed_on": "2026-06-01", "effective_from": "2026-06-01",
        "authority_name": authority, "authority_cin": ico_a,
        "authority_address": "Štefanovičova 5, 817 82 Bratislava",
        "supplier_name": supplier, "supplier_cin": ico_s,
        "subject": "Zmluva o poskytnutí dotácie", "subject_description": "",
    }


hlavicka("1. Ministerstvo ako prijimatel sa OTOCI")
df = pd.DataFrame([zmluva(MIN_FIN, "Obec Ľudovítová, Ľudovítová 21, 951 44 Ľudovítová",
                          ico_a="00151742", ico_s="00308421")])
# POZOR: v CRZ je prijimatel v poli DODAVATELA, takze tu je to naopak:
# authority = ministerstvo (poskytovatel), supplier = obec (prijimatel).
# Tento riadok je teda SPRAVNE orientovany a otacat sa NESMIE.
out = subsidies.z_contracts(df, dnes=date(2026, 9, 16))
assert len(out) == 1, out
assert out.loc[0, "prijimatel"].startswith("Obec Ľudovítová"), out.loc[0, "prijimatel"]
assert not bool(out.loc[0, "strany_vymenene"])
print(f"  OK  spravne orientovany riadok zostal: prijimatel = "
      f"{out.loc[0, 'prijimatel'][:34]}")

hlavicka("2. VYMENENY riadok sa otoci a dostane kraj OBCE, nie ministerstva")
# Tu je to naopak: obec je v poli objednavatela, ministerstvo v poli dodavatela.
df2 = pd.DataFrame([zmluva("Obec Ľudovítová, Ľudovítová 21, 951 44 Ľudovítová",
                           MIN_FIN, ico_a="00308421", ico_s="00151742")])
out2 = subsidies.z_contracts(df2, dnes=date(2026, 9, 16))
assert len(out2) == 1, out2
assert out2.loc[0, "prijimatel"].startswith("Obec Ľudovítová"), out2.loc[0, "prijimatel"]
assert out2.loc[0, "poskytovatel"].startswith("Ministerstvo"), out2.loc[0, "poskytovatel"]
assert bool(out2.loc[0, "strany_vymenene"]), "priznak sa musi nastavit"
# ICO musi ist s prijimatelom, teda s obcou.
assert out2.loc[0, "prijimatel_ico"] == "00308421", out2.loc[0, "prijimatel_ico"]
print(f"  OK  otocene: prijimatel = {out2.loc[0, 'prijimatel'][:30]}")
print(f"      poskytovatel = {out2.loc[0, 'poskytovatel'][:30]}")
print(f"      ICO islo s obcou: {out2.loc[0, 'prijimatel_ico']}")
print(f"      strany_vymenene = {bool(out2.loc[0, 'strany_vymenene'])}")

hlavicka("3. Kraj sa po otoceni NESMIE brat zo sidla ministerstva")
# Bez otocenia by kraj vysiel z nazvu "Ministerstvo ... Bratislava".
# Obec Ludovitova v zozname okresnych miest nie je, takze kraj zostane
# prazdny — a to je SPRAVNE. Prazdno je lepsie nez Bratislava.
kraj = out2.loc[0, "kraj"]
assert kraj != "Bratislavský kraj", (
    "kraj sa zobral zo sidla ministerstva — presne ta chyba, ktoru "
    "tento test ma chytit")
print(f"  OK  kraj = {kraj!r} (nie Bratislavský)")

hlavicka("4. Kraj ako prijimatel od ministerstva sa NEOTACA")
df4 = pd.DataFrame([zmluva(MIN_FIN, "Košický samosprávny kraj",
                           ico_a="00151742", ico_s="00035541")])
out4 = subsidies.z_contracts(df4, dnes=date(2026, 9, 16))
assert len(out4) == 1
assert out4.loc[0, "prijimatel"] == "Košický samosprávny kraj"
assert not bool(out4.loc[0, "strany_vymenene"])
print("  OK  kraj moze dotaciu od ministerstva dostat, neotaca sa")

hlavicka("5. Mesto dava vlastnej organizacii — NEOTACA sa, len prejde")
df5 = pd.DataFrame([zmluva("Mesto Senica", "Mestská poliklinika Senica, a.s.",
                           ico_a="00309974", ico_s="44455666")])
out5 = subsidies.z_contracts(df5, dnes=date(2026, 9, 16))
assert len(out5) == 1
assert out5.loc[0, "prijimatel"].startswith("Mestská poliklinika"), out5.loc[0, "prijimatel"]
assert not bool(out5.loc[0, "strany_vymenene"]), (
    "toto je SPRAVNA orientacia (mesto dava svojej organizacii), "
    "otacat sa nesmie")
print("  OK  'Mesto Senica -> Mestská poliklinika' zostalo ako je")

hlavicka("6. Ministerstvo sa uz NEMOZE dostat medzi prijimatelov")
# Stary filter ho prepustil, pretoze hladal "mestska cast" kdekolvek
# a nasiel to v ADRESE ministerstva.
assert not subsidies._je_samosprava(MIN_FIN), (
    "ministerstvo s adresou 'Bratislava - mestská časť Staré Mesto' "
    "sa opat tvari ako samosprava")
print("  OK  ministerstvo s 'mestská časť' v adrese uz neprejde")

print("\nVSETKY TESTY PRESLI\n")
