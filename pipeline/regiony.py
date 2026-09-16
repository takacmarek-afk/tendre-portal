"""Urcenie mesta a kraja z adresy obstaravatela alebo z nazvu organizacie.

Adresu uz mame ulozenu pri kazdej zmluve, len sme ju nikdy nepouzili.
Filter na mesto a kraj teda nepotrebuje ziadny novy zdroj dat.

DVE CESTY, KAZDA PRE INU VRSTVU:
  doplnit(df)                     — z adresy obstaravatela (bezne zmluvy)
  doplnit_z_nazvu(df, "stlpec")   — z nazvu organizacie (dotacie)

Pri dotacnej zmluve je totiz v poli adresy sidlo MINISTERSTVA v Bratislave,
nie sidlo obce, ktora dotaciu dostala. Keby sme aj tam pouzili adresu,
kazda dotacia na Slovensku by skoncila v Bratislavskom kraji.

PRESNOST: prvotne mapujeme podla nazvu mesta. Zoznam obsahuje vsetkych
79 okresnych miest a najvacsie mesta — teda 122 nazvov, nie 2 890 obci.
Male obce preto podla nazvu neurcime.

TRETIA CESTA — PSC, NAUCENE Z VLASTNYCH DAT:
Male obce su v CRZ aj samy obstaravatelmi a maju tam vlastnu adresu
s PSC. Z tych zmluv, ktorym kraj z nazvu mesta URCIT VIEME, sa da naucit
mapa "prvé tri cislice PSC -> kraj" a tou potom doplnit obce, ktore
v zozname nie su. Ziadny novy zdroj dat na to netreba.

  nauc_psc(adresy)                — postavi mapu, vola sa raz za beh
  doplnit_z_nazvu(df, stlpec, adresy_podla_ica=...)

Odmerane 13. 9. 2026: bez tejto cesty nemalo kraj 71,3 % dotacii — teda
782 M EUR z 1 470 M bolo pre filtrovanie podla kraja neviditelnych.
S nou klesol podiel na 17,6 %.

Zamerne NEHADAME. Nespravne priradeny kraj je horsi nez prazdna hodnota:
firma z Presova si vyfiltruje Presovsky kraj, dostane kosicke zakazky
a stratime doveru na prvy pohlad.

Preto hlasuju MESTA a vyzaduje sa UPLNA zhoda. Prva verzia vazila hlasy
poctom zmluv a pri prefixe 925 to zlyhalo: Sladkovicovo (Trnavsky) ma
v CRZ ovela viac zmluv nez obce okolo Sale (Nitriansky), takze prefix
vysiel ako Trnavsky a Obec Kralova nad Vahom skoncila v zlom kraji.
Ked hlasuje kazde mesto raz a staci jeden nesuhlas na zahodenie prefixu,
hranicne prefixy sa neprijmu vobec.
"""
import re
import unicodedata

# Jediny zdroj pravdy. Nazvy su spravne, s diakritikou — zobrazuju sa
# zakaznikovi vo filtri. Normalizovane kluce na porovnavanie sa dopocitaju.
OKRESY = {
    "Bratislavský kraj": [
        "Bratislava", "Malacky", "Pezinok", "Senec", "Stupava", "Svätý Jur",
        "Modra",
    ],
    "Trnavský kraj": [
        "Trnava", "Dunajská Streda", "Galanta", "Hlohovec", "Piešťany",
        "Senica", "Skalica", "Sereď", "Holíč", "Vrbové", "Gbely",
    ],
    "Trenčiansky kraj": [
        "Trenčín", "Bánovce nad Bebravou", "Ilava", "Myjava",
        "Nové Mesto nad Váhom", "Partizánske", "Považská Bystrica",
        "Prievidza", "Púchov", "Dubnica nad Váhom", "Handlová", "Nováky",
        "Stará Turá", "Nemšová", "Trenčianske Teplice",
    ],
    "Nitriansky kraj": [
        "Nitra", "Komárno", "Levice", "Nové Zámky", "Šaľa", "Topoľčany",
        "Zlaté Moravce", "Šurany", "Vráble", "Štúrovo", "Kolárovo",
        "Hurbanovo", "Tlmače", "Želiezovce",
    ],
    "Žilinský kraj": [
        "Žilina", "Bytča", "Čadca", "Dolný Kubín", "Kysucké Nové Mesto",
        "Liptovský Mikuláš", "Martin", "Námestovo", "Ružomberok",
        "Turčianske Teplice", "Tvrdošín", "Liptovský Hrádok", "Rajec",
        "Krásno nad Kysucou", "Trstená", "Vrútky", "Bytčica",
    ],
    "Banskobystrický kraj": [
        "Banská Bystrica", "Banská Štiavnica", "Brezno", "Detva", "Krupina",
        "Lučenec", "Poltár", "Revúca", "Rimavská Sobota", "Veľký Krtíš",
        "Zvolen", "Žarnovica", "Žiar nad Hronom", "Hnúšťa", "Fiľakovo",
        "Tornaľa", "Sliač", "Nová Baňa", "Kremnica", "Tisovec", "Dudince",
    ],
    "Prešovský kraj": [
        "Prešov", "Bardejov", "Humenné", "Kežmarok", "Levoča",
        "Medzilaborce", "Poprad", "Sabinov", "Snina", "Stará Ľubovňa",
        "Stropkov", "Svidník", "Vranov nad Topľou", "Svit", "Lipany",
        "Giraltovce", "Spišská Belá", "Vysoké Tatry",
        "Spišské Podhradie", "Podolínec",
        # Velky Saris tu chybal a bol omylom vedeny v Kosickom kraji.
        # Patri do okresu Presov. Chyba tohto typu je najhorsia, aku tu
        # mozeme mat: nielenze zaradi mesto do zleho kraja, ale otravi aj
        # naucenu mapu PSC — z prefixu 082 by sa stal "Kosicky kraj"
        # a s nim by do Kosickeho kraja spadli vsetky obce okolo Presova.
        "Veľký Šariš",
        "Spišská Stará Ves", "Hanušovce nad Topľou",
    ],
    "Košický kraj": [
        "Košice", "Gelnica", "Michalovce", "Rožňava", "Sobrance",
        "Spišská Nová Ves", "Trebišov", "Moldava nad Bodvou", "Sečovce",
        "Strážske", "Krompachy", "Dobšiná", "Medzev",
        "Veľké Kapušany", "Kráľovský Chlmec", "Čierna nad Tisou",
        "Spišské Vlachy",
    ],
}

# Kontrola pri importe. Duplicitny nazov v dvoch krajoch by sa inak
# prepisal potichu a vyhralo by to, co je v slovniku neskor — presne
# takto sa tu "Velky Saris" tvaril ako kosicky. Radsej padnem pri starte.
_videne = {}
for _k, _mesta in OKRESY.items():
    for _m in _mesta:
        if _m in _videne and _videne[_m] != _k:
            raise ValueError(
                f"Regiony: mesto '{_m}' je v dvoch krajoch — "
                f"'{_videne[_m]}' a '{_k}'. Oprav OKRESY.")
        _videne[_m] = _k
del _videne


def _norm(t: str) -> str:
    nfkd = unicodedata.normalize("NFKD", str(t or ""))
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


# normalizovany nazov -> (spravny nazov, kraj)
MESTO_KRAJ = {}
for _kraj, _mesta in OKRESY.items():
    for _m in _mesta:
        MESTO_KRAJ[_norm(_m)] = (_m, _kraj)

_PSC = re.compile(r"\b(\d{3})\s?(\d{2})\b")

# Vzor na hladanie mesta v nazve organizacie. Od najdlhsieho nazvu, aby
# "Banska Bystrica" vyhrala nad pripadnou kratsou zhodou.
_V_NAZVE = re.compile(
    r"\b(" + "|".join(re.escape(m) for m in
                      sorted(MESTO_KRAJ, key=len, reverse=True)) + r")\b")

# Pri neznamom meste odstranime cislo domu — "Neznama 1" ako nazov mesta
# vo filtri vypada ako chyba.
_CISLO_DOMU = re.compile(r"\s*\d+\s*[a-zA-Z]?\s*$")

# A po nom aj znacku cisla, ktora tam zostane. Adresa "Rakovice c. 8" dala
# po odstraneni cisla "Rakovice c." a strip(" ,.-") z toho urobil
# "Rakovice c" — takto to aj naozaj bolo na stranke v zalozke ziadatelov.
# Pozor na diakritiku: v adresach je "c." aj "c." s hackom, takze trieda
# znakov [cc] obsahuje oba tvary. Bez toho by sa opravila len polovica.
_ZNACKA_CISLA = re.compile(r"[\s,.\-]*\b(?:[cč]|[cč]islo|no|nr)\b[\s,.\-]*$",
                           re.IGNORECASE)


def _hladaj(text: str):
    """Najde znamy nazov mesta v texte. Vrati (spravny nazov, kraj) alebo (None, None)."""
    m = _V_NAZVE.search(_norm(text))
    if m:
        return MESTO_KRAJ[m.group(1)]
    return None, None


def rozober_adresu(adresa):
    """Vrati (mesto, psc, kraj). Kazda hodnota moze byt None.

    Adresy v CRZ maju tvar "Ulica 1, P.O. Box 5, 814 99 Bratislava" alebo
    "Namestie 1, 010 01 Zilina". Mesto je teda za PSC.

    POZOR NA NaN. Toto tu uz raz nefungovalo a bolo to VIDIET NA STRANKE:
    Obec Smrdaky mala v zalozke ziadatelov ako mesto napisane "nan".
    Pandas dava do chybajucej hodnoty float("nan") a `not float("nan")`
    je v Pythone False, takze stara podmienka `if not adresa` NaN
    prepustila, `str(nan)` z toho urobil retazec "nan" a ten preposol
    az do databazy. Preto sa tu NaN testuje explicitne.
    """
    if adresa is None:
        return None, None, None
    # NaN sa nerovna sam sebe. Nechcem tu importovat pandas len pre isna().
    if isinstance(adresa, float) and adresa != adresa:
        return None, None, None

    text = re.sub(r"\s+", " ", str(adresa)).strip()
    if not text or text.lower() in ("nan", "none", "null", "<na>"):
        return None, None, None

    def prve_slovo_mesta(s):
        """"Bratislava - mestska cast Karlova Ves" -> "Bratislava"."""
        s = re.sub(r"^\d{3}\s?\d{2}\s*", "", s or "").strip(" ,.-")
        return re.split(r"\s*[-–]\s*|,", s)[0].strip() or None

    def posledny_diel(s):
        """Posledny neprazdny useknuty diel. Pozor: pred PSC byva ciarka,
        takze naivne split(",")[-1] vrati prazdny retazec."""
        casti = [c for c in (s or "").split(",") if c.strip()]
        return casti[-1] if casti else None

    mesto, psc = None, None
    m = _PSC.search(text)
    if m:
        psc = m.group(1) + " " + m.group(2)
        # Mesto byva ZA PSC, ale niekedy je PSC na konci adresy a mesto
        # pred nim: "Bratislava - mestska cast Karlova Ves, 841 04".
        mesto = (prve_slovo_mesta(text[m.end():])
                 or prve_slovo_mesta(posledny_diel(text[:m.start()])))

    if not mesto:
        mesto = prve_slovo_mesta(posledny_diel(text))

    # Ked mesto pozname, pouzijeme NASU podobu nazvu. Inak zostane surovy
    # text z adresy, ale bez cisla domu.
    znamy, kraj = _hladaj(mesto) if mesto else (None, None)
    if znamy:
        mesto = znamy
    elif mesto:
        mesto = _CISLO_DOMU.sub("", mesto)
        mesto = _ZNACKA_CISLA.sub("", mesto).strip(" ,.-") or None
        # Po odstraneni cisla a znacky moze zostat samotna cast adresy
        # bez nazvu obce. Cokolvek kratsie nez tri znaky nie je nazov.
        if mesto and len(mesto) < 3:
            mesto = None

    return (mesto or None), psc, kraj


# ── PSC -> kraj, naucene z vlastnych dat ───────────────────────────────────
# Prazdna mapa znamena "nenaucene" a treti fallback sa vtedy vobec nespusti.
# Chcem, aby sa pipeline bez nauceneho kroku chovala presne ako predtym.
PSC_KRAJ = {}     # tri cislice -> kraj, presnejsie
PSC2_KRAJ = {}    # dve cislice -> kraj, hrubsie, len ked je jednoznacne

# Diagnostika, nie data: trojciferne prefixy, ktore sa zahodili PRE SPOR
# medzi krajmi, a kto za ktory kraj hlasoval. Zapisuje sa v _prijmi()
# a vypisuje v nauc_psc(). Nic sa podla toho nerozhoduje — sluzi to na to,
# aby sa dalo pozriet, ci je zahodenie skutocna hranica kraja, alebo jedno
# pokazene mesto, ktore kazi cely okres.
SPORY = {}

# Hlasuju MESTA, nie zmluvy — vid vysvetlenie v _prijmi().
MIN_CISTOTA_PSC = 1.0    # ZIADNY spor. Prefix na hranici kraja radsej zahodim.

# Trojciferny prefix pokryva male uzemie, obvykle jeden okres. Jedno znama
# mesto je tam dost silny dokaz.
MIN_MIEST_PSC3 = 1

# Dvojciferny prefix pokryva uzemie niekolkych okresov a hranice krajov
# prekracuje bezne. Jedno mesto by tam mohlo stiahnut desiatky obci z uplne
# ineho kraja, ktore samy hlasovat nevedia, lebo ich v zozname nemame.
# Preto tu chcem vidiet aspon tri mesta, a vsetky musia sedet.
MIN_MIEST_PSC2 = 3


def _prijmi(hlasy, kam, min_miest):
    """Z hlasovania prijme len prefixy, ktore prah prejdu. Vrati (prijate, zahodene).

    HLASUJU MESTA, NIE ZMLUVY. Toto je oprava skutocnej chyby, nie detail.

    Prvy raz som pocital vzorky podla poctu zmluv. Prefix 925 tak vysiel ako
    "Trnavsky kraj", pretoze Sladkovicovo (okres Galanta, Trnavsky) ma v CRZ
    ovela viac zmluv nez obce okolo Sale (Nitriansky) s tym istym prefixom.
    Vysledok: Obec Kralova nad Vahom, ktora patri do okresu Sala, skoncila
    v Trnavskom kraji. Cistota VZORKY nie je cistota UZEMIA — staci jedno
    ukecane mesto a prefix sa prikloni k jeho kraju.

    Ked hlasuje kazde mesto raz, konflikt na hranici kraja sa ukaze aj vtedy,
    ked je jedna strana v datach zastupena stokrat viac.
    """
    zahodene = 0
    zapisuj_spory = kam is PSC_KRAJ
    if zapisuj_spory:
        SPORY.clear()
    for prefix, po_krajoch in hlasy.items():
        # po_krajoch je {kraj: mnozina normalizovanych nazvov miest}
        spolu = sum(len(m) for m in po_krajoch.values())
        kraj, mesta = max(po_krajoch.items(), key=lambda kv: len(kv[1]))
        if spolu >= min_miest and len(mesta) / spolu >= MIN_CISTOTA_PSC:
            kam[prefix] = kraj
        else:
            zahodene += 1
            # Zapisem SI, PRECO sa prefix zahodil. Bez tohto sa neda
            # rozhodnut, ci je zahodenie spravne (skutocna hranica kraja)
            # alebo ci jedno pokazene mesto kazi cely okres. Hadat to
            # z hlavy som skusil a nevedel som to rozhodnut.
            if zapisuj_spory and len(po_krajoch) > 1:
                SPORY[prefix] = {k: sorted(v) for k, v in po_krajoch.items()}
    return len(kam), zahodene


def nauc_psc(adresy, log=None):
    """Postavi mapy PSC -> kraj z adries, ktorym kraj uz urcit vieme podla
    nazvu mesta. Vrati pocet prijatych trojcifernych prefixov.

    Vstup je iterovatelne pole adries (staci `df["authority_address"]`).
    Volaj raz za beh, pred vypoctom prilezitosti aj dotacii.

    Ucime sa na dvoch urovniach, pretoze PSC obce sa nemusi zhodovat
    s PSC jej okresneho mesta — Zdana ma 044, ale Kosice 040. Trojciferny
    prefix je presnejsi, dvojciferny chyta viac obci. Oba maju rovnaku
    poistku: prefix prijmeme len ked ma dost vzoriek a takmer vsetky
    ukazuju na jeden kraj. Dvojciferne prefixy skutocne hranice krajov
    prekracuju (napr. 05x je aj Presovsky aj Kosicky), takze poistka
    ich zahodi — a to je spravne, radsej prazdno nez zle.
    """
    PSC_KRAJ.clear()
    PSC2_KRAJ.clear()
    h3, h2 = {}, {}
    for adresa in adresy:
        if not adresa:
            continue
        mesto, psc, kraj = rozober_adresu(adresa)
        if not (psc and kraj and mesto):
            continue
        cifry = re.sub(r"\D", "", psc)
        if len(cifry) < 3:
            continue
        kluc_mesta = _norm(mesto)
        for hlasy, prefix in ((h3, cifry[:3]), (h2, cifry[:2])):
            hlasy.setdefault(prefix, {})
            hlasy[prefix].setdefault(kraj, set()).add(kluc_mesta)

    p3, z3 = _prijmi(h3, PSC_KRAJ, MIN_MIEST_PSC3)
    p2, z2 = _prijmi(h2, PSC2_KRAJ, MIN_MIEST_PSC2)

    if log:
        log.info("PSC mapa: 3-ciferne %s prijatych / %s zahodenych, "
                 "2-ciferne %s / %s. Hlasuju mesta (nie zmluvy), "
                 "vyzaduje sa uplna zhoda.", p3, z3, p2, z2)

        # Vypis sporov. Zoradene tak, aby boli hore prefixy, kde je
        # nesuhlas NAJTESNEJSI (jedno mesto proti mnohym) — tam je
        # najvyssia sanca, ze nejde o hranicu kraja, ale o chybu.
        def _tesnost(kv):
            po_krajoch = kv[1]
            pocty = sorted((len(m) for m in po_krajoch.values()), reverse=True)
            return (pocty[1], -pocty[0])      # najmensia mensina, najvacsia vacsina

        for prefix, po_krajoch in sorted(SPORY.items(), key=_tesnost)[:12]:
            rozpis = "; ".join(
                f"{kraj.replace(' kraj', '')}={len(mesta)} ({', '.join(mesta[:4])})"
                for kraj, mesta in sorted(po_krajoch.items(),
                                          key=lambda kv: -len(kv[1])))
            log.info("PSC spor %sxx: %s", prefix, rozpis)
        if SPORY:
            log.info("PSC: spornych trojcifernych prefixov %s z %s zahodenych. "
                     "Zvysok sa zahodil pre nedostatok vzoriek, nie pre spor.",
                     len(SPORY), z3)
    return p3


def z_psc(psc):
    """Kraj podla prefixu PSC, alebo None. Funguje len po nauc_psc().

    Najprv skusi presnejsi trojciferny prefix, potom hrubsi dvojciferny.
    """
    if not psc:
        return None
    cifry = re.sub(r"\D", "", str(psc))
    if len(cifry) < 3:
        return None
    return PSC_KRAJ.get(cifry[:3]) or PSC2_KRAJ.get(cifry[:2])


def z_nazvu(nazov):
    """Vrati (mesto, kraj) z NAZVU organizacie. Kazda hodnota moze byt None.

    Toto potrebujeme pri dotaciach — v poli adresy je sidlo ministerstva.
    Nazov samospravy naproti tomu obec takmer vzdy obsahuje: "Mesto Presov",
    "Obec Nizna", "Zakladna skola, Hlavna 5, Kezmarok".
    """
    if not nazov:
        return None, None
    n = _norm(nazov)

    # Najistejsi tvar: "Mesto X" / "Obec X". Zoberieme, co je za slovom.
    m = re.match(r"^(?:mesto|obec|mestska cast)\s+(.+)$", n)
    if m:
        kandidat = re.split(r"\s*[-–,]", m.group(1))[0].strip()
        if kandidat in MESTO_KRAJ:
            return MESTO_KRAJ[kandidat]

    # Inak hladame znamy nazov mesta kdekolvek v nazve, ale ako cele slovo:
    # "Kezmarska 28, Kosice" nesmie sadnut na Kezmarok.
    return _hladaj(nazov)


def doplnit(df):
    """Prida stlpce mesto, psc a kraj z adresy OBSTARAVATELA.

    Pri dotaciach toto NEPOUZIVAJ — pouzi doplnit_z_nazvu(df, "prijimatel").

    Chybajuci stlpec `authority_address` sa tu NESMIE prehliadnut. Keby sme
    len vratili df bez zmeny, prazdny filter na kraj by vypadal ako "ziadne
    zakazky v tvojom kraji" — presne ten typ tichej chyby, ktory nam uz raz
    spravil "dotacie=0". Preto to zhavarujeme s vysvetlenim.
    """
    if df.empty:
        return df
    if "authority_address" not in df.columns:
        raise KeyError(
            "Regiony: v datach chyba stlpec 'authority_address'. "
            "Doplnte ho do store.nacitaj_contracts.")
    rozobrane = df["authority_address"].apply(rozober_adresu)
    df["mesto"] = [r[0] for r in rozobrane]
    df["psc"] = [r[1] for r in rozobrane]
    df["kraj"] = [r[2] for r in rozobrane]

    # Zalozna cesta: co adresa nedala, skusime z nazvu uradu.
    # "Zakladna skola, Hlavna 5, Presov" kraj vyda, aj ked sa adresa
    # rozobrat nedala. Bez tohto zostavala stvrtina zaznamov bez kraja
    # a filter na kraj ich zakaznikovi ticho schoval.
    chyba = df["kraj"].isna()
    if chyba.any() and "authority_name" in df.columns:
        nahradne = df.loc[chyba, "authority_name"].apply(z_nazvu)
        df.loc[chyba, "mesto"] = [n[0] or m for n, m
                                  in zip(nahradne, df.loc[chyba, "mesto"])]
        df.loc[chyba, "kraj"] = [n[1] for n in nahradne]

    # Treti pokus: PSC z adresy. Adresu uz rozobranu mame, takze toto je
    # zadarmo a chyta presne tie male obce, ktore v zozname miest nie su.
    chyba = df["kraj"].isna()
    if chyba.any():
        df.loc[chyba, "kraj"] = [z_psc(p) for p in df.loc[chyba, "psc"]]
    return df


def doplnit_z_nazvu(df, stlpec_nazvu, adresy_podla_ica=None, stlpec_ica=None):
    """Prida mesto a kraj odvodene z nazvu organizacie v danom stlpci.

    `adresy_podla_ica` je nepovinna mapa {ICO: adresa}. Ked ju dostanem,
    riadkom, ktorym nazov kraj nedal, dohladam VLASTNU adresu prijimatela
    a kraj urcim z jej PSC. Nazov obce z tej adresy sa zapise do `mesto`,
    takze male obce uz nebudu v zobrazeni bez mesta.

    Toto je podstatne prave pri dotaciach: v poli adresy zmluvy je sidlo
    ministerstva, ale ta ista obec je inde v CRZ sama obstaravatelom
    a tam uz vlastnu adresu ma.
    """
    if df.empty:
        return df
    if stlpec_nazvu not in df.columns:
        raise KeyError(f"Regiony: v datach chyba stlpec '{stlpec_nazvu}'.")
    rozobrane = df[stlpec_nazvu].apply(z_nazvu)
    df["mesto"] = [r[0] for r in rozobrane]
    df["kraj"] = [r[1] for r in rozobrane]

    if not adresy_podla_ica:
        return df

    stlpec_ica = stlpec_ica or (stlpec_nazvu + "_ico")
    if stlpec_ica not in df.columns:
        raise KeyError(
            f"Regiony: pri dohladavani adresy chyba stlpec '{stlpec_ica}'.")

    chyba = df["kraj"].isna()
    if not chyba.any():
        return df

    mesta, kraje = [], []
    for ico, stare_mesto in zip(df.loc[chyba, stlpec_ica],
                                df.loc[chyba, "mesto"]):
        adresa = adresy_podla_ica.get(str(ico).strip()) if ico else None
        if not adresa:
            mesta.append(stare_mesto)
            kraje.append(None)
            continue
        mesto, psc, kraj = rozober_adresu(adresa)
        mesta.append(mesto or stare_mesto)
        kraje.append(kraj or z_psc(psc))

    df.loc[chyba, "mesto"] = mesta
    df.loc[chyba, "kraj"] = kraje
    return df
