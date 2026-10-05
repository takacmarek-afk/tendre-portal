"""Testy pre posli_obec_mesacny_email.py (P3.2 B, mesacny email o obci,
29.9.2026).

Testuje len ciste funkcie a rozhodovaciu logiku (bez skutocnej DB/Resend) —
rovnaky princip ako ostatne male testy v pipeline (test_dopyt_email.py,
test_konkurencia.py, test_obce.py): overit logiku, nie infrastrukturu okolo
nej. Vyzaduje nainstalovany balik `supabase` (rovnaka podmienka ako
test_dopyt_email.py — beh v tomto pieskovisku bez sietoveho pristupu preto
nie je mozny, ale v GitHub Actions/lokalne u Mareka ano).
Spustenie: python test_obec_mesacny_email.py  (alebo pytest pipeline/)
"""
from datetime import datetime, timedelta, timezone

from posli_obec_mesacny_email import (
    _platny_email,
    _ma_sa_poslat,
    _obsah,
    MIN_DNI_MEDZI_EMAILMI,
)


# ── _platny_email ────────────────────────────────────────────────────────

def test_platny_email():
    dobre = ["a@b.sk", "starosta.sena@obec.sk", "x.y+z@firma.co"]
    zle = ["", None, "nieco", "a@b", "a b@c.sk", "@b.sk"]
    for e in dobre:
        assert _platny_email(e), f"malo prejst: {e!r}"
    for e in zle:
        assert not _platny_email(e), f"nemalo prejst: {e!r}"


# ── _ma_sa_poslat (mesacna kadencia) ────────────────────────────────────

def _pred(dni):
    return (datetime.now(timezone.utc) - timedelta(days=dni)).isoformat()


def test_ma_sa_poslat_este_nikdy():
    assert _ma_sa_poslat({"posledny_mesacny_email": None},
                          datetime.now(timezone.utc)) is True


def test_ma_sa_poslat_nedavno():
    dnes = datetime.now(timezone.utc)
    obec = {"posledny_mesacny_email": _pred(5)}
    assert _ma_sa_poslat(obec, dnes) is False


def test_ma_sa_poslat_presne_na_hranici():
    dnes = datetime.now(timezone.utc)
    obec = {"posledny_mesacny_email": _pred(MIN_DNI_MEDZI_EMAILMI + 1)}
    assert _ma_sa_poslat(obec, dnes) is True


def test_ma_sa_poslat_neplatny_format():
    # Neplatny/nespracovatelny format sa nema tichoo preskocit — radsej
    # poslat, nez navzdy stratit obec z rotacie kvoli chybnym datam.
    dnes = datetime.now(timezone.utc)
    assert _ma_sa_poslat({"posledny_mesacny_email": "nieco-zle"}, dnes) is True


# ── _obsah ────────────────────────────────────────────────────────────────

def test_obsah_prazdny_sa_neposiela():
    # Ziadne konciace zmluvy, ziadne bezice dotacie, ziadne programy ->
    # None, nikdy prazdny e-mail (rovnaka zasada ako tyzdenny posli_email.py).
    obec = {"nazov": "Seňa"}
    suhrn = {"pocet_konciacich": 0, "objem_konciacich": 0,
             "pocet_dotacii_bezi": 0, "objem_dotacii_bezi": 0}
    assert _obsah(obec, suhrn, []) is None


def test_obsah_ziadny_suhrn_ale_su_programy():
    # Ked RPC zlyha (suhrn=None), ale vseobecne programy pre obce existuju,
    # e-mail sa napriek tomu ma poslat.
    obec = {"nazov": "Seňa"}
    programy = [{"poskytovatel": "Envirofond", "zmluv_90d": 12,
                 "obci_90d": 9, "objem_90d": 500000,
                 "median_dotacie": 40000, "posledna_zmluva": "2026-09-01"}]
    obsah = _obsah(obec, None, programy)
    assert obsah is not None
    assert len(obsah["bloky"]) == 1
    assert obsah["bloky"][0]["titul"] == "Envirofond"


def test_obsah_konciace_zmluvy_a_dotacie():
    obec = {"nazov": "Seňa"}
    suhrn = {"pocet_konciacich": 3, "objem_konciacich": 45000,
             "pocet_dotacii_bezi": 2, "objem_dotacii_bezi": 120000}
    obsah = _obsah(obec, suhrn, [])
    assert obsah["titulok"] == "Novinky pre obec Seňa"
    assert len(obsah["bloky"]) == 2
    assert "3 zmluvy sa končia" in obsah["bloky"][0]["popis"]
    assert "2 dotácie, ktoré ešte bežia" in obsah["bloky"][1]["popis"]
    # Odhlasenie je cez odpoved na e-mail, nie cez odkaz mimo predtendrom.sk
    # (rovnaka poistka ako _obal() v posli_email.py).
    assert "odpovedzte" in obsah["odhlasenie"]


def test_obsah_bez_velkosti_obce():
    # Zadanie hovori "obce jeho velkosti", ale spolahlivy zdroj poctu
    # obyvatelov nemame (rovnake zistenie ako pri cenovom benchmarku) —
    # text preto nema slovo "velkost" ani "velkosti" nikde.
    obec = {"nazov": "Seňa"}
    suhrn = {"pocet_konciacich": 1, "objem_konciacich": 10000,
             "pocet_dotacii_bezi": 0, "objem_dotacii_bezi": 0}
    obsah = _obsah(obec, suhrn, [])
    cely_text = obsah["titulok"] + obsah["uvod"] + "".join(
        (b["titul"] or "") + (b["popis"] or "") for b in obsah["bloky"])
    assert "veľkosť" not in cely_text.lower()
    assert "velkost" not in cely_text.lower()


if __name__ == "__main__":
    import sys
    testy = [f for n, f in list(globals().items())
             if n.startswith("test_") and callable(f)]
    for f in testy:
        f()
        print(f"{f.__name__}: OK")
    print(f"VSETKY TESTY PRESLI ({len(testy)})")
