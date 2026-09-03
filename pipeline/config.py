"""Konfiguracia. Klucove slova a prahy sa ladia tu, nikde inde."""
import os

# --- Zdroj dat -------------------------------------------------------------
CRZ_SYNC_URL = "https://datahub.ekosystem.slovensko.digital/api/data/crz/contracts/sync"
USER_AGENT = "tendre-portal/1.0 (open data client)"

BOOTSTRAP_SINCE = os.getenv("BOOTSTRAP_SINCE", "2022-01-01T00:00:00Z")
TIME_BUDGET_MIN = int(os.getenv("TIME_BUDGET_MIN", "45"))

# --- Okno predikcie --------------------------------------------------------
# Bolo 90-180 dni, co je uzke okienko a klient v svojom okrese videl jednu
# polozku. 30-365 ukaze skoro stvornasobok; triedenie podla skore aj tak
# vytlaci to najlepsie hore a filtrovanie si spravi pouzivatel sam.
DNI_MIN = int(os.getenv("DNI_MIN", "30"))
DNI_MAX = int(os.getenv("DNI_MAX", "365"))
MIN_HODNOTA_EUR = float(os.getenv("MIN_HODNOTA_EUR", "5000"))

PRAH_SKORE = int(os.getenv("PRAH_SKORE", "3"))

# --- Vylucujuce slova (platia pre vsetky sektory) --------------------------
# Najcastejsi zdroj falosnych zhod. Najomna zmluva na budovu obsahuje slovo
# "budova", poistna zmluva "strecha", dotacna "rekonstrukcia". Bez tohto
# zoznamu by nam do stavebnych prac padala polovica registra.
NEGATIVNE = [
    "najomna zmluva", "zmluva o najme", "podnajomna", "poistna zmluva",
    "poistenie", "licencna zmluva", "o poskytnuti dotacie", "dotacna zmluva",
    "pracovna zmluva", "dohoda o vykonani prace", "dohoda o pracovnej cinnosti",
    "kolektivna zmluva", "mandatna zmluva", "zmluva o uvere", "darovacia zmluva",
    "zmluva o spolupraci pri vyskume", "memorandum", "zmluva o dielo na vypracovanie studie",
    "kupna zmluva o prevode nehnutelnosti", "zmluva o buducej zmluve",
]
VAHA_NEGATIVNA = -5

# --- Sektory ---------------------------------------------------------------
# Poradie ma vyznam. Pri rovnakom skore vyhrava prvy v poradi, preto su
# specificke remesla PRED vseobecnymi stavebnymi pracami. Klucove slovo patri
# vzdy len do jedneho sektora — inak by sa skore scitavalo dvakrat.
SEKTORY = {
    "ELEKTROINSTALACIE": {
        "cpv": "45310000-3",
        "popis": "Elektroinstalacie a osvetlenie",
        "kluc": {
            3: ["elektroinstalacia", "elektroinstalacne prace", "elektromontazne",
                "rekonstrukcia elektroinstalacie", "verejne osvetlenie",
                "bleskozvod", "rozvadzac", "trafostanica", "fotovoltick",
                "elektricka pripojka"],
            2: ["osvetlenie", "elektrina rozvody", "silnoprud", "slaboprud",
                "revizia elektro"],
        },
    },
    "KURENIE_VODA_PLYN": {
        "cpv": "45330000-9",
        "popis": "Kurenie, voda, plyn, vzduchotechnika",
        "kluc": {
            3: ["vodoinstalacia", "plynoinstalacia", "rekonstrukcia kotolne",
                "vymena kotla", "tepelne cerpadlo", "vykurovacia sustava",
                "rozvody vody", "kanalizacna pripojka", "vodovodna pripojka",
                "vzduchotechnika", "klimatizacia"],
            2: ["kotolna", "vykurovanie", "radiatory", "vodovod", "kanalizacia",
                "cistiaren odpadovych vod", "sanitarne zariadenia"],
        },
    },
    "STRECHY_IZOLACIE": {
        "cpv": "45260000-7",
        "popis": "Strechy, zateplenie, izolacie",
        "kluc": {
            3: ["rekonstrukcia strechy", "vymena strechy", "oprava strechy",
                "stresna krytina", "hydroizolacia", "zateplenie",
                "zateplenie fasady", "klampiarske prace", "izolacia proti vlhkosti"],
            2: ["strecha", "krytina", "fasada", "zateplovaci system"],
        },
    },
    "OKNA_DVERE_POVRCHY": {
        "cpv": "45420000-7",
        "popis": "Okna, dvere, podlahy, povrchove upravy",
        "kluc": {
            3: ["vymena okien", "vymena dveri", "vymena podlah",
                "stolarske prace", "maliarske prace", "obklady a dlazby",
                "sadrokarton"],
            2: ["okna a dvere", "podlaha", "omietky", "malovanie", "dlazba",
                "obklad", "truhlarske"],
        },
    },
    "ZELEN_ZIMNA_UDRZBA": {
        "cpv": "77310000-6",
        "popis": "Udrzba zelene a zimna udrzba",
        "kluc": {
            3: ["udrzba zelene", "kosenie travnatych", "kosenie travy",
                "zimna udrzba", "odpratavanie snehu", "posyp komunikacii",
                "vyrub drevin", "orez stromov", "starostlivost o zelen"],
            2: ["zelen", "travnate plochy", "sadove upravy", "parkova uprava"],
        },
    },
    "UPRATOVANIE": {
        "cpv": "90900000-6",
        "popis": "Upratovacie a cistiace sluzby",
        "kluc": {
            3: ["upratovacie sluzby", "upratovanie", "cistiace sluzby",
                "komplexne upratovanie", "dezinfekcia", "deratizacia",
                "dezinsekcia", "upratovacie prace", "umyvanie okien"],
            2: ["cistenie priestorov", "hygienicky servis", "pranie a zehlenie",
                "sanitarne sluzby"],
        },
    },
    "DOPRAVA_MECHANIZACIA": {
        "cpv": "60000000-8",
        "popis": "Doprava, zemne prace, mechanizacia",
        "kluc": {
            3: ["nakladna doprava", "zemne prace", "vykopove prace",
                "prenajom mechanizacie", "odvoz a zneskodnenie odpadu",
                "prenajom kontajnerov", "autobusova doprava", "zvoz odpadu"],
            2: ["preprava", "odvoz odpadu", "bagrovanie", "prenajom stroja",
                "nakladka", "skladka"],
        },
    },
    "STRAVOVANIE": {
        "cpv": "55500000-5",
        "popis": "Stravovanie a dodavka potravin",
        "kluc": {
            3: ["stravovacie sluzby", "zabezpecenie stravovania",
                "dodavka potravin", "skolske stravovanie", "catering",
                "prevadzka jedalne"],
            2: ["strava", "obedy", "potraviny", "jedalen", "kuchyna vybavenie"],
        },
    },
    "OSTRAHA": {
        "cpv": "79710000-4",
        "popis": "Ostraha, bezpecnost, kamerove systemy",
        "kluc": {
            3: ["strazna sluzba", "ochrana majetku", "bezpecnostna sluzba",
                "kamerovy system", "elektronicka poziarna signalizacia",
                "zabezpecovaci system", "pult centralnej ochrany"],
            2: ["ostraha", "monitoring objektu", "vratnica"],
        },
    },
    "IT_TECHNIKA": {
        "cpv": "72000000-5",
        "popis": "IT sluzby a vypoctova technika",
        "kluc": {
            3: ["vypoctova technika", "dodavka pocitacov", "sprava siete",
                "informacny system", "softverova podpora", "serverova infrastruktura",
                "strukturovana kabelaz", "webove sidlo"],
            2: ["notebooky", "servery", "licencie softver", "it podpora",
                "datove centrum"],
        },
    },
    "TLAC_KANCELARIA": {
        "cpv": "79800000-2",
        "popis": "Tlaciarenske a kancelarske sluzby",
        "kluc": {
            3: ["tlaciarenske sluzby", "tlac publikacii", "polygraficke sluzby",
                "dodavka kancelarskych potrieb", "tonery a naplne"],
            2: ["tlac", "kancelarske potreby", "kopirovacie sluzby"],
        },
    },
    # VSEOBECNE STAVEBNE PRACE JE POSLEDNE ZAMERNE.
    # Je to zberny sektor pre vsetko, co sa netrafilo do konkretneho remesla.
    "STAVEBNE_PRACE": {
        "cpv": "45000000-7",
        "popis": "Stavebne prace vseobecne",
        "kluc": {
            3: ["stavebne prace", "stavebne upravy", "rekonstrukcia objektu",
                "zhotovenie stavby", "realizacia stavby", "vystavba",
                "pristavba", "nadstavba", "obnova budovy", "sanacia",
                "buracie prace", "asfaltovanie", "rekonstrukcia chodnika",
                "oprava miestnej komunikacie", "revitalizacia", "modernizacia budovy"],
            2: ["zmluva o dielo", "stavebny dozor", "chodnik", "miestna komunikacia",
                "telocvicna", "detske ihrisko", "most", "parkovisko",
                "rekonstrukcia", "stavebny material"],
            1: ["oprava", "modernizacia", "udrzba budovy"],
        },
    },
}
