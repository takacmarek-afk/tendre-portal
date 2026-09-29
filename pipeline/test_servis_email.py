"""Testy pre posli_servis_email.py (P3.2 C, servis -> dopyt prevod,
29.9.2026).

Rovnaky princip ako ostatne male testy v pipeline: overit ciste funkcie a
rozhodovaciu logiku, nie infrastrukturu okolo (DB/Resend). Vyzaduje
nainstalovany balik `supabase` (beh v tomto pieskovisku bez sietoveho
pristupu preto nie je mozny, ale v GitHub Actions/lokalne u Mareka ano).
Spustenie: python test_servis_email.py  (alebo pytest pipeline/)
"""
from posli_servis_email import _platny_email, _odkaz, _obsah


# ── _platny_email ────────────────────────────────────────────────────────

def test_platny_email():
    dobre = ["a@b.sk", "starosta.sena@obec.sk", "x.y+z@firma.co"]
    zle = ["", None, "nieco", "a@b", "a b@c.sk", "@b.sk"]
    for e in dobre:
        assert _platny_email(e), f"malo prejst: {e!r}"
    for e in zle:
        assert not _platny_email(e), f"nemalo prejst: {e!r}"


# ── _odkaz ────────────────────────────────────────────────────────────────

def test_odkaz_ma_token_a_dalej_trh():
    o = _odkaz("abc-123")
    assert o.startswith("https://predtendrom.sk/prihlasenie.html?")
    assert "servis=abc-123" in o
    assert "dalej=trh.html" in o


# ── _obsah ────────────────────────────────────────────────────────────────

def test_obsah_ma_cta_na_predtendrom_a_obsahuje_obec():
    sd = {"id": 1, "obec": "Seňa", "kontakt_email": "starosta@sena.sk", "token": "tok-1"}
    obsah = _obsah(sd)
    assert "Seňa" in obsah["uvod"]
    assert obsah["cta_url"].startswith("https://predtendrom.sk")
    assert "tok-1" in obsah["cta_url"]
    assert len(obsah["bloky"]) == 1


def test_obsah_bez_obce_ma_fallback_text():
    sd = {"id": 2, "obec": None, "kontakt_email": "x@y.sk", "token": "tok-2"}
    obsah = _obsah(sd)
    assert "vašu obec" in obsah["uvod"]


if __name__ == "__main__":
    import sys
    testy = [f for n, f in list(globals().items())
             if n.startswith("test_") and callable(f)]
    for f in testy:
        f()
        print(f"{f.__name__}: OK")
    print(f"VSETKY TESTY PRESLI ({len(testy)})")
