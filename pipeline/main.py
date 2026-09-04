"""Pipeline: CRZ -> klasifikacia -> Supabase -> prepocet prilezitosti.

Spusta sa z GitHub Actions kazdy pracovny den.
Prvy beh potrebuje prepinac --bootstrap; ked sa nestihne, workflow si
zavola pokracovanie sam, kym nedobehne.
"""
import os
import sys
import logging
import argparse

import crz
import score
import store
import subsidies
from config import (
    BOOTSTRAP_SINCE, TIME_BUDGET_MIN, DNI_MIN, DNI_MAX, SEKTORY,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)-8s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("main")


def zapis_vystup(**hodnoty):
    """Odovzda hodnoty workflowu cez GITHUB_OUTPUT. Mimo Actions nerobi nic."""
    cesta = os.environ.get("GITHUB_OUTPUT")
    if not cesta:
        return
    with open(cesta, "a", encoding="utf-8") as f:
        for k, v in hodnoty.items():
            if isinstance(v, bool):
                v = "true" if v else "false"
            f.write(f"{k}={v}\n")


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

    # Zapisujeme davkovo, nie po kazdej stranke. Kazdy zapis do Supabase je
    # HTTP volanie a trva takmer dve sekundy — pri 100 zaznamoch na stranku
    # by nas rezia stala viac casu nez samotne stahovanie.
    #
    # Poradie je dolezite: najprv zaznamy, az potom checkpoint. Keby to beh
    # nestihol, zopakuje par stranok, co nevadi (zapis je idempotentny).
    # Opacne poradie by spravilo dieru v datach.
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
    zapis(sb)   # doposli zvysok vyrovnavacej pamate

    store.set_meta(sb, "bootstrap_hotovy", "1" if hotovo else "0")

    log.info("Stiahnute %s | zaradene %s | ulozene %s | dokoncene: %s",
             fetched, kept, stav["ulozene"], hotovo)

    # Signal pre workflow zapisujeme HNED, kym vieme, ako sync dopadol.
    # Keby spadol prepocet nizsie, retazenie bootstrapu by sa inak preruslo —
    # a to je horsie nez chybajuca tabulka prilezitosti, ktora sa aj tak
    # prepocitava pri kazdom behu odznova.
    zapis_vystup(hotovo=hotovo)

    if not hotovo:
        log.warning("Beh sa nedokoncil v rozpocte, pokracovanie sa spusti samo.")

    # ── 2. PREPOCET PRILEZITOSTI ───────────────────────────────────────────
    # Cely blok je poisteny. Stahovanie je drahe (hodiny), prepocet lacny
    # (sekundy). Nema zmysel zahodit odrobenu pracu preto, ze zlyhal krok,
    # ktory sa o hodinu zopakuje.
    tabulka, vlozene, dotacii = None, 0, 0
    try:
        vsetky = store.nacitaj_contracts(sb)
        tabulka = score.prilezitosti(vsetky)
        vlozene = store.nahrad_opportunities(sb, tabulka)

        # Dotacie su samostatna vrstva: nie zakazka, ale predzvest tendra.
        dot = subsidies.z_contracts(vsetky)
        dotacii = store.nahrad_subsidies(sb, dot)
        if dotacii:
            log.info("Dotacie s ocakavanym tendrom: %s", dotacii)
    except Exception as e:
        log.exception("Prepocet zlyhal")
        print(f"::error::Prepocet zlyhal: {type(e).__name__}: {e}")

    try:
        celkom = store.pocet_contracts(sb)
    except Exception:
        celkom = 0

    log.info("Zmluv v databaze: %s | prilezitosti v okne %s-%s dni: %s",
             celkom, DNI_MIN, DNI_MAX, vlozene)

    # ── 3. SAMOKONTROLA KALIBRACIE ─────────────────────────────────────────
    if tabulka is not None and not tabulka.empty:
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
        log.info("Prilezitosti podla sektora:")
        for k, v in tabulka["sector"].value_counts().items():
            log.info("   %-22s %s", k, v)
    elif hotovo:
        log.warning("Ziadne prilezitosti v okne. Skus rozsirit DNI_MIN/DNI_MAX "
                    "alebo znizit MIN_HODNOTA_EUR v config.py.")

    zapis_vystup(zmluv=celkom, prilezitosti=vlozene, dotacie=dotacii)
    print(f"::notice::stiahnute={fetched} zaradene={kept} zmluv_v_db={celkom} "
          f"prilezitosti={vlozene} dotacie={dotacii} dokoncene={hotovo}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
