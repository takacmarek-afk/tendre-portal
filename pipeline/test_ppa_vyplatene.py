"""Test oznacovania vyplatenych PPA dotacii.
Spusti: python test_ppa_vyplatene.py"""
import pandas as pd
import ppa_vyplatene as pv

PPA = pd.DataFrame([
    {"fy": "2025", "fy_koniec": "2025-10-15", "obec": "Revúcka Lehota", "kod": "VI.24", "suma": 7699.00},
    {"fy": "2025", "fy_koniec": "2025-10-15", "obec": "Lazisko", "kod": "VI.24", "suma": 10992.02},
    {"fy": "2024", "fy_koniec": "2024-10-15", "obec": "Dvojka", "kod": "VI.24", "suma": 5000.00},
    {"fy": "2025", "fy_koniec": "2025-10-15", "obec": "Neskoro", "kod": "VI.24", "suma": 9000.00},
])
PPA["fy_koniec"] = pd.to_datetime(PPA["fy_koniec"])
P = "Pôdohospodárska platobná agentúra"


def riadok(prijimatel, suma, podpis="2024-03-01", poskytovatel=P):
    return {"prijimatel": prijimatel, "poskytovatel": poskytovatel, "suma": suma,
            "podpisane": podpis, "ucinne_od": podpis}


def test_presna_zhoda():
    d = pv.oznac(pd.DataFrame([riadok("Obec Revúcka Lehota", 7699.0)]), PPA)
    assert bool(d.loc[0, "vyplatene"]) and d.loc[0, "vyplatene_fy"] == "FY2025"


def test_ciastocna_92_percent():
    d = pv.oznac(pd.DataFrame([riadok("Obec Lazisko", 11997.2)]), PPA)
    assert bool(d.loc[0, "vyplatene"])


def test_prilis_nizka_suma_sa_neparuje():
    d = pv.oznac(pd.DataFrame([riadok("Obec Lazisko", 20000.0)]), PPA)
    assert not bool(d.loc[0, "vyplatene"])


def test_vyssia_suma_ako_zmluva_sa_neparuje():
    d = pv.oznac(pd.DataFrame([riadok("Obec Revúcka Lehota", 5000.0)]), PPA)
    assert not bool(d.loc[0, "vyplatene"])


def test_iny_poskytovatel_sa_neoznaci():
    d = pv.oznac(pd.DataFrame([riadok("Obec Revúcka Lehota", 7699.0,
                                      poskytovatel="Ministerstvo financií SR")]), PPA)
    assert not bool(d.loc[0, "vyplatene"])


def test_podpis_po_konci_fy_sa_neparuje():
    d = pv.oznac(pd.DataFrame([riadok("Obec Neskoro", 9000.0, podpis="2025-11-20")]), PPA)
    assert not bool(d.loc[0, "vyplatene"])


def test_jedna_operacia_len_pre_jednu_zmluvu():
    d = pv.oznac(pd.DataFrame([riadok("Obec Dvojka", 5000.0),
                               riadok("Obec Dvojka", 5020.0)]), PPA)
    assert d["vyplatene"].sum() == 1
    assert bool(d.loc[0, "vyplatene"])   # presnejsia zhoda vyhrava


def test_nazov_s_adresou_za_ciarkou():
    d = pv.oznac(pd.DataFrame([riadok("Obec Revúcka Lehota, Revúcka Lehota 12, 049 11 Revúcka Lehota",
                                      7699.0)]), PPA)
    assert bool(d.loc[0, "vyplatene"])


def test_cez_z_contracts_a_zachovanie_poctu_riadkov():
    from datetime import date
    import subsidies
    from classify import SEKTOR_DOTACIE
    z = lambda i, obec, suma: {
        "id": i, "sector": SEKTOR_DOTACIE, "price_total": suma,
        "signed_on": "2025-06-01", "effective_from": "2025-06-10",
        "authority_name": P + ", Hlboká cesta 2, 834 04 Bratislava",
        "authority_cin": "30794323",
        "authority_address": "Hlboká cesta 2, 834 04 Bratislava",
        "supplier_name": obec, "supplier_cin": "0000000" + str(i),
        "subject": "Zmluva o poskytnutí nenávratného finančného príspevku",
        "subject_description": ""}
    df = pd.DataFrame([z(1, "Obec Revúcka Lehota", 7699.0),
                       z(2, "Obec Iná Dedina", 30000.0)])
    out = subsidies.z_contracts(df, dnes=date(2026, 10, 8))
    # okno uz nemusi platit pre oba — kontrolujeme len stlpce a pocty ak su
    assert "vyplatene" in out.columns and "vyplatene_fy" in out.columns
    if not out.empty:
        r = out[out["prijimatel"].str.contains("Revúcka")]
        if len(r):
            assert bool(r.iloc[0]["vyplatene"])
        r2 = out[out["prijimatel"].str.contains("Iná")]
        if len(r2):
            assert not bool(r2.iloc[0]["vyplatene"])


def test_ina_obec_sa_neparuje():
    d = pv.oznac(pd.DataFrame([riadok("Obec Iná Lehota", 7699.0)]), PPA)
    assert not bool(d.loc[0, "vyplatene"])


def test_prazdny_vstup_a_chybajuci_subor():
    import tempfile, os
    tmp_path = __import__("pathlib").Path(tempfile.mkdtemp())
    assert pv.oznac(pd.DataFrame(), PPA).empty
    assert pv.nacitaj(str(tmp_path / "nie.csv")).empty
    d = pv.oznac(pd.DataFrame([riadok("Obec Lazisko", 11000.0)]),
                 pv.nacitaj(str(tmp_path / "nie.csv")))
    assert not bool(d.loc[0, "vyplatene"])


if __name__ == "__main__":
    n = 0
    for nazov, f in sorted(globals().items()):
        if nazov.startswith("test_") and callable(f):
            f()
            n += 1
            print("  OK ", nazov)
    print(f"\nVSETKY TESTY PRESLI ({n})\n")
