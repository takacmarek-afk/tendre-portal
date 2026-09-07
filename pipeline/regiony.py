"""Urcenie mesta a kraja z adresy obstaravatela alebo z nazvu organizacie.

Adresu uz mame ulozenu pri kazdej zmluve, len sme ju nikdy nepouzili.
Filter na mesto a kraj teda nepotrebuje ziadny novy zdroj dat.

DVE CESTY, KAZDA PRE INU VRSTVU:
  doplnit(df)                     — z adresy obstaravatela (bezne zmluvy)
  doplnit_z_nazvu(df, "stlpec")   — z nazvu organizacie (dotacie)

Pri dotacnej zmluve je totiz v poli adresy sidlo MINISTERSTVA v Bratislave,
nie sidlo obce, ktora dotaciu dostala. Keby sme aj tam pouzili adresu,
kazda dotacia na Slovensku by skoncila v Bratislavskom kraji.

PRESNOST: mapujeme podla nazvu mesta, nie podla PSC. Zoznam obsahuje
vsetkych 79 okresnych miest a najvacsie mesta. Zmluvy uradov v malych
obciach zostanu bez kraja — vtedy je v `mesto` aspon nazov z adresy.

Zamerne NEHADAME. Nespravne priradeny kraj je horsi nez prazdna hodnota:
firma z Presova si vyfiltruje Presovsky kraj, dostane kosicke zakazky
a stratime doveru na prvy pohlad.
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
        "Giraltovce", "Spišská Belá", "Vysoké Tatry", "Stará Ľubovňa",
        "Spišské Podhradie", "Podolínec",
    ],
    "Košický kraj": [
        "Košice", "Gelnica", "Michalovce", "Rožňava", "Sobrance",
        "Spišská Nová Ves", "Trebišov", "Moldava nad Bodvou", "Sečovce",
        "Strážske", "Krompachy", "Veľký Šariš", "Dobšiná", "Medzev",
        "Veľké Kapušany", "Kráľovský Chlmec", "Čierna nad Tisou",
    ],
}


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
    """
    if not adresa:
        return None, None, None

    text = re.sub(r"\s+", " ", str(adresa)).strip()

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
        mesto = _CISLO_DOMU.sub("", mesto).strip(" ,.-") or None

    return (mesto or None), psc, kraj


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
    return df


def doplnit_z_nazvu(df, stlpec_nazvu):
    """Prida mesto a kraj odvodene z nazvu organizacie v danom stlpci."""
    if df.empty:
        return df
    if stlpec_nazvu not in df.columns:
        raise KeyError(f"Regiony: v datach chyba stlpec '{stlpec_nazvu}'.")
    rozobrane = df[stlpec_nazvu].apply(z_nazvu)
    df["mesto"] = [r[0] for r in rozobrane]
    df["kraj"] = [r[1] for r in rozobrane]
    return df
