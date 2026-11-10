from datetime import date

import zdravie_dat as z


def test_vek_a_sprava():
    d = date(2026, 11, 10)
    assert z.vek_dni("2026-11-08", d) == 2 and z.vek_dni("2026-11-01T10:00:00+00:00", d) == 9
    assert z.sprava([("CRZ", 1, 4, "x", "")], []) is None
    s = z.sprava([("ITMS21+", 9, 5, "eurofondy", "posledný záznam pred 9 dňami")], ["nova_funkcia"])
    assert "ITMS21+" in s[1] and "nova_funkcia" in s[1]
