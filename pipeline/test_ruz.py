"""Test dekodera RUZ sablon (ruz.py) na REALNYCH datach, nie vymyslenych.

Fixture pre "Uc MUJ" (sablona 687) je doslovna kopia odpovede
registeruz.sk/cruz-public/api/sablona?id=687 (tabulka "Vykaz ziskov a
strat") a registeruz.sk/cruz-public/api/uctovny-vykaz?id=9927599 (LoveHome
s.r.o., ICO 47586362, FY2025) - overene naživo cez Browser pane 21.9.2026.
Rucne dopocitane: vynosy 9 EUR, dan 340 EUR (minimalna dan), vysledok po
zdaneni = 9 - 340 = -331 EUR (bezne obdobie), -340 EUR (predch. obdobie,
kde vynosy boli 0). Test len overuje, ze dekoder vrati presne tieto cisla.

Fixture pre "Uc POD" (sablona 699) je ZMENSENA (61 riadkov nahradenych
vyplnkovym textom okrem riadku 0 a 60, ktore su doslovne z realnej
odpovede pre Novogal a.s.) - dolezite su tu spravne POCTY riadkov/stlpcov
a REALNE cisla na spravnych poziciach (obrat 29 301 899 / 23 126 353,
vysledok hospodarenia 4 888 868 / 570 743 EUR), nie znenie ostatnych 59
riadkov, ktore dekoder ignoruje.

Spustenie:  python test_ruz.py
"""
import ruz


def hlavicka(t):
    print("\n" + "=" * 66)
    print(t)
    print("=" * 66)


def riadok(text, oznacenie=""):
    return {"text": {"sk": text}, "oznacenie": oznacenie}


# ── Fixture: Uc MUJ (sablona 687), realne texty riadkov Vykazu ziskov a strat
MUJ_RIADKY_TEXT = [
    "Výnosy z hospodárskej činnosti spolu súčet (r. 02 až r. 07)",
    "Tržby z predaja tovaru (604, 607)",
    "Tržby z predaja vlastných výrobkov a služieb (601, 602, 606)",
    "Zmena stavu vnútroorganizačných zásob (+/-) (účtová skupina 61)",
    "Aktivácia (účtová skupina 62)",
    "Tržby z predaja dlhodobého nehmotného majetku, dlhodobého hmotného majetku a materiálu (641, 642)",
    "Ostatné výnosy z hospodárskej činnosti (644, 645, 646, 648, 655, 657)",
    "Náklady na hospodársku činnosť spolu súčet (r. 09 až r. 17)",
    "Náklady vynaložené na obstaranie predaného tovaru (504, (+/- ) 505A, 507)",
    "Spotreba materiálu, energie a ostatných neskladovateľných dodávok (501, 502, 503, (+/-) 505A)",
    "Služby (účtová skupina 51)",
    "Osobné náklady (účtová skupina 52)",
    "Dane a poplatky (účtová skupina 53)",
    "Odpisy a opravné položky k dlhodobému nehmotnému majetku a dlhodobému hmotnému majetku (551, (+/-) 553)",
    "Zostatková cena predaného dlhodobého majetku a predaného materiálu (541, 542)",
    "Opravné položky k pohľadávkam (+/- 547)",
    "Ostatné náklady na hospodársku činnosť (543, 544, 545, 546, 548, 549, 555, 557)",
    "Výsledok hospodárenia z hospodárskej činnosti (+/-) (r. 01 - r. 08)",
    "Pridaná hodnota (r. 02 - r. 09) + (r. 03 + r. 04 + r. 05) - (r. 10 + r. 11)",
    "Výnosy z finančnej činnosti spolu súčet (r. 21 až r. 26)",
    "Tržby z predaja cenných papierov a podielov (661)",
    "Výnosy z dlhodobého finančného majetku (665)",
    "Výnosy z krátkodobého finančného majetku (666)",
    "Výnosové úroky (662)",
    "Kurzové zisky (663)",
    "Ostatné výnosy z finančnej činnosti (668)",
    "Náklady na finančnú činnosť spolu súčet (r. 28 až r. 33)",
    "Predané cenné papiere a podiely (561)",
    "Náklady na krátkodobý finančný majetok (566)",
    "Opravné položky k finančnému majetku (+/-) (565)",
    "Nákladové úroky (562)",
    "Kurzové straty (563)",
    "Ostatné náklady na finančnú činnosť (568, 569)",
    "Výsledok hospodárenia z finančnej činnosti (+/-) (r. 20 - r. 27)",
    "Výsledok hospodárenia za účtovné obdobie pred zdanením (+/-) (r. 18 + r. 34)",
    "Daň z príjmov (591, 595)",
    "Prevod podielov na výsledku hospodárenia spoločníkom (+/-) (596)",
    "Výsledok hospodárenia za účtovné obdobie po zdanení (+/-) (r. 35 - r. 36 - r. 37)",
]
assert len(MUJ_RIADKY_TEXT) == 38

MUJ_SABLONA = {
    "id": 687,
    "nazov": {"sk": "Úč MUJ"},
    "tabulky": [{
        "nazov": {"sk": ruz.NAZOV_TABULKY_VYKAZ},
        "hlavicka": [
            {"riadok": 1, "stlpec": 1}, {"riadok": 1, "stlpec": 2},
            {"riadok": 1, "stlpec": 3}, {"riadok": 1, "stlpec": 4},
            {"riadok": 1, "stlpec": 5},
        ],
        "riadky": [riadok(t) for t in MUJ_RIADKY_TEXT],
    }],
}

# Doslovne z registeruz.sk/cruz-public/api/uctovny-vykaz?id=9927599
MUJ_DATA = [
    "9", "", "", "", "", "", "", "", "", "", "", "", "9", "", "", "", "", "",
    "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "9", "",
    "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "",
    "", "", "", "", "", "", "", "", "", "", "", "", "", "", "9", "", "340",
    "340", "", "", "-331", "-340",
]
assert len(MUJ_DATA) == 76

MUJ_VYKAZ = {
    "id": 9927599,
    "idSablony": 687,
    "obsah": {"tabulky": [{"nazov": {"sk": ruz.NAZOV_TABULKY_VYKAZ}, "data": MUJ_DATA}]},
}


# ── Fixture: Uc POD (sablona 699), zmensena - riadky 0 a 60 su realne texty
# a realne hodnoty (Novogal a.s.), ostatne su vyplnkove (dekoder ich necita)
POD_RIADKY_TEXT = ["Výplňový riadok č. %d" % i for i in range(61)]
POD_RIADKY_TEXT[0] = "Čistý obrat (časť účt. tr. 6 podľa zákona)"
POD_RIADKY_TEXT[60] = "Výsledok hospodárenia za účtovné obdobie po zdanení (+/-) (r. 56 - r. 57 - r. 60)"

POD_SABLONA = {
    "id": 699,
    "nazov": {"sk": "Úč POD"},
    "tabulky": [{
        "nazov": {"sk": ruz.NAZOV_TABULKY_VYKAZ},
        "hlavicka": [
            {"riadok": 1, "stlpec": 1}, {"riadok": 1, "stlpec": 2},
            {"riadok": 1, "stlpec": 3}, {"riadok": 1, "stlpec": 4},
            {"riadok": 2, "stlpec": 4}, {"riadok": 2, "stlpec": 5},
        ],
        "riadky": [riadok(t) for t in POD_RIADKY_TEXT],
    }],
}

# 61 riadkov * 2 stlpce = 122 hodnot. Realne su len pozicie 0,1 (riadok 0)
# a 120,121 (riadok 60) - overene naživo na Novogal a.s.
POD_DATA = [""] * 122
POD_DATA[0], POD_DATA[1] = "29301899", "23126353"
POD_DATA[120], POD_DATA[121] = "4888868", "570743"

POD_VYKAZ = {
    "id": 10110916,
    "idSablony": 699,
    "obsah": {"tabulky": [{"nazov": {"sk": ruz.NAZOV_TABULKY_VYKAZ}, "data": POD_DATA}]},
}


# ── Testy ────────────────────────────────────────────────────────────────

hlavicka("Uc MUJ (LoveHome s.r.o., FY2025) - realne data")
vysledok = ruz.dekoduj_vykaz(MUJ_VYKAZ, MUJ_SABLONA)
assert vysledok is not None, "dekoder nemal vratit None"
assert vysledok["obrat"] == 9.0, vysledok
assert vysledok["vysledok_hospodarenia"] == -331.0, vysledok
print("OK:", vysledok)

hlavicka("Uc POD (Novogal a.s.) - realne data na spravnych poziciach")
vysledok = ruz.dekoduj_vykaz(POD_VYKAZ, POD_SABLONA)
assert vysledok is not None
assert vysledok["obrat"] == 29301899.0, vysledok
assert vysledok["vysledok_hospodarenia"] == 4888868.0, vysledok
print("OK:", vysledok)

hlavicka("Neznama/nesediaca sablona -> None, ziadne hadanie")
zla_sablona = {
    "tabulky": [{
        "nazov": {"sk": ruz.NAZOV_TABULKY_VYKAZ},
        "hlavicka": MUJ_SABLONA["tabulky"][0]["hlavicka"],
        "riadky": [riadok("len jeden riadok")],  # nesedi s dlzkou MUJ_DATA
    }],
}
vysledok = ruz.dekoduj_vykaz(MUJ_VYKAZ, zla_sablona)
assert vysledok is None, "pri nesediacej dlzke dat sa nesmie hadat"
print("OK: vratilo None namiesto hadania")

hlavicka("Vykaz bez tabulky 'Vykaz ziskov a strat' -> None")
prazdny_vykaz = {"obsah": {"tabulky": []}}
vysledok = ruz.dekoduj_vykaz(prazdny_vykaz, MUJ_SABLONA)
assert vysledok is None
print("OK")

hlavicka("Vykaz s 'obsah' bez kluca 'tabulky' -> None, nie KeyError (22.9.2026)")
# Realny pripad z produkcie: aspon 5 ICO malo vykaz, kde "obsah" existoval,
# ale bez "tabulky" vobec - povodny kod pristupoval vykaz["obsah"]["tabulky"]
# natvrdo a spadol na KeyError('tabulky'), co vyhodilo cele ICO z behu.
vykaz_bez_tabuliek = {"id": 1, "idSablony": 687, "obsah": {"nieco_ine": []}}
vysledok = ruz.dekoduj_vykaz(vykaz_bez_tabuliek, MUJ_SABLONA)
assert vysledok is None
print("OK")

hlavicka("Vykaz uplne bez kluca 'obsah' -> None, nie KeyError")
vykaz_bez_obsahu = {"id": 2, "idSablony": 687}
vysledok = ruz.dekoduj_vykaz(vykaz_bez_obsahu, MUJ_SABLONA)
assert vysledok is None
print("OK")

hlavicka("vyber_najnovsie_zavierky_po_rokoch: duplicity v ramci roka")
zavierky = [
    {"id": 100, "obdobieDo": "2024-12"},
    {"id": 105, "obdobieDo": "2024-12"},  # ten isty rok, vyssie id -> vyhrava
    {"id": 90, "obdobieDo": "2023-12"},
]
podla_roka = ruz.vyber_najnovsie_zavierky_po_rokoch(zavierky)
assert podla_roka[2024]["id"] == 105, podla_roka
assert podla_roka[2023]["id"] == 90, podla_roka
print("OK:", {r: z["id"] for r, z in podla_roka.items()})

hlavicka("nace_nazov(): staticka tabulka zo suboru pipeline/data/sk_nace.json")
assert ruz.nace_nazov("73110") == "Reklamné agentúry", ruz.nace_nazov("73110")
assert ruz.nace_nazov("01470") == "Chov hydiny", ruz.nace_nazov("01470")
assert ruz.nace_nazov("99999") is None
print("OK")

print("\nVsetky testy prebehli.")
