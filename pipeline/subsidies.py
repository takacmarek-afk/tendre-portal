"""Dotacie ako predzvest tendra.

Ked obec dostane nenavratny financny prispevok na rekonstrukciu skoly,
musi na tu rekonstrukciu vyhlasit verejne obstaravanie. Vidime to teda
o pol roka az rok a pol skor, nez sa tender objavi vo vestniku.

Pozor na semantiku CRZ: pri dotacnej zmluve je poskytovatel (ministerstvo,
agentura) v poli objednavatela a PRIJIMATEL, teda obec, je v poli dodavatela.
Je to naopak nez pri beznej zmluve — ale NIE VZDY. Cast zmluv ma strany
zapisane obratene a pipeline ich otaca, viz komentar pri `_je_vyssi_subjekt`.

DODATKY: PRILEZITOSTI ICH ZAHADZUJU VSETKY, DOTACIE NIE
Nie je to nekonzistencia, je to iny dovod a stoji za to to zapisat, aby to
niekto (aj ja) "neopravil" na jednotny postup:

  * V prilezitostiach je rozhodujuci KONIEC ZMLUVY. Ten ma materska
    zmluva, takze dodatok nepridava ziadny novy signal — len by tu istu
    zakazku zobrazil druhy raz.
  * V dotaciach je OSIRELY dodatok casto JEDINY DOKAZ, ze peniaze boli
    priznane. Materska zmluva moze byt mimo nasej historie, alebo jej
    uz preslo okno (`okno_do` = ucinne_od + 540 dni) a odfiltrovala sa
    skor. Zahodit osirely dodatok teda znamena stratit celu prilezitost.

Preto sa v dotaciach zahadzuje len dodatok, ktoremu sa NASIEL rodic,
a osirele sa ponechavaju a oznacia. Zo SUCTOV OBJEMU sa vsak dodatky
vyhadzuju vzdy — viz `bez_dvojitych_zapisov`.

OKNO SA POCITA Z UCINNOSTI, NIE Z PODPISU
`okno_od` = ucinne_od + 180 dni, `okno_do` = ucinne_od + 540 dni, a ked
`ucinne_od` chyba, pouzije sa podpis. Preto ma zmluva podpisana v roku
2002 s ucinnostou 2025 okno az na rok 2026 — a je to spravne, lebo
obstaravat sa zacne po ucinnosti.

Riadky s `okno_do` pred dneskom sa ZAHADZUJU (viz filter nizsie). Dosledok,
ktory treba mat na pamati pri citani cisel: "okno preslo" je preto vzdy
NULA a v UI sa taky stav ani neponuka.
"""
import logging
import re
from datetime import date, timedelta

import pandas as pd

import regiony
import score
from classify import klasifikuj_ucel, SEKTOR_DOTACIE, bez_diakritiky
from config import DOTACIA_OKNO_OD_DNI, DOTACIA_OKNO_DO_DNI, MIN_DOTACIA_EUR

log = logging.getLogger("subsidies")


# Samosprava sa pozna podla ZACIATKU nazvu, nie podla vyskytu kdekolvek.
#
# TOTO BOLA SKUTOCNA CHYBA A MALA VIDITELNY DOSLEDOK. V CRZ je za nazvom
# organizacie casto prilepena aj jej adresa:
#
#   "Ministerstvo financií SR, Štefanovičova 5, 817 82
#    Bratislava - mestská časť Staré Mesto"
#
# Stara verzia hladala "mestska cast" KDEKOLVEK v texte a nasla to
# v ADRESE. Ministerstvo teda preslo filtrom na samospravu a skoncilo
# v tabulke dotacii ako PRIJIMATEL. Kedze kraj sa odvodzuje z nazvu
# prijimatela, dostalo Bratislavsky kraj a mesto Bratislava — takze
# dotacia pre Obec Ludovitova (Nitriansky kraj) sa zakaznikovi
# zobrazovala ako bratislavska. Odmerane 16. 9. 2026: 4 taketo riadky.
#
# Je to ta ista trieda chyby ako pri uceni mapy PSC (viz regiony.py):
# zhoda podretazcom v poli, ktore obsahuje viac nez nazov.
_PREFIXY_OBCE = ("obec ", "mesto ", "mestska cast", "mestsky urad",
                 "obecny urad")

# Kraj sa menuje "Kosicky samospravny kraj", takze "samospravny kraj" NIE JE
# na zaciatku nazvu a prefixova zhoda tu nefunguje. V adresach sa to ale
# nevyskytuje, takze substringova zhoda je bezpecna. To iste plati pre skoly
# a nemocnice.
_KDEKOLVEK_SAMOSPRAVA = ("samospravny kraj", "vyssi uzemny celok",
                         "zakladna skola", "materska skola", "stredna skola",
                         "gymnazium", "domov socialnych", "nemocnica",
                         "poliklinika", "zakladna umelecka")


def _norm_nazov(nazov) -> str:
    return bez_diakritiky(str(nazov or "")).lower().strip()


def _je_obec_alebo_mesto(nazov: str) -> bool:
    """Len OBEC alebo MESTO, nie kraj, nie skola, nie poliklinika.

    Pouziva sa ako JEDNA Z DVOCH podmienok pri odhalovani vymenenych
    stran. Sama o sebe NESTACI a moj prvy pokus na tom padol: obec v poli
    poskytovatela je totiz aj vtedy, ked mesto legitimne dava dotaciu
    svojej vlastnej organizacii ("Mesto Senica -> Mestska poliklinika").
    Takych riadkov je 17 a su spravne orientovane.

    Rozhoduje az dvojica: vyssi subjekt ako prijimatel A obec ako
    poskytovatel. Viz `_je_vyssi_subjekt`.
    """
    return _norm_nazov(nazov).startswith(_PREFIXY_OBCE)


def _je_samosprava(nazov: str) -> bool:
    """Hruby filter na obce, mesta, kraje a ich organizacie.
    Firmy dostavaju dotacie tiez, ale tie si obstaravanie robit nemusia."""
    if not nazov:
        return False
    n = _norm_nazov(nazov)
    return (n.startswith(_PREFIXY_OBCE)
            or any(k in n for k in _KDEKOLVEK_SAMOSPRAVA))


# ── Kanonicky nazov subjektu ───────────────────────────────────────────────
# V CRZ je za nazvom casto prilepena adresa a ten isty subjekt ma viacero
# pisanych podob. Odmerane 16. 9. 2026: Ministerstvo dopravy figuruje ako
# 19 ROZNYCH subjektov — "Ministerstvo dopravy SR", "...a vystavby SR",
# "...Slovenskej republiky", "...vystavby a regionalneho rozvoja", jedna
# verzia s dvojitou medzerou a jedna so sekciou na konci. Bez zjednotenia
# hovori kazdy sucet podla poskytovatela o zlomku skutocnosti.
_PSC_V_TEXTE = re.compile(r"\b\d{3}\s?\d{2}\b")
_PRAVNA_FORMA = re.compile(
    r"\b(s\s?r\s?o|spol\s+s\s?r\s?o|a\s?s|v\s?o\s?s|k\s?s|n\s?o|sro|"
    r"prispevkova\s+organizacia|statny\s+podnik|sp)\b")


def bez_adresy(nazov) -> str:
    """Odstrani adresu prilepenu za nazov organizacie.

    Reze na PRVEJ ciarke, za ktorou sa este nachadza PSC:

        "Mesto Gelnica, Banicke namestie 4, 056 01 Gelnica"  -> "Mesto Gelnica"
        "Obec Mestecko, c. 118, 020 52 Mestecko"             -> "Obec Mestecko"
        "Diervilla, spol. s r.o."                            -> nezmenene (nema PSC)

    PRVA a nie POSLEDNA ciarka zamerne. Rezanie na poslednej nechavalo
    v texte ulicu: "ProjektyEuropskychSpolocenstiev, s.r.o., 1. maja
    1091/37, 953 01 Zlate Moravce" davalo kluc
    "projektyeuropskychspolocenstiev 1 maja", takze ten isty subjekt
    s inou adresou by sa nezlucil.

    CENA: pri firmach sa odreze aj pravna forma (", s.r.o."). Je to
    prijatelne, pretoze `bez_adresy` sluzi na KLUCE, nie na zobrazovanie,
    a `kanonicky_subjekt` pravne formy aj tak odstranuje. Na stranku ide
    vzdy povodny nazov.
    """
    s = str(nazov or "").strip()
    if not _PSC_V_TEXTE.search(s):
        return s
    kus = ""
    for i, cast in enumerate(s.split(",")):
        zvysok = ",".join(s.split(",")[i:])
        if i > 0 and _PSC_V_TEXTE.search(zvysok):
            break
        kus = (kus + "," + cast) if kus else cast
    return kus.strip().rstrip(",-– ").strip() or s


def kanonicky_subjekt(nazov) -> str:
    """Zjednoteny kluc na porovnavanie subjektov. NIE na zobrazovanie.

    Ministerstva sa krati na dve slova ("ministerstvo dopravy"), cim sa
    zlucia vsetky premenovania a sekcie. Ostatne subjekty na tri slova
    bez pravnej formy, cim sa zlucia "Diervilla s.r.o" a "Diervilla,
    spol. s r.o.".

    POZOR: je to kluc, nie nazov. Na stranku patri povodny `poskytovatel`,
    nie tento vystup — inak by sa zakaznikovi zobrazovalo "ministerstvo
    dopravy" malymi pismenami a bez SR.
    """
    n = bez_diakritiky(bez_adresy(nazov)).lower()
    n = re.sub(r"[^a-z0-9 ]+", " ", n)
    n = _PRAVNA_FORMA.sub(" ", n)
    slova = [w for w in n.split() if w]
    if not slova:
        return ""
    if slova[0] == "ministerstvo":
        return " ".join(slova[:2])
    return " ".join(slova[:3])


# Subjekt NAD obcou: ten, kto obci peniaze rozdava. Obec mu dotaciu
# nikdy nedava, takze taky subjekt v poli PRIJIMATELA znamena, ze su
# strany vymenene.
_VYSSI_PREFIX = ("ministerstv", "urad vlady", "agentura", "slovenska agentura",
                 "slovenska inovacn", "environmentalny fond", "fond na podporu",
                 "statny fond", "posta")
# Kraj sa menuje "Kosicky samospravny kraj", teda nie na zaciatku.
_VYSSI_KDEKOLVEK = ("samospravny kraj", "vyssi uzemny celok")


def _je_vyssi_subjekt(nazov: str) -> bool:
    """Ministerstvo, agentura, fond alebo samospravny kraj.

    NIE organizacia zriadena obcou. To je podstatny rozdiel a moj prvy
    pokus na nom padol: pravidlo "poskytovatel je obec" samo o sebe
    otocilo aj riadok "Mesto Senica -> Mestska poliklinika Senica",
    ktory je pritom SPRAVNE orientovany — mesto naozaj dava dotaciu
    svojej vlastnej poliklinike. Takych je 17 a otocit ich by znamenalo
    vyrobit 17 novych chyb pri oprave 11 starych.
    """
    if not nazov:
        return False
    n = _norm_nazov(nazov)
    return (n.startswith(_VYSSI_PREFIX)
            or any(k in n for k in _VYSSI_KDEKOLVEK))


POTREBNE_STLPCE = ("sector", "price_total", "signed_on", "effective_from",
                   "supplier_name", "supplier_cin", "authority_name",
                   "subject", "subject_description", "id")


def bez_dvojitych_zapisov(df: pd.DataFrame, stlpec_prijimatela: str,
                          log_nazov: str = "") -> pd.DataFrame:
    """Odstrani dodatky a dvojite zverejnenie. Pre SUCTY OBJEMU.

    `obce.py` a `ucely.py` pocitaju z hrubych `contracts`, nie z uz
    odduplikovaneho vystupu tohto modulu, takze ich sucty boli
    nadhodnotene dvakrat nezavisle:

        dodatky:              682 riadkov = 14,4 % objemu (565 M EUR)
        dvojite zverejnenie: 1 524 riadkov

    Cislo "rozdelil 39 470 869 EUR" na obce.html teda hovorilo o inej
    sume, nez sa naozaj rozdelilo. Objem MUSI byt spravny bez ohladu na
    to, ako sa raz zmeni heuristika na dodatky — preto sa dodatky zo
    suctov vyhadzuju VZDY, aj ked v zozname dotacii ostavaju ako osirele.
    """
    if df.empty:
        return df
    pred = len(df)
    d = df[~df["subject"].apply(lambda x: score.je_dodatok(x, ""))].copy()
    bez_dodatkov = len(d)

    kluc = d[stlpec_prijimatela].apply(
        lambda x: bez_diakritiky(bez_adresy(x)).lower()[:40])
    d = d.assign(_k=kluc).drop_duplicates(
        ["_k", "price_total", "signed_on"], keep="first").drop(columns=["_k"])

    if log_nazov and pred != len(d):
        log.info("%s: zo suctov vyradenych %s dodatkov a %s dvojitych "
                 "zapisov (z %s riadkov zostalo %s).", log_nazov,
                 pred - bez_dodatkov, bez_dodatkov - len(d), pred, len(d))
    return d


def _deduplikuj(d: pd.DataFrame) -> pd.DataFrame:
    """Odstrani dvojite zapisy toho isteho prispevku. Dve nezavisle faze.

    ── FAZA 1: DVOJITE ZVEREJNENIE ────────────────────────────────────────
    Ten isty prispevok je v CRZ casto zverejneny DVAKRAT, raz z kazdej
    strany, a kazdy zapis ma vlastne contract_id. Odmerane 16. 9. 2026:
    z 7 698 riadkov bolo 1 524 nadbytocnych.
    Kluc: prijimatel + suma + datum podpisu.

    ── FAZA 2: DODATKY ────────────────────────────────────────────────────
    Dodatok nie je nova dotacia, je to zmena uz priznanej. Spojit ho
    s materskou zmluvou PRESNE NEVIEME — v CRZ na to nie je pole:
    `contract_identifier` je identifikator TOHTO dokumentu, nie rodica,
    a `type_id` je 1 pri dodatku aj pri beznej zmluve. Vytiahnut cislo
    rodica z textu sa da pri 87 % dodatkov, ale na `contract_identifier`
    sedelo 1 z 12 vzoriek — tá cesta je slepa.

    Pouziva sa preto HEURISTIKA a je zamerne TESNA: dodatok zahodime len
    vtedy, ked ten isty prijimatel ma zakladnu zmluvu OD TOHO ISTEHO
    POSKYTOVATELA. Odmerane:

        siroky kluc (len prijimatel):      611 spojenych,  71 osirelych
        tesny (prijimatel + poskytovatel): 341 spojenych, 341 osirelych

    Siroky kluc teda spajal 270 dodatkov s NESUVISIACIMI dotaciami tej
    istej obce — dodatok k prispevku od Ministerstva investicii pripojil
    k dotacii od Fondu na podporu umenia. Tesny kluc necha viac osirelych,
    ale nezahadzuje naslepo, a to je pri dotaciach spravna vymena.

    ── CO TO NERIESI A PRIZNAVA SA TO NA RIADKU ───────────────────────────
    Dodatok casto nesie AKTUALNEJSIU sumu nez materska zmluva: pri 87
    z 682 dodatkov je suma vyssia. Ked dodatok zahodime, zobrazujeme
    prekonanu sumu. Spojit ich nedokazeme, takze sa to hovori nahlas —
    `ma_dodatky` drzi ich pocet a UI k tomu pise, ze suma sa mohla zmenit
    a da sa overit v CRZ (odkaz na riadku je od migracie 14).

    ── PRECO PRILEZITOSTI ZAHADZUJU VSETKY DODATKY A DOTACIE NIE ──────────
    Nie je to nekonzistencia, je to iny dovod. V prilezitostiach je
    rozhodujuci KONIEC ZMLUVY a ten ma materska zmluva, takze dodatok
    ziadny novy signal nepridava. V dotaciach je osirely dodatok casto
    JEDINY DOKAZ, ze peniaze boli priznane — materska zmluva moze byt
    mimo nasej historie. Preto sa osirele dodatky ponechavaju.
    """
    if d.empty:
        return d

    pred = len(d)
    d = d.copy()
    d["_prij_kluc"] = d["prijimatel"].apply(
        lambda x: bez_diakritiky(bez_adresy(x)).lower()[:40])
    d["_posk_kluc"] = d["poskytovatel"].apply(kanonicky_subjekt)
    d["je_dodatok"] = d["ucel"].apply(lambda x: score.je_dodatok(x, ""))
    d["contract_id_alt"] = pd.NA
    d["ma_dodatky"] = 0

    # Poradie preferencie pri zluceni: ma kraj -> ma ICO -> nizsie
    # contract_id. Posledne kriterium je tam pre DETERMINIZMUS — bez neho
    # by ten isty vstup dal pri kazdom behu iny primarny zaznam a odkaz
    # do CRZ by sa zakaznikovi menil pod rukami.
    d["_ma_kraj"] = d["kraj"].notna().astype(int)
    d["_ma_ico"] = d["prijimatel_ico"].notna().astype(int)
    d = d.sort_values(["_ma_kraj", "_ma_ico", "contract_id"],
                      ascending=[False, False, True])

    # ── FAZA 1 ────────────────────────────────────────────────────────────
    kluc1 = ["_prij_kluc", "suma", "podpisane"]
    alt = (d.groupby(kluc1, dropna=False)["contract_id"]
             .apply(lambda s: s.iloc[1] if len(s) > 1 else pd.NA))
    d = d.drop_duplicates(kluc1, keep="first").copy()
    d["contract_id_alt"] = d.set_index(kluc1).index.map(alt).values
    po_faze1 = len(d)

    # ── FAZA 2 ────────────────────────────────────────────────────────────
    zakladne = d[~d["je_dodatok"]]
    pary = set(zip(zakladne["_prij_kluc"], zakladne["_posk_kluc"]))
    ma_rodica = d["je_dodatok"] & d.apply(
        lambda r: (r["_prij_kluc"], r["_posk_kluc"]) in pary, axis=1)

    if ma_rodica.any():
        # Pocitadlo na PREZIVAJUCI riadok, aby sa zahodenie neslo bez stopy.
        pocty = (d[ma_rodica].groupby(["_prij_kluc", "_posk_kluc"]).size())
        idx = pd.MultiIndex.from_arrays(
            [d["_prij_kluc"], d["_posk_kluc"]])
        d["ma_dodatky"] = idx.map(pocty).fillna(0).astype(int).values
        d.loc[d["je_dodatok"], "ma_dodatky"] = 0

    d = d[~ma_rodica].copy()

    log.info("Dotacie po deduplikacii: %s riadkov (z %s). Dvojite "
             "zverejnenie zlucilo %s, dodatkov s rodicom zahodenych %s, "
             "osirelych dodatkov ponechanych %s.",
             len(d), pred, pred - po_faze1, int(ma_rodica.sum()),
             int(d["je_dodatok"].sum()))

    return d.drop(columns=["_prij_kluc", "_posk_kluc", "_ma_kraj", "_ma_ico"])


def adresy_samosprav(df: pd.DataFrame) -> dict:
    """Mapa {ICO: adresa} zo vsetkych zmluv, kde je organizacia OBSTARAVATELOM.

    Presne toto nam chybalo na urcenie kraja malych obci. Obec Zdana nie je
    v zozname okresnych miest, takze z nazvu kraj neurcime — ale tá istá obec
    ma v CRZ vlastne zmluvy, kde je obstaravatelom, a tam je jej adresa
    "Jarmocna 118/4, 044 11 Zdana". Z PSC 044 uz kraj vieme.

    Pri viacerych adresach na jedno ICO beriem tu najcastejsiu, nie prvu —
    adresy sa v case menia a preklepy su bezne.
    """
    if df.empty or "authority_cin" not in df.columns:
        return {}
    d = df[df["authority_cin"].notna() & df["authority_address"].notna()]
    if d.empty:
        return {}
    # POZOR: dict(zip(...)) nechava pri duplicitnom kluci POSLEDNU hodnotu,
    # nie prvu. Bez drop_duplicates by zoradenie zostupne podla poctu
    # vybralo tu NAJMENEJ castu adresu — presny opak toho, co chcem.
    pom = pd.DataFrame({
        "ico": d["authority_cin"].astype(str).str.strip(),
        "adresa": d["authority_address"],
    })
    pocty = (pom.groupby(["ico", "adresa"]).size().reset_index(name="n")
                .sort_values(["ico", "n"], ascending=[True, False])
                .drop_duplicates("ico", keep="first"))
    return dict(zip(pocty["ico"], pocty["adresa"]))


def z_contracts(df: pd.DataFrame, dnes: date = None,
                adresy_podla_ica: dict = None) -> pd.DataFrame:
    """Vstup: vsetky ulozene zmluvy. Vystup: riadky pre tabulku subsidies."""
    dnes = dnes or date.today()
    if df.empty:
        return pd.DataFrame()

    # Chybajuci stlpec sa tu nesmie tvarit ako prazdna hodnota. Prave to nam
    # spravilo "dotacie=0" bez jedinej chybovej hlasky — filter na datum vyhodil
    # vsetko, pretoze `signed_on` sa vobec nestahoval z databazy.
    chyba = [c for c in POTREBNE_STLPCE if c not in df.columns]
    if chyba:
        raise KeyError(
            f"Dotacie: v datach chybaju stlpce {chyba}. "
            f"Doplnte ich do store.nacitaj_contracts.")

    d = df[df["sector"] == SEKTOR_DOTACIE].copy()
    log.info("Dotacnych zmluv v databaze: %s", len(d))
    if d.empty:
        return pd.DataFrame()

    d["suma"] = pd.to_numeric(d["price_total"], errors="coerce")
    d["podpisane"] = pd.to_datetime(d["signed_on"], errors="coerce")
    d["ucinne_od"] = pd.to_datetime(d["effective_from"], errors="coerce")

    # Zaklad pre odhad okna: ucinnost, a ked chyba, tak podpis.
    zaklad = d["ucinne_od"].fillna(d["podpisane"])
    d = d[zaklad.notna() & (d["suma"] >= MIN_DOTACIA_EUR)].copy()
    if d.empty:
        return pd.DataFrame()

    zaklad = d["ucinne_od"].fillna(d["podpisane"])
    d["okno_od"] = zaklad + pd.Timedelta(days=DOTACIA_OKNO_OD_DNI)
    d["okno_do"] = zaklad + pd.Timedelta(days=DOTACIA_OKNO_DO_DNI)

    # Dotacie, ktorym uz okno uplynulo, su bezcenne — tender uz bud bol,
    # alebo sa projekt nerealizoval.
    d = d[d["okno_do"] >= pd.Timestamp(dnes)].copy()
    if d.empty:
        return pd.DataFrame()

    # V CRZ je prijimatel dotacie v poli dodavatela.
    d["prijimatel"] = d["supplier_name"]
    d["prijimatel_ico"] = d["supplier_cin"]
    d["poskytovatel"] = d["authority_name"]
    d["strany_vymenene"] = False

    # ── VYMENENE STRANY ───────────────────────────────────────────────────
    # To "naopak" v hlavicke tohto modulu NEPLATI VZDY. Pri casti zmluv je
    # poskytovatel v poli dodavatela a obec v poli objednavatela, teda
    # presne naopak nez inak. Odmerane 16. 9. 2026: 11 riadkov z 3 276
    # (0,4 %) — malo, ale kazdy jeden je viditelna nezmysel: "Ministerstvo
    # financii" alebo "Kosicky samospravny kraj" ako PRIJIMATEL dotacie.
    #
    # A skoda nie je len v poradi stlpcov. Kraj sa odvodzuje z nazvu
    # prijimatela, takze tych 11 riadkov dostalo kraj a mesto SIDLA
    # POSKYTOVATELA: styri Bratislavu, sest Kosice. Dotacia pre Obec
    # Ludovitova sa teda zakaznikovi zobrazovala ako bratislavska.
    #
    # Riadky NEZAHADZUJEM, ale otacam — obec za nimi je skutocna
    # prilezitost a prisli by sme o nu.
    # PRAVIDLO: obec alebo mesto v poli POSKYTOVATELA a zaroven NIE obec
    # v poli prijimatela. Obec totiz nikdy nedava dotaciu ministerstvu ani
    # kraju — taky riadok je teda spolahlivo otoceny.
    #
    # Naopak "Mesto Senica dava dotaciu Mestskej poliklinike Senica" je
    # spravna orientacia a tych je 17. Tie sa NEOTACAJU, len oznacia.
    vymenene = (d["prijimatel"].apply(_je_vyssi_subjekt)
                & d["poskytovatel"].apply(_je_obec_alebo_mesto))
    if vymenene.any():
        log.info("Dotacie: %s zmluv ma vymenene strany (poskytovatel v poli "
                 "prijimatela), otacam ich.", int(vymenene.sum()))
        # `authority_cin` je ICO tej strany, ktora je v poli objednavatela —
        # po otoceni je to prijimatel, takze ICO musi ist s nim.
        d.loc[vymenene, ["prijimatel", "poskytovatel", "prijimatel_ico"]] = (
            d.loc[vymenene, ["poskytovatel", "prijimatel", "authority_cin"]].values)
        d.loc[vymenene, "strany_vymenene"] = True

    d = d[d["prijimatel"].apply(_je_samosprava)].copy()
    if d.empty:
        return pd.DataFrame()

    d["ucel"] = d["subject"].fillna("") + " " + d["subject_description"].fillna("")
    # Rovnake ocistenie ako pri prilezitostiach. CRZ posiela HTML entity
    # aj v dotacnych predmetoch a bez tohto by sa `&quot;` zobrazilo
    # zakaznikovi ako text. Drzim to na jednej funkcii v score.py, aby
    # sa obe vrstvy nemohli rozist.
    d["ucel"] = d["ucel"].apply(score.odkoduj_entity).str.strip()
    for stlpec in ("prijimatel", "poskytovatel"):
        d[stlpec] = d[stlpec].apply(
            lambda x: score.odkoduj_entity(x) if isinstance(x, str) else x)
    d["sektor_odhad"] = d.apply(
        lambda r: klasifikuj_ucel(r["subject"], r["subject_description"]), axis=1)


    # POZOR: nie regiony.doplnit(). Adresa v dotacnej zmluve patri
    # ministerstvu v Bratislave, nie obci, ktora dotaciu dostala. Kraj sa
    # tu preto odvodzuje z NAZVU prijimatela, a ked nazov nesadne (male
    # obce v zozname okresnych miest nie su), z VLASTNEJ adresy prijimatela
    # dohladanej podla ICO.
    d = regiony.doplnit_z_nazvu(d, "prijimatel",
                                adresy_podla_ica=adresy_podla_ica,
                                stlpec_ica="prijimatel_ico")
    bez_kraja = int(d["kraj"].isna().sum())
    if bez_kraja:
        log.info("Dotacie bez kraja: %s z %s (%.1f %%).",
                 bez_kraja, len(d), 100.0 * bez_kraja / len(d))

    d["odkaz"] = "https://www.crz.gov.sk/zmluva/" + d["id"].astype(str) + "/"
    d["contract_id"] = d["id"]

    # Deduplikacia AZ TU, po vypocte kraja. Preferencia pri zluceni je
    # "ma kraj -> ma ICO -> nizsie contract_id", takze kraj uz musi
    # existovat — inak by sa vyberal primarny zaznam naslepo.
    d = _deduplikuj(d)
    if d.empty:
        return pd.DataFrame()

    for c in ("podpisane", "ucinne_od", "okno_od", "okno_do"):
        d[c] = d[c].dt.strftime("%Y-%m-%d")

    stlpce = ["contract_id", "prijimatel", "prijimatel_ico", "poskytovatel",
              "ucel", "suma", "podpisane", "ucinne_od", "sektor_odhad",
              "okno_od", "okno_do", "odkaz", "mesto", "kraj",
              "strany_vymenene", "contract_id_alt", "ma_dodatky",
              "je_dodatok"]
    out = d[stlpce].sort_values("suma", ascending=False).reset_index(drop=True)
    out["contract_id"] = pd.to_numeric(out["contract_id"], errors="coerce").astype("Int64")
    return out
