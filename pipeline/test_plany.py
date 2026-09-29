"""Jedna verzia pravdy o plánoch (audit 27. 9. 2026, P1.1).

public/plany.js je zdroj. Statické stránky majú čísla v texte natvrdo
(aby fungovali bez JavaScriptu) — tento test ich porovná so zdrojom
a zlyhá, keď sa niečo rozíde. Spustenie: python test_plany.py
"""
import json
import re
from pathlib import Path

KOREN = Path(__file__).resolve().parent.parent
PUB = KOREN / "public"


def plany():
    t = (PUB / "plany.js").read_text(encoding="utf-8")
    m = re.search(r"window\.PLANY\s*=\s*(\{.*\});", t, re.S)
    return json.loads(m.group(1))


def _eur(n):
    """340 -> '340', 2490 -> '2&nbsp;490' (tak, ako je to v HTML)."""
    s = f"{n:,}".replace(",", "&nbsp;")
    return s


def _stranky():
    return {p.name: p.read_text(encoding="utf-8")
            for p in [PUB / "index.html", PUB / "cennik.html", PUB / "prihlasenie.html", PUB / "app.html"]}


def test_skusobna_doba_vsade_rovnaka():
    dni = plany()["skusobneDni"]
    for meno, t in _stranky().items():
        for m in re.finditer(r"(\d+)\s*(?:dni|dní|dňa)\s+zadarmo", t):
            assert int(m.group(1)) == dni, f"{meno}: '{m.group(0)}' nesedí s plany.js ({dni})"
        assert not re.search(r"\d-dňov\w* skúšk", t), f"{meno}: stará formulácia skúšky"
        assert "otvoreného obdobia" not in t.replace("otvoreneho obdobia", ""), \
            f"{meno}: 'otvorené obdobie' namiesto {dni} dní"
        assert "bez skúšobnej lehoty" not in t, f"{meno}: 'bez skúšobnej lehoty' odporuje {dni} dňom"


def test_ceny_v_cenniku():
    t = _stranky()["cennik.html"]
    for kod in ("start", "growth", "team"):
        p = plany()["plany"][kod]
        assert f">{_eur(p['mesiac'])}&nbsp;€<" in t, f"cenník: mesačná cena {kod} nesedí"
        assert f"alebo {_eur(p['rok'])}&nbsp;€ ročne" in t, f"cenník: ročná cena {kod} nesedí"
    # Poradca: dočasne "Zadarmo" (zakladajúci člen, rozhodnutie 29.9.2026),
    # nie aktívna cena ako pri ostatných — no budúca cena z plany.js musí
    # niekde v karte ostať ako referencia, nech sa nestratí pri spoplatnení.
    p = plany()["plany"]["poradca"]
    usek_poradca = t.split('>Poradca<', 1)[1][:600]
    assert "Zadarmo" in usek_poradca, "cenník: Poradca už nemá text 'Zadarmo'"
    assert str(p["mesiac"]) in usek_poradca, \
        f"cenník: budúca mesačná cena poradca ({p['mesiac']}) sa v karte nespomína"
    assert _eur(p["rok"]) in usek_poradca, \
        f"cenník: budúca ročná cena poradca ({p['rok']}) sa v karte nespomína"
    assert "alebo ~" not in t, "cenník: cena s vlnovkou"


def test_ceny_v_databaze():
    sql = (KOREN / "supabase" / "50_plany_14_dni.sql").read_text(encoding="utf-8")
    for kod, p in plany()["plany"].items():
        for obdobie in ("mesiac", "rok"):
            assert re.search(rf"\('{kod}',\s*'{obdobie}',\s*{p[obdobie]}\.00\)", sql), \
                f"50_plany_14_dni.sql: {kod}/{obdobie} nesedí s plany.js"
    assert f"interval '{plany()['skusobneDni']} days'" in sql


def test_ziadne_podkopavanie_ceny():
    for meno, t in _stranky().items():
        for zakazane in ("Najobľúbenejšia", "cenník dolaďujeme", "radi si od vás vypočujeme",
                         "až 2 roky skôr", "Prístup je jeden na firmu"):
            assert zakazane not in t, f"{meno}: '{zakazane}'"


if __name__ == "__main__":
    for meno, f in list(globals().items()):
        if meno.startswith("test_") and callable(f):
            f()
            print("OK", meno)
