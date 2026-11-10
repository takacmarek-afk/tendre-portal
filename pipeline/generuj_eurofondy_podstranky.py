"""Staticke SEO podstranky /eurofondy/<odbor>/<kraj> (10. 11. 2026).

Pripravovane obstaravania z eurofondovych projektov (ITMS21+, tabulka itms_vo,
migracia 97): urad uz obstaravanie zapisal do projektu, sutaz este nevyhlasil.
Na Slovensku to verejne po odboroch a krajoch nikto neukazuje, preto su to
stranky s vlastnym obsahom (nie kopia Vestnika).

HRANICA ZADARMO / PLATENE: verejne je pocet, objem, pocet uradov a najviac
5 prikladov (urad, nazov, predpokladana hodnota). Cely zoznam s terminmi
a upozornenim pri vyhlaseni je v appke (itms_pripravovane, Growth+).
Riadky nad 5 sa do HTML nezapisuju vobec.

Spusta sa v .github/workflows/itms.yml po klasifikacii.
"""
import logging
import os
from collections import defaultdict
from datetime import date, timedelta
from urllib.parse import urlencode

from generuj_obce_podstranky import _slug, _suma, _cislo, _datum, _tvar, _e, VSETKY_KRAJE, LOKAL_KRAJA
from generuj_zmluvy_podstranky import HLAVICKA as _HLAVICKA_ZMLUVY, SEKTORY_SEO, _velke_prve
from strankuj import vsetky

log = logging.getLogger("generuj_eurofondy_podstranky")

KOREN = os.path.join(os.path.dirname(__file__), "..", "public")
VYSTUP_DIR = os.path.join(KOREN, "eurofondy")
SITEMAP_CESTA = os.path.join(KOREN, "sitemap-eurofondy.xml")
ROBOTS_CESTA = os.path.join(KOREN, "robots.txt")
PRIKLADOV = 5
MIN_INDEX = 3          # menej obstaravani = tenky obsah -> noindex, nie v sitemap
DNI_CERSTVOST = 730    # ITMS ma aj stare "Pripravované", ktore uz nikto neaktualizuje

HLAVICKA = _HLAVICKA_ZMLUVY.replace("/konciace-zmluvy/{cesta}", "/eurofondy/{cesta}")

PATICKA = """
<section class="max-w-[900px] mx-auto px-5 mt-12">
  <div class="rounded-lg border border-line bg-white p-5">
    <div class="text-[16px] font-semibold">Čo znamená „pripravované“?</div>
    <p class="mt-1 text-[14px] leading-relaxed text-slate2">Úrad alebo obec má obstarávanie zapísané v projekte
    financovanom z eurofondov (systém ITMS21+), ale súťaž ešte nevyhlásil. Termín vyhlásenia určuje úrad
    a niektoré obstarávania sa môžu zmeniť alebo zrušiť. Kto o nich vie vopred, má čas na prípravu ponuky.</p>
    <p class="mt-3 text-[14px]">
      <a href="/eurofondy/" class="text-accent font-semibold hover:underline">Všetky odbory a kraje →</a>
      · <a href="/konciace-zmluvy/" class="text-accent hover:underline">Končiace zmluvy úradov</a>
      · <a href="/kontrola" class="text-accent hover:underline">Kontrola podľa IČO</a>
    </p>
  </div>
</section>

<footer class="border-t border-line mt-12">
  <div class="max-w-[900px] mx-auto px-5 py-8 text-[12px] text-slate2">
    Údaje z otvorených dát ITMS21+ (projekty z eurofondov). Aktualizované pravidelne, naposledy {aktualizovane}.
    <a href="/zdroje" class="text-accent hover:underline">Ako to počítame</a>
    · <a href="mailto:info@predtendrom.sk" class="text-accent hover:underline">info@predtendrom.sk</a>
  </div>
  <p class="pt-pravne text-[12px] text-slate2 text-center py-4 border-t border-line"><a href="/obchodne-podmienky" class="underline hover:text-ink">Obchodné podmienky</a> &middot; <a href="/ochrana-osobnych-udajov" class="underline hover:text-ink">Ochrana osobných údajov</a> &middot; <a href="#" onclick="window.ptCookieNastavenia&amp;&amp;window.ptCookieNastavenia();return false;" class="underline hover:text-ink">Nastavenia cookies</a></p>
</footer>
<script>
// Kto prisiel zo studeneho e-mailu (utm_source=email), nesie si zdroj aj do registracie.
(function () {{
  var q = new URLSearchParams(location.search);
  if (q.get('utm_source') !== 'email') return;
  document.querySelectorAll('a[href^="/prihlasenie"]').forEach(function (a) {{
    var u = new URL(a.getAttribute('href'), location.origin);
    u.searchParams.set('utm_source', 'email');
    u.searchParams.set('utm_medium', q.get('utm_medium') || 'oslovenie');
    u.searchParams.set('utm_campaign', (q.get('utm_campaign') || 'firmy') + '-seo');
    a.setAttribute('href', u.pathname + u.search);
  }});
}})();
</script>
</body>
</html>
"""


def _kratko(t, n=140):
    t = " ".join(str(t or "").split())
    return t if len(t) <= n else t[: n - 1].rstrip() + "…"


def agreguj(riadky):
    """riadky itms_vo -> {(sektor, kraj): {pocet, objem, uradov, priklady}}. Cista funkcia."""
    skup = defaultdict(list)
    for r in riadky:
        if r.get("sektor") in SEKTORY_SEO and r.get("kraj") in LOKAL_KRAJA:
            skup[(r["sektor"], r["kraj"])].append(r)
    out = {}
    for k, rr in skup.items():
        rr.sort(key=lambda r: -float(r.get("predpokladana_hodnota") or 0))
        out[k] = {
            "pocet": len(rr),
            "objem": sum(float(r.get("predpokladana_hodnota") or 0) for r in rr),
            "uradov": len({(r.get("obstaravatel_nazov") or "").strip().lower() for r in rr}),
            "priklady": [{"urad": _kratko(r.get("obstaravatel_nazov"), 90), "nazov": _kratko(r.get("nazov")),
                          "hodnota": float(r["predpokladana_hodnota"]) if r.get("predpokladana_hodnota") else None}
                         for r in rr[:PRIKLADOV]],
        }
    return out


def cesta_stranky(sektor, kraj):
    """Verejna adresa stranky (bez .html) alebo None, ak sa negeneruje."""
    info = SEKTORY_SEO.get(sektor)
    return f"/eurofondy/{info['slug']}/{_slug(kraj)}" if info and kraj in LOKAL_KRAJA else None


def _obstaravani(n):
    return _tvar(n, "pripravované obstarávanie", "pripravované obstarávania", "pripravovaných obstarávaní")


def _stranka(sektor, kraj, a, dostupne):
    info = SEKTORY_SEO[sektor]
    lokal = _velke_prve(LOKAL_KRAJA[kraj])   # "v Košickom kraji"
    slug, kslug = info["slug"], _slug(kraj)
    n = a["pocet"]
    utm = f"utm_source=seo_eurofondy_{slug}_{kslug}&utm_medium=organic&utm_campaign=programmatic_seo"
    priklady = "\n".join(f"""      <div class="rounded-lg border border-line bg-white p-4">
        <div class="text-[14px] font-medium">{_e(p['nazov'])}</div>
        <div class="mt-1 flex items-center justify-between gap-3 text-[13px] text-slate2">
          <span>{_e(p['urad'])}</span><span class="shrink-0 tabular-nums">{_suma(p['hodnota'])}</span>
        </div>
      </div>""" for p in a["priklady"])
    zvysok = n - len(a["priklady"])
    blok_zvysok = f"""
  <div class="mt-3 rounded-lg border border-dashed border-line bg-[#F3F5F7] p-5 text-center">
    <p class="text-[14px] text-slate2">+ {_cislo(zvysok)} {_tvar(zvysok, 'ďalšie obstarávanie', 'ďalšie obstarávania', 'ďalších obstarávaní')} v tomto kraji a odbore.</p>
    <a href="/prihlasenie?{utm}" class="mt-3 inline-block rounded-md bg-accent text-white text-[13px] font-medium px-4 py-2 hover:bg-accentDark">
      Zobraziť všetky a dostať správu pri vyhlásení (14 dní zadarmo)</a>
  </div>""" if zvysok > 0 else ""
    odber_q = urlencode({"sektor": sektor, "kraj": kraj}).replace("&", "&amp;")
    zmluvy = (f' · <a href="/konciace-zmluvy/{slug}/{kslug}" class="text-accent hover:underline">'
              f'Končiace zmluvy na {_e(info["nazov"])} v kraji</a>')
    kraje = " ".join(f'<a href="/eurofondy/{slug}/{_slug(k)}" class="text-accent hover:underline">{_e(k.replace(" kraj", ""))}</a>'
                     for k in VSETKY_KRAJE if k != kraj and (sektor, k) in dostupne)
    odbory = " ".join(f'<a href="/eurofondy/{i["slug"]}/{kslug}" class="text-accent hover:underline">{_e(_velke_prve(i["nazov_nom"]))}</a>'
                      for s, i in SEKTORY_SEO.items() if s != sektor and (s, kraj) in dostupne)
    blok_kraje = (f'  <h2 class="mt-10 text-[16px] font-semibold">{_velke_prve(info["nazov_nom"])} z eurofondov v iných krajoch</h2>\n'
                  f'  <p class="mt-2 text-[14px] leading-loose flex flex-wrap gap-x-4">{kraje}</p>') if kraje else ""
    blok_odbory = ('  <h2 class="mt-6 text-[16px] font-semibold">Iné odbory v kraji</h2>\n'
                   f'  <p class="mt-2 text-[14px] leading-loose flex flex-wrap gap-x-4">{odbory}</p>') if odbory else ""
    titul = f"{_velke_prve(info['nazov_nom'])} z eurofondov v {lokal} kraji: pripravované obstarávania | PredTendrom.sk"
    popis = (f"{_cislo(n)} {_obstaravani(n)} na {info['nazov']} z eurofondov v {lokal} kraji"
             f"{'' if _suma(a['objem']) == '—' else ', spolu ' + _suma(a['objem'])}. Úrady ich pripravujú, súťaž ešte nevyhlásili.")
    telo = f"""
<section class="max-w-[900px] mx-auto px-5 pt-10 pb-8">
  <p class="inline-block text-[12px] font-semibold text-accent bg-accent/10 rounded-full px-3 py-1">{_e(kraj)}, {info['nazov_nom']}, eurofondy</p>
  <h1 class="mt-5 text-[28px] sm:text-[34px] font-bold leading-tight tracking-tight">
    Pripravované obstarávania na {info['nazov_2']} z eurofondov v {lokal} kraji</h1>
  <p class="mt-4 text-[16px] leading-relaxed text-slate2 max-w-[640px]">
    Úrady, obce a školy ich majú zapísané v projektoch z eurofondov, súťaž ešte nevyhlásili.
    Kto o nich vie teraz, má mesiace na prípravu a nečaká na Vestník.</p>
  <div class="mt-8 grid grid-cols-3 gap-3">
    <div class="rounded-lg border border-line bg-white p-4"><div class="text-[22px] font-semibold tabular-nums">{_cislo(n)}</div>
      <div class="text-[12px] text-slate2 mt-1">{_obstaravani(n)}</div></div>
    <div class="rounded-lg border border-line bg-white p-4"><div class="text-[22px] font-semibold tabular-nums">{_suma(a['objem'])}</div>
      <div class="text-[12px] text-slate2 mt-1">predpokladaná hodnota spolu</div></div>
    <div class="rounded-lg border border-line bg-white p-4"><div class="text-[22px] font-semibold tabular-nums">{_cislo(a['uradov'])}</div>
      <div class="text-[12px] text-slate2 mt-1">{_tvar(a['uradov'], 'obstarávateľ', 'obstarávatelia', 'obstarávateľov')}</div></div>
  </div>
  <div class="mt-4 flex flex-col sm:flex-row sm:items-center gap-3">
    <a href="/prihlasenie?{utm}&amp;utm_content=hore" class="inline-flex justify-center items-center rounded-md bg-accent text-white text-[15px] font-semibold px-5 py-3 hover:bg-accentDark">
      Sledovať tieto obstarávania</a>
    <span class="text-[13px] leading-snug text-slate2">14 dní zadarmo, bez platobnej karty.<br class="hidden sm:inline">
      Keď úrad súťaž vyhlási, dáme Vám vedieť.</span>
  </div>
  <p class="mt-3 text-[13px] text-slate2">Bez registrácie:
    <a href="/?{odber_q}#ukazka" class="text-accent font-semibold hover:underline">posielať mi zadarmo každý týždeň nové súťaže a končiace zmluvy</a></p>
  <h2 class="mt-10 text-[18px] font-semibold">Najväčšie pripravované obstarávania</h2>
  <div class="mt-4 grid gap-3">
{priklady}
  </div>
{blok_zvysok}
{blok_kraje}
{blok_odbory}
  <p class="mt-4 text-[14px]"><a href="/eurofondy/" class="text-accent hover:underline">Všetky odbory a kraje</a>{zmluvy}</p>
</section>
"""
    return (HLAVICKA.format(titul=titul, popis=popis, cesta=f"{slug}/{kslug}",
                            robots="index,follow" if n >= MIN_INDEX else "noindex,follow")
            + telo + PATICKA.format(aktualizovane=_datum(date.today().isoformat())))


def _hub(agr):
    spolu_n = sum(a["pocet"] for a in agr.values())
    spolu_obj = sum(a["objem"] for a in agr.values())
    bloky = []
    for s, info in SEKTORY_SEO.items():
        kraje = sorted(((k, a) for (ss, k), a in agr.items() if ss == s), key=lambda x: -x[1]["pocet"])
        if not kraje:
            continue
        n = sum(a["pocet"] for _, a in kraje)
        odkazy = " ".join(f'<a href="/eurofondy/{info["slug"]}/{_slug(k)}" class="text-accent hover:underline">'
                          f'{_e(k.replace(" kraj", ""))} ({_cislo(a["pocet"])})</a>' for k, a in kraje)
        bloky.append((n, f"""    <div class="rounded-lg border border-line bg-white p-4">
      <div class="text-[15px] font-semibold">{_e(_velke_prve(info['nazov_nom']))}</div>
      <div class="text-[13px] text-slate2 mt-1">{_cislo(n)} {_obstaravani(n)}</div>
      <p class="mt-2 text-[13px] leading-loose flex flex-wrap gap-x-3">{odkazy}</p>
    </div>"""))
    polozky = "\n".join(t for _, t in sorted(bloky, key=lambda x: -x[0]))
    telo = f"""
<section class="max-w-[900px] mx-auto px-5 pt-10 pb-16">
  <h1 class="text-[28px] sm:text-[34px] font-bold leading-tight tracking-tight">Pripravované obstarávania z eurofondov</h1>
  <p class="mt-4 text-[16px] leading-relaxed text-slate2 max-w-[640px]">
    {_cislo(spolu_n)} obstarávaní za {_suma(spolu_obj)} majú úrady a obce zapísané v projektoch z eurofondov,
    súťaž ešte nevyhlásili. Vyberte odbor a kraj.</p>
  <div class="mt-8 grid gap-3">
{polozky}
  </div>
</section>
"""
    return (HLAVICKA.format(titul="Pripravované obstarávania z eurofondov podľa odboru a kraja | PredTendrom.sk",
                            popis="Obstarávania z eurofondov, ktoré úrady a obce pripravujú a ešte nevyhlásili. Stavby, IT, energetika a ďalšie odbory v každom kraji Slovenska.",
                            cesta="", robots="index,follow")
            + telo + PATICKA.format(aktualizovane=_datum(date.today().isoformat())))


def vygeneruj(agr, vystup_dir=VYSTUP_DIR, sitemap=SITEMAP_CESTA, robots=ROBOTS_CESTA):
    napisane, urls = [], ["/eurofondy/"]
    dostupne = set(agr)
    for (s, k), a in agr.items():
        adr = os.path.join(vystup_dir, SEKTORY_SEO[s]["slug"])
        os.makedirs(adr, exist_ok=True)
        p = os.path.join(adr, f"{_slug(k)}.html")
        with open(p, "w", encoding="utf-8") as f:
            f.write(_stranka(s, k, a, dostupne))
        napisane.append(p)
        if a["pocet"] >= MIN_INDEX:
            urls.append(cesta_stranky(s, k))
    os.makedirs(vystup_dir, exist_ok=True)
    with open(os.path.join(vystup_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(_hub(agr))
    dnes = date.today().isoformat()
    with open(sitemap, "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                + "\n".join(f"  <url><loc>https://predtendrom.sk{u}</loc><lastmod>{dnes}</lastmod></url>" for u in sorted(urls))
                + "\n</urlset>\n")
    riadok = "Sitemap: https://predtendrom.sk/sitemap-eurofondy.xml"
    if os.path.exists(robots):
        with open(robots, encoding="utf-8") as f:
            obsah = f.read()
        if riadok not in obsah:
            with open(robots, "a", encoding="utf-8") as f:
                f.write(f"\n{riadok}\n")
    return napisane


def hlavne():
    from supabase import create_client
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
    od = (date.today() - timedelta(days=DNI_CERSTVOST)).isoformat()
    riadky = vsetky(lambda a, b: sb.table("itms_vo")
                    .select("id,sektor,kraj,nazov,obstaravatel_nazov,predpokladana_hodnota")
                    .eq("stav", "Pripravované").gte("itms_updated_at", od).is_("vyhlasene_zistene_at", "null")
                    .order("id").range(a, b).execute())
    agr = agreguj(riadky)
    if not agr:
        log.warning("Ziadne pripravovane obstaravania, nic sa negeneruje.")
        return
    n = vygeneruj(agr)
    log.info("Eurofondy: %d stranok, %d kombinacii odbor x kraj", len(n), len(agr))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s")
    hlavne()
