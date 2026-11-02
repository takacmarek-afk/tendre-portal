"""Jednorazove spatne zaradenie zmluv do sektora ODPAD (2. 11. 2026).

PRECO DVE FAZY
--------------
Tabulka `contracts` obsahuje LEN zmluvy, ktore pri stahovani padli do niektoreho
sektora. Zmluva "vyvoz komunalneho odpadu" sa pred zavedenim sektora ODPAD
nezaradila nikam, takze v databaze vobec NIE JE. Preto:

  Faza A (rychla, minuty): prejde zmluvy, ktore v DB uz su (v inom sektore),
          a tie, ktore klasifikator teraz zaradi do ODPAD, presunie.
          Typicky "upratovanie a vyvoz odpadu" zaradene do UPRATOVANIE.

  Faza B (pomala, hodiny): znova prejde CRZ od zadaneho datumu (datahub
          Slovensko.Digital) a ulozi LEN zmluvy, ktore teraz patria do ODPAD.
          Pokracuje od vlastneho checkpointu `checkpoint_odpad`, takze sa da
          spustat opakovane, kym nevypise "HOTOVO". Hlavny checkpoint pipeline
          sa NEMENI.

Po skonceni treba prepocitat odvodene tabulky (opportunities):
    python main.py --iba-prepocet
(setup_pilot.sh to urobi sam.)

Spustenie (premenne SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY):
    python reprocess_odpad.py                     # na sucho: len vypise, co by sa zmenilo
    python reprocess_odpad.py --zapis             # faza A + B, zapisuje
    python reprocess_odpad.py --zapis --len-a     # len faza A
    python reprocess_odpad.py --zapis --len-b --od 2024-01-01 --budget 60

Nic sa nemaze. Faza A meni len stlpec `sector` (a class_score), faza B robi
upsert podla id (idempotentne).
"""
import argparse
import logging
import sys

import crz
import store
from classify import klasifikuj

SEKTOR = "ODPAD"
META_CHECKPOINT = "checkpoint_odpad"
META_HOTOVO = "reprocess_odpad_hotovy"
# Dotacie sa neprekvalifikuju: zmluva o dotacii na zberny dvor je dotacia,
# nie zakazka na vyvoz odpadu (signal pre dotacie ide cez subsidies).
NEPRESUVAT_Z = {"DOTACIE_NFP", SEKTOR}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("reprocess_odpad")


def kandidati_fazy_a(riadky):
    """riadky: dicty s id, sector, subject, subject_description.
    Vrati {id: (stary_sektor, skore)} pre zmluvy, ktore teraz patria do ODPAD."""
    zmeny = {}
    for r in riadky:
        if r.get("sector") in NEPRESUVAT_Z:
            continue
        novy, skore = klasifikuj(r.get("subject"), r.get("subject_description"))
        if novy == SEKTOR:
            zmeny[r["id"]] = (r.get("sector"), skore)
    return zmeny


def _nacitaj_vsetky(sb, davka=1000):
    """Strankovane citanie contracts (len stlpce potrebne na klasifikaciu)."""
    od = 0
    while True:
        res = (sb.table("contracts")
               .select("id, sector, subject, subject_description")
               .order("id").range(od, od + davka - 1).execute())
        riadky = res.data or []
        yield from riadky
        if len(riadky) < davka:
            return
        od += davka


def faza_a(sb, zapis: bool) -> int:
    log.info("Faza A: prekvalifikovanie zmluv, ktore uz su v databaze")
    riadky = list(_nacitaj_vsetky(sb))
    zmeny = kandidati_fazy_a(riadky)
    podla = {}
    for _, (stary, _) in zmeny.items():
        podla[stary] = podla.get(stary, 0) + 1
    log.info("  prejdenych %s, do ODPAD patri %s (z: %s)", len(riadky), len(zmeny),
             ", ".join(f"{k} {v}" for k, v in sorted(podla.items(), key=lambda x: -x[1])) or "-")
    for i, (stary, skore) in list(zmeny.items())[:10]:
        r = next(x for x in riadky if x["id"] == i)
        log.info("    ukazka %s [%s -> ODPAD, skore %s]: %s", i, stary, skore, (r.get("subject") or "")[:90])
    if zapis and zmeny:
        n = store.zapis_sektory(sb, {i: SEKTOR for i in zmeny})
        log.info("  zapisane: %s", n)
    return len(zmeny)


def faza_b(sb, zapis: bool, od: str, budget_min: int) -> bool:
    """Vrati True, ak sa prechod CRZ dokoncil."""
    since = store.get_meta(sb, META_CHECKPOINT, None) or f"{od}T00:00:00Z"
    log.info("Faza B: prechod CRZ od %s (rozpocet %s min)%s", since, budget_min, "" if zapis else " NA SUCHO")
    stav = {"najdene": 0, "buffer": [], "cp": since}

    def flush():
        if zapis and stav["buffer"]:
            store.upsert_contracts(sb, stav["buffer"])
        stav["buffer"] = []
        if zapis:
            store.set_meta(sb, META_CHECKPOINT, stav["cp"])

    def on_batch(riadky, checkpoint):
        # crz.sync posiela uz zaradene riadky (sektor podla aktualneho config.py)
        odpad = [r for r in riadky if r.get("sector") == SEKTOR]
        stav["najdene"] += len(odpad)
        stav["buffer"].extend(odpad)
        stav["cp"] = checkpoint
        if len(stav["buffer"]) >= 200:
            flush()

    fetched, kept, checkpoint, hotovo = crz.sync(since, on_batch, budget_min * 60)
    stav["cp"] = checkpoint
    flush()
    if zapis:
        store.set_meta(sb, META_HOTOVO, "1" if hotovo else "0")
    log.info("  stiahnutych %s, zaradenych %s, z toho ODPAD %s, checkpoint %s, %s",
             fetched, kept, stav["najdene"], checkpoint, "HOTOVO" if hotovo else "POKRACUJE (spustite znova)")
    if not zapis:
        log.info("  na sucho sa checkpoint neuklada; dalsi beh zacne znova od %s", since)
    return hotovo


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--zapis", action="store_true", help="Zapisat do databazy (inak na sucho).")
    ap.add_argument("--len-a", action="store_true", help="Len faza A (zmluvy v DB).")
    ap.add_argument("--len-b", action="store_true", help="Len faza B (prechod CRZ).")
    ap.add_argument("--od", default="2023-01-01", help="Od kedy prejst CRZ vo faze B (prvy beh).")
    ap.add_argument("--budget", type=int, default=45, help="Casovy rozpocet fazy B v minutach.")
    a = ap.parse_args()

    sb = store.klient()
    hotovo = True
    if not a.len_b:
        faza_a(sb, a.zapis)
    if not a.len_a:
        hotovo = faza_b(sb, a.zapis, a.od, a.budget)
    if a.zapis:
        log.info("Dalej: python main.py --iba-prepocet (prepocet prilezitosti)")
    # navratovy kod 3 = treba spustit znova (pre setup_pilot.sh)
    return 0 if hotovo else 3


if __name__ == "__main__":
    sys.exit(main())
