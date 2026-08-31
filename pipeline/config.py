"""Konfiguracia. Klucove slova a prahy sa ladia tu, nikde inde."""
import os

# --- Zdroj dat -------------------------------------------------------------
CRZ_SYNC_URL = "https://datahub.ekosystem.slovensko.digital/api/data/crz/contracts/sync"
USER_AGENT = "vo-monitor/1.0 (open data client)"

# Odkial zacat pri uplne prvom behu (dalej uz riadi checkpoint v DB)
BOOTSTRAP_SINCE = os.getenv("BOOTSTRAP_SINCE", "2022-01-01T00:00:00Z")

# Casovy rozpocet jedneho behu v minutach. GitHub Actions ma strop 6 h.
# Bootstrap sa moze rozlozit do viacerych behov, checkpoint sa uklada priebezne.
TIME_BUDGET_MIN = int(os.getenv("TIME_BUDGET_MIN", "45"))

# --- Okno predikcie --------------------------------------------------------
DNI_MIN = int(os.getenv("DNI_MIN", "90"))
DNI_MAX = int(os.getenv("DNI_MAX", "180"))
MIN_HODNOTA_EUR = float(os.getenv("MIN_HODNOTA_EUR", "5000"))

# Do e-mailu posielaj len prilezitosti nad tymto skore
MIN_SKORE_NOTIFIKACIE = int(os.getenv("MIN_SKORE_NOTIFIKACIE", "30"))

# --- Vystupy ---------------------------------------------------------------
SHEET_NAME = os.getenv("SHEET_NAME", "VO_Predikcia")
DB_PATH = os.getenv("DB_PATH", "data/vo.db")

# --- Klasifikator ----------------------------------------------------------
# CRZ neobsahuje CPV kody, preto vazene textove triedenie.
# Zaporne vahy vylucuju najomne, poistne a dotacne zmluvy — to je najcastejsi sum.
PRAH_SKORE = int(os.getenv("PRAH_SKORE", "3"))

SEKTORY = {
    "STAVEBNE_PRACE": {
        "cpv": "45000000-7",
        "popis": "Stavebne prace maleho rozsahu",
        "kluc": {
            3: [
                "stavebne prace", "stavebne upravy", "rekonstrukcia",
                "zhotovenie stavby", "realizacia stavby", "vystavba",
                "pristavba", "nadstavba", "zateplenie", "obnova budovy",
                "rekonstrukcia strechy", "vymena strechy", "sanacia",
                "buracie prace", "asfaltovanie", "rekonstrukcia chodnika",
                "oprava miestnej komunikacie", "vystavba kanalizacie",
                "revitalizacia", "stavebne prace na objekte",
            ],
            2: [
                "zmluva o dielo", "stavebny dozor", "fasada", "vymena okien",
                "elektroinstalacia", "vykurovanie", "vodovod", "kanalizacia",
                "chodnik", "miestna komunikacia", "telocvicna", "detske ihrisko",
                "verejne osvetlenie", "most", "parkovisko", "kotolna",
                "vzduchotechnika", "podlaha", "omietky",
            ],
            1: ["oprava", "modernizacia", "udrzba budovy", "stavebny material"],
            -5: [
                "najomna zmluva", "zmluva o najme", "poistna zmluva",
                "licencna zmluva", "o poskytnuti dotacie", "pracovna zmluva",
                "mandatna zmluva", "zmluva o uvere", "darovacia zmluva",
                "kolektivna zmluva", "zmluva o spolupraci pri vyskume",
                "dohoda o vykonani prace",
            ],
        },
    },
    "UPRATOVANIE_UDRZBA": {
        "cpv": "90900000-6",
        "popis": "Upratovacie a udrziavacie sluzby",
        "kluc": {
            3: [
                "upratovacie sluzby", "upratovanie", "cistiace sluzby",
                "komplexne upratovanie", "dezinfekcia", "deratizacia",
                "dezinsekcia", "zimna udrzba", "udrzba zelene",
                "kosenie travnatych", "kosenie travy", "upratovacie prace",
            ],
            2: [
                "cistenie", "umyvanie okien", "sanitarne sluzby",
                "starostlivost o zelen", "udrzba arealu", "udrzba priestorov",
                "odpratavanie snehu", "zametanie", "hygienicky servis",
            ],
            1: ["udrzba", "hygienicke potreby", "cistiace prostriedky"],
            -5: [
                "najomna zmluva", "poistna zmluva", "pracovna zmluva",
                "o poskytnuti dotacie", "cistiaren odpadovych vod",
                "licencna zmluva", "dohoda o vykonani prace",
            ],
        },
    },
}
