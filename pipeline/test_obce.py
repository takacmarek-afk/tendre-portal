"""Test obce.sprostredkovatelia() — cistenie zoznamu (audit P3.5, 28.9.2026).

Marek 28.9.2026 rucne overil, ze 4 firmy v zozname "Kto obciam ziadosti
pise" nie su poradcovia (dostali sa tam sirokym regexom na predmet zmluvy),
ze dve zmluvy tej istej firmy (Diervilla) sa netriedia spolu, lebo jednej
chyba ICO, a ze jedna firma ma adresu vlepenu priamo do nazvu. Tento test
overuje opravu vsetkych troch vecí na malej syntetickej vzorke.
Spustenie: python test_obce.py
"""
from datetime import date

import pandas as pd

import obce


def z(obec, firma, ico, predmet="Vypracovanie žiadosti o poskytnutie dotácie",
      suma=1500, datum="2026-06-01", adresa="Hlavná 1, 040 01 Košice"):
    """Zmluva medzi obcou (objednavatel) a firmou (sprostredkovatel)."""
    return {"authority_name": obec, "authority_address": adresa,
            "supplier_name": firma, "supplier_cin": ico,
            "subject": predmet, "price_total": suma, "signed_on": datum}


def test_vylucene_ico_von():
    df = pd.DataFrame([
        z("Obec Testov", "SOLARPARK KOMÁRNO s.r.o.", "45729735"),
        z("Obec Testov", "Ján Poradca s.r.o.", "11112222"),
    ])
    out = obce.sprostredkovatelia(df)
    mena = set(out["sprostredkovatel"])
    assert "SOLARPARK KOMÁRNO s.r.o." not in mena, mena
    assert "Ján Poradca s.r.o." in mena, mena


def test_podozrivo_nizka_cena_von_ale_nula_ostava():
    df = pd.DataFrame([
        # Pod MIN_CENA_SPROSTREDKOVATEL, ale nad nulou -> von.
        z("Obec A", "Lacná Firma s.r.o.", "22223333", suma=49),
        # Presne 0 (chybajuci udaj v CRZ, nie podozrivo nizka cena) -> ostava.
        z("Obec B", "Nulová Firma s.r.o.", "33334444", suma=0),
        # Bezna cena -> ostava.
        z("Obec C", "Normálna Firma s.r.o.", "44445555", suma=1500),
    ])
    out = obce.sprostredkovatelia(df)
    mena = set(out["sprostredkovatel"])
    assert "Lacná Firma s.r.o." not in mena, mena
    assert "Nulová Firma s.r.o." in mena, mena
    assert "Normálna Firma s.r.o." in mena, mena


def test_diervilla_chybajuce_ico_sa_zluci():
    df = pd.DataFrame([
        z("Obec X", "Diervilla s.r.o", None, suma=1000),
        z("Obec Y", "Diervilla, spol. s r.o.", "36506001", suma=1200),
    ])
    out = obce.sprostredkovatelia(df)
    assert len(out) == 1, f"malo sa zlucit do 1 riadku, je {len(out)}: {out['sprostredkovatel'].tolist()}"
    assert out.loc[0, "obci"] == 2, out.loc[0, "obci"]
    assert out.loc[0, "supplier_cin"] == "36506001", out.loc[0, "supplier_cin"]


def test_adresa_sa_oreze_z_nazvu():
    df = pd.DataFrame([
        z("Obec Zlaté Moravce", "Projekty Európskych Spoločenstiev, s.r.o., "
          "1.mája 1091/37, 95301 Zlaté Moravce", "51698862"),
    ])
    out = obce.sprostredkovatelia(df)
    assert len(out) == 1
    nazov = out.loc[0, "sprostredkovatel"]
    assert nazov == "Projekty Európskych Spoločenstiev, s.r.o.", nazov


def test_dve_rozne_ico_sa_nezlucuju_len_kvoli_podobnemu_menu():
    # Dve NAOZAJ rozne firmy (rozne ICO) s takmer identickym nazvom sa
    # nesmu potichu zliat len preto, ze vyzeraju rovnako — to by bolo
    # tvrdenie, ktore sa neda overit v registri (viz projektovy princip
    # "pri pochybnosti nezverejnujeme/nezlucujeme").
    df = pd.DataFrame([
        z("Obec X", "Firma s.r.o.", "11111111"),
        z("Obec Y", "Firma s.r.o.", "22222222"),
    ])
    out = obce.sprostredkovatelia(df)
    assert len(out) == 2, f"malo zostat 2 rozne firmy, je {len(out)}"


if __name__ == "__main__":
    for meno, f in list(globals().items()):
        if meno.startswith("test_") and callable(f):
            f()
            print("OK", meno)
