"""Testy: súhlas obce -> e-mail firmám (bez siete)."""
from email.message import EmailMessage

import dopyt_obce as d

POL = [{"nazov": "Stavebné práce - rekonštrukcia kultúrneho domu", "predpokladana_hodnota": 240000,
        "sektor": "STAVEBNE_PRACE", "kraj": "Košický kraj"},
       {"nazov": "Rekonštrukcia strechy MŠ", "predpokladana_hodnota": 60000,
        "sektor": "STRECHY_IZOLACIE", "kraj": "Košický kraj"}]
T = "123e4567-e89b-12d3-a456-426614174000"


def test_priradenie_obce():
    mid, em, dom, seg = d.mapy_obci(
        [{"ico": "00324698", "email": "obec@hran.sk"}, {"ico": "1", "email": "starosta@gmail.com"}],
        [{"ico": "00324698", "vlna": "vlna1", "stav": "odoslane", "segment": "eurofondy", "resend_id": "<x@predtendrom.sk>"}],
        ("gmail.com",))
    assert seg["00324698"] == "eurofondy" and "gmail.com" not in dom
    m = EmailMessage()
    m["From"], m["In-Reply-To"] = "iny@iny.sk", "<x@predtendrom.sk>"
    assert d.priradit_obec(m, mid, em, dom) == "00324698"
    m = EmailMessage()
    m["From"] = "Starosta <starosta@hran.sk>"
    assert d.priradit_obec(m, mid, em, dom) == "00324698"
    m = EmailMessage()
    m["From"] = "cudzi@gmail.com"
    assert d.priradit_obec(m, mid, em, dom) is None


def test_vyber_firiem_odbor_kraj_limit():
    odbery = [{"id": 5, "email": "Odber@a.sk", "sektor": "STAVEBNE_PRACE", "kraj": None, "token": T,
               "potvrdeny": True},
              {"id": 6, "email": "x@b.sk", "sektor": "UPRATOVANIE", "kraj": None, "token": T, "potvrdeny": True},
              {"id": 7, "email": "y@c.sk", "sektor": "STAVEBNE_PRACE", "kraj": "Žilinský kraj", "token": T,
               "potvrdeny": True}]
    firmy = [{"ico": f"{i:08d}", "email": f"f{i}@firma.sk", "stav": "ok", "segment": "STAVEBNE_PRACE",
              "kraj": "Košický kraj", "token": T} for i in range(20)]
    firmy += [{"ico": "99", "email": "odber@a.sk", "stav": "ok", "segment": "STAVEBNE_PRACE",
               "kraj": "Košický kraj", "token": T},
              {"ico": "98", "email": "z@z.sk", "stav": "odpovedal", "segment": "STAVEBNE_PRACE",
               "kraj": "Košický kraj", "token": T},
              {"ico": "97", "email": "k@k.sk", "stav": "ok", "segment": "STAVEBNE_PRACE",
               "kraj": "Prešovský kraj", "token": T}]
    v = d.vyber_firmy(POL, odbery, firmy, set(), {"firma-00000000"})
    assert len(v) == d.MAX_FIRIEM
    assert v[0] == ("odber-5", "odber@a.sk", T, "odber")          # odberatelia prví
    emaily = [x[1] for x in v]
    assert len(set(emaily)) == len(emaily)                          # bez duplicít
    assert "x@b.sk" not in emaily and "y@c.sk" not in emaily        # iný odbor / kraj
    assert "f0@firma.sk" not in emaily                              # už poslané
    assert "z@z.sk" not in emaily and "k@k.sk" not in emaily
    assert d.vyber_firmy([], odbery, firmy, set(), set()) == []


def test_text_firme_len_overene_udaje():
    predmet, t = d.text_firme("Hraň", "Košický kraj", POL, "obec@hran.sk", "https://predtendrom.sk/x")
    assert predmet.startswith("Hraň pripravuje obstarávanie: Stavebné práce")
    assert "240 000 €" in t and "60 000 €" in t and "obec@hran.sk" in t
    assert "ešte nie sú vyhlásené" in t and "odpísať „áno“" in t and "https://predtendrom.sk/x" in t
    for zle in ("garant", "vyhráte", "istá zákazka"):
        assert zle not in t.lower()


def test_odhlasenie_odkazy():
    assert d.odhlasenie_pre("odber", T) == f"https://predtendrom.sk/odber-firmy?t={T}&akcia=odhlasit"
    assert d.odhlasenie_pre("firma", T) == f"https://predtendrom.sk/odhlasenie-firmy.html?t={T}"
    assert d.odhlasenie_pre("firma", "zly") is None


class _Q:
    def __init__(self, sb, t):
        self.sb, self.t, self.f, self.op, self.data = sb, t, {}, "select", None
    def select(self, *a): return self
    def eq(self, k, v): self.f[k] = v; return self
    def in_(self, k, v): self.f[k] = v; return self
    def is_(self, *a): return self
    def order(self, *a, **k): return self
    def range(self, *a): return self
    def limit(self, *a): return self
    def insert(self, r): self.op, self.data = "insert", r; return self
    def update(self, r): self.op, self.data = "update", r; return self
    def execute(self):
        class R: pass
        r = R()
        self.sb.log.append((self.t, self.op, self.f, self.data))
        if self.op != "select":
            r.data = []
            return r
        if self.t == "kampan_obce_odoslane" and self.f.get("vlna") == d.VLNA_SUHLAS:
            r.data = [{"id": 1, "ico": "00324698", "email": "starosta@hran.sk"}]
        elif self.t == "kampan_obce_kontakty":
            r.data = [{"ico": "00324698", "obec": "Obec Hraň", "kraj": "Košický kraj", "email": "obec@hran.sk"}]
        elif self.t == "itms_vo":
            r.data = POL
        elif self.t == "odber_firmy":
            r.data = []
        elif self.t == "oslovenie_firiem_kontakty":
            r.data = [{"ico": "11", "email": "f@firma.sk", "stav": "ok", "segment": "STAVEBNE_PRACE",
                       "kraj": "Košický kraj", "token": T}]
        else:
            r.data = []
        return r


class _Sb:
    def __init__(self): self.log = []
    def table(self, t): return _Q(self, t)


class _Smtp:
    poslane = []
    def __init__(self, *a, **k): pass
    def login(self, *a): pass
    def send_message(self, m): _Smtp.poslane.append(m); return {}
    def quit(self): pass


def test_posli_firmam_ostro_a_nasucho():
    sb = _Sb()
    assert d.posli_firmam(sb, "h", False) == {"suhlasy": 1, "firmy": 1, "bez_firiem": 0, "chyby": 0}
    assert not [x for x in sb.log if x[1] != "select"]               # nasucho nič nezapíše
    sb = _Sb()
    p = d.posli_firmam(sb, "h", True, _smtp=_Smtp)
    assert p["firmy"] == 1 and len(_Smtp.poslane) == 1
    m = _Smtp.poslane[0]
    assert m["To"] == "f@firma.sk" and "starosta@hran.sk" in m.get_content()
    zapisy = [x for x in sb.log if x[1] != "select"]
    assert zapisy[0][1] == "insert" and zapisy[0][3]["vlna"] == "dopyt-324698" and zapisy[0][3]["ico"] == "firma-11"
    assert zapisy[-1][1] == "update" and zapisy[-1][3]["stav"] == "odoslane"
