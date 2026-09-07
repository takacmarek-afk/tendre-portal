"""Konfiguracia. Klucove slova a prahy sa ladia tu, nikde inde.

DOLEZITE PRAVIDLO PRE KLUCOVE SLOVA
-----------------------------------
Slovencina sa sklonuje. V zmluvach je "rekonstrukcia strechY", nie "strechA",
a "vymena krytinY", nie "krytinA". Preto sa tu NEPISU cele slova v prvom pade,
ale SLOVNE ZAKLADY: "strech" zachyti strecha, strechy, streche aj strechu.

Toto bola realna chyba, ktora nam znizovala uspesnost klasifikatora na zlomok
skutocnosti. Ked pridavas nove slovo, vzdy si polozi otazku: v akom pade to
bude v zmluve napisane?

Vynimka: pri kratkych alebo nejednoznacnych zakladoch radsej vypis varianty.
Napriklad "oprav" by zachytilo aj "opravnenie podnikat", preto je tam
"oprava", "opravy", "opravu" zvlast.
"""
import os

# --- Zdroj dat -------------------------------------------------------------
CRZ_SYNC_URL = "https://datahub.ekosystem.slovensko.digital/api/data/crz/contracts/sync"
USER_AGENT = "tendre-portal/1.0 (open data client)"

BOOTSTRAP_SINCE = os.getenv("BOOTSTRAP_SINCE", "2023-01-01T00:00:00Z")
TIME_BUDGET_MIN = int(os.getenv("TIME_BUDGET_MIN", "45"))

# --- Okno predikcie --------------------------------------------------------
DNI_MIN = int(os.getenv("DNI_MIN", "30"))
DNI_MAX = int(os.getenv("DNI_MAX", "365"))
MIN_HODNOTA_EUR = float(os.getenv("MIN_HODNOTA_EUR", "5000"))

PRAH_SKORE = int(os.getenv("PRAH_SKORE", "3"))

# --- Dotacie ---------------------------------------------------------------
# Odhad okna, kedy po podpise dotacie pride tender.
DOTACIA_OKNO_OD_DNI = 180
DOTACIA_OKNO_DO_DNI = 540
MIN_DOTACIA_EUR = float(os.getenv("MIN_DOTACIA_EUR", "20000"))

# --- Vylucujuce slova (platia pre vsetky sektory) --------------------------
NEGATIVNE = [
    "najomna zmluva", "zmluva o najme", "podnajomn", "poistna zmluva",
    "poisten", "licencna zmluva",
    "pracovna zmluva", "dohoda o vykonani prace", "dohoda o pracovnej cinnosti",
    "kolektivna zmluva", "mandatna zmluva", "zmluva o uvere", "darovacia zmluva",
    "zmluva o spolupraci pri vyskume", "memorandum",
    "kupna zmluva o prevode nehnutel", "zmluva o buducej zmluve",
]
VAHA_NEGATIVNA = -5

# --- Objekty samospravy ----------------------------------------------------
# Same o sebe nestacia (vaha 2), ale v spojeni s akymkolvek pracovnym slovom
# uz prekrocia prah. "Obnova materskej skoly" = obnov(1) + materskej skol(2).
OBJEKTY_SAMOSPRAVY = [
    "materskej skol", "materska skol", "materskej skoly",
    "zakladnej skol", "zakladna skol",
    "strednej skol", "stredna skol", "gymnazi",
    "obecneho uradu", "obecny urad", "mestskeho uradu", "mestsky urad",
    "kulturneho domu", "kulturny dom", "domu kultury",
    "hasicsk", "dom smutku", "domu smutku",
    "telocvicn", "sportovej hal", "sportova hal", "sportoveho arealu",
    "domov socialnych", "zariadenia pre seniorov", "zariadenie pre seniorov",
    "zdravotneho stredisk", "zdravotne stredisk",
]

# --- Sektory ---------------------------------------------------------------
# Poradie ma vyznam. Pri rovnakom skore vyhrava prvy v poradi, preto su
# dotacie prve a konkretne remesla pred vseobecnymi stavebnymi pracami.
SEKTORY = {
    # DOTACIE SU PRVE ZAMERNE.
    # "Zmluva o poskytnuti NFP na rekonstrukciu ZS" obsahuje "rekonstrukci"
    # a bez tohto poradia by spadla medzi stavebne prace.
    # Nie je to prilezitost na sutazenie — je to predzvest tendra.
    "DOTACIE_NFP": {
        "cpv": None,
        "popis": "Dotacie a nenavratne prispevky (predzvest tendra)",
        "kluc": {
            5: ["nenavratneho financneho prispevku", "nenavratny financny prispevok",
                "o poskytnuti dotaci", "dotacna zmluva", "zmluva o dotaci",
                "o poskytnuti prostriedkov mechanizmu",
                "plan obnovy a odolnosti",
                "o poskytnuti podpory z environmentalneho",
                # Skratka NFP sa v zmluvach pouziva bezne. Zamerne ako
                # viacslovne spojenie — samotne "nfp" by ako podretazec
                # mohlo trafit nieco ine.
                "poskytnuti nfp", "zmluva o nfp", "ziadost o nfp"],
            3: ["nenavratn", "operacny program", "operacneho programu",
                "envirofond", "environmentalneho fondu",
                "o poskytnuti financnych prostriedkov",
                "eurofond", "integrovany regionalny operacny program"],
        },
    },
    # PASPORTIZACIA A SPRAVA BUDOV
    # Pred vseobecnymi stavebnymi pracami: "pasportizacia budov" obsahuje
    # "budov" a bez tohto poradia by spadla medzi stavebne prace.
    # Tento sektor je zamerne uzko vymedzeny na sluzby okolo dokumentacie
    # a spravy budov, nie na stavanie.
    "PASPORTIZACIA_SPRAVA_BUDOV": {
        "cpv": "71315000-9",
        "popis": "Pasportizacia, sprava budov, energeticke audity",
        "kluc": {
            3: ["pasportizaci", "pasport budov", "pasport stavieb",
                "energeticky audit", "energeticke audity", "energeticka certifikaci",
                "energeticky certifikat", "termovizn", "termodiagnostik",
                "digitalizaci dokumentacie", "zameranie stavby", "zamerania stavieb",
                "3d skenovani", "bim model", "technicka pasportizaci",
                "sprava a udrzba nehnutel", "facility management",
                "technicka sprava budov", "technicka sprava objektov"],
            2: ["pasport", "obhliadka budov", "diagnostika budov",
                "energeticky manazment", "revizie technickych zariadeni",
                "evidencia majetku", "sprava nehnutel", "prevadzka budov"],
        },
    },
    "ELEKTROINSTALACIE": {
        "cpv": "45310000-3",
        "popis": "Elektroinstalacie a osvetlenie",
        "kluc": {
            3: ["elektroinstalaci", "elektromontazn", "verejneho osvetleni",
                "verejne osvetleni", "bleskozvod", "rozvadzac", "trafostanic",
                "fotovoltick", "elektrick pripojk"],
            2: ["osvetleni", "silnoprud", "slaboprud", "revizia elektro",
                "elektroenergetick"],
        },
    },
    "KURENIE_VODA_PLYN": {
        "cpv": "45330000-9",
        "popis": "Kurenie, voda, plyn, vzduchotechnika",
        "kluc": {
            3: ["vodoinstalaci", "plynoinstalaci", "kotoln", "vymena kotl",
                "tepelne cerpadl", "tepelneho cerpadl", "vykurovacej sustav",
                "rozvody vody", "kanalizacn pripojk", "vodovodn pripojk",
                "vzduchotechnik", "klimatizaci"],
            2: ["vykurovani", "vykurovania", "radiator", "vodovod",
                "kanalizaci", "cistiaren odpadovych vod", "sanitarn"],
        },
    },
    "STRECHY_IZOLACIE": {
        "cpv": "45260000-7",
        "popis": "Strechy, zateplenie, izolacie",
        "kluc": {
            3: ["strech", "striech", "stresn", "hydroizolaci", "zateplen",
                "klampiarsk", "izolacia proti vlhkosti"],
            2: ["krytin", "fasad", "zateplovaci system", "zateplovacieho systemu"],
        },
    },
    "OKNA_DVERE_POVRCHY": {
        "cpv": "45420000-7",
        "popis": "Okna, dvere, podlahy, povrchove upravy",
        "kluc": {
            3: ["vymena okien", "vymen okien", "vymena dveri", "vymena podlah",
                "stolarsk", "truhlarsk", "maliarsk", "sadrokarton"],
            2: ["okien", "dveri", "podlah", "omietk", "malovani", "dlazb",
                "obklad"],
        },
    },
    "ZELEN_ZIMNA_UDRZBA": {
        "cpv": "77310000-6",
        "popis": "Udrzba zelene a zimna udrzba",
        "kluc": {
            3: ["udrzba zelen", "udrzbu zelen", "udrzby zelen",
                "kosen", "zimna udrzb", "zimnej udrzb", "zimnu udrzb",
                "odpratavani snehu", "odpratavanie snehu", "posyp",
                "vyrub drevin", "orez stromov", "starostlivost o zelen"],
            2: ["zelen", "travnat", "sadove uprav", "parkov uprav",
                "verejnej zelen", "verejna zelen"],
        },
    },
    "UPRATOVANIE": {
        "cpv": "90900000-6",
        "popis": "Upratovacie a cistiace sluzby",
        "kluc": {
            3: ["upratovac", "upratovani", "upratovanie", "upratovania",
                "cistiac", "dezinfekci", "deratizaci", "dezinsekci",
                "umyvani okien", "umyvanie okien"],
            2: ["cisten", "hygienick servis", "pranie a zehleni", "sanitarn sluzb"],
        },
    },
    "DOPRAVA_MECHANIZACIA": {
        "cpv": "60000000-8",
        "popis": "Doprava, zemne prace, mechanizacia",
        "kluc": {
            3: ["nakladn doprav", "zemn prac", "vykopov prac",
                "prenajom mechanizaci", "prenajmu mechanizaci",
                "odvoz a zneskodneni", "prenajom kontajnerov",
                "autobusov doprav", "zvoz odpadu", "zvoz komunalneho"],
            2: ["preprav", "odvoz odpadu", "bagrovani", "nakladka", "skladk"],
        },
    },
    "STRAVOVANIE": {
        "cpv": "55500000-5",
        "popis": "Stravovanie a dodavka potravin",
        "kluc": {
            3: ["stravovaci sluzb", "stravovacich sluzieb", "zabezpeceni stravovani",
                "dodavk potravin", "dodavka potravin", "skolsk stravovani",
                "catering", "prevadzk jedaln"],
            2: ["stravovani", "obedov", "potravin", "jedalen", "jedalne"],
        },
    },
    "OSTRAHA": {
        "cpv": "79710000-4",
        "popis": "Ostraha, bezpecnost, kamerove systemy",
        "kluc": {
            3: ["strazn sluzb", "ochran majetku", "bezpecnostn sluzb",
                "kamerov system", "kamerovy system", "kameroveho systemu",
                "elektronick poziarn signalizaci", "zabezpecovaci system",
                "pult centralnej ochrany"],
            2: ["ostrah", "monitoring objektu", "vratnic"],
        },
    },
    "IT_TECHNIKA": {
        "cpv": "72000000-5",
        "popis": "IT sluzby a vypoctova technika",
        "kluc": {
            3: ["vypoctov technik", "vypoctovej techniky", "dodavk pocitac",
                "sprava siet", "spravu siet", "informacn system",
                "softverov podpor", "serverov infrastruktur",
                "strukturovan kabelaz", "webove sidlo", "webovej stranky"],
            2: ["notebook", "server", "licenci softver", "it podpor",
                "datove centrum"],
        },
    },
    "TLAC_KANCELARIA": {
        "cpv": "79800000-2",
        "popis": "Tlaciarenske a kancelarske sluzby",
        "kluc": {
            3: ["tlaciarensk", "tlac publikaci", "polygrafick",
                "dodavk kancelarsk", "tonerov", "tonery a naplne"],
            2: ["kancelarsk potrieb", "kancelarske potreby", "kopirovaci sluzb"],
        },
    },
    # VSEOBECNE STAVEBNE PRACE JE POSLEDNE ZAMERNE.
    # Zberny sektor pre vsetko, co sa netrafilo do konkretneho remesla.
    "STAVEBNE_PRACE": {
        "cpv": "45000000-7",
        "popis": "Stavebne prace vseobecne",
        "kluc": {
            3: ["stavebn prac", "stavebn uprav", "zhotoveni stavby",
                "realizaci stavby", "vystavb", "pristavb", "nadstavb",
                "burac", "asfaltovani", "rekonstrukci chodnik",
                "oprav miestnej komunikaci", "revitalizaci", "sanaci"],
            2: ["zmluva o dielo", "stavebn dozor", "chodnik", "miestn komunikaci",
                "detsk ihrisk", "mostn", "premosteni", "parkovisk",
                "rekonstrukci", "modernizaci", "stavebn material",
                "spevnen ploch", "cintorin"],
            1: ["oprava", "opravy", "opravu", "obnov", "udrzb budov"],
        },
    },
}

# Objekty samospravy sa pridavaju do vseobecnych stavebnych prac s vahou 2.
# Same o sebe neprekrocia prah, ale v spojeni s "obnova" alebo "oprava" ano.
SEKTORY["STAVEBNE_PRACE"]["kluc"][2].extend(OBJEKTY_SAMOSPRAVY)
