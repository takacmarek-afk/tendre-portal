"""Audit 27. 9. 2026 (P0.3): obec je sama sebe miestom; ziadatel, ktory uz
dotaciu dostal (aj pri vymenenych stranach v CRZ), medzi ziadatelmi nie je."""
import pandas as pd

import regiony
import ziadatelia


def test_obec_nie_je_posta_inej_obce():
    df = pd.DataFrame({"authority_name": ["Obec Sliepkovce", "Základná škola, Hlavná 5, Prešov"],
                       "authority_address": ["Sliepkovce 34, 072 36 Lastomír", "Hlavná 5, 080 01 Prešov"]})
    out = regiony.doplnit(df)
    assert list(out["mesto"]) == ["Sliepkovce", "Prešov"]
    assert out["kraj"].iat[0] == "Košický kraj"


def _riadok(**kw):
    zaklad = {"sector": "INE", "authority_name": "", "authority_cin": "", "authority_address": "",
              "supplier_name": "", "supplier_cin": "", "subject": "", "price_total": 0,
              "signed_on": "", "id": 1}
    zaklad.update(kw)
    return zaklad


def test_sena_s_dotaciou_pri_vymenenych_stranach_vypadne():
    df = pd.DataFrame([
        _riadok(id=11332551, authority_name="Obec Seňa", authority_cin="00324698",
                authority_address="Seňa 1, 044 58 Seňa",
                supplier_name="Poradenská kancelária pre štrukturálne fondy, s. r. o.",
                supplier_cin="56803966",
                subject="Vypracovanie a podanie žiadosti o nenávratný finančný príspevok",
                price_total=3000, signed_on="2025-09-19"),
        # dotacia s vymenenymi stranami: ministerstvo v poli dodavatela
        _riadok(id=12505763, sector="DOTACIE_NFP", authority_name="Obec Seňa",
                authority_cin="00324698", supplier_name="Ministerstvo financií Slovenskej republiky",
                supplier_cin="00151742", subject="Zmluva o poskytnutí dotácie",
                price_total=33000, signed_on="2026-06-23"),
        # ina obec bez dotacie ostava
        _riadok(id=3, authority_name="Obec Kristy", authority_cin="00331601",
                authority_address="Kristy 1, 073 01 Sobrance",
                supplier_name="Grant Projekt s.r.o.", supplier_cin="12345678",
                subject="Vypracovanie žiadosti o nenávratný finančný príspevok",
                price_total=2500, signed_on="2026-03-01"),
    ])
    out = ziadatelia.z_contracts(df, dnes=pd.Timestamp("2026-09-28").date())
    assert list(out["obec"]) == ["Obec Kristy"]
    assert out["mesto"].iat[0] == "Kristy"
