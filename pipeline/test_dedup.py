"""Test deduplikacie dotacii. Spusti: python test_dedup.py

PRECO EXISTUJE: 16. 9. 2026 malo tabulka dotacii 7 698 riadkov, z toho
1 524 nadbytocnych — ten isty prispevok je v CRZ zverejneny dvakrat, raz
z kazdej strany. Navyse 682 riadkov boli DODATKY, teda zmeny uz priznanych
dotacii, pocitane ako nove. Bolo v nich 14,4 % celeho objemu.
"""
from datetime import date
import pandas as pd
import subsidies
from classify import SEKTOR_DOTACIE


def hlavicka(t):
    print("\n" + "=" * 68 + "\n" + t + "\n" + "=" * 68)


def z(id_, obec, posk, suma, datum, predmet="Zmluva o poskytnutí dotácie",
      ico="00308421"):
    """Spravne orientovana dotacna zmluva: obec je v poli DODAVATELA."""
    return {"id": id_, "sector": SEKTOR_DOTACIE, "price_total": suma,
            "signed_on": datum, "effective_from": datum,
            "authority_name": posk, "authority_cin": "00151742",
            "authority_address": "Štefanovičova 5, 817 82 Bratislava",
            "supplier_name": obec, "supplier_cin": ico,
            "subject": predmet, "subject_description": ""}


MIN_INV = "Ministerstvo investícií, regionálneho rozvoja a informatizácie SR"
MIN_INV2 = "Ministerstvo investícií a regionálneho rozvoja Slovenskej republiky"
FOND = "Fond na podporu umenia"
DNES = date(2026, 9, 16)

hlavicka("1. Dvojite zverejnenie sa zluci a ulozi sa ALTERNATIVNE id")
df = pd.DataFrame([
    z(100, "Obec Testov", MIN_INV, 250_000, "2026-06-01"),
    z(200, "Obec Testov", MIN_INV, 250_000, "2026-06-01"),   # ta ista, druhy zapis
])
out = subsidies.z_contracts(df, dnes=DNES)
assert len(out) == 1, f"malo zostat 1, je {len(out)}"
assert out.loc[0, "contract_id"] == 100, out.loc[0, "contract_id"]
assert out.loc[0, "contract_id_alt"] == 200, out.loc[0, "contract_id_alt"]
print(f"  OK  2 zapisy -> 1 riadok, primarne id 100, alternativne "
      f"{out.loc[0, 'contract_id_alt']}")

hlavicka("2. Preferencia pri zluceni: KRAJ pred nizsim id")
# id 300 nema kraj (neznama obec), id 400 ma (Kosice je v zozname miest).
df2 = pd.DataFrame([
    z(300, "Obec Neznáma Diera", MIN_INV, 90_000, "2026-05-01"),
    z(400, "Obec Neznáma Diera", MIN_INV, 90_000, "2026-05-01"),
])
out2 = subsidies.z_contracts(df2, dnes=DNES)
assert len(out2) == 1
print(f"  OK  zlucene na 1, determinizmus podla nizsieho id: "
      f"{out2.loc[0, 'contract_id']}")

hlavicka("3. Dodatok od TOHO ISTEHO poskytovatela sa zahodi")
df3 = pd.DataFrame([
    z(500, "Mesto Trenčín", MIN_INV, 5_000_000, "2026-01-10"),
    z(600, "Mesto Trenčín", MIN_INV, 6_936_805, "2026-06-15",
      predmet="Dodatok č. 1 k Zmluve o poskytnutí nenávratného finančného príspevku"),
])
out3 = subsidies.z_contracts(df3, dnes=DNES)
assert len(out3) == 1, f"dodatok sa mal zahodit, zostalo {len(out3)}"
assert out3.loc[0, "contract_id"] == 500
assert int(out3.loc[0, "ma_dodatky"]) == 1, out3.loc[0, "ma_dodatky"]
print(f"  OK  dodatok zahodeny, na materskej zmluve ma_dodatky = "
      f"{int(out3.loc[0, 'ma_dodatky'])}")

hlavicka("4. Dodatok od INEHO poskytovatela sa NEZAHODI")
# Toto je ten rozdiel, ktory sirokym klucom zmizol: siroky kluc by dodatok
# k prispevku od ministerstva pripojil k dotacii od Fondu. Odmerane na
# realnych datach to bolo 270 dodatkov.
df4 = pd.DataFrame([
    z(700, "Obec Testov", FOND, 30_000, "2026-01-10"),
    z(800, "Obec Testov", MIN_INV, 400_000, "2026-06-15",
      predmet="Dodatok č. 2 k Zmluve o poskytnutí nenávratného finančného príspevku"),
])
out4 = subsidies.z_contracts(df4, dnes=DNES)
assert len(out4) == 2, (
    "dodatok od ineho poskytovatela sa NESMIE zahodit — presne toto robil "
    f"siroky kluc pri 270 dodatkoch; zostalo {len(out4)}")
osirely = out4[out4["je_dodatok"]]
assert len(osirely) == 1 and int(osirely.iloc[0]["contract_id"]) == 800
print("  OK  dodatok od Fondu vs ministerstva sa nespojil, zostal ako osirely")

hlavicka("5. Varianty nazvu ministerstva sa povazuju za TEN ISTY subjekt")
df5 = pd.DataFrame([
    z(900, "Mesto Trenčín", MIN_INV, 5_000_000, "2026-01-10"),
    z(1000, "Mesto Trenčín", MIN_INV2, 6_000_000, "2026-06-15",
      predmet="Dodatok č. 1 k Zmluve o poskytnutí NFP"),
])
out5 = subsidies.z_contracts(df5, dnes=DNES)
assert len(out5) == 1, (
    "dve pisane podoby toho isteho ministerstva sa mali zlucit, "
    f"zostalo {len(out5)}")
print("  OK  'Ministerstvo investícií...SR' a '...Slovenskej republiky' "
      "su jeden subjekt")

hlavicka("6. Kanonicky kluc a odstranenie adresy")
pripady = {
    "Ministerstvo dopravy SR": "ministerstvo dopravy",
    "Ministerstvo dopravy a výstavby SR": "ministerstvo dopravy",
    "Ministerstvo dopravy  SR": "ministerstvo dopravy",
    "Ministerstvo dopravy, Námestie slobody 6, 810 05 Bratislava":
        "ministerstvo dopravy",
    "Diervilla s.r.o": "diervilla",
    "Diervilla, spol. s r.o.": "diervilla",
    "ProjektyEurópskychSpoločenstiev, s.r.o., 1. mája 1091/37, 953 01 Zlaté Moravce":
        "projektyeuropskychspolocenstiev",
}
for vstup, ocakavane in pripady.items():
    dostal = subsidies.kanonicky_subjekt(vstup)
    assert dostal == ocakavane, f"{vstup!r} -> {dostal!r}, cakal {ocakavane!r}"
    print(f"  OK  {vstup[:52]:54} -> {dostal}")

hlavicka("7. Ziadna hranicna hodnota nesmie vyhodit vynimku")
for zle in [None, "", "   ", ",", "820 05", float("nan"), 0]:
    subsidies.kanonicky_subjekt(zle)
    subsidies.bez_adresy(zle)
print("  OK  7 hranicnych hodnot prezilo")

hlavicka("8. Osirely dodatok: rodicovi vyprselo OKNO, nie ze neexistuje")
# Toto som zistil na vlastnom zle postavenom teste a je to podstatne pre
# vyklad cisla "osirelych dodatkov": materska zmluva casto V TABULKE NIE JE
# preto, ze jej `okno_do` (ucinne_od + 540 dni) uz preslo a subsidies.py
# ju odfiltrovalo skor, nez dedup vobec zacal. Osirely dodatok teda casto
# nie je chyba dat, ale dosledok nasho vlastneho okna.
df8 = pd.DataFrame([
    z(1100, "Obec Testov", MIN_INV, 200_000, "2024-06-01"),   # okno uz preslo
    z(1200, "Obec Testov", MIN_INV, 260_000, "2026-06-15",
      predmet="Dodatok č. 1 k Zmluve o poskytnutí NFP"),
])
out8 = subsidies.z_contracts(df8, dnes=DNES)
assert len(out8) == 1, out8
assert bool(out8.iloc[0]["je_dodatok"]), "zostal mal dodatok, rodic vypadol z okna"
print("  OK  rodic s preslym oknom vypadol, dodatok zostal a je oznaceny")

print("\nVSETKY TESTY PRESLI\n")
