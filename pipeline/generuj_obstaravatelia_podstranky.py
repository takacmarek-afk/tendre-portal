"""Verejne SEO stranky obstaravatelov: /obstaravatelia/, /obstaravatelia/<kraj>/, /obstaravatelia/<kraj>/<nazov>-<ico>.

20. 11. 2026, oba portaly (ceska obdoba: hledam-zakazky.cz /zadavatele/). Pre kazdy
urad, obec, mesto a kraj spoji zmluvy z CRZ, ktore skoncia do 12 mesiacov, a
pripravovane obstaravania z eurofondov (ITMS). Verejne len pocty, objemy a najviac
3 ukazky; DODAVATEL sa nezapisuje (rovnaka hranica ako /konciace-zmluvy). Stranka
vznikne len pri obstaravatelovi s dostatkom obsahu (tenke stranky Google nechce).

Data: RPC seo_obstaravatelia() (supabase/107), len service_role.
Spusta .github/workflows/obstaravatelia-podstranky.yml (pondelok).
"""
import logging
import os
import re
import shutil
import unicodedata
from collections import defaultdict
from datetime import date

from generuj_obce_podstranky import VSETKY_KRAJE, LOKAL_KRAJA, _slug, _suma, _cislo, _tvar, _e, _datum
from generuj_zmluvy_podstranky import HLAVICKA as _HL, PATICKA

log = logging.getLogger("generuj_obstaravatelia_podstranky")

KOREN = os.path.join(os.path.dirname(__file__), "..", "public")
VYSTUP_DIR = os.path.join(KOREN, "obstaravatelia")
SITEMAP_CESTA = os.path.join(KOREN, "sitemap-obstaravatelia.xml")
ROBOTS_CESTA = os.path.join(KOREN, "robots.txt")
BAZA = "https://predtendrom.sk"
MIN_POLOZIEK = 3

HLAVICKA = (_HL.replace("https://predtendrom.sk/konciace-zmluvy/{cesta}", "https://predtendrom.sk/{cesta}")
               .replace("../../config.js", "/config.js"))


def slug(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return t[:50].rstrip("-") or "obstaravatel"


def ma_stranku(o: dict) -> bool:
    return (o.get("kraj") in VSETKY_KRAJE and bool((o.get("nazov") or "").strip())
            and int(o.get("konci12") or 0) + int(o.get("eurofondy_pocet") or 0) >= MIN_POLOZIEK)


def cesta(o: dict) -> str:
    return f"obstaravatelia/{_slug(o['kraj'])}/{slug(o['nazov'])}-{o['ico']}"


def mesiac(m) -> str:
    try:
        r, mm = str(m).split("-")
        return f"{int(mm)}/{r}"
    except ValueError:
        return ""


def _karty(polozky):
    return "\n".join(f"""      <div class="rounded-lg border border-line bg-white p-4">
        <div class="text-[14px] font-medium">{_e(a)}</div>
        <div class="mt-1 text-[13px] text-slate2">{_e(b)}</div>
      </div>""" for a, b in polozky)


def stranka(o: dict, dnes: str) -> str:
    n, kraj = o["nazov"].strip(), o["kraj"]
    lokal = LOKAL_KRAJA.get(kraj, "")
    k12, ep = int(o.get("konci12") or 0), int(o.get("eurofondy_pocet") or 0)
    casti = []
    if k12:
        casti.append(f"{_cislo(k12)} {_tvar(k12, 'zmluva', 'zmluvy', 'zmlúv')} z CRZ skončí do 12 mesiacov"
                     + (f" ({_suma(o.get('objem12'))})" if o.get("objem12") else ""))
    if ep:
        casti.append(f"{_cislo(ep)} {_tvar(ep, 'pripravované obstarávanie', 'pripravované obstarávania', 'pripravovaných obstarávaní')}"
                     f" z eurofondov" + (f" ({_suma(o.get('eurofondy_objem'))})" if o.get("eurofondy_objem") else ""))
    telo = [f"""
<section class="max-w-[900px] mx-auto px-5 pt-10 pb-8">
  <p class="inline-block text-[12px] font-semibold text-accent bg-accent/10 rounded-full px-3 py-1">Obstarávateľ · {_e(kraj)}</p>
  <h1 class="mt-5 text-[28px] sm:text-[34px] font-bold leading-tight tracking-tight">{_e(n)}: končiace zmluvy a pripravované obstarávania</h1>
  <p class="mt-1 text-[13px] text-slate2 font-mono">IČO {_e(o['ico'])}</p>
  <p class="mt-4 text-[16px] leading-relaxed text-slate2 max-w-[640px]">{_e('; '.join(casti))}. Keď zmluva skončí, úrad musí službu nakúpiť znova. Kto to vie skôr, pripraví si ponuku v pokoji.</p>
  <div class="mt-4 flex flex-col sm:flex-row sm:items-center gap-3">
    <a href="/prihlasenie?utm_source=seo_obstaravatel&utm_medium=organic&utm_campaign=programmatic_seo"
       class="inline-flex justify-center items-center rounded-md bg-accent text-white text-[15px] font-semibold px-5 py-3 hover:bg-accentDark">Sledovať tohto obstarávateľa</a>
    <span class="text-[13px] leading-snug text-slate2">14 dní zadarmo, bez platobnej karty.</span>
  </div>"""]
    if o.get("ukazky"):
        telo.append('  <h2 class="mt-10 text-[18px] font-semibold">Najväčšie zmluvy, ktoré skončia do roka</h2>\n  <div class="mt-4 grid gap-3">')
        telo.append(_karty([(u.get("predmet") or "Predmet neuvedený",
                             f"zmluva končí v {mesiac(u.get('mesiac'))} · {_suma(u.get('cena'))}") for u in o["ukazky"]]))
        telo.append("  </div>")
        zvysok = k12 - len(o["ukazky"])
        if zvysok > 0:
            telo.append(f'  <p class="mt-3 text-[14px] text-slate2">+ {_cislo(zvysok)} {_tvar(zvysok, "ďalšia zmluva", "ďalšie zmluvy", "ďalších zmlúv")} v aplikácii, aj s tým, kto ich dnes plní.</p>')
    if o.get("eurofondy"):
        telo.append('  <h2 class="mt-10 text-[18px] font-semibold">Pripravované obstarávania z eurofondov</h2>\n  <div class="mt-4 grid gap-3">')
        telo.append(_karty([(u.get("nazov") or "", f"predpokladaná hodnota {_suma(u.get('hodnota'))}") for u in o["eurofondy"]]))
        telo.append("  </div>")
    telo.append(f"""  <p class="mt-8 text-[14px]"><a class="text-accent hover:underline" href="/obstaravatel?ico={_e(o['ico'])}">Podrobný profil obstarávateľa</a>
  · <a class="text-accent hover:underline" href="/obstaravatelia/{_slug(kraj)}/">Ďalší obstarávatelia v {_e(lokal)} kraji</a></p>
  <p class="mt-6 text-[12px] text-slate2 leading-relaxed">Zdroje: Centrálny register zmlúv a ITMS21+ (pripravované verejné obstarávania), stav {dnes}.
  Koniec zmluvy je podľa CRZ; pripravované obstarávanie ešte nie je vyhlásená súťaž.</p>
</section>
""")
    titul = f"{n}: končiace zmluvy a obstarávania | PredTendrom.sk"
    popis = f"{n} ({kraj}): {'; '.join(casti)}."
    return (HLAVICKA.format(titul=_e(titul), popis=_e(popis), cesta=cesta(o), robots="index,follow")
            + "\n".join(telo) + PATICKA.format(aktualizovane=dnes))


def stranka_kraja(kraj: str, oo: list, dnes: str) -> str:
    oo = sorted(oo, key=lambda o: (-(int(o.get("konci12") or 0) + int(o.get("eurofondy_pocet") or 0)), o["nazov"]))
    li = "\n".join(f"""    <a href="/{cesta(o)}" class="flex justify-between gap-4 rounded-lg border border-line bg-white px-4 py-3 hover:border-accent">
      <span class="text-[14px] font-medium">{_e(o['nazov'].strip())}</span>
      <span class="text-[12px] text-slate2 whitespace-nowrap">{_cislo(o.get('konci12') or 0)} zmlúv · {_cislo(o.get('eurofondy_pocet') or 0)} z eurofondov</span>
    </a>""" for o in oo)
    lokal = LOKAL_KRAJA.get(kraj, "")
    telo = f"""
<section class="max-w-[900px] mx-auto px-5 pt-10 pb-8">
  <p class="inline-block text-[12px] font-semibold text-accent bg-accent/10 rounded-full px-3 py-1">Obstarávatelia · {_e(kraj)}</p>
  <h1 class="mt-5 text-[28px] sm:text-[34px] font-bold leading-tight tracking-tight">Úrady, obce a mestá v {_e(lokal)} kraji: končiace zmluvy a obstarávania</h1>
  <p class="mt-4 text-[16px] text-slate2">{_cislo(len(oo))} obstarávateľov s končiacimi zmluvami alebo pripravovanými obstarávaniami z eurofondov.</p>
  <div class="mt-6 grid gap-2">
{li}
  </div>
  <p class="mt-6 text-[14px]"><a class="text-accent hover:underline" href="/obstaravatelia/">Všetky kraje</a> · <a class="text-accent hover:underline" href="/obstaravatel">Nájsť obstarávateľa podľa IČO</a></p>
</section>
"""
    return (HLAVICKA.format(titul=_e(f"Obstarávatelia v {lokal} kraji: končiace zmluvy | PredTendrom.sk"),
                            popis=_e(f"{len(oo)} úradov, obcí a miest v {lokal} kraji: končiace zmluvy z CRZ a pripravované obstarávania z eurofondov."),
                            cesta=f"obstaravatelia/{_slug(kraj)}/", robots="index,follow")
            + telo + PATICKA.format(aktualizovane=dnes))


def stranka_hub(po_kraji: dict, dnes: str) -> str:
    li = "\n".join(f"""    <a href="/obstaravatelia/{_slug(k)}/" class="flex justify-between rounded-lg border border-line bg-white px-4 py-3 hover:border-accent">
      <span class="text-[14px] font-medium">{_e(k)}</span><span class="text-[13px] text-slate2">{_cislo(len(po_kraji[k]))}</span>
    </a>""" for k in VSETKY_KRAJE if k in po_kraji)
    spolu = sum(len(v) for v in po_kraji.values())
    telo = f"""
<section class="max-w-[900px] mx-auto px-5 pt-10 pb-8">
  <h1 class="text-[28px] sm:text-[34px] font-bold leading-tight tracking-tight">Čo chystajú úrady, obce a kraje</h1>
  <p class="mt-4 text-[16px] text-slate2">{_cislo(spolu)} obstarávateľov s končiacimi zmluvami alebo pripravovanými obstarávaniami z eurofondov. Vyberte kraj, alebo <a class="text-accent hover:underline" href="/obstaravatel">nájdite obstarávateľa podľa IČO</a>.</p>
  <div class="mt-6 grid gap-2">
{li}
  </div>
</section>
"""
    return (HLAVICKA.format(titul="Obstarávatelia podľa kraja: končiace zmluvy a obstarávania | PredTendrom.sk",
                            popis=_e(f"{spolu} úradov, obcí a krajov: končiace zmluvy z CRZ a pripravované obstarávania z eurofondov."),
                            cesta="obstaravatelia/", robots="index,follow")
            + telo + PATICKA.format(aktualizovane=dnes))


def vygeneruj(radky, vystup_dir=VYSTUP_DIR, sitemap=SITEMAP_CESTA, robots=ROBOTS_CESTA, dnes=None):
    dnes = dnes or _datum(date.today().isoformat())
    oo = [o for o in radky if ma_stranku(o)]
    if os.path.isdir(vystup_dir):
        shutil.rmtree(vystup_dir)
    os.makedirs(vystup_dir)
    po_kraji, urls, psane = defaultdict(list), ["/obstaravatelia/"], []
    for o in oo:
        po_kraji[o["kraj"]].append(o)
        c = cesta(o)
        p = os.path.join(vystup_dir, _slug(o["kraj"]), c.rsplit("/", 1)[1] + ".html")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(stranka(o, dnes))
        psane.append(p)
        urls.append("/" + c)
    for k, lst in po_kraji.items():
        with open(os.path.join(vystup_dir, _slug(k), "index.html"), "w", encoding="utf-8") as f:
            f.write(stranka_kraja(k, lst, dnes))
        urls.append(f"/obstaravatelia/{_slug(k)}/")
    with open(os.path.join(vystup_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(stranka_hub(po_kraji, dnes))
    with open(sitemap, "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                + "\n".join(f"  <url><loc>{BAZA}{u}</loc></url>" for u in sorted(urls)) + "\n</urlset>\n")
    riadok = f"Sitemap: {BAZA}/sitemap-obstaravatelia.xml"
    obsah = open(robots, encoding="utf-8").read() if os.path.exists(robots) else ""
    if riadok not in obsah:
        with open(robots, "a", encoding="utf-8") as f:
            f.write(("" if obsah.endswith("\n") or not obsah else "\n") + riadok + "\n")
    return psane


def hlavne():
    import store
    from strankuj import vsetky
    sb = store.klient()
    radky = vsetky(lambda od, do: sb.rpc("seo_obstaravatelia", {}).order("ico").range(od, do).execute())
    n = vygeneruj(radky)
    log.info("Obstaravatelia: %d stranok z %d obstaravatelov", len(n), len(radky))
    if len(n) < 100:
        log.warning("Podozrivo malo stranok obstaravatelov: %d", len(n))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s")
    hlavne()
