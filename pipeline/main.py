"""Pipeline: CRZ -> klasifikacia -> Supabase -> prepocet prilezitosti.

Spusta sa z GitHub Actions kazdy pracovny den.
Prvy beh potrebuje prepinac --bootstrap, ktory ma dlhsi casovy rozpocet.
"""
import sys
import logging
import argparse

import crz
import score
import store
from config import (
    BOOTSTRAP_SINCE, TIME_BUDGET_MIN, DNI_MIN, DNI_MAX, SEKTORY,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)-8s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("main")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bootstrap", action="store_true",
                    help="Prvotne naplnenie: dlhsi casovy rozpocet.")
    ap.add_argument("--budget", type=int, default=None)
    args = ap.parse_args()

    sb = store.klient()

    # ── 1. SYNC ────────────────────────────────────────────────────────────
    since = store.get_meta(sb, "checkpoint", BOOTSTRAP_SINCE)
    budget = args.budget or (300 if args.bootstrap else TIME_BUDGET_MIN)
    log.info("Sync od %s (rozpocet %s min)", since, budget)

    # Zapisujeme davkovo, nie po kazdej stranke.
    # Kazdy zapis do Supabase je HTTP volanie a trva takmer dve sekundy —
    # pri 100 zaznamoch na stranku by nas rezia stala viac casu nez samotne
    # stahovanie. Zbierame do vyrovnavacej pamate a posielame po 500.
    #
    # Poradie je dolezite: najprv zapiseme zaznamy, az potom checkpoint.
    # Keby to beh nestihol medzitym, zopakuje par stranok — a to nevadi,
    # zapis je idempotentny. Opacne poradie by dieru v datach spravilo.
    stav = {"ulozene": 0, "stran": 0, "buffer": [], "cp": since}
    FLUSH_ZAZNAMOV = 500
    FLUSH_STRAN = 100

    def zapis(sb_):
        if stav["buffer"]:
            stav["ulozene"] += store.upsert_contracts(sb_, stav["buffer"])
            stav["buffer"] = []
        store.set_meta(sb_, "checkpoint", stav["cp"])

    def on_batch(riadky, checkpoint):
        stav["buffer"].extend(riadky)
        stav["cp"] = checkpoint
        stav["stran"] += 1
        if len(stav["buffer"]) >= FLUSH_ZAZNAMOV or stav["stran"] % FLUSH_STRAN == 0:
            zapis(sb)

    fetched, kept, checkpoint, hotovo = crz.sync(since, on_batch, budget * 60)
    stav["cp"] = checkpoint
    zapis(sb)   # doposli, co zostalo vo vyrovnavacej pamati
    store.set_meta(sb, "bootstrap_hotovy", "1" if hotovo else "0")

    log.info("Stiahnute %s | zaradene %s | ulozene %s | dokoncene: %s",
             fetched, kept, stav["ulozene"], hotovo)

    if not hotovo:
        log.warning("Beh sa nedokoncil v rozpocte. Spusti bootstrap znova, "
                    "nadviaze na checkpointe.")

    # ── 2. PREPOCET PRILEZITOSTI ───────────────────────────────────────────
    vsetky = store.nacitaj_contracts(sb)
    tabulka = score.prilezitosti(vsetky)
    vlozene = store.nahrad_opportunities(sb, tabulka)

    celkom = store.pocet_contracts(sb)
    log.info("Zmluv v databaze: %s | prilezitosti v okne %s-%s dni: %s",
             celkom, DNI_MIN, DNI_MAX, vlozene)

    # ── 3. SAMOKONTROLA KALIBRACIE ─────────────────────────────────────────
    if not tabulka.empty:
        podiel_vysoke = (tabulka["riziko"] == "VYSOKE").mean()
        if podiel_vysoke > 0.6:
            log.warning("KALIBRACIA: %.0f %% zaznamov ma VYSOKE riziko. To je "
                        "prilis vela — prahy v score._riziko su volne.",
                        podiel_vysoke * 100)
        log.info("Rozlozenie rizika: %s", tabulka["riziko"].value_counts().to_dict())
        log.info("Skore: min %s, median %s, max %s",
                 int(tabulka["skore"].min()),
                 int(tabulka["skore"].median()),
                 int(tabulka["skore"].max()))
        for k in SEKTORY:
            log.info("  %s: %s prilezitosti", k, int((tabulka["sector"] == k).sum()))
    else:
        log.warning("Ziadne prilezitosti. Ak je databaza prazdna, spusti --bootstrap.")

    print(f"::notice::stiahnute={fetched} zaradene={kept} zmluv_v_db={celkom} "
          f"prilezitosti={vlozene} dokoncene={hotovo}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
