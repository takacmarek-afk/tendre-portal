"""Test retencia_udajov.py: vola RPC, nasucho nic nevola."""
import os
import sys
import types

# supabase balik nemusi byt nainstalovany: pre import staci stub.
if "supabase" not in sys.modules:
    m = types.ModuleType("supabase")
    m.create_client = lambda *a, **k: None
    sys.modules["supabase"] = m

import retencia_udajov as r  # noqa: E402


class _Res:
    def __init__(self, data):
        self.data = data

    def execute(self):
        return self


class _SB:
    def __init__(self):
        self.volania = []

    def rpc(self, nazov, *a):
        self.volania.append(nazov)
        return _Res({"navstevy": 3, "odber_obce_nepotvrdeny": 1})


def test_vola_rpc():
    sb = _SB()
    out = r.spusti(sb)
    assert sb.volania == ["retencia_udajov"]
    assert out["navstevy"] == 3
    print("OK test_vola_rpc")


def test_nasucho_nevola():
    sb = _SB()
    assert r.spusti(sb, nasucho=True) == {}
    assert sb.volania == []
    print("OK test_nasucho_nevola")


def test_bez_kluca_konci_chybou():
    for k in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"):
        os.environ.pop(k, None)
    assert r.main([]) == 2
    print("OK test_bez_kluca_konci_chybou")


if __name__ == "__main__":
    test_vola_rpc()
    test_nasucho_nevola()
    test_bez_kluca_konci_chybou()
