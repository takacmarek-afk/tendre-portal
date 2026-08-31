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

    stav = {"ulozene": 0}

    def on_batch(riadky, checkpoint):
        if riadky:
            stav["ulozene"] += store.upsert_contracts(sb, riadky)
        store.set_meta(sb, "checkpoint", checkpoint)

    fetched, kept, checkpoint, hotovo = crz.sync(since, on_batch, budget * 60)
    store.set_meta(sb, "checkpoint", checkpoint)
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
