"""Testy kampane pre obce a nacitania vysledkov volieb (bez siete a DB)."""
from datetime import date

import kampan_obce as k
import volby


# ── posudenie adresy ───────────────────────────────────────────────────────

def test_vseobecna_adresa_na_domene_obce_je_ok():
    assert k.posud_email("podatelna@dolnastreda.sk", "Obec Dolná Streda")[0] == "ok"
    assert k.posud_email("obec@dolna-streda.sk", "Obec Dolná Streda")[0] == "ok"
    assert k.posud_email("msu@presov.sk", "Mesto Prešov")[0] == "ok"


def test_osobna_adresa_ide_na_kontrolu():
    stav, dovod = k.posud_email("jana.novakova@dolnastreda.sk", "Obec Dolná Streda")
    assert stav == "na_kontrolu" and "osobn" in dovod
    assert k.posud_email("vojtech.kral@dolnastreda.sk", "Obec Dolná Streda")[0] == "na_kontrolu"
    assert k.posud_email("mudr.novak@dolnastreda.sk", "Obec Dolná Streda")[0] == "na_kontrolu"


def test_cudzia_domena_ide_na_kontrolu():
    # externy obstaravatel vyplnil oznamenie za obec
    assert k.posud_email("vo@obstaravanie-firma.sk", "Obec Dolná Streda")[0] == "na_kontrolu"
    assert k.posud_email("peter@agentura.sk", "Obec Dolná Streda")[0] == "na_kontrolu"


def test_verejna_schranka():
    assert k.posud_email("obecdolnastreda@gmail.com", "Obec Dolná Streda")[0] == "ok"
    assert k.posud_email("ou.dolnastreda@azet.sk", "Obec Dolná Streda")[0] == "ok"
    assert k.posud_email("ferko123@gmail.com", "Obec Dolná Streda")[0] == "na_kontrolu"
    # vseobecne slovo na gmaile nestaci — moze to byt agentura
    assert k.posud_email("obstaravanie.sk@gmail.com", "Obec Dolná Streda")[0] == "na_kontrolu"


def test_realne_vzory_z_vestnika():
    # hosting obecnych webov: nazov obce v adrese
    assert k.posud_email("kristy@lekosonline.sk", "Obec Kristy")[0] == "ok"
    # externy obstaravatel
    assert k.posud_email("klient@tenders.sk", "Obec Tužina")[0] == "na_kontrolu"
    assert k.posud_email("info@cvo.sk", "Obec Tužina")[0] == "na_kontrolu"
    # jednoslovna adresa na domene obce moze byt osobna (priezvisko)
    assert k.posud_email("ranto@martin.sk", "Mesto Martin") == \
        ("na_kontrolu", "adresa na domene obce, ale moze byt osobna")
    assert k.posud_email("info@martin.sk", "Mesto Martin")[0] == "ok"
    # prikratky nazov obce sa nesmie najst nahodou
    assert k.posud_email("info@kolarovo.sk", "Obec Ol")[0] == "na_kontrolu"


def test_neplatna_adresa():
    assert k.posud_email("nie je email", "Obec X")[0] == "vylucene"


# ── register a vyber kontaktov ─────────────────────────────────────────────

REGISTER = {
    "dolnastreda": [("504556", "Trnavský kraj")],
    "rohoznik": [("508233", "Bratislavský kraj"), ("524000", "Prešovský kraj")],
}
KRAJE = {"SK021": "Trnavský kraj", "SK010": "Bratislavský kraj", "SK041": "Prešovský kraj"}


def test_kod_obce_jednoznacny_a_podla_kraja():
    assert k.kod_obce("Obec Dolná Streda", None, REGISTER) == "504556"
    assert k.kod_obce("Obec Rohožník", None, REGISTER) is None
    assert k.kod_obce("Obec Rohožník", "Prešovský kraj", REGISTER) == "524000"


def test_vyber_kontaktov_preferuje_ok_a_novsie():
    riadky = [
        {"obstaravatel_ico": "00312345", "obstaravatel_nazov": "Obec Dolná Streda",
         "obstaravatel_email": "peter@agentura.sk", "nuts": "SK021", "publikovane": "2026-09-01"},
        {"obstaravatel_ico": "00312345", "obstaravatel_nazov": "Obec Dolná Streda",
         "obstaravatel_email": "podatelna@dolnastreda.sk", "nuts": "SK021", "publikovane": "2025-03-01"},
        {"obstaravatel_ico": "99", "obstaravatel_nazov": "Stavby s.r.o.",
         "obstaravatel_email": "info@stavby.sk", "nuts": "SK021", "publikovane": "2026-01-01"},
    ]
    out = k.vyber_kontakty(riadky, REGISTER, KRAJE)
    assert list(out) == ["00312345"]          # firma nie je obec
    kon = out["00312345"]
    assert kon["email"] == "podatelna@dolnastreda.sk" and kon["stav"] == "ok"
    assert kon["kraj"] == "Trnavský kraj" and kon["kod_obce"] == "504556"


# ── texty ──────────────────────────────────────────────────────────────────

def test_oslovenie():
    assert k.oslovenie("Obec X", None) == "Dobrý deň,"
    assert k.oslovenie("Obec X", {"priezvisko": "Nováková"}) == "Dobrý deň, pani starostka Nováková,"
    assert k.oslovenie("Obec X", {"priezvisko": "Horský"}) == "Dobrý deň, pán starosta Horský,"
    assert k.oslovenie("Mesto Y", {"priezvisko": "Malá"}) == "Dobrý deň, pani primátorka Malá,"
    assert k.oslovenie("Mesto Y", {"priezvisko": "KOVÁČ"}) == "Dobrý deň, pán primátor Kováč,"


KONTAKT = {"ico": "00312345", "obec": "Obec Dolná Streda", "kraj": "Trnavský kraj",
           "email": "podatelna@dolnastreda.sk", "token": "11111111-2222-3333-4444-555555555555"}


def test_segment_podla_priority_a_obsah():
    data = {"uvo": {"predmet": "Zimná údržba ciest", "dodavatel": "Cesty <s.r.o.>",
                    "hodnota": 48200, "koniec": "2027-03-31"},
            "dotacie": {"pocet": 3, "suma": 120000}}
    s = k.zostav("vlna1", KONTAKT, {"priezvisko": "Horský"}, data)
    assert s["segment"] == "uvo"
    assert s["predmet"] == "Dolná Streda: čo má obec podpísané a kedy to končí"
    text, telo = k.vyrenderuj(s, KONTAKT["token"])
    assert "Zimná údržba ciest — súťaž vyhrala firma Cesty <s.r.o.> za 48 200 €, zmluva končí 31. 3. 2027." in text
    assert "Cesty &lt;s.r.o.&gt;" in telo and "<s.r.o.>" not in telo     # escapovanie
    assert "pre obce v Trnavskom kraji je zadarmo" in text
    assert "utm_campaign=vlna1-uvo" in telo
    assert "odhlasenie-obce.html?t=11111111-2222-3333-4444-555555555555" in text


def test_bez_konkretneho_udaja_nic():
    assert k.zostav("vlna1", KONTAKT, None, {}) is None


def test_poradca_ma_prednost_a_chybajuci_datum_vypadne():
    s = k.zostav("vlna1", KONTAKT, None, {"poradca": {"sprostredkovatel": "Grant s.r.o.", "najate": None},
                                          "uvo": {"predmet": "x", "dodavatel": "y", "koniec": "2027-01-01"}})
    assert s["segment"] == "poradca"
    text, _ = k.vyrenderuj(s, KONTAKT["token"])
    assert "obec má zmluvu s firmou Grant s.r.o." in text and " od " not in text.split("Grant")[0][-10:]


def test_dotacie_sklonovanie():
    for pocet, slovo in ((1, "1 dotáciu"), (3, "3 dotácie"), (7, "7 dotácií")):
        s = k.zostav("vlna1", KONTAKT, None, {"dotacie": {"pocet": pocet, "suma": 0}})
        text, _ = k.vyrenderuj(s, KONTAKT["token"])
        assert slovo in text and "celkovej sume" not in text


def test_odkaz_mimo_webu_zhodi():
    s = {"odstavce": [["x ", ("odkaz", "zle", "https://evil.example/")]]}
    try:
        k.vyrenderuj(s, "t")
    except ValueError:
        return
    raise AssertionError("cudzi odkaz musel zhodit")


# ── kto dostane e-mail ─────────────────────────────────────────────────────

def test_vyber_prijemcov():
    kontakty = [
        {"ico": "1", "stav": "ok"},
        {"ico": "2", "stav": "na_kontrolu"},
        {"ico": "3", "stav": "ok", "odhlasene_at": "2026-12-01"},
        {"ico": "4", "stav": "ok"},             # uz poslane v vlne 1
        {"ico": "5", "stav": "ok"},             # ma ucet
    ]
    odoslane = [{"ico": "4", "vlna": "vlna1", "stav": "odoslane", "odoslane_at": "2026-11-25T08:00:00"}]
    dnes = date(2026, 11, 26)
    assert [x["ico"] for x in k.vyber_prijemcov(kontakty, odoslane, {"5"}, "vlna1", dnes)] == ["1"]
    # vlna 2 len tym, ktorym vlna 1 odisla aspon pred 14 dnami
    assert k.vyber_prijemcov(kontakty, odoslane, set(), "vlna2", dnes) == []
    assert [x["ico"] for x in k.vyber_prijemcov(kontakty, odoslane, set(), "vlna2", date(2027, 1, 12))] == ["4"]


def test_smie_ostro():
    assert k.smie_ostro("vlna1", date(2026, 11, 20), False)            # pred datumom
    assert k.smie_ostro("vlna1", date(2026, 11, 28), False)            # sobota
    assert k.smie_ostro("vlna1", date(2026, 11, 24), False) is None    # utorok
    assert k.smie_ostro("vlna1", date(2026, 10, 1), True) is None


# ── volby ──────────────────────────────────────────────────────────────────

CSV_2022 = (
    "Tab. 4d Zvolení starostovia\r\n"
    "Kód kraja;Názov kraja;Kód územného obvodu;Názov územného obvodu;Kód okresu;Názov okresu;"
    "Kód obce;Názov obce;Meno;Priezvisko;Politický subjekt\r\n"
    "2;Trnavský kraj;2;Trnava;205;Galanta;504556;Dolná Streda;Ján;Horský;NEKA\r\n"
    "2;Trnavský kraj;2;Trnava;205;Galanta;504557;Obec bez volieb;;;\r\n"
    "2;Trnavský kraj;2;Trnava;205;Galanta;504556;Dolná Streda;Duplicitný;Riadok;X\r\n"
)


def test_volby_rozober_cp1250():
    text = volby.dekoduj(CSV_2022.encode("cp1250"))
    r = volby.rozober(text, 2022, "u")
    assert len(r) == 1
    assert r[0] == {"rok": 2022, "kod_obce": "504556", "obec": "Dolná Streda", "okres": "Galanta",
                    "kraj": "Trnavský kraj", "meno": "Ján", "priezvisko": "Horský",
                    "titul_pred": None, "subjekt": "NEKA", "zdroj_url": "u"}


def test_volby_tab04x_a_utf8():
    t = "Kód mesta;Názov mesta;Meno;Priezvisko;Politický subjekt\n529346;Bratislava;Matúš;Vallo;Team Bratislava\n"
    r = volby.rozober(volby.dekoduj(t.encode("utf-8")), 2022)
    assert r[0]["kod_obce"] == "529346" and r[0]["priezvisko"] == "Vallo" and r[0]["okres"] is None


def test_volby_bez_hlavicky_zhodi():
    try:
        volby.rozober("a;b;c\n1;2;3\n", 2022)
    except ValueError:
        return
    raise AssertionError("chybajuca hlavicka musela zhodit")


def test_kraj_lokal_a_followup():
    assert k.kraj_lokal("Banskobystrický kraj") == "Banskobystrickom kraji"
    assert k.kraj_lokal("Trenčiansky kraj") == "Trenčianskom kraji"
    s = k.zostav("vlna2", KONTAKT, None, {"uvo": {"predmet": "Zimná údržba."}})
    text, _ = k.vyrenderuj(s, KONTAKT["token"])
    assert "znova obstarávať zákazku „Zimná údržba“, na predtendrom.sk/obce" in text
    text, _ = k.vyrenderuj(k.zostav("vlna2", KONTAKT, None, {}), KONTAKT["token"])
    assert "alebo niečo obstarávať, na" in text


def test_skutocny_register_mestske_casti():
    register, kraje = k.nacitaj_register()
    assert kraje["SK010"] == "Bratislavský kraj"
    assert k.kod_obce("Mestská časť Bratislava-Staré Mesto", None, register) == "528595"
    assert k.kod_obce("Mestská časť Bratislava - Staré Mesto", None, register) == "528595"


def test_volby_presny_tvar_2022():
    """Prve riadky suborov OSO2022 tak, ako ich SU realne zverejnil (overene 25. 9. 2026)."""
    d = ("Zoznam zvolených starostov;;;;;;;;;;\r\n;;;;;;;;;;\r\n"
         "Kód kraja;Názov kraja;Kód územného obvodu;Názov územného obvodu;Kód okresu;Názov okresu;"
         "Kód obce;Názov obce;Meno;Priezvisko;Politický subjekt\r\n"
         "1;Bratislavský kraj;101;Bratislava;101;Bratislava I;528595;Bratislava - Staré Mesto;"
         "Matej;Vagač;Team Bratislava, Progresívne Slovensko\r\n")
    r = volby.rozober(volby.dekoduj(d.encode("cp1250")), 2022)
    assert r[0]["kod_obce"] == "528595" and r[0]["priezvisko"] == "Vagač"
    assert r[0]["subjekt"] == "Team Bratislava, Progresívne Slovensko"
    x = ('"Zoznam zvolených starostov\r\n za mestá Bratislava a Košice";;;;\r\n;;;;\r\n'
         "Kód mesta;Názov mesta;Meno;Priezvisko;Politický subjekt\r\n"
         "582000;Bratislava;Matúš;Vallo;Team Bratislava\r\n")
    r = volby.rozober(volby.dekoduj(x.encode("cp1250")), 2022)
    assert [(z["kod_obce"], z["priezvisko"]) for z in r] == [("582000", "Vallo")]
