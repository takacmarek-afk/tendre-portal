"""Generuje staticke SEO podstranky /obce/kraj-*.html per kraj.

AUDIT 18.9.2026 ("Marketing", "Prioritizacia"): /obce.html ma vysoky
long-tail SEO potencial ("dotacie pre obce [kraj]"), ale bola to jedna
staticka stranka. Tento skript vyrobi po jednej stranke na kraj z
verejneho agregatu `kraj_prehlad` (supabase/33_kraj_prehlad.sql) a
`sprostredkovatelia` — oba su UZ anon-citatelne agregaty, presne tie
iste, co pouziva /obce.html. NEPOUZIVA `subsidies`/`obce_ziadatelia`
(riadkove data, authenticated-only) — ziadna nova unikanie dodavatelskeho
obsahu do verejnej casti.

Kedze cely web je staticky (Cloudflare Pages, ziadny build ani server),
"programovo generovane podstranky" tu znamena presne to: tento skript
vyrobi skutocne .html subory do public/obce/, ktore GitHub Actions
prida ako obycajny commit. Zamerne NIE JE zapojeny do denneho cronu
pipeline.yml (ten ma contents:read, nie write) — beh je v samostatnom
workflow .github/workflows/obce-podstranky.yml s rovnakou disciplinou
ako pozvanky.yml/statistiky.yml: `schedule:` zakomentovany, kym Marek
sam raz nerozbehne workflow_dispatch a neskontroluje vysledok.

Spustenie lokálne: python generuj_obce_podstranky.py
Potrebuje SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY (rovnake ako ostatne
pipeline skripty） — cita len anon-citatelne tabulky, service_role sa tu
pouziva len preto, aby skript sedel s `store.klient()`, nie preto, ze by
bol nutny.
"""
import os
import re
import logging
import unicodedata
from datetime import date

log = logging.getLogger("generuj_obce_podstranky")

VYSTUP_DIR = os.path.join(os.path.dirname(__file__), "..", "public", "obce")

# Poradie krajov v prehladovom indexe — od najvacsieho poctu dotacii,
# ale to sa dopocita az z realnych dat. Toto je len fallback zoznam
# vsetkych 8 krajov, aby stranka existovala aj pre kraj s nulovymi
# datami (nemalo by nastat, ale nech to nespadne ticho).
VSETKY_KRAJE = [
    "Bratislavský kraj", "Trnavský kraj", "Trenčiansky kraj", "Nitriansky kraj",
    "Žilinský kraj", "Banskobystrický kraj", "Prešovský kraj", "Košický kraj",
]

# Slovenska gramatika sa neda spolahlivo odvodit retazcovou manipulaciou
# ("Kosicky kraj" -> "v kosickom kraji", nie "kosickyom") — radsej explicitny
# zoznam pre vsetkych 8 known krajov nez pokus o vseobecne pravidlo.
LOKAL_KRAJA = {
    "Bratislavský kraj": "bratislavskom",
    "Trnavský kraj": "trnavskom",
    "Trenčiansky kraj": "trenčianskom",
    "Nitriansky kraj": "nitrianskom",
    "Žilinský kraj": "žilinskom",
    "Banskobystrický kraj": "banskobystrickom",
    "Prešovský kraj": "prešovskom",
    "Košický kraj": "košickom",
}


def _slug(kraj: str) -> str:
    """'Banskobystrický kraj' -> 'banskobystricky'."""
    bez_diakritiky = unicodedata.normalize("NFKD", kraj).encode("ascii", "ignore").decode()
    bez_slova_kraj = bez_diakritiky.replace(" kraj", "").strip()
    return re.sub(r"[^a-z0-9]+", "-", bez_slova_kraj.lower()).strip("-")


def _suma(x):
    # POZOR: naivny .replace('.', ',') na uz zlozenom retazci pokazi aj
    # bodku v skratke "mil." (vysledok "mil," namiesto "mil.") — desatinnu
    # ciarku treba vyrobit len z cisla, PRED spojenim s jednotkou/skratkou.
    #
    # `x <= 0` je zamerne rovnaka podmienka ako `eur()` v public/obce.html
    # (odkial tato tabulka data preberala pred timto auditom 19.9.2026):
    # 0 v `median_ceny`/`median_suma` v praxi neznamena zdarma, ale
    # neuvedenu cenu. Predtym tato funkcia brala ako neuvedenu len `None`,
    # takze rovnaky zaznam vedel na hlavnej obce.html ukazat "—" a na
    # generovanej krajskej podstranke "0 €" — nasiel sa napr. pri
    # "Diervilla, spol. s r.o." na /obce/kraj-kosicky.html.
    if x is None or float(x) <= 0:
        return "—"
    x = float(x)
    if x >= 1_000_000:
        cislo = f"{x/1_000_000:.1f}".replace(".", ",")
        return f"{cislo} mil. €"
    return f"{x:,.0f} €".replace(",", " ")


def _cislo(x):
    return "—" if x is None else f"{int(x):,}".replace(",", " ")


def _datum(iso: str) -> str:
    """'2026-09-16' -> '16.9.2026', rovnaky format ako zvysok webu."""
    try:
        y, m, d = iso.split("-")
        return f"{int(d)}.{int(m)}.{y}"
    except Exception:
        return iso


HLAVICKA = """<!doctype html>
<html lang="sk">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{titul}</title>
<meta name="description" content="{popis}">
<meta name="robots" content="index,follow">
<link rel="canonical" href="https://predtendrom.sk/obce/kraj-{slug}.html">
<script src="../config.js"></script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<script src="https://cdn.tailwindcss.com"></script>
<script>
tailwind.config = {{ theme: {{ extend: {{
  fontFamily: {{ sans: ['IBM Plex Sans','system-ui','sans-serif'], serif: ['Instrument Serif','Georgia','serif'], mono: ['IBM Plex Mono','SFMono-Regular','Menlo','monospace'] }},
  colors: {{ ink:'#0B1220', slate2:'#6B6558', line:'#E4DFD2', accent:'#B25313', accentDark:'#8A3F0D', amber:'#E8A33D', paper:'#F7F3EA' }}
}}}} }}
</script>
</head>
<body class="font-sans text-ink bg-paper antialiased">

<header class="border-b border-line bg-white/95">
  <div class="max-w-[900px] mx-auto flex items-center justify-between h-16 px-5">
    <a href="../index.html" class="flex items-center gap-2">
      <svg width="19" height="19" viewBox="0 0 40 40" fill="none" class="text-accent shrink-0">
        <path d="M4 30 L14 22 L24 14 L34 8" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" opacity="0.35"/>
        <circle cx="4" cy="30" r="2.5" fill="currentColor" opacity="0.35"/>
        <circle cx="14" cy="22" r="2.5" fill="currentColor" opacity="0.5"/>
        <circle cx="24" cy="14" r="3" fill="currentColor" opacity="0.75"/>
        <circle cx="34" cy="8" r="4.5" fill="currentColor"/>
      </svg>
      <span class="font-serif italic text-[18px] text-ink">predtendrom</span>
    </a>
    <a href="../obce.html" class="text-[13px] text-slate2 hover:text-ink">Pre obce a mestá</a>
  </div>
</header>
"""

PATICKA = """
<footer class="border-t border-line mt-16">
  <div class="max-w-[900px] mx-auto px-5 py-8 text-[12px] text-slate2">
    Dáta z Centrálneho registra zmlúv. Aktualizované pravidelne, naposledy {aktualizovane}.
    <a href="../zdroje.html" class="text-accent hover:underline">Ako to počítame</a>
    · <a href="mailto:info@predtendrom.sk" class="text-accent hover:underline">info@predtendrom.sk</a>
  </div>
</footer>
</body>
</html>
"""


def _vygeneruj_stranku_kraja(row, spolu_sprostredkovatelia):
    kraj = row["kraj"]
    slug = _slug(kraj)
    kraj_bez_slova = kraj.replace(" kraj", "")
    lokal = LOKAL_KRAJA.get(kraj, kraj_bez_slova.lower() + "om")  # fallback, ale VSETKY_KRAJE pokryva vsetky

    sprostredkovatelia_v_kraji = [
        s for s in spolu_sprostredkovatelia
        if s.get("kraje") and kraj in s["kraje"]
    ][:10]

    if sprostredkovatelia_v_kraji:
        riadky_sprostr = "\n".join(
            f"""      <tr class="border-b border-line last:border-0">
        <td class="py-2.5 pr-3 text-[14px]">{s['sprostredkovatel']}</td>
        <td class="py-2.5 px-3 text-[14px] text-right whitespace-nowrap">{_cislo(s.get('obci'))}</td>
        <td class="py-2.5 pl-3 text-[14px] text-right whitespace-nowrap">{_suma(s.get('median_ceny'))}</td>
      </tr>"""
            for s in sprostredkovatelia_v_kraji
        )
        sekcia_sprostr = f"""
<section class="max-w-[900px] mx-auto px-5 pb-12">
  <h2 class="text-[20px] font-semibold">Kto v {lokal} kraji píše obciam žiadosti</h2>
  <p class="mt-2 text-[14px] text-slate2 max-w-[640px]">
    Firmy a jednotlivci, ktorí obciam v tomto kraji pripravovali žiadosti o dotáciu — bez skóre
    úspešnosti (sprostredkovateľ v žiadosti nefiguruje, podáva ju obec).
  </p>
  <table class="mt-5 w-full">
    <thead>
      <tr class="border-b border-line text-[11px] uppercase tracking-wide text-slate2">
        <th class="text-left pb-2 font-medium">Sprostredkovateľ</th>
        <th class="text-right pb-2 font-medium">Obcí</th>
        <th class="text-right pb-2 font-medium">Typická cena</th>
      </tr>
    </thead>
    <tbody>
{riadky_sprostr}
    </tbody>
  </table>
</section>"""
    else:
        sekcia_sprostr = ""

    titul = f"Dotácie pre obce — {kraj} | PredTendrom.sk"
    popis = (
        f"{_cislo(row['obci'])} obcí a miest v {lokal} kraji dostalo dotáciu, "
        f"spolu {_suma(row['objem_eur'])}. Kto ich dáva a na čo — z Centrálneho registra zmlúv, bez registrácie."
    )

    telo = f"""
<section class="max-w-[900px] mx-auto px-5 pt-10 pb-8">
  <p class="inline-block text-[12px] font-semibold text-accent bg-accent/10 rounded-full px-3 py-1">
    {kraj} · bez registrácie
  </p>
  <h1 class="mt-5 text-[28px] sm:text-[34px] font-bold leading-tight tracking-tight">
    Kto v {lokal} kraji dáva obciam peniaze
  </h1>
  <p class="mt-4 text-[16px] leading-relaxed text-slate2 max-w-[640px]">
    Spočítané z Centrálneho registra zmlúv — dotácie, ktoré obce a mestá
    v {lokal} kraji naozaj podpísali, nie prísľuby z výziev.
  </p>

  <div class="mt-8 grid grid-cols-2 sm:grid-cols-4 gap-3">
    <div class="rounded-lg border border-line bg-white p-4">
      <div class="text-[22px] font-semibold font-mono">{_cislo(row['obci'])}</div>
      <div class="text-[12px] text-slate2 mt-1">obcí a miest s dotáciou</div>
    </div>
    <div class="rounded-lg border border-line bg-white p-4">
      <div class="text-[22px] font-semibold font-mono">{_cislo(row['dotacii'])}</div>
      <div class="text-[12px] text-slate2 mt-1">podpísaných dotácií</div>
    </div>
    <div class="rounded-lg border border-line bg-white p-4">
      <div class="text-[22px] font-semibold font-mono">{_suma(row['objem_eur'])}</div>
      <div class="text-[12px] text-slate2 mt-1">spolu rozdelené</div>
    </div>
    <div class="rounded-lg border border-line bg-white p-4">
      <div class="text-[22px] font-semibold font-mono">{_suma(row['median_suma'])}</div>
      <div class="text-[12px] text-slate2 mt-1">typická dotácia (medián)</div>
    </div>
  </div>

  <p class="mt-6 text-[14px] leading-relaxed text-slate2 max-w-[640px]">
    Najčastejší poskytovatelia v tomto kraji: {row.get('top_poskytovatelia') or '—'}.
  </p>

  <div class="mt-8 rounded-lg border border-line bg-[#F3F0E6] p-5">
    <p class="text-[14px] text-slate2">
      Toto je len súhrn za kraj. Kompletný, priebežne aktualizovaný prehľad
      (na čo sa dáva, kto aktívne rozdáva teraz, otvorené výzvy) je na
      <a href="../obce.html" class="text-accent hover:underline font-medium">hlavnej stránke pre obce</a>,
      zadarmo a bez prihlásenia.
    </p>
  </div>
</section>
{sekcia_sprostr}
"""

    aktualizovane = _datum(row.get("posledna") or date.today().isoformat())
    return (
        HLAVICKA.format(titul=titul, popis=popis, slug=slug)
        + telo
        + PATICKA.format(aktualizovane=aktualizovane)
    )


def _vygeneruj_index(riadky):
    polozky = "\n".join(
        f"""    <a href="./kraj-{_slug(r['kraj'])}.html"
       class="block rounded-lg border border-line bg-white p-4 hover:border-accent transition">
      <div class="text-[15px] font-semibold">{r['kraj']}</div>
      <div class="text-[13px] text-slate2 mt-1">{_cislo(r['obci'])} obcí · {_suma(r['objem_eur'])}</div>
    </a>"""
        for r in riadky
    )
    telo = f"""
<section class="max-w-[900px] mx-auto px-5 pt-10 pb-16">
  <h1 class="text-[28px] sm:text-[34px] font-bold leading-tight tracking-tight">
    Dotácie pre obce podľa kraja
  </h1>
  <p class="mt-4 text-[16px] leading-relaxed text-slate2 max-w-[640px]">
    Vyberte kraj a zistite, koľko obcí tam dostalo dotáciu, koľko to bolo
    a kto peniaze dáva.
  </p>
  <div class="mt-8 grid sm:grid-cols-2 gap-3">
{polozky}
  </div>
</section>
"""
    return (
        HLAVICKA.format(
            titul="Dotácie pre obce podľa kraja | PredTendrom.sk",
            popis="Prehľad dotácií pre obce a mestá za všetkých 8 krajov Slovenska — z Centrálneho registra zmlúv.",
            slug="",
        )
        + telo
        + PATICKA.format(aktualizovane=_datum(date.today().isoformat()))
    )


def vygeneruj(riadky_kraj, riadky_sprostredkovatelia, vystup_dir=VYSTUP_DIR):
    """riadky_kraj = zoznam dictov z kraj_prehlad, riadky_sprostredkovatelia
    z tabulky sprostredkovatelia. Cista funkcia (ziadne IO okrem zapisu
    suborov), aby sa dala volat aj s uz nacitanymi datami (napr. z
    jednorazoveho bootstrapu)."""
    os.makedirs(vystup_dir, exist_ok=True)
    napisane = []

    for row in sorted(riadky_kraj, key=lambda r: r.get("dotacii") or 0, reverse=True):
        html = _vygeneruj_stranku_kraja(row, riadky_sprostredkovatelia)
        cesta = os.path.join(vystup_dir, f"kraj-{_slug(row['kraj'])}.html")
        with open(cesta, "w", encoding="utf-8") as f:
            f.write(html)
        napisane.append(cesta)

    index_html = _vygeneruj_index(
        sorted(riadky_kraj, key=lambda r: r.get("dotacii") or 0, reverse=True)
    )
    cesta_index = os.path.join(vystup_dir, "index.html")
    with open(cesta_index, "w", encoding="utf-8") as f:
        f.write(index_html)
    napisane.append(cesta_index)

    cesta_sitemap = _zapis_sitemap(riadky_kraj, vystup_dir)
    napisane.append(cesta_sitemap)

    return napisane


# Staticke verejne stranky, ktore existuju bez ohladu na kraj_prehlad.
# Rucny zoznam — web nema build, teda ani automaticky zoznam suborov.
STATICKE_STRANKY = [
    "/index.html", "/cennik.html", "/obce.html", "/zdroje.html", "/prihlasenie.html",
]


def _zapis_sitemap(riadky_kraj, vystup_dir):
    """sitemap.xml v koreni public/ — audit 18.9. ("Marketing"): nove
    podstranky su na nic, kym ich vyhladavace nenajdu. Prepisuje sa cely
    subor pri kazdom behu, nie len pridava — jednoduchsie a bezpecnejsie
    nez rucne udrziavat diff."""
    baza = "https://predtendrom.sk"
    dnes = date.today().isoformat()
    urls = list(STATICKE_STRANKY) + ["/obce/index.html"] + [
        f"/obce/kraj-{_slug(r['kraj'])}.html" for r in riadky_kraj
    ]
    polozky = "\n".join(
        f"  <url><loc>{baza}{u}</loc><lastmod>{dnes}</lastmod></url>" for u in urls
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{polozky}\n"
        "</urlset>\n"
    )
    cesta = os.path.join(vystup_dir, "..", "sitemap.xml")
    with open(cesta, "w", encoding="utf-8") as f:
        f.write(xml)
    return cesta


def hlavne():
    import store  # lazy: cista vygeneruj() nema poziadat na supabase-py
    sb = store.klient()
    kraj_data = sb.table("kraj_prehlad").select("*").execute().data
    sprostr_data = sb.table("sprostredkovatelia").select(
        "sprostredkovatel,obci,kraje,median_ceny"
    ).execute().data

    if not kraj_data:
        log.warning("kraj_prehlad je prazdna, nie je co generovat.")
        return

    napisane = vygeneruj(kraj_data, sprostr_data)
    log.info("Vygenerovanych %d suborov do %s", len(napisane), VYSTUP_DIR)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s")
    hlavne()
