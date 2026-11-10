"""Testy triedenia odpovedi (bez siete)."""
from email.message import EmailMessage
from email import message_from_string

import odpovede as o


def sprava(text, predmet="RE: Zmluvy na ostrahu", od="Jana <jana@firma.sk>", **hl):
    m = EmailMessage()
    m["From"], m["Subject"], m["Message-ID"] = od, predmet, "<abc@firma.sk>"
    for k, v in hl.items():
        m[k.replace("_", "-")] = v
    m.set_content(text)
    return m


def triedenie(text, **kw):
    m = sprava(text, **kw)
    return o.roztried(m, o.text_spravy(m))


def test_jasne_nie():
    assert triedenie("Dobrý deň pán Takáč,\nĎakujem za ponuku. Nemáme záujem.\nSúťaží sa nezúčastňujeme.\n") == "nie"
    assert triedenie("Prosím, neposielajte nám ďalšie e-maily.") == "nie"
    assert triedenie("Nie.") == "nie"
    assert triedenie("Odhláste nás prosím.") == "nie"


def test_otazka_alebo_zaujem_ide_marekovi():
    assert triedenie("Nemáme záujem o ostrahu, ale robíte aj upratovanie?") == "rucne"
    assert triedenie("Dobrý deň, zaujíma nás to, aká je cena?") == "rucne"
    assert triedenie("Ďakujem, pozriem sa na to.") == "rucne"


def test_citacia_nasho_emailu_sa_neberie():
    t = "Ďakujem, zavolajte mi.\n\nOd: Marek Takáč\n> Ak to pre Vás nie je, odpíšte Nie a už nenapíšem."
    assert triedenie(t) == "rucne"
    assert "odpíšte" not in o.text_spravy(sprava(t))


def test_automaticka_odpoved():
    assert triedenie("Som na dovolenke do 20. 11.", predmet="Automatická odpoveď: Zmluvy") == "auto"
    assert triedenie("Nemáme záujem", Auto_Submitted="auto-replied") == "auto"


def test_nedorucena_sprava():
    m = sprava("Delivery failed for stara@firma.sk: user unknown", predmet="Undelivered Mail Returned to Sender",
               od="mailer-daemon@mail.zoho.eu")
    assert o.roztried(m, "") == "nedorucene"
    assert o.nedorucene_adresy(m) == {"stara@firma.sk"}
    m2 = sprava("x", od="MAILER-DAEMON@x.sk", X_Failed_Recipients="a@b.sk, c@d.sk")
    assert o.nedorucene_adresy(m2) == {"a@b.sk", "c@d.sk"}


def test_priradenie_firmy():
    m = sprava("Nie", In_Reply_To="<nasa-123@predtendrom.sk>", od="iny@ina.sk")
    assert o.priradit_ico(m, {}, {}, {"<nasa-123@predtendrom.sk>": "111"}) == "111"
    m = sprava("Nie", od="Katarína <katarina.x@firma.sk>")
    assert o.priradit_ico(m, {"info@firma.sk": "222"}, {"firma.sk": "222"}, {}) == "222"
    assert o.priradit_ico(sprava("Nie", od="cudzi@gmail.com"), {}, {"firma.sk": "222"}, {}) is None


def test_zdvorila_odpoved_hlavicky():
    r = o.zdvorila_odpoved(sprava("Nemáme záujem", predmet="RE: Zmluvy"))
    assert r["Subject"] == "RE: Zmluvy" and r["In-Reply-To"] == "<abc@firma.sk>"
    assert r["To"] == "Jana <jana@firma.sk>" and r["Auto-Submitted"] == "auto-replied"
    assert "ďalej Vás už nebudem kontaktovať" in r.get_content()
    assert o.zdvorila_odpoved(sprava("x", predmet="Zmluvy"))["Subject"] == "Re: Zmluvy"
