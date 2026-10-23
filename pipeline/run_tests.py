"""Spusti VSETKY testy v pipeline/ bez pytestu.

    python pipeline/run_tests.py          # (PYTHONUTF8=1 na Windowse)

Preco: cast testov su len funkcie test_* bez vlastneho spustaca. Prikaz
`python test_x.py` ich neodpali a tvari sa, ze preslo. Tento skript importuje
kazdy test_*.py, spusti kazdu funkciu test_* (aj subory s vlastnym spustacom)
a skonci s chybou, ak cokolvek zlyha. Podporuje fixture `monkeypatch`.
Rovnaky vysledok da `python -m pytest pipeline`, ak je pytest nainstalovany.
"""
import importlib
import inspect
import os
import sys
import traceback
from pathlib import Path

TU = Path(__file__).resolve().parent


class MonkeyPatch:
    def __init__(self):
        self._spat = []

    def setattr(self, obj, meno, hodnota=None, raising=True):
        if isinstance(obj, str):            # monkeypatch.setattr("modul.atribut", hodnota)
            modul, _, atr = obj.rpartition(".")
            obj, meno, hodnota = importlib.import_module(modul), atr, meno
        self._spat.append(("attr", obj, meno, getattr(obj, meno, None)))
        setattr(obj, meno, hodnota)

    def setenv(self, meno, hodnota):
        self._spat.append(("env", None, meno, os.environ.get(meno)))
        os.environ[meno] = str(hodnota)

    def delenv(self, meno, raising=True):
        self._spat.append(("env", None, meno, os.environ.get(meno)))
        os.environ.pop(meno, None)

    def undo(self):
        for druh, obj, meno, stara in reversed(self._spat):
            if druh == "attr":
                setattr(obj, meno, stara)
            elif stara is None:
                os.environ.pop(meno, None)
            else:
                os.environ[meno] = stara
        self._spat.clear()


def main():
    os.chdir(TU)
    sys.path.insert(0, str(TU))
    vzor = sys.argv[1] if len(sys.argv) > 1 else ""
    ok = zle = 0
    for subor in sorted(TU.glob("test_*.py")):
        if vzor and vzor not in subor.name:
            continue
        try:
            modul = importlib.import_module(subor.stem)
        except Exception:
            zle += 1
            print(f"FAIL {subor.name}: import\n{traceback.format_exc(limit=3)}")
            continue
        for meno, f in inspect.getmembers(modul, inspect.isfunction):
            if not meno.startswith("test_") or f.__module__ != modul.__name__:
                continue
            mp = MonkeyPatch()
            try:
                parametre = inspect.signature(f).parameters
                f(**{p: mp for p in parametre if p == "monkeypatch"})
                ok += 1
            except Exception:
                zle += 1
                print(f"FAIL {subor.name}::{meno}\n{traceback.format_exc(limit=4)}")
            finally:
                mp.undo()
    print(f"\n{ok}/{ok + zle} testov preslo")
    return 1 if zle else 0


if __name__ == "__main__":
    sys.exit(main())
