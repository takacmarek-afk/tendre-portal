"""obce_demografia: JSON-stat -> pocet obyvatelov (spolu = najvacsia bunka)."""
from obce_demografia import jsonstat_maxima, norm, NRO_OKRESY


def test_jsonstat_pole_aj_slovnik():
    dims = {"nuts": {"category": {"index": {"SK0328516741": 0, "SK0328516767": 1, "SK0": 2}}},
            "rok": {"category": {"index": {"2025": 0}}},
            "pohl": {"category": {"index": {"m": 0, "z": 1, "spolu": 2}}}}
    d = {"id": ["nuts", "rok", "pohl"], "size": [3, 1, 3], "dimension": dims,
         "value": [120, 130, 250, 4000, 4200, 8200, 1, 1, 2]}
    assert jsonstat_maxima(d) == {"516741": 250, "516767": 8200}
    d["value"] = {"0": 120, "2": 250, "5": 8200}
    assert jsonstat_maxima(d) == {"516741": 250, "516767": 8200}


def test_nro_normalizacia():
    assert norm("Okres Košice - okolie") == norm("Košice - okolie")
    assert len(NRO_OKRESY) == 19
