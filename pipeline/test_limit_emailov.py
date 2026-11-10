from datetime import datetime, timezone

import limit_emailov as le


class R:
    def __init__(self, d): self.d = d
    def raise_for_status(self): pass
    def json(self): return self.d


def test_pocty_a_strankovanie():
    teraz = datetime(2026, 11, 10, 12, tzinfo=timezone.utc)
    s1 = {"has_more": True, "data": [{"id": "a", "created_at": "2026-11-10 10:00:00.123456+00"},
                                      {"id": "b", "created_at": "2026-11-09 08:00:00+00"}]}
    s2 = {"has_more": True, "data": [{"id": "c", "created_at": "2026-10-20T08:00:00Z"},
                                      {"id": "d", "created_at": "2026-09-01 08:00:00+00"}]}
    stranky = iter([s1, s2])
    assert le.spocitaj("k", teraz, _get=lambda *a, **k: R(next(stranky))) == (1, 3)


def test_prah():
    assert le.sprava(69, 2000) is None
    assert le.sprava(70, 0) and le.sprava(0, 2100)
