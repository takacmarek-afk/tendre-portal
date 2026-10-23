"""Testy oslovenia firiem (bez siete a DB)."""
import re
from datetime import date, datetime

import oslovenie_firiem as of

TOKEN = "11111111-2222-3333-4444-555555555555"
KONTAKT = {"ico": "36034762", "nazov": "DUG s.r.o.", "email": "info@dug.sk", "stav": "ok",
           "segment": "OSTRAHA", "kraj": "Bratislavský kraj", "posledny_urad": "Mesto Pezinok",
           "token": TOKEN, "odhlasene_at": None}


def _zmluva(cid, urad, suma, koniec, ico="11111111", seg="OSTRAHA", kraj="Bratislavský kraj"):
    return {"contract_id": cid, "sector": seg, "kraj": kraj, "authority_name": urad,
            "subject": "Zmluva o poskytovaní strážnej služby", "price_total": suma,
            "effective_to": koniec, "supplier_name": "X", "supplier_ico": ico}


# ── adresy ────────────────────────────────────────────────────────────────

def test_vseobecna_adresa_je_ok():
    assert of.posud_email("info@dug.sk", "DUG s.r.o.")[0] == "ok"
    assert of.posud_email("obchod@firma.sk", "Firma s.r.o.")[0] == "ok"
    assert of.posud_email("office.ba@firma.sk", "Firma s.r.o.")[0] == "ok"


def test_osobna_a_verejna_schranka_na_kontrolu():
    assert of.posud_email("jan.novak@dug.sk", "DUG s.r.o.")[0] == "na_kontrolu"
    assert of.posud_email("dugsro@gmail.com", "DUG s.r.o.")[0] == "na_kontrolu"
    assert of.posud_email("zle", "X")[0] == "vylucene"


def test_adresa_s_nazvom_firmy_je_ok():
    assert of.posud_email("abcclean@abcclean.sk", "ABC Clean, s. r. o.")[0] == "ok"


def test_kratky_nazov_bez_pravnej_formy():
    assert of.kratky_nazov("ABC Clean, s. r. o.") == "ABC Clean"
    assert of.kratky_nazov("EUROMAR spol. s r.o.") == "EUROMAR"
    assert of.kratky_nazov("Bezpečnosť a.s.") == "Bezpečnosť"


def test_zluc_berie_najnovsiu_adresu_a_najcastejsi_kraj():
    r = [{"ico": "1", "nazov": "A s.r.o.", "email": "stary@a.sk", "segment": "OSTRAHA",
          "kraj": "Košický kraj", "zdroj_datum": "2025-01-01"},
         {"ico": "1", "nazov": "A s.r.o.", "email": "info@a.sk", "segment": "OSTRAHA",
          "kraj": "Bratislavský kraj", "zdroj_datum": "2026-05-01"},
         {"ico": "1", "nazov": "A s.r.o.", "email": "info@a.sk", "segment": "OSTRAHA",
          "kraj": "Bratislavský kraj", "zdroj_datum": "2026-03-01"}]
    k = of.zluc_kontakty(r)
    assert len(k) == 1 and k[0]["email"] == "info@a.sk" and k[0]["kraj"] == "Bratislavský kraj"
    assert k[0]["stav"] == "ok"


# ── kontakty z formulara Vestnika ─────────────────────────────────────────

def test_kontakty_z_formulara(monkeypatch):
    import uvo
    riadky = [{"vitaz_ico": "36034762", "vitaz_nazov": "DUG s.r.o.", "obstaravatel_ico": "00305081",
               "obstaravatel_nazov": "Mesto Pezinok", "sektor": "OSTRAHA", "nuts": "SK010",
               "url": "https://www.uvo.gov.sk/x", "publikovane": "2026-05-01"},
              {"vitaz_ico": "99999999", "vitaz_nazov": "Bez e-mailu", "obstaravatel_ico": "1",
               "sektor": "OSTRAHA", "nuts": "SK010"}]
    monkeypatch.setattr(uvo, "rozober", lambda f, v, p: ("vysledok", riadky))
    orgs = [("ORG-1", {"BT-501-Organization-Company-CIN": ["36034762"],
                       "BT-506-Organization-Company": ["INFO@dug.sk"]}),
            ("ORG-2", {"BT-501-Organization-Company-CIN": ["00305081"],
                       "BT-506-Organization-Company": ["podatelna@pezinok.sk"]})]
    monkeypatch.setattr(uvo, "_s_id", lambda uzly, pref: orgs)
    monkeypatch.setattr(uvo, "najdi", lambda k, n: [])
    out = of.kontakty_z_formulara({"components": []}, "1/2026", "2026-05-01")
    assert len(out) == 1
    assert out[0]["email"] == "info@dug.sk" and out[0]["kraj"] == "Bratislavský kraj"
    assert out[0]["posledny_urad"] == "Mesto Pezinok"


# ── hook ──────────────────────────────────────────────────────────────────

def test_hook_neukaze_vlastnu_zmluvu_a_ide_podla_sumy():
    dnes = date(2026, 10, 23)
    zm = [_zmluva(1, "BVS", 8_000_000, "2027-09-01", ico="36034762"),   # vlastna
          _zmluva(2, "Mesto Senec", 120_000, "2027-03-31"),
          _zmluva(3, "Obec Ivanka", 30_000, "2027-01-15"),
          _zmluva(4, "Košice", 900_000, "2027-02-01", kraj="Košický kraj")]
    h = of.hook_pre_firmu(KONTAKT, zm, dnes)
    assert h["N"] == 2
    assert [z["urad"] for z in h["zmluvy"]] == ["Mesto Senec", "Obec Ivanka"]


def test_bez_zmluvy_ziadny_email():
    assert of.hook_pre_firmu(KONTAKT, [], date(2026, 10, 23)) is None
    assert of.hook_pre_firmu({**KONTAKT, "kraj": None}, [_zmluva(2, "X", 1, "2027-01-01")],
                             date(2026, 10, 23)) is None


# ── texty ─────────────────────────────────────────────────────────────────

def _hook():
    return {"N": 23, "zmluvy": [
        {"urad": "Mesto Senec", "predmet": "Zmluva o poskytovaní strážnej služby", "suma": "120 000 €",
         "koniec": "2027-03-31", "contract_id": 2},
        {"urad": "Obec Ivanka", "predmet": "Ostraha budovy", "suma": None, "koniec": "2027-01-15",
         "contract_id": 3},
        {"urad": "Obec Chorvátsky Grob", "predmet": "Strážna služba", "suma": "40 000 €",
         "koniec": "2027-05-30", "contract_id": 5}]}


def _slova_tela(text):
    telo = text.split("\n--\n")[0]
    return len(re.findall(r"\S+", telo))


def test_tri_kroky_do_100_slov_a_bez_predpovede():
    for krok in (1, 2, 3):
        for v in ("A", "B"):
            s = of.zostav(krok, KONTAKT, _hook(), v)
            text, telo = of.vyrenderuj(s, TOKEN)
            assert _slova_tela(text) <= 100, (krok, v, _slova_tela(text))
            nizke = text.lower()
            for zakazane in ("predpoved", "zaruč", "garant", "väčšia šanca"):
                assert zakazane not in nizke, (krok, zakazane)
            assert "odhlasenie-firmy.html?t=" + TOKEN in text and "LoveHome s.r.o." in text
            assert "Vestníka verejného obstarávania" in text
            assert "<img" not in telo   # ziadny sledovaci pixel


def test_krok1_obsahuje_skutocnu_zmluvu_a_urad_firmy():
    s = of.zostav(1, KONTAKT, _hook(), "A")
    text, _ = of.vyrenderuj(s, TOKEN)
    assert "Mesto Senec" in text and "120 000 €" in text and "31. 3. 2027" in text
    assert "Mesto Pezinok" in text and "DUG pracuje" in text
    assert s["predmet"].startswith("Zmluva na ostrahu pre Mesto Senec končí v marci 2027")
    sb = of.zostav(1, KONTAKT, _hook(), "B")
    assert sb["predmet"] == "23 zmlúv na ostrahu v Bratislavskom kraji končí do roka"


def test_odkazy_len_na_predtendrom():
    s = {"predmet": "x", "odstavce": [[("a", "zly", "https://zly.sk/")]]}
    try:
        of.vyrenderuj(s, TOKEN)
        assert False, "mal padnut"
    except ValueError:
        pass


def test_html_je_escapovany():
    k = {**KONTAKT, "posledny_urad": "<script>alert(1)</script>"}
    _, telo = of.vyrenderuj(of.zostav(1, k, _hook(), "A"), TOKEN)
    assert "<script>" not in telo and "&lt;script&gt;" in telo


# ── kto je na rade ────────────────────────────────────────────────────────

def test_na_rade_nadvazuje_po_dnoch_a_obmedzi_novych():
    dnes = date(2026, 11, 5)
    kontakty = [{**KONTAKT, "ico": str(10000000 + i), "email": f"info@f{i}.sk"} for i in range(5)]
    odoslane = [{"ico": "10000000", "krok": 1, "stav": "odoslane", "odoslane_at": "2026-11-01T09:00"},  # +4 dni → krok 2
                {"ico": "10000001", "krok": 1, "stav": "odoslane", "odoslane_at": "2026-11-03T09:00"},  # skoro
                {"ico": "10000002", "krok": 1, "stav": "odoslane", "odoslane_at": "2026-10-20T09:00"},
                {"ico": "10000002", "krok": 2, "stav": "odoslane", "odoslane_at": "2026-10-31T09:00"}]  # +5 → krok 3
    rad = of.na_rade(kontakty, odoslane, ["OSTRAHA"], set(), set(), dnes, novych=1)
    assert [(k["ico"], krok) for k, krok in rad] == [("10000000", 2), ("10000002", 3), ("10000003", 1)]


def test_na_rade_vynecha_odhlasenych_zakaznikov_a_odberatelov():
    dnes = date(2026, 11, 5)
    kontakty = [{**KONTAKT, "ico": "1", "email": "info@a.sk", "odhlasene_at": "2026-11-01"},
                {**KONTAKT, "ico": "2", "email": "info@b.sk"},
                {**KONTAKT, "ico": "3", "email": "info@c.sk"},
                {**KONTAKT, "ico": "4", "email": "info@d.sk", "stav": "na_kontrolu"},
                {**KONTAKT, "ico": "5", "email": "info@e.sk", "stav": "odpovedal"},
                {**KONTAKT, "ico": "6", "email": "info@f.sk", "segment": "IT_TECHNIKA"}]
    rad = of.na_rade(kontakty, [], ["OSTRAHA"], {"00000002"}, {"info@c.sk"}, dnes, novych=10)
    assert rad == []


def test_po_tretom_kroku_koniec_a_chyba_sa_nepocita():
    dnes = date(2026, 12, 1)
    k = [{**KONTAKT, "ico": "7", "email": "info@g.sk"}]
    odos = [{"ico": "7", "krok": n, "stav": "odoslane", "odoslane_at": "2026-11-01T09:00"} for n in (1, 2, 3)]
    assert of.na_rade(k, odos, ["OSTRAHA"], set(), set(), dnes, 5) == []
    chyba = [{"ico": "7", "krok": 1, "stav": "chyba", "odoslane_at": "2026-11-01T09:00"}]
    assert of.na_rade(k, chyba, ["OSTRAHA"], set(), set(), dnes, 5)[0][1] == 1


def test_smie_ostro():
    assert of.smie_ostro(datetime(2026, 10, 27, 9, 0), False) is None          # utorok
    assert "pondelok" in of.smie_ostro(datetime(2026, 10, 30, 9, 0), False)    # piatok
    assert "8:00" in of.smie_ostro(datetime(2026, 10, 27, 18, 0), False)
    assert of.smie_ostro(datetime(2026, 10, 31, 22, 0), True) is None


def test_variant_ab_je_stabilny():
    assert of.variant_pre("36034762") == "A" and of.variant_pre("36034761") == "B"


def test_neposiela_cez_resend():
    src = open(of.__file__, encoding="utf-8").read()
    assert "api.resend.com" not in src and "RESEND_API_KEY" not in src


if __name__ == "__main__":
    # Spustenie bez pytestu (python test_oslovenie_firiem.py), ako ostatne testy v pipeline.
    import inspect
    import sys

    class _MP:
        def __init__(self):
            self._spat = []

        def setattr(self, obj, meno, hodnota):
            self._spat.append((obj, meno, getattr(obj, meno)))
            setattr(obj, meno, hodnota)

        def undo(self):
            for obj, meno, stara in reversed(self._spat):
                setattr(obj, meno, stara)

    chyby = 0
    for meno, f in sorted(globals().items()):
        if not meno.startswith("test_") or not callable(f):
            continue
        mp = _MP()
        try:
            f(mp) if inspect.signature(f).parameters else f()
            print("OK  ", meno)
        except Exception as e:      # noqa: BLE001
            chyby += 1
            print("FAIL", meno, type(e).__name__, e)
        finally:
            mp.undo()
    print("VSETKO OK" if not chyby else f"{chyby} CHYB")
    sys.exit(1 if chyby else 0)
