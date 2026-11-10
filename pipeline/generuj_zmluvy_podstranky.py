"""Generuje staticke SEO podstranky /konciace-zmluvy/[sektor]/[kraj].html.

VYVOJARSKE ZADANIE 23.9.2026 ("Marketing", "Programmatic SEO"): rozsirenie
uz funkcneho vzoru z generuj_obce_podstranky.py na druhu vrstvu produktu —
konciace zmluvy z `opportunities`. Rozdiel oproti tomu skriptu: `opportunities`
je authenticated-only riadkovy zdroj (na rozdiel od uz-agregovaneho
kraj_prehlad), takze tento skript NAJPRV spocita agregat priamo z
`opportunities` (cez service_role, ktory RLS obchadza) a ZAPISE ho do
`zmluvy_seo_agregat` (supabase/44_zmluvy_seo_agregat.sql, anon-citatelna),
az potom z toho vygeneruje HTML. `kraj_prehlad` tento refresh krok nema
(zname obmedzenie) — tento skript ho ma zabudovany, aby nevznikol ten isty
dlh.

HRANICA MEDZI ZADARMO A PLATENYM OBSAHOM (potvrdena, marketingova strategia
sekcia 7): verejne (v HTML aj v zmluvy_seo_agregat) smie byt NAJVIAC:
  - sektor + kraj + pocet konciacich zmluv + celkovy objem (agregat)
  - najviac 3 teaser riadky, VZDY LEN authority_name / price_total / mesiac
    konca (nie presny den)
NIKDY sa nezapisuje supplier_name, top_dodavatel, podiel_top_dodavatela,
historicky_pocet, pocet_dodavatelov ani odkaz — to je jadro platenej
konkurencnej hodnoty (Growth/Team). Riadky NAD teaser (4. a dalsi) sa do
HTML nezapisuju VOBEC, ani ako "zamazane" — zobrazi sa len pocet + CTA.
Dovod: staticke HTML komittovane do repozitara je vzdy citatelne cez
view-source/curl, takze CSS blur na realnych datach by paywall obisiel.

ROZSAH: MVP (zadanie, 23.9.2026) 3 sektory x 8 krajov = 24 stranok, od 5.10.2026 5 sektorov x 8 krajov = 40
stranok. Rozsirenie na cely register je dalsi krok, az po 2-3 tyzdnoch
sledovania Impressions v Google Search Console.

Spustenie lokálne: python generuj_zmluvy_podstranky.py
Potrebuje SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY (rovnake ako ostatne
pipeline skripty).
"""
import os
import logging
from datetime import date, datetime, timedelta
from collections import defaultdict

import generuj_obce_podstranky as obce_podstranky
from strankuj import vsetky
from generuj_obce_podstranky import _slug, _suma, _cislo, _datum, _tvar, _e, VSETKY_KRAJE, LOKAL_KRAJA

log = logging.getLogger("generuj_zmluvy_podstranky")

VYSTUP_DIR = os.path.join(os.path.dirname(__file__), "..", "public", "konciace-zmluvy")
SITEMAP_CESTA = os.path.join(os.path.dirname(__file__), "..", "public", "sitemap-zmluvy.xml")
ROBOTS_CESTA = os.path.join(os.path.dirname(__file__), "..", "public", "robots.txt")

# MVP: 3 najsilnejsie sektory (zadanie 23.9.2026). Kluce presne ako v
# pipeline/config.py SEKTORY — `opportunities.sector` ich take aj obsahuje.
#  "nazov" je akuzativ (pouziva sa vo vetach ako "zmluvy na ostrahu"),
#  "nazov_nom" je nominativ (pre samostatny nadpis/title, kde akuzativ
#  znie zle — "Ostrahu v Presovskom kraji" namiesto "Ostraha..."). Oprava
#  z auditu 29.9.2026 ("Ostrahu v Prešovský kraj" v <title>).
SEKTORY_SEO = {
    "UPRATOVANIE": {"slug": "upratovanie", "nazov": "upratovanie", "nazov_nom": "upratovanie", "nazov_2": "upratovacie služby"},
    "STRAVOVANIE": {"slug": "stravovanie", "nazov": "stravovanie", "nazov_nom": "stravovanie", "nazov_2": "stravovanie a dodávku potravín"},
    "OSTRAHA":     {"slug": "ostraha",     "nazov": "ostrahu",     "nazov_nom": "ostraha",     "nazov_2": "ostrahu a bezpečnostné služby"},
    # Rozsirenie 5.10.2026: dalsie dva sektory, ktore maju zmluvy vo vsetkych
    # 8 krajoch a dost riadkov na obsahovu stranku (STAVEBNE_PRACE 142,
    # IT_TECHNIKA 95; zelen 35 a elektroinstalacie 29 by boli tenke).
    "STAVEBNE_PRACE": {"slug": "stavebne-prace", "nazov": "stavebné práce", "nazov_nom": "stavebné práce", "nazov_2": "stavebné práce"},
    "IT_TECHNIKA":    {"slug": "it-technika",    "nazov": "IT služby a výpočtovú techniku", "nazov_nom": "IT služby a výpočtová technika", "nazov_2": "IT služby a výpočtovú techniku"},
    # Rozsirenie 2. 11. 2026 (audit, bod 3 Top 5): vsetky opakovane odbory.
    # Kombinacie s nulou zmluv dostanu noindex a nie su v sitemap (tenky obsah).
    "ZELEN_ZIMNA_UDRZBA":  {"slug": "zelen-zimna-udrzba", "nazov": "údržbu zelene a zimnú údržbu", "nazov_nom": "údržba zelene a zimná údržba", "nazov_2": "údržbu zelene a zimnú údržbu"},
    "ELEKTROINSTALACIE":   {"slug": "elektroinstalacie",  "nazov": "elektroinštalácie", "nazov_nom": "elektroinštalácie", "nazov_2": "elektroinštalácie a revízie"},
    "KURENIE_VODA_PLYN":   {"slug": "kurenie-voda-plyn",  "nazov": "kúrenie, vodu a plyn", "nazov_nom": "kúrenie, voda a plyn", "nazov_2": "kúrenie, vodu a plyn"},
    "STRECHY_IZOLACIE":    {"slug": "strechy-izolacie",   "nazov": "strechy a zateplenie", "nazov_nom": "strechy a zateplenie", "nazov_2": "strechy a zateplenie"},
    "OKNA_DVERE_POVRCHY":  {"slug": "okna-dvere-povrchy", "nazov": "okná, dvere a povrchy", "nazov_nom": "okná, dvere a povrchy", "nazov_2": "okná, dvere a povrchy"},
    "DOPRAVA_MECHANIZACIA":{"slug": "doprava",            "nazov": "dopravu a mechanizáciu", "nazov_nom": "doprava a mechanizácia", "nazov_2": "dopravu a mechanizáciu"},
    "TLAC_KANCELARIA":     {"slug": "tlac-kancelaria",    "nazov": "tlač a kancelárske potreby", "nazov_nom": "tlač a kancelárske potreby", "nazov_2": "tlač a kancelárske potreby"},
    "ODPAD":               {"slug": "odpad",              "nazov": "zber a vývoz odpadu", "nazov_nom": "zber a vývoz odpadu", "nazov_2": "zber a vývoz odpadu"},
    "PASPORTIZACIA_SPRAVA_BUDOV": {"slug": "sprava-budov", "nazov": "správu budov a pasportizáciu", "nazov_nom": "správa budov a pasportizácia", "nazov_2": "správu budov a pasportizáciu"},
}

HUB_CESTA = os.path.join(os.path.dirname(__file__), "..", "public", "konciace-zmluvy", "index.html")

MESIACE_SK = ["", "januári", "februári", "marci", "apríli", "máji", "júni",
              "júli", "auguste", "septembri", "októbri", "novembri", "decembri"]


def _mesiac_konca(effective_to) -> str:
    """date/str -> 'december 2026' (len mesiac + rok, nikdy presny den — cast
    hranice medzi zadarmo a platenym obsahom, viz modulovy docstring)."""
    if effective_to is None:
        return "—"
    if isinstance(effective_to, str):
        try:
            effective_to = datetime.strptime(effective_to[:10], "%Y-%m-%d").date()
        except ValueError:
            return "—"
    return f"{MESIACE_SK[effective_to.month]} {effective_to.year}"


def _spocitaj_agregat(riadky):
    """riadky = zoznam dictov z `opportunities` (sector, kraj, authority_name,
    price_total, effective_to) pre jeden sektor. Vrati zoznam agregatov per
    kraj — presne polia, ktore smu byt verejne (viz modulovy docstring)."""
    podla_kraja = defaultdict(list)
    for r in riadky:
        kraj = r.get("kraj")
        if not kraj:
            continue
        podla_kraja[kraj].append(r)

    agregaty = []
    for kraj, rr in podla_kraja.items():
        rr_zoradene = sorted(
            (r for r in rr if r.get("effective_to")),
            key=lambda r: r["effective_to"],
        )
        teaser = [
            {
                "authority_name": r.get("authority_name") or "—",
                "price_total": float(r["price_total"]) if r.get("price_total") else None,
                "mesiac_konca": _mesiac_konca(r["effective_to"]),
            }
            for r in rr_zoradene[:3]
        ]
        objemy = [float(r["price_total"]) for r in rr if r.get("price_total")]
        agregaty.append({
            "kraj": kraj,
            "pocet": len(rr),
            "objem_eur": sum(objemy) if objemy else None,
            "najblizsi_koniec": rr_zoradene[0]["effective_to"] if rr_zoradene else None,
            "teaser": teaser,
        })
    return agregaty


HLAVICKA = """<!doctype html>
<html lang="sk">
<head>
<meta charset="utf-8">
<script src="/consent-analytics.js"></script>
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="icon" href="/favicon.ico" sizes="any">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<title>{titul}</title>
<meta name="description" content="{popis}">
<meta name="robots" content="{robots}">
<link rel="canonical" href="https://predtendrom.sk/konciace-zmluvy/{cesta}">
<meta property="og:title" content="{titul}">
<meta property="og:description" content="{popis}">
<meta property="og:type" content="website">
<meta property="og:url" content="https://predtendrom.sk/konciace-zmluvy/{cesta}">
<meta property="og:locale" content="sk_SK">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{titul}">
<meta name="twitter:description" content="{popis}">
<meta property="og:image" content="https://predtendrom.sk/og-image.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:image" content="https://predtendrom.sk/og-image.png">
<script src="../../config.js"></script>
<link rel="preload" href="/fonts/IBMPlexSans-Variable.woff" as="font" type="font/woff" crossorigin>
<link rel="stylesheet" href="/fonts/fonts.css">
<link rel="stylesheet" href="/style.css">
</head>
<body class="font-sans text-ink bg-paper antialiased">

<header class="border-b border-line bg-white/95">
  <div class="max-w-[900px] mx-auto flex items-center justify-between h-16 px-5">
    <a href="/" class="flex items-center gap-2">
      <svg width="19" height="19" viewBox="0 0 40 40" fill="none" class="text-accent shrink-0">
        <path d="M4 30 L14 22 L24 14 L34 8" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" opacity="0.35"/>
        <circle cx="4" cy="30" r="2.5" fill="currentColor" opacity="0.35"/>
        <circle cx="14" cy="22" r="2.5" fill="currentColor" opacity="0.5"/>
        <circle cx="24" cy="14" r="3" fill="currentColor" opacity="0.75"/>
        <circle cx="34" cy="8" r="4.5" fill="currentColor"/>
      </svg>
      <span class="font-serif text-[18px] text-ink">predtendrom</span>
    </a>
    <a href="/cennik" class="text-[13px] text-slate2 hover:text-ink">Cenník</a>
  </div>
</header>
"""

PATICKA = """
<section class="max-w-[900px] mx-auto px-5 mt-12">
  <div class="rounded-lg border border-line bg-white p-5">
    <div class="text-[16px] font-semibold">Kedy končia zmluvy konkrétnej firmy?</div>
    <p class="mt-1 text-[14px] text-slate2">Zadajte IČO a zistíte, ktoré zmluvy sa blížia ku koncu. Bez registrácie, zadarmo.</p>
    <p class="mt-3 text-[14px]">
      <a href="/kontrola" class="text-accent font-semibold hover:underline">Skontrolovať podľa IČO →</a>
      · <a href="/mapa" class="text-accent hover:underline">Mapa končiacich zmlúv podľa krajov</a>
    </p>
  </div>
</section>

<footer class="border-t border-line mt-12">
  <div class="max-w-[900px] mx-auto px-5 py-8 text-[12px] text-slate2">
    Dáta z Centrálneho registra zmlúv. Aktualizované pravidelne, naposledy {aktualizovane}.
    <a href="/zdroje" class="text-accent hover:underline">Ako to počítame</a>
    · <a href="mailto:info@predtendrom.sk" class="text-accent hover:underline">info@predtendrom.sk</a>
  </div>
  <p class="pt-pravne text-[12px] text-slate2 text-center py-4 border-t border-line"><a href="/obchodne-podmienky" class="underline hover:text-ink">Obchodné podmienky</a> &middot; <a href="/ochrana-osobnych-udajov" class="underline hover:text-ink">Ochrana osobných údajov</a> &middot; <a href="#" onclick="window.ptCookieNastavenia&amp;&amp;window.ptCookieNastavenia();return false;" class="underline hover:text-ink">Nastavenia cookies</a></p>
</footer>
<script>
// Audit 10. 11. 2026: kto prisiel zo studeneho e-mailu (utm_source=email),
// nesie si zdroj aj do registracie, inak by sa v lieviku ratal ako SEO.
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


def _popis_stranky(agregat_row, sektor_info, lokal):
    """Meta description stranky sektor x kraj. Spravne sklonovanie poctu
    (1 zmluva / 2-4 zmluvy / 5+ zmlus), pri 0 zmluvach iná veta a ked chyba
    suma, veta o "spolu" sa vynecha uplne (audit 5.10.2026, C5)."""
    pocet = agregat_row["pocet"]
    nazov = sektor_info["nazov"]
    if not pocet:
        return (
            f"V {lokal} kraji sa momentálne neblíži ku koncu žiadna zmluva na {nazov}. "
            f"Sledujte, ktoré sa uvoľnia. Údaje z Centrálneho registra zmlúv."
        )
    zmluvy = _tvar(pocet, "zmluva", "zmluvy", "zmlúv")
    sloveso = _tvar(pocet, "sa blíži", "sa blížia", "sa blíži")
    suma = _suma(agregat_row["objem_eur"])
    spolu = f", spolu {suma}" if suma != "—" else ""
    dalsia = (
        "Prehľad, kedy sa uvoľní"
        if int(pocet) == 1 else "Prehľad, kedy sa uvoľnia"
    )
    return (
        f"{_cislo(pocet)} {zmluvy} na {nazov} v {lokal} kraji {sloveso} ku koncu{spolu}. "
        f"{dalsia}, kto ich robí a za koľko. Údaje z Centrálneho registra zmlúv."
    )


def _velke_prve(t):
    """Prve pismeno velke, zvysok bez zmeny ('IT služby' nesmie byt 'It služby' ako pri str.capitalize())."""
    return t[:1].upper() + t[1:]


def _vygeneruj_stranku(sector, agregat_row):
    kraj = agregat_row["kraj"]
    sektor_info = SEKTORY_SEO[sector]
    sektor_slug = sektor_info["slug"]
    kraj_slug = _slug(kraj)
    kraj_bez_slova = kraj.replace(" kraj", "")
    lokal = _velke_prve(LOKAL_KRAJA.get(kraj, kraj_bez_slova.lower() + "om"))  # "v Košickom kraji" (10. 11. 2026)

    if agregat_row["teaser"]:
        riadky_teaser = "\n".join(
            f"""      <div class="rounded-lg border border-line bg-white p-4">
        <div class="text-[14px] font-medium">{_e(str(t['authority_name']).strip())}</div>
        <div class="mt-1 flex items-center justify-between text-[13px] text-slate2">
          <span>{_suma(t['price_total'])}</span>
          <span>zmluva končí v {_e(t['mesiac_konca'])}</span>
        </div>
      </div>"""
            for t in agregat_row["teaser"]
        )
    else:
        riadky_teaser = """      <div class="rounded-lg border border-line bg-white p-4 text-[14px] text-slate2">
        Teraz tu nekončí žiadna zmluva. Pozrite iný kraj nižšie alebo sa vráťte neskôr.
      </div>"""

    zvysok = max(0, agregat_row["pocet"] - len(agregat_row["teaser"]))
    if zvysok > 0:
        # ZAMERNE ziadne realne polia pre riadky nad teaser — len pocet + CTA.
        # Staticke HTML je vzdy citatelne cez view-source/curl, CSS blur na
        # skutocnych datach by tu paywall neochranil (viz modulovy docstring).
        blok_zvysok = f"""
    <div class="mt-3 rounded-lg border border-dashed border-line bg-[#F3F5F7] p-5 text-center">
      <p class="text-[14px] text-slate2">+ {_cislo(zvysok)} {_tvar(zvysok, 'ďalšia zmluva', 'ďalšie zmluvy', 'ďalších zmlúv')} v tomto kraji a sektore.</p>
      <a href="/prihlasenie?utm_source=seo_{sektor_slug}_{kraj_slug}&utm_medium=organic&utm_campaign=programmatic_seo"
         class="mt-3 inline-block rounded-md bg-accent text-white text-[13px] font-medium px-4 py-2 hover:bg-accentDark">
        Zobraziť všetky (14 dní zadarmo, bez karty)
      </a>
    </div>"""
    else:
        blok_zvysok = ""

    # 10. 11. 2026: ludia zo studeneho e-mailu prisli, ale nikto nesiel dalej.
    # Vyzva bola len v strede stranky (na mobile pod cookie listou). Hned pod
    # cislami je teraz jasny dalsi krok s rovnakym slubom ako v e-maile.
    from urllib.parse import urlencode
    _odber_q = urlencode({"sektor": sector, "kraj": kraj}).replace("&", "&amp;")
    if zvysok > 0:
        p = agregat_row["pocet"]
        blok_hore = f"""
  <div class="mt-4 flex flex-col sm:flex-row sm:items-center gap-3">
    <a href="/prihlasenie?utm_source=seo_{sektor_slug}_{kraj_slug}&utm_medium=organic&utm_campaign=programmatic_seo&utm_content=hore"
       class="inline-flex justify-center items-center rounded-md bg-accent text-white text-[15px] font-semibold px-5 py-3 hover:bg-accentDark">
      Pozrieť {_tvar(p, 'celú', 'všetky', 'všetkých')} {_cislo(p)} {_tvar(p, 'zmluvu', 'zmluvy', 'zmlúv')}
    </a>
    <span class="text-[13px] leading-snug text-slate2">14 dní zadarmo, bez platobnej karty.<br class="hidden sm:inline">
      Nové končiace zmluvy Vám potom pošleme e-mailom.</span>
  </div>
  <p class="mt-3 text-[13px] text-slate2">Bez registrácie:
    <a href="/?{_odber_q}#ukazka" class="text-accent font-semibold hover:underline">posielať mi zadarmo každý týždeň nové súťaže a končiace zmluvy</a></p>"""
    else:
        blok_hore = ""

    # Pri stavbach koniec zmluvy spravidla neznamena novu sutaz (stavba sa
    # dokonci), preto o tom tento sektor otvorene hovori (audit 6. 10. 2026).
    if sector == "STAVEBNE_PRACE":
        blok_zvysok += """
    <p class="mt-4 text-[13px] leading-relaxed text-slate2">
      Pri stavbách koniec zmluvy spravidla neznamená novú súťaž, stavba sa dokončí.
      Pre stavebné firmy sú dôležitejšie dotácie obcí, ktoré ešte len prídu.
    </p>"""

    # OPRAVA (audit 29.9.2026): "v {kraj}" pouzival nominativ po predlozke
    # "v", ktora vyzaduje lokal ("v Bratislavský kraj" -> "v Bratislavskom
    # kraji"). "nazov_nom" rieši rovnaky problem pre sektor (OSTRAHA malo
    # v nazov ulozeny akuzativ "ostrahu", ktory v title cital ako "Ostrahu").
    titul = f"{_velke_prve(sektor_info['nazov_nom'])} v {lokal} kraji: končiace zmluvy úradov | PredTendrom.sk"
    popis = _popis_stranky(agregat_row, sektor_info, lokal)

    telo = f"""
<section class="max-w-[900px] mx-auto px-5 pt-10 pb-8">
  <p class="inline-block text-[12px] font-semibold text-accent bg-accent/10 rounded-full px-3 py-1">
    {_e(kraj)}, {sektor_info['nazov_nom']}
  </p>
  <h1 class="mt-5 text-[28px] sm:text-[34px] font-bold leading-tight tracking-tight">
    Komu v {lokal} kraji čoskoro skončí zmluva na {sektor_info['nazov_2']}
  </h1>
  <p class="mt-4 text-[16px] leading-relaxed text-slate2 max-w-[640px]">
    Zmluvy úradov, škôl a obcí z Centrálneho registra zmlúv, ktoré skončia v najbližších
    mesiacoch. Keď zmluva skončí, úrad musí službu nakúpiť znova. Kto to vie skôr,
    pripraví si ponuku v pokoji.
  </p>

  <div class="mt-8 grid grid-cols-2 gap-3">
    <div class="rounded-lg border border-line bg-white p-4">
      <div class="text-[22px] font-semibold tabular-nums">{_cislo(agregat_row['pocet'])}</div>
      <div class="text-[12px] text-slate2 mt-1">{_tvar(agregat_row['pocet'], 'končiaca zmluva', 'končiace zmluvy', 'končiacich zmlúv')}</div>
    </div>
    <div class="rounded-lg border border-line bg-white p-4">
      <div class="text-[22px] font-semibold tabular-nums">{_suma(agregat_row['objem_eur'])}</div>
      <div class="text-[12px] text-slate2 mt-1">spolu v týchto zmluvách</div>
    </div>
  </div>

{blok_hore}
  <h2 class="mt-10 text-[18px] font-semibold">Príklady</h2>
  <div class="mt-4 grid gap-3">
{riadky_teaser}
  </div>
{blok_zvysok}
{_odkazy(sector, kraj)}
</section>
"""

    aktualizovane = _datum(date.today().isoformat())
    return (
        HLAVICKA.format(titul=titul, popis=popis, cesta=f"{sektor_slug}/{kraj_slug}",
                        robots="index,follow" if agregat_row["pocet"] else "noindex,follow")
        + telo
        + PATICKA.format(aktualizovane=aktualizovane)
    )


# Odbory, pre ktore sa v tomto behu naozaj generuju stranky (nastavi
# vygeneruj()). Audit 10. 11. 2026: odbor bez dat (sprava budov) sa
# preskocil, ale ostatne stranky nan odkazovali -> 104 rozbitych odkazov.
DOSTUPNE_SEKTORY = set()


def _odkazy(sector, kraj):
    """Interne odkazy: rovnaky odbor v inych krajoch a ine odbory v tom istom
    kraji. Pomahaju Googlu najst vsetky stranky a navstevnikovi preskocit."""
    info = SEKTORY_SEO[sector]
    kraje = " ".join(
        f'<a href="/konciace-zmluvy/{info["slug"]}/{_slug(k)}" class="text-accent hover:underline">{_e(k.replace(" kraj", ""))}</a>'
        for k in VSETKY_KRAJE if k != kraj)
    odbory = " ".join(
        f'<a href="/konciace-zmluvy/{i["slug"]}/{_slug(kraj)}" class="text-accent hover:underline">{_e(_velke_prve(i["nazov_nom"]))}</a>'
        for s, i in SEKTORY_SEO.items()
        if s != sector and (not DOSTUPNE_SEKTORY or s in DOSTUPNE_SEKTORY))
    # 10. 11. 2026: odkaz na pripravovane obstaravania z eurofondov, ak stranka existuje
    eu = os.path.join(os.path.dirname(__file__), "..", "public", "eurofondy", info["slug"], f"{_slug(kraj)}.html")
    eurofondy = (f' · <a href="/eurofondy/{info["slug"]}/{_slug(kraj)}" class="text-accent font-semibold hover:underline">'
                 f'Pripravované obstarávania z eurofondov v kraji</a>' if os.path.exists(eu) else "")
    return f"""
  <h2 class="mt-10 text-[16px] font-semibold">{_velke_prve(info['nazov_nom'])} v iných krajoch</h2>
  <p class="mt-2 text-[14px] leading-loose flex flex-wrap gap-x-4">{kraje}</p>
  <h2 class="mt-6 text-[16px] font-semibold">Iné odbory v kraji</h2>
  <p class="mt-2 text-[14px] leading-loose flex flex-wrap gap-x-4">{odbory}</p>
  <p class="mt-4 text-[14px]"><a href="/konciace-zmluvy/" class="text-accent hover:underline">Všetky odbory a kraje</a>{eurofondy}</p>"""


def _vygeneruj_hub(vsetky_agregaty):
    """Rozcestnik /konciace-zmluvy/: vsetky odbory s poctom zmluv."""
    riadky = []
    for sector, agregaty in vsetky_agregaty.items():
        info = SEKTORY_SEO[sector]
        pocet = sum(int(r["pocet"] or 0) for r in agregaty)
        riadky.append((pocet, f"""    <a href="/konciace-zmluvy/{info['slug']}/" class="block rounded-lg border border-line bg-white p-4 hover:border-accent transition">
      <div class="text-[15px] font-semibold">{_e(_velke_prve(info['nazov_nom']))}</div>
      <div class="text-[13px] text-slate2 mt-1">{_cislo(pocet)} {_tvar(pocet, 'končiaca zmluva', 'končiace zmluvy', 'končiacich zmlúv')}</div>
    </a>"""))
    polozky = "\n".join(t for _, t in sorted(riadky, key=lambda x: -x[0]))
    telo = f"""
<section class="max-w-[900px] mx-auto px-5 pt-10 pb-16">
  <h1 class="text-[28px] sm:text-[34px] font-bold leading-tight tracking-tight">Končiace zmluvy úradov podľa odboru</h1>
  <p class="mt-4 text-[16px] leading-relaxed text-slate2 max-w-[640px]">
    Vyberte odbor a potom kraj. Pri každom uvidíte, koľko zmlúv štátu, škôl a obcí sa blíži ku koncu a za koľko.
  </p>
  <div class="mt-8 grid sm:grid-cols-2 gap-3">
{polozky}
  </div>
</section>
"""
    return (HLAVICKA.format(titul="Končiace zmluvy úradov podľa odboru a kraja | PredTendrom.sk",
                            popis="Ktorým úradom, školám a obciam končí zmluva na upratovanie, ostrahu, stravovanie, IT a ďalšie služby. Podľa odboru a kraja, z Centrálneho registra zmlúv.",
                            cesta="", robots="index,follow")
            + telo + PATICKA.format(aktualizovane=_datum(date.today().isoformat())))


def _vygeneruj_index_sektora(sector, agregaty):
    sektor_info = SEKTORY_SEO[sector]
    polozky = "\n".join(
        f"""    <a href="/konciace-zmluvy/{sektor_info['slug']}/{_slug(r['kraj'])}"
       class="block rounded-lg border border-line bg-white p-4 hover:border-accent transition">
      <div class="text-[15px] font-semibold">{_e(r['kraj'])}</div>
      <div class="text-[13px] text-slate2 mt-1">{_cislo(r['pocet'])} {_tvar(r['pocet'], 'zmluva', 'zmluvy', 'zmlúv')}{'' if _suma(r['objem_eur']) == '—' else ' · ' + _suma(r['objem_eur'])}</div>
    </a>"""
        for r in sorted(agregaty, key=lambda r: r["pocet"], reverse=True)
    )
    telo = f"""
<section class="max-w-[900px] mx-auto px-5 pt-10 pb-16">
  <h1 class="text-[28px] sm:text-[34px] font-bold leading-tight tracking-tight">
    Končiace zmluvy na {sektor_info['nazov']} podľa kraja
  </h1>
  <p class="mt-4 text-[16px] leading-relaxed text-slate2 max-w-[640px]">
    Vyberte kraj a zistite, koľko zmlúv na {sektor_info['nazov']} sa tam blíži ku koncu.
  </p>
  <div class="mt-8 grid sm:grid-cols-2 gap-3">
{polozky}
  </div>
  <div class="mt-8 rounded-lg border border-dashed border-line bg-[#F3F5F7] p-5 text-center">
    <p class="text-[14px] text-slate2">Zoznam konkrétnych zmlúv, termín, dokedy sa pripraviť a upozornenia vo vašom kraji a sektore.</p>
    <a href="/prihlasenie?utm_source=seo_{sektor_info['slug']}_index&utm_medium=organic&utm_campaign=programmatic_seo"
       class="mt-3 inline-block rounded-md bg-accent text-white text-[13px] font-medium px-4 py-2 hover:bg-accentDark">
      Vyskúšať 14 dní zadarmo, bez karty
    </a>
  </div>
</section>
"""
    return (
        HLAVICKA.format(
            titul=f"{_velke_prve(sektor_info['nazov_nom'])}: končiace zmluvy úradov podľa kraja | PredTendrom.sk",
            robots="index,follow",
            popis=f"Prehľad končiacich zmlúv na {sektor_info['nazov']} za všetkých 8 krajov Slovenska.",
            # OPRAVA (audit 29.9.2026): prazdny kraj_slug davel rozbity canonical
            # ".../ostraha/.html" (chybajuci "index"). Rovnaky vzor ako subor sam:
            # tato stranka sa fyzicky vola index.html.
            # U25 (5.10.2026): canonical bez .html (Cloudflare .html presmeruje 308);
            # index sektora je adresa /konciace-zmluvy/<sektor>/ (koncove lomitko).
            cesta=f"{sektor_info['slug']}/",
        )
        + telo
        + PATICKA.format(aktualizovane=_datum(date.today().isoformat()))
    )


def _zapis_sitemap(vsetky_kombinacie):
    baza = "https://predtendrom.sk"
    dnes = date.today().isoformat()
    # U25 (5.10.2026): adresy BEZ .html (Cloudflare .html presmeruje 308);
    # index sektora ma koncove lomitko.
    urls = ["/konciace-zmluvy/"] + [f"/konciace-zmluvy/{s}/" for s in sorted({k[0] for k in vsetky_kombinacie})] + [
        f"/konciace-zmluvy/{sektor_slug}/{kraj_slug}" for sektor_slug, kraj_slug in vsetky_kombinacie
    ]
    polozky = "\n".join(f"  <url><loc>{baza}{u}</loc><lastmod>{dnes}</lastmod></url>" for u in urls)
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{polozky}\n"
        "</urlset>\n"
    )
    with open(SITEMAP_CESTA, "w", encoding="utf-8") as f:
        f.write(xml)
    return SITEMAP_CESTA


def _zaregistruj_v_robots():
    """Prida druhy Sitemap: riadok do robots.txt, ak tam este nie je.
    robots.txt podporuje viac Sitemap: riadkov naraz — nejde o nahradu."""
    riadok = "Sitemap: https://predtendrom.sk/sitemap-zmluvy.xml"
    with open(ROBOTS_CESTA, "r", encoding="utf-8") as f:
        obsah = f.read()
    if riadok in obsah:
        return False
    with open(ROBOTS_CESTA, "a", encoding="utf-8") as f:
        f.write(f"\n{riadok}\n")
    return True


def vygeneruj(vsetky_agregaty, vystup_dir=VYSTUP_DIR):
    """vsetky_agregaty = {sector: [agregat_row, ...]}. Cista funkcia
    (okrem zapisu suborov), rovnaky vzor ako generuj_obce_podstranky.vygeneruj."""
    napisane = []
    kombinacie = []
    DOSTUPNE_SEKTORY.clear()
    DOSTUPNE_SEKTORY.update(vsetky_agregaty)

    for sector, agregaty in vsetky_agregaty.items():
        sektor_slug = SEKTORY_SEO[sector]["slug"]
        adresar = os.path.join(vystup_dir, sektor_slug)
        os.makedirs(adresar, exist_ok=True)

        for row in agregaty:
            html = _vygeneruj_stranku(sector, row)
            cesta = os.path.join(adresar, f"{_slug(row['kraj'])}.html")
            with open(cesta, "w", encoding="utf-8") as f:
                f.write(html)
            napisane.append(cesta)
            if row["pocet"]:
                kombinacie.append((sektor_slug, _slug(row["kraj"])))

        index_html = _vygeneruj_index_sektora(sector, agregaty)
        cesta_index = os.path.join(adresar, "index.html")
        with open(cesta_index, "w", encoding="utf-8") as f:
            f.write(index_html)
        napisane.append(cesta_index)

    if vsetky_agregaty:
        hub = os.path.join(vystup_dir, "index.html")
        with open(hub, "w", encoding="utf-8") as f:
            f.write(_vygeneruj_hub(vsetky_agregaty))
        napisane.append(hub)
    napisane.append(_zapis_sitemap(kombinacie))
    if _zaregistruj_v_robots():
        napisane.append(ROBOTS_CESTA)

    return napisane


def hlavne():
    import store  # lazy, rovnaky dovod ako v generuj_obce_podstranky.py
    sb = store.klient()

    vsetky_agregaty = {}
    for sector in SEKTORY_SEO:
        # Strankovane: PostgREST inak potichu orezava na 1 000 riadkov a
        # verejne stranky by uvadzali podhodnoteny pocet a objem.
        riadky = vsetky(lambda od, do: (
            sb.table("opportunities")
            .select("sector,kraj,authority_name,price_total,effective_to")
            .eq("sector", sector)
            .order("contract_id")
            .range(od, do)
            .execute()
        ))
        if not riadky:
            log.warning("opportunities: ziadne riadky pre sektor %s, preskakujem.", sector)
            continue

        agregaty = _spocitaj_agregat(riadky)
        # Doplnit chybajuce kraje s nulou, aby stranka existovala aj tam,
        # kde momentalne nic nekonci (rovnaky dovod ako VSETKY_KRAJE v
        # generuj_obce_podstranky.py).
        znamych = {r["kraj"] for r in agregaty}
        for kraj in VSETKY_KRAJE:
            if kraj not in znamych:
                agregaty.append({"kraj": kraj, "pocet": 0, "objem_eur": None,
                                  "najblizsi_koniec": None, "teaser": []})
        vsetky_agregaty[sector] = agregaty

        # Zapis agregatu do verejnej tabulky (service_role obchadza RLS).
        dnes = date.today().isoformat()
        zaznamy = [{
            "sector": sector,
            "kraj": r["kraj"],
            "pocet": r["pocet"],
            "objem_eur": r["objem_eur"],
            "najblizsi_koniec": r["najblizsi_koniec"],
            "teaser": r["teaser"],
            "last_seen_at": dnes,
        } for r in agregaty]
        sb.table("zmluvy_seo_agregat").upsert(zaznamy, on_conflict="sector,kraj").execute()

    if not vsetky_agregaty:
        log.warning("Ziadne data pre ziadny MVP sektor, nic sa negeneruje.")
        return

    napisane = vygeneruj(vsetky_agregaty)
    log.info("Vygenerovanych/aktualizovanych %d suborov do %s", len(napisane), VYSTUP_DIR)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s")
    hlavne()
