"""Testy idempotencie notifikacii dopytov (audit 6. 10. 2026, B2).
Spustenie: PYTHONPATH=pipeline python pipeline/test_posli_dopyt_email.py"""
import sys, os, types
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if "supabase" not in sys.modules:
    try:
        import supabase  # noqa: F401
    except ImportError:
        fake = types.ModuleType("supabase")
        fake.create_client = lambda *a, **k: None
        sys.modules["supabase"] = fake

import posli_dopyt_email as pd


class _Odp:
    def __init__(self, data): self.data = data


class _Q:
    def __init__(self, sb, tab):
        self.sb, self.tab, self.f, self.patch, self.cil = sb, tab, [], None, None

    def select(self, *a, **k): return self
    def eq(self, c, v):
        if self.patch is not None: self.cil = (c, v)
        else: self.f.append((c, v))
        return self
    def limit(self, n): return self
    def update(self, p): self.patch = p; return self
    def execute(self):
        rows = self.sb.t[self.tab]
        if self.patch is not None:
            for r in rows:
                if r.get(self.cil[0]) == self.cil[1]: r.update(self.patch)
            return _Odp([])
        return _Odp([dict(r) for r in rows if all(r.get(c) == v for c, v in self.f)])


class _Sb:
    def __init__(self, t): self.t = t
    def table(self, n): return _Q(self, n)


def _sb(n_poradcov=2):
    return _Sb({
        "dopyty": [{"id": "d1", "obec_nazov": "Testovo", "kraj": "BA", "stav": "otvoreny", "nazov": "N",
                    "poradcovia_notifikovani": False}],
        "poradcovia_profily": [{"kontakt_email": f"p{i}@x.sk", "nazov": f"P{i}", "kraje_posobenia": [], "aktivny": True}
                               for i in range(n_poradcov)],
    })


def _s_posli(vysledky):
    it = iter(vysledky)
    pd.PAUZA_S = 0
    orig = pd.posli
    pd.posli = lambda *a, **k: next(it)
    return orig


def test_vsetko_ok_oznaci():
    sb = _sb(); orig = _s_posli([True, True])
    try: p, z = pd.posli_poradcom(sb, "k", False)
    finally: pd.posli = orig
    assert (p, z) == (2, 0) and sb.t["dopyty"][0]["poradcovia_notifikovani"] is True


def test_ciastocny_uspech_oznaci():
    sb = _sb(); orig = _s_posli([True, False])
    try: pd.posli_poradcom(sb, "k", False)
    finally: pd.posli = orig
    assert sb.t["dopyty"][0]["poradcovia_notifikovani"] is True


def test_uplny_vypadok_neoznaci():
    sb = _sb(); orig = _s_posli([False, False])
    try: p, z = pd.posli_poradcom(sb, "k", False)
    finally: pd.posli = orig
    assert (p, z) == (0, 2) and sb.t["dopyty"][0]["poradcovia_notifikovani"] is False


def test_komu_neoznaci_nikdy():
    sb = _sb(); orig = _s_posli([True])
    try: pd.posli_poradcom(sb, "k", False, obmedz_na="p0@x.sk")
    finally: pd.posli = orig
    assert sb.t["dopyty"][0]["poradcovia_notifikovani"] is False


def test_nasucho_neoznaci():
    sb = _sb(); orig = _s_posli([True, True])
    try: pd.posli_poradcom(sb, "k", True)
    finally: pd.posli = orig
    assert sb.t["dopyty"][0]["poradcovia_notifikovani"] is False


if __name__ == "__main__":
    t = [f for n, f in list(globals().items()) if n.startswith("test_")]
    for f in t:
        f(); print(f.__name__, "OK")
    print(f"VSETKY TESTY PRESLI ({len(t)})")
