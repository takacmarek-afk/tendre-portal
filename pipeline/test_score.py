"""Testy pre score.py — zamerne LEN pre novu vrstvu #13 (17.9.2026,
"sanca na vyhru"). Zvysok score.py (skore, riziko, klasifikacia zakaziek)
je uz nepriamo pokryty cez test_pipeline.py::prilezitosti().

Cielom tychto testov je overit presne tie dve veci, ktore boli hlavnym
rizikom pri navrhu #13:
  1. GDPR: zivnostnik (fyzicka osoba) sa NESMIE objavit v
     top_dodavatel_cin/top_dodavatel_pravnicky, aj ked v historii
     jednoznacne vyhrava najviac.
  2. Povodne top_dodavatel/podiel_top_dodavatela (bez GDPR filtra, podla
     mena) OSTAVAJU presne take, ako boli pred #13 — pouziva ich uz
     kalibrovana _riziko()/_skore() a nesmu sa ziadnou upravou zmenit.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pandas as pd
import score


def _rec(cin, sector, supplier_name, supplier_cin, price=10000):
    return {
        "authority_cin": cin, "sector": sector,
        "supplier_name": supplier_name, "supplier_cin": supplier_cin,
        "price_total": price,
    }


def _df(riadky):
    return pd.DataFrame(riadky)


# ── 1. Zivnostnik dominuje poctom, ale nesmie sa objavit v _pravnicky poli ──
riadky = (
    [_rec("A1", "IT", "Jan Novak", "10000001") for _ in range(6)] +   # zivnostnik, 6x
    [_rec("A1", "IT", "Firma s.r.o.", "20000002") for _ in range(2)]  # firma, 2x
)
h = score._historia(_df(riadky))
r = h.iloc[0]
print(f"1) povodne top_dodavatel={r['top_dodavatel']!r} (ocakavane: Jan Novak, "
      f"zivnostnik dominuje poctom) | top_dodavatel_pravnicky="
      f"{r['top_dodavatel_pravnicky']!r} (ocakavane: Firma s.r.o.)")
assert r["top_dodavatel"] == "Jan Novak", "povodne pole sa nesmie menit"
assert r["podiel_top_dodavatela"] == 0.75, "povodny podiel (6 z 8) sa nesmie menit"
assert r["top_dodavatel_pravnicky"] == "Firma s.r.o.", (
    "zivnostnik unikol do GDPR-bezpecneho pola")
assert r["top_dodavatel_cin"] == "20000002"
assert r["podiel_top_dodavatela_pravnicky"] == 1.0, (
    "medzi pravnickymi osobami je Firma s.r.o. jedina, podiel musi byt 100 %")

# ── 2. Ziadna pravnicka osoba v historii -> vsetky nove polia None, ────────
#    povodne polia normalne funguju (regresia oproti stavu pred #13).
riadky2 = [_rec("A2", "STAVEBNICTVO", "Peter Horvath", "30000003") for _ in range(4)]
h2 = score._historia(_df(riadky2))
r2 = h2.iloc[0]
print(f"2) len zivnostnik v historii -> top_dodavatel_cin={r2['top_dodavatel_cin']!r}, "
      f"povodne top_dodavatel={r2['top_dodavatel']!r}")
assert r2["top_dodavatel_cin"] is None
assert r2["top_dodavatel_pravnicky"] is None
assert r2["podiel_top_dodavatela_pravnicky"] is None
assert r2["top_dodavatel"] == "Peter Horvath", "povodne pole funguje aj bez pravnickych osob"

# ── 3. Rovnake ICO, dve rozne varianty nazvu -> pocitaju sa ako JEDEN ──────
#    dodavatel (podla CIN, nie podla mena) — presne preto CIN, nie meno.
riadky3 = (
    [_rec("A3", "DOPRAVA", "ABC s.r.o.", "40000004") for _ in range(3)] +
    [_rec("A3", "DOPRAVA", "ABC, s. r. o.", "40000004") for _ in range(2)] +  # ine formatovanie, ten isty CIN
    [_rec("A3", "DOPRAVA", "XYZ a.s.", "50000005") for _ in range(2)]
)
h3 = score._historia(_df(riadky3))
r3 = h3.iloc[0]
print(f"3) rovnake ICO rozne meno -> top_dodavatel_cin={r3['top_dodavatel_cin']!r}, "
      f"podiel={r3['podiel_top_dodavatela_pravnicky']} (ocakavane 5/7=0.71)")
assert r3["top_dodavatel_cin"] == "40000004"
assert r3["podiel_top_dodavatela_pravnicky"] == round(5 / 7, 2)

# ── 4. prazdny vstup -> prazdny DataFrame so vsetkymi ocakavanymi stlpcami ──
h4 = score._historia(_df([]).assign(authority_cin=[], sector=[], supplier_name=[],
                                     supplier_cin=[], price_total=[]))
ocakavane = {"authority_cin", "sector", "historicky_pocet", "pocet_dodavatelov",
             "priemerna_hodnota", "top_dodavatel", "podiel_top_dodavatela",
             "top_dodavatel_cin", "top_dodavatel_pravnicky",
             "podiel_top_dodavatela_pravnicky"}
print(f"4) prazdny vstup -> stlpce={set(h4.columns) == ocakavane}")
assert set(h4.columns) == ocakavane

print("VSETKY TESTY PRESLI (score._historia, #13)")


# ── 5. rozdel_na_sancu: NEZNAME/chybajuce riziko sa nezapisuju ─────────────
t = pd.DataFrame([
    {"contract_id": 1, "supplier_cin": "1", "top_dodavatel_cin": "2",
     "top_dodavatel_pravnicky": "X s.r.o.", "podiel_top_dodavatela_pravnicky": 0.5,
     "riziko": "VYSOKE", "skore": 80},
    {"contract_id": 2, "supplier_cin": "1", "top_dodavatel_cin": None,
     "top_dodavatel_pravnicky": None, "podiel_top_dodavatela_pravnicky": None,
     "riziko": "NEZNAME", "skore": 50},
    {"contract_id": 3, "supplier_cin": "1", "top_dodavatel_cin": None,
     "top_dodavatel_pravnicky": None, "podiel_top_dodavatela_pravnicky": None,
     "riziko": None, "skore": 40},
])
zvysok, sanca = score.rozdel_na_sancu(t)
print(f"5) rozdel_na_sancu: {len(sanca)} riadkov v sanca (ocakavane 1, len VYSOKE), "
      f"riziko v zvysku: {'riziko' in zvysok.columns}, "
      f"sanca-stlpce v zvysku: {score.SANCA_STLPCE.__class__ and [c for c in score.SANCA_STLPCE if c in zvysok.columns and c not in ('contract_id', 'riziko')]}")
assert len(sanca) == 1
assert sanca.iloc[0]["contract_id"] == 1
assert "riziko" in zvysok.columns, "riziko je FREE stlpec, nesmie sa odobrat"
assert "contract_id" in zvysok.columns
for stlpec in ("supplier_cin", "top_dodavatel_cin", "top_dodavatel_pravnicky",
               "podiel_top_dodavatela_pravnicky"):
    assert stlpec not in zvysok.columns, f"{stlpec} unikol do verejnej tabulky"

print("VSETKY TESTY PRESLI (score.rozdel_na_sancu, #13)")
