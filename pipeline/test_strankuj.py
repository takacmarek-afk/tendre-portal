"""Test strankovania: PostgREST vracia najviac 1 000 riadkov na dotaz.
Spusti: python test_strankuj.py"""
from strankuj import vsetky


class _Odp:
    def __init__(self, data): self.data = data


def _dotaz(n):
    zdroj = [{"i": i} for i in range(n)]
    volania = []

    def fn(od, do):
        volania.append((od, do))
        # simulacia max_rows = 1000 na serveri
        return _Odp(zdroj[od:do + 1][:1000])
    return fn, volania


for n, ocak_volani in [(0, 1), (999, 1), (1000, 2), (1001, 2), (2500, 3), (3000, 4)]:
    fn, v = _dotaz(n)
    r = vsetky(fn)
    assert len(r) == n, (n, len(r))
    assert [x["i"] for x in r] == list(range(n)), n
    assert len(v) == ocak_volani, (n, v)
    print(f"  OK  {n} riadkov, {len(v)} volani")
print("\nVSETKY TESTY PRESLI\n")
