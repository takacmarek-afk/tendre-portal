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


def test_ano_len_kratka_jasna_odpoved():
    import email as _e
    m = _e.message_from_string("From: a@firma.sk\nSubject: Re: x\n\nx")
    for t in ("Áno", "ano, prosím", "Ano dakujem", "OK", "Súhlasím.", "Máme záujem, posielajte"):
        assert o.roztried(m, t) == "ano", t
    for t in ("Áno, a koľko to stojí?", "Ano ale len pre Košický kraj a zavolajte mi", "Nie", "Nemáme záujem",
              "Dobrý deň, áno, robíme aj strechy, ale momentálne máme plno a neviem, či to pre nás je"):
        assert o.roztried(m, t) != "ano", t


def test_ano_od_obce():
    import email as _e
    m = _e.message_from_string("From: obec@hran.sk\nSubject: Re: x\n\nx")
    for t in ("Áno, pošlite to", "Súhlasíme.", "Áno, môžete", "Pošlite prosím"):
        assert o.roztried(m, t) == "ano", t


def test_ano_s_ceskou_alebo_gmail_citaciou_a_podpisom():
    for hlavicka in ("út 17. 11. 2026 v 8:27 odesílatel Marek Takáč z PredTendrom.sk <marek@predtendrom.sk>\nnapsal:",
                     "ut 17. 11. 2026 o 8:27 Marek Takáč <marek@predtendrom.sk> napísal(a):",
                     "On Tue, Nov 17, 2026 at 8:27 AM Marek Takáč <marek@predtendrom.sk> wrote:"):
        t = ("áno\n\n" + hlavicka + "\n\nDobrý deň,\nnadväzujem na môj e-mail. Ak to pre Vás nie je, "
             "odpíšte „nie“ a už nenapíšem.\n\n--\nJán Konateľ\nKonateľ spoločnosti\n+421 900 000 000")
        assert o.text_spravy(sprava(t)) == "áno", hlavicka
        assert triedenie(t) == "ano", hlavicka
    assert triedenie("áno\n\n--\nJán Konateľ\nKonateľ spoločnosti\nwww.firma.sk") == "ano"


def test_gmail_slovenska_citacia_zalomena():
    for t in ("ano\r\n\r\nut 17. 11. 2026 o 8:21 PredTendrom.sk <marek@predtendrom.sk>\r\nnapísal(a):\r\n\r\n> Dobrý deň,",
              "ano\n\nut 17. 11. 2026 o 8:21 PredTendrom.sk <\nmarek@predtendrom.sk> napísal(a):\n\n> Dobrý deň,",
              "Áno\n\nOn Tue, 17. 11. 2026 PredTendrom.sk <marek@predtendrom.sk>\nwrote:"):
        m = sprava(t)
        assert o.roztried(m, o.text_spravy(m)) == "ano", t


def test_gmail_slovenska_citacia():
    t = ("ano\n\nut 17. 11. 2026 o 8:20 PredTendrom.sk <marek@predtendrom.sk> napísal(a):\n\n"
         "Dobrý deň, v Centrálnom registri zmlúv som videl...")
    m = sprava(t)
    assert o.text_spravy(m) == "ano"
    assert o.roztried(m, o.text_spravy(m)) == "ano"


def test_auto_odpoved_odisiel_je_nedorucene():
    m = sprava("Dobrý deň, ďakujem za správu, ale nakoľko moje pôsobenie v spoločnosti X nateraz skončilo, "
               "nemôžem na ňu odpovedať.", predmet="Automatická odpoveď: 37 obstarávaní")
    assert o.roztried(m, o.text_spravy(m)) == "nedorucene"
    m = sprava("Som na dovolenke do 20. 11.", predmet="Automatická odpoveď: x")
    assert o.roztried(m, o.text_spravy(m)) == "auto"
