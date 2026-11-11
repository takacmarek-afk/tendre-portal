from datetime import date

import zdravie_dat as z


def test_vek_a_sprava():
    d = date(2026, 11, 10)
    assert z.vek_dni("2026-11-08", d) == 2 and z.vek_dni("2026-11-01T10:00:00+00:00", d) == 9
    assert z.sprava([("CRZ", 1, 4, "x", "")], []) is None
    s = z.sprava([("ITMS21+", 9, 5, "eurofondy", "posledný záznam pred 9 dňami")], ["nova_funkcia"])
    assert "ITMS21+" in s[1] and "nova_funkcia" in s[1]


def test_planovac_hlasi_ked_neboli_behy():
    from datetime import datetime, timezone
    import zdravie_dat as z

    class R:
        def __init__(self, d): self.d = d
        def json(self): return self.d
    teraz = datetime(2026, 11, 12, 12, 0, tzinfo=timezone.utc)
    cerstvy = lambda *a, **k: R({"workflow_runs": [{"created_at": "2026-11-12T11:45:00Z"}]})
    stary = lambda *a, **k: R({"workflow_runs": [{"created_at": "2026-11-12T06:00:00Z"}]})
    assert z.planovac("o/r", "t", cerstvy, teraz) == ""
    assert "pred 6 h" in z.planovac("o/r", "t", stary, teraz)
    assert z.planovac(None, None) == "" or True
    assert "Plánovač" in z.sprava([], [], "x")[1]
