"""Testy rozboru Vestníka ÚVO (pipeline/uvo.py).

Fixtúry sú ručne zostavené podľa tvaru skutočných formulárov z čísel
192/2026 a 193/2026 (štruktúra kľúčov a implicitné ID ORG/TPA/TEN/CON
odpozorované v Browser pane 25. 9. 2026) — skrátené na polia, ktoré
parser používa.
"""
import json

import uvo


def n(key, value=None, *deti):
    u = {"key": key}
    if value is not None:
        u["value"] = value
    if deti:
        u["components"] = list(deti)
    return u


def org(nazov, ico, ctx=None):
    deti = [n("GR-Company", None, n("BT-500-Organization-Company", nazov),
              n("BT-501-Organization-Company-CIN", ico))]
    if ctx:
        deti.insert(0, n("DL-Context-Org", ctx))
    return n("GR-Organisations_panel", None, *deti)


def lot(ctx, nazov, cpv, trvanie=None, hodnota=None, deadline=None):
    deti = [n("DL-Title-Lot", nazov), n("DL-Context-Lot", ctx),
            n("GR-Lot-Purpose", None,
              n("GR-Lot-Description", None, n("BT-21-Lot", nazov), n("BT-23-Lot", "services")),
              n("GR-Lot-Scope", None,
                n("BT-27-Lot_currencyWrapper", None, n("BT-27-Lot_value", hodnota), n("BT-27-Lot_currency", "EUR")) if hodnota else n("x"),
                n("GR-Lot-Scope-MainClassification", None, n("BT-262-Lot", cpv))),
              n("GR-Lot-PlaceOfPerformance", None, n("GR-Lot-PlaceOfPerformance_panel", None, n("BT-5071-Lot", "SK022"))))]
    if trvanie:
        deti.append(n("GR-Lot-PlannedDuration", None, n("BT-36-Lot_measureWrapper", None,
                                                        n("BT-36-Lot_value", trvanie), n("BT-36-Lot_measure", "MONTH"))))
    if deadline:
        deti.append(n("GR-Lot-SubmissionInfo", None, n("GR-Lot-Deadlines1", None,
                                                       n("BT-131(d)-Lot", deadline[0]), n("BT-131(t)-Lot", deadline[1]))))
    return n("GR-Lot_well", None, *deti)


def metadata(typ, zakazka="Upratovanie budov (ID: 557846)"):
    return n("metadataWrapper", None, n("DL-Metadata-Partner", "Mesto Test (ID: 1)"),
             n("DL-Metadata-Order", zakazka), n("BT-03-notice", typ))


def buyer(org_id="ORG-0002"):
    return n("GR-Buyer", None, n("GR-ContractingAuthority", None, n("GR-ContractingAuthority_panel", None,
             n("GR-ContractingAuthority-Buyer", None, n("OPT-300-Procedure-Buyer", org_id)),
             n("GR-Procedure-SProvider", None, n("GR-Procedure-SProvider_panel", None,
               n("OPT-300-Procedure-SProvider", "ORG-0001"))))))


def procedure(nazov, cpv):
    return n("GR-Procedure", None, n("GR-Procedure-Purpose", None,
             n("GR-Procedure-Description", None, n("BT-21-Procedure", nazov), n("BT-23-Procedure", "services")),
             n("GR-Procedure-Scope", None, n("GR-Procedure-Scope-MainClassification", None, n("BT-262-Procedure", cpv)))))


def lot_result(lot_id, ten_id, con_id, ponuk, vitaz="selec-w"):
    return n("GR-LotResult_panel", None,
             n("GR-Winner", None, n("BT-142-LotResult", vitaz)),
             n("GR-LotResult-1", None, n("BT-13713-LotResult", lot_id),
               n("GR-LotResult-Tender-Id-Ref", None, n("GR-LotResult-Tender-Id-Ref_panel", None, n("OPT-320-LotResult", ten_id))),
               n("GR-LotResult-Contract-Id-Ref", None, n("GR-LotResult-Contract-Id-Ref_panel", None, n("OPT-315-LotResult", con_id)))),
             n("GR-LotResult-ReceivedSubmissions", None,
               n("GR-LotResult-ReceivedSubmissions_panel", None, n("BT-760-LotResult", "part-req"), n("BT-759-LotResult", "0")),
               n("GR-LotResult-ReceivedSubmissions_panel", None, n("BT-760-LotResult", "tenders"), n("BT-759-LotResult", str(ponuk)))))


def tender(hodnota, lot_id, tpa_id):
    return n("GR-LotTender_panel", None,
             n("GR-Tender", None, n("BT-720-Tender_currencyWrapper", None,
                                    n("BT-720-Tender_value", hodnota), n("BT-720-Tender_currency", "EUR"))),
             n("GR-LotTender-1", None, n("BT-13714-Tender", lot_id), n("OPT-310-Tender", tpa_id)))


def tpa(*org_ids):
    return n("GR-TenderingParty_panel", None, n("GR-Tenderer", None,
             *[n("GR-Tenderer_panel", None, n("OPT-300-Tenderer", o)) for o in org_ids]))


def contract(cislo, podpis, crz, ten_id):
    return n("GR-SettledContract_panel", None, n("GR-SettledContract-1", None,
             n("BT-150-Contract", cislo), n("BT-145-Contract", podpis), n("BT-151-Contract", crz),
             n("GR-SettledContractTenderReference", None, n("GR-SettledContractTenderReference_panel", None,
               n("BT-3202-Contract", ten_id)))))


VYSLEDOK = {
    "name": "Oznámenie o výsledku verejného obstarávania (D24)",
    "id": 1418398,
    "components": [
        metadata("result"),
        n("tabs", None, n("GR-Organisations-Section", None, n("GR-Organisations", None,
          org("Úrad pre verejné obstarávanie", "31797903", "ORG-0001"),
          org("Mesto Test", "00311111", "ORG-0002"),
          org("Čisto s.r.o.", "36283576"),                # implicitne ORG-0003
          org("Lesk a.s.", "31717802")))),                # implicitne ORG-0004
        buyer(),
        procedure("Upratovanie budov mesta", "90910000"),
        n("groupsAndLots_well", None, n("GR-Lot", None,
          lot("LOT-0001", "Časť 1 - radnica", "90911200", trvanie="36", hodnota="120 000.00"),
          lot("LOT-0002", "Časť 2 - škola", "90911200", trvanie="24"))),
        n("GR-Result", None,
          n("GR-LotResult-Section", None, n("GR-LotResult", None,
            lot_result("LOT-0001", "TEN-0001", "CON-0001", 3),
            lot_result("LOT-0002", "TEN-0002", "CON-0002", 1))),
          n("GR-TenderingParty-Section", None, n("GR-TenderingParty", None,
            tpa("ORG-0003"), tpa("ORG-0004"))),
          n("GR-LotTender-Section", None, n("GR-LotTender", None,
            tender("84 709.6", "LOT-0001", "TPA-0001"),
            tender("27 990", "LOT-0002", "TPA-0002"))),
          n("GR-SettledContract-Section", None, n("GR-SettledContract", None,
            contract("78_2026", "2026-09-18T00:00:00", "https://www.crz.gov.sk/zmluva/12817231/", "TEN-0001"),
            contract("79_2026", "2026-01-31T00:00:00", "https://www.crz.gov.sk/zmluva/12817250/", "TEN-0002")))),
    ],
}

SUTAZ = {
    "name": "Oznámenie o vyhlásení verejného obstarávania (D24)",
    "id": 1419000,
    "components": [
        metadata("competition", "Pekárenské výrobky (ID: 565784)"),
        n("tabs", None, n("GR-Organisations-Section", None, n("GR-Organisations", None,
          org("Úrad pre verejné obstarávanie", "31797903"),
          org("SOŠ strojnícka", "37922459")))),
        buyer(),
        procedure("Strážna služba areálu", "79713000"),
        n("groupsAndLots_well", None, n("GR-Lot", None,
          lot("LOT-0001", "Strážna služba", "79713000", trvanie="2", hodnota="50 000,50",
              deadline=("2026-10-05T00:00:00", "2026-09-21T09:00:00")))),
    ],
}

OPRAVA = dict(SUTAZ, name="Oprava: Oznámenie o vyhlásení verejného obstarávania (D24)", id=1)


def test_vysledok_viac_casti_implicitne_id():
    druh, riadky = uvo.rozober(VYSLEDOK, "193/2026", "2026-09-22")
    assert druh == "vysledok"
    assert len(riadky) == 2
    r1, r2 = riadky
    assert r1["obstaravatel_ico"] == "00311111"
    assert r1["vitaz_ico"] == "36283576" and r1["vitaz_nazov"] == "Čisto s.r.o."
    assert r2["vitaz_ico"] == "31717802"
    assert r1["hodnota"] == 84709.6 and r2["hodnota"] == 27990.0
    assert r1["pocet_ponuk"] == 3 and r2["pocet_ponuk"] == 1
    assert r1["podpisane"] == "2026-09-18"
    assert r1["koniec"] == "2029-09-18" and r1["koniec_odhad"] is True
    assert r2["koniec"] == "2028-01-31"          # 31. 1. + 24 mesiacov
    assert r1["crz_url"].endswith("/12817231/")
    assert r1["zakazka_id"] == 557846 and r1["url"].endswith("/detail/557846")
    assert r1["sektor"] == "UPRATOVANIE"
    assert r1["predpokladana_hodnota"] == 120000.0
    assert r1["nuts"] == "SK022"


def test_uvo_nikdy_nie_je_vitaz():
    druh, riadky = uvo.rozober(VYSLEDOK, "193/2026", "2026-09-22")
    assert all(r["vitaz_ico"] != "31797903" for r in riadky)


def test_bez_vitaza_sa_neuklada():
    v = json.loads(json.dumps(VYSLEDOK))
    lr = uvo.najdi(v["components"], "GR-LotResult_panel")[1]
    uvo.najdi(lr["components"], "BT-142-LotResult")[0]["value"] = "clos-nw"
    _, riadky = uvo.rozober(v, "193/2026", "2026-09-22")
    assert [r["cast_id"] for r in riadky] == ["LOT-0001"]


def test_sutaz():
    druh, riadky = uvo.rozober(SUTAZ, "193/2026", "2026-09-22")
    assert druh == "sutaz"
    (r,) = riadky
    assert r["typ"] == "sutaz"
    assert r["obstaravatel_ico"] == "37922459"
    assert r["predpokladana_hodnota"] == 50000.5
    assert r["lehota_ponuk"] == "2026-10-05T09:00:00+02:00"
    assert r["sektor"] == "OSTRAHA"
    assert r["zakazka_id"] == 565784
    assert r["trvanie_mesiace"] == 2


def test_oprava_sa_preskakuje():
    assert uvo.rozober(OPRAVA, "193/2026", None) == (None, [])


def test_rozober_cislo_pocita_xml_a_opravy():
    data = {
        "bulletinPublishDate": "2026-09-22T00:16:35.4",
        "bulletinItemList": [
            {"itemData": json.dumps(VYSLEDOK)},
            {"itemData": json.dumps(SUTAZ)},
            {"itemData": json.dumps(OPRAVA)},
            {"itemData": "<?xml version='1.0'?><x/>"},
        ],
    }
    vys, vyz, st = uvo.rozober_cislo(data, "193/2026")
    assert len(vys) == 2 and len(vyz) == 1
    assert st == {"oznameni": 4, "preskocenych": 1, "oprav_a_inych": 1}
    assert vys[0]["publikovane"] == "2026-09-22"


def test_cisla_a_datumy():
    assert uvo.cislo("461 380.30") == 461380.30
    assert uvo.cislo("1.234.567,89") == 1234567.89
    assert uvo.cislo("420321.8") == 420321.8
    assert uvo.cislo("abc") is None
    assert uvo.mesiace("2", "YEAR") == 24
    assert uvo.pridaj_mesiace("2026-01-31", 1) == "2026-02-28"
    assert uvo.lehota("2026-01-10T00:00:00", "2026-09-21T09:00:00") == "2026-01-10T09:00:00+01:00"


def test_sektor_tovary_bez_textu():
    # potraviny (CPV 15) nesmú skončiť v STRAVOVANIE len kvôli slovu v názve
    assert uvo.sektor("15000000", "Potraviny na zabezpečenie stravovania") is None
    assert uvo.sektor("45210000", "Rekonštrukcia") == "STAVEBNE_PRACE"
    assert uvo.sektor("45310000", "") == "ELEKTROINSTALACIE"


def _tender_rank(hodnota, lot_id, tpa_id, rank):
    t = tender(hodnota, lot_id, tpa_id)
    t["components"][0]["components"].append(n("BT-171-Tender", rank))
    return t


# Národný formulár: víťazná časť nemá OPT-320 (odkaz na ponuku), ponuky sú
# zoradené cez BT-171, zmluva nemá BT-3202. Plus nesprávne DL-Context-Org
# pri obstarávateľovi (tak to v dátach naozaj býva — odkazy platia podľa poradia).
NARODNY = {
    "name": "Oznámenie o výsledku verejného obstarávania ",
    "id": 1420000,
    "components": [
        metadata("result", "Rekonštrukcia budovy (ID: 555000)"),
        n("tabs", None, n("GR-Organisations-Section", None, n("GR-Organisations", None,
          org("Úrad pre verejné obstarávanie", "31797903", "ORG-0001"),
          org("Nemocnica Test", "31936415", "ORG-0003"),   # chybné DL-Context-Org
          org("Stavby A", "11111111"),
          org("Stavby B", "22222222"),
          org("Stavby C", "36812251")))),
        buyer("ORG-0002"),
        procedure("Rekonštrukcia a nadstavba budovy", "45000000"),
        n("groupsAndLots_well", None, n("GR-Lot", None,
          lot(None, "Rekonštrukcia a nadstavba budovy", "45000000", trvanie="6"))),
        n("GR-Result", None,
          n("GR-LotResult-Section", None, n("GR-LotResult", None,
            n("GR-LotResult_panel", None, n("GR-Winner", None, n("BT-142-LotResult", "selec-w")),
              n("GR-LotResult-1", None, n("BT-13713-LotResult", "LOT-0001")),
              n("BT-710-LotResult_value", "4 499 776.29")))),
          n("GR-TenderingParty-Section", None, n("GR-TenderingParty", None,
            tpa("ORG-0003"), tpa("ORG-0004"), tpa("ORG-0005"))),
          n("GR-LotTender-Section", None, n("GR-LotTender", None,
            _tender_rank("4 835 989.03", "LOT-0001", "TPA-0001", "3"),
            _tender_rank("4 594 000.00", "LOT-0001", "TPA-0002", "2"),
            _tender_rank("4 499 776.29", "LOT-0001", "TPA-0003", "1"))),
          n("GR-SettledContract-Section", None, n("GR-SettledContract", None,
            n("GR-SettledContract_panel", None, n("GR-SettledContract-1", None,
              n("BT-145-Contract", "2026-09-16T00:00:00"),
              n("BT-151-Contract", "https://www.crz.gov.sk/zmluva/12818187/")))))),
    ],
}


def test_narodny_formular_vitaz_podla_poradia():
    druh, riadky = uvo.rozober(NARODNY, "193/2026", "2026-09-22")
    assert druh == "vysledok"
    (r,) = riadky
    assert r["obstaravatel_ico"] == "31936415"      # podľa poradia, nie DL-Context-Org
    assert r["vitaz_ico"] == "36812251" and r["vitaz_nazov"] == "Stavby C"
    assert r["hodnota"] == 4499776.29
    assert r["podpisane"] == "2026-09-16"
    assert r["koniec"] == "2027-03-16"
    assert r["crz_url"].endswith("/12818187/")
    assert r["cast_id"] == "LOT-0001"
    assert r["sektor"] == "STAVEBNE_PRACE"


class _FakeResp:
    def __init__(self, data):
        self._d = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._d

    @property
    def content(self):
        return json.dumps(self._d, ensure_ascii=False).encode("utf-8")


class _FakeSess:
    """Katalóg s 3 číslami (jedno staršie ako od_rok) a jedným súborom."""
    headers = {}

    def post(self, url, json=None, timeout=None):
        if json["page"] > 1:
            return _FakeResp({"items": []})
        items = [
            {"id": "a", "name": "Vestník 193/2026", "distributions": [{"downloadUrl": "https://x/download?id=1"}]},
            {"id": "b", "name": "Vestník 192/2026", "distributions": [{"downloadUrl": "https://x/download?id=2"}]},
            {"id": "c", "name": "Vestník 262/2024", "distributions": [{"downloadUrl": "https://x/download?id=3"}]},
            {"id": "d", "name": "Datasety 2025", "distributions": []},
        ]
        return _FakeResp({"items": items})

    def get(self, url, timeout=None):
        return _FakeResp({
            "bulletinPublishDate": "2026-09-22T00:16:35",
            "bulletinItemList": [{"itemData": json.dumps(VYSLEDOK)}, {"itemData": json.dumps(SUTAZ)}],
        })


def test_zoznam_cisel_a_nasucho_beh(monkeypatch=None):
    orig = uvo._session
    uvo._session = lambda: _FakeSess()
    try:
        cisla = uvo.zoznam_cisel(_FakeSess(), 2025)
        assert [c["vestnik"] for c in cisla] == ["192/2026", "193/2026"]
        assert uvo.main(["--nasucho", "--od-rok", "2025"]) == 0
    finally:
        uvo._session = orig


def test_stiahni_dekoduje_utf8_aj_bez_charsetu():
    class R:
        content = json.dumps({"x": "zabezpečenie"}, ensure_ascii=False).encode("utf-8")
        encoding = "ISO-8859-1"
        def raise_for_status(self):
            pass
    class S:
        def get(self, url, timeout=None):
            return R()
    assert uvo.stiahni(S(), "u") == {"x": "zabezpečenie"}


def test_pokazene_cislo_nezastavi_beh():
    import requests as rq

    class Zly(_FakeSess):
        def get(self, url, timeout=None):
            if url.endswith("id=1"):
                r = rq.Response()
                r.status_code = 404
                r.url = url
                raise rq.exceptions.HTTPError("404", response=r)
            return super().get(url, timeout)

    orig = uvo._session
    uvo._session = lambda: Zly()
    try:
        assert uvo.main(["--nasucho", "--od-rok", "2025"]) == 0
    finally:
        uvo._session = orig
