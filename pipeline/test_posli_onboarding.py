"""Testy uvitacich e-mailov (bez siete a DB)."""
import re
from datetime import datetime, timedelta, timezone

import posli_onboarding as po

TERAZ = datetime(2026, 11, 2, 8, 0, tzinfo=timezone.utc)
TOKEN = "11111111-2222-3333-4444-555555555555"


def _k(dni, **kw):
    k = {"user_id": "u1", "email": "a@b.sk", "token": TOKEN,
         "registrovany_at": (TERAZ - timedelta(days=dni)).isoformat(),
         "plan": "trial", "stav": "trial",
         "trial_konci": (TERAZ - timedelta(days=dni) + timedelta(days=14)).isoformat(),
         "zaplatene": False, "kraj": "Bratislavský kraj", "sektor": "UPRATOVANIE",
         "ma_vyber": True, "pocet_zmluv": 12,
         "najblizsia": {"urad": "Mesto Pezinok", "predmet": "Upratovanie budov", "koniec": "2027-03-31"},
         "ma_sledovanie": False, "odoslane": []}
    k.update(kw)
    return k


def test_den0_hned_po_registracii():
    assert po.na_rade(_k(0.1), TERAZ) == (0, [])


def test_po_kroku0_den1_az_od_prveho_dna():
    assert po.na_rade(_k(0.5, odoslane=[0]), TERAZ) == (None, [])
    assert po.na_rade(_k(1.2, odoslane=[0]), TERAZ) == (1, [])


def test_den1_caka_na_vyber_a_potom_vynecha():
    assert po.na_rade(_k(1.5, odoslane=[0], ma_vyber=False), TERAZ) == (None, [])
    assert po.na_rade(_k(3.2, odoslane=[0], ma_vyber=False), TERAZ) == (3, [1])


def test_jeden_email_za_beh_a_zmeskane_okna_sa_vynechaju():
    krok, vyn = po.na_rade(_k(7.5), TERAZ)
    assert krok == 7 and vyn == [0, 1, 3]


def test_den7_vynecha_ked_uz_sleduje():
    assert po.na_rade(_k(7.5, odoslane=[0, 1, 3], ma_sledovanie=True), TERAZ) == (None, [7])


def test_krok12_dva_dni_pred_koncom_a_nie_po_zaplateni():
    k = _k(12, odoslane=[0, 1, 3, 7])
    assert po.na_rade(k, TERAZ) == (12, [])
    assert po.na_rade(dict(k, zaplatene=True), TERAZ) == (None, [12])
    assert po.na_rade(_k(15, odoslane=[0, 1, 3, 7]), TERAZ) == (None, [12])
    assert po.na_rade(dict(k, plan="growth"), TERAZ) == (None, [])


def test_bez_firmy_krok12_nepride():
    k = _k(12, odoslane=[0, 1, 3, 7], trial_konci=None, plan=None)
    assert po.na_rade(k, TERAZ) == (None, [])


def test_v_kraji():
    assert po.v_kraji("Bratislavský kraj") == "v Bratislavskom kraji"
    assert po.v_kraji("Trenčiansky kraj") == "v Trenčianskom kraji"
    assert po.v_kraji("Košický kraj") == "v Košickom kraji"


def test_texty_kratke_a_s_jednym_videom():
    for krok in po.KROKY:
        o = po.obsah(krok, _k(1))
        htm, txt = po.zostav(o, TOKEN)
        telo = txt.split("Marek Takáč")[0]
        assert len(re.findall(r"\w+", telo)) <= 110, krok
        assert txt.count("/navody?") == 1, krok
        assert f"odhlasenie-tipov?t={TOKEN}" in htm and f"odhlasenie-tipov?t={TOKEN}" in txt
        assert "{" not in txt and "None" not in txt


def test_den1_cisla_a_datum():
    o = po.obsah(1, _k(1))
    assert o["predmet"] == "12 zmlúv vo Vašom výbere končí do roka"
    assert "Mesto Pezinok – Upratovanie budov, končí 31. 3. 2027" in o["odseky"][0]
    assert "upratovanie, Bratislavský kraj" in o["odseky"][0]


def test_den3_predmet():
    assert po.obsah(3, _k(3))["predmet"] == "Kto vyhráva upratovanie v Bratislavskom kraji"
    assert po.obsah(3, _k(3, sektor=None))["predmet"] == "Kto vyhráva vo Vašom odbore"


def test_krok12_zakladajuca_cena_len_ked_su_miesta():
    s = " ".join(x if isinstance(x, str) else x[0] for x in po.obsah(12, _k(12), 5)["odseky"])
    assert "ZAKLADATEL" in s and "240 €" in s
    s = " ".join(x if isinstance(x, str) else x[0] for x in po.obsah(12, _k(12), 0)["odseky"])
    assert "ZAKLADATEL" not in s


def test_html_escapuje_data_z_registra():
    k = _k(1, najblizsia={"urad": "<script>x</script>", "predmet": "A&B", "koniec": "2027-01-01"})
    htm, _ = po.zostav(po.obsah(1, k), TOKEN)
    assert "<script>" not in htm and "&lt;script&gt;" in htm


def test_odkazy_len_na_predtendrom():
    for krok in po.KROKY:
        htm, _ = po.zostav(po.obsah(krok, _k(1)), TOKEN)
        for u in re.findall(r'href="([^"]+)"', htm):
            assert u.startswith("https://predtendrom.sk/"), u


def test_nasucho_nic_neposle(monkeypatch):
    def nie(*a, **kw):
        raise AssertionError("siet")
    monkeypatch.setattr(po.requests, "post", nie)
    assert po.posli("k", "a@b.sk", "P", "<p>", "t", TOKEN, True)
