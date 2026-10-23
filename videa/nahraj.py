"""Nahra videa navodov 1-6 na ukazkovom ucte a zostriha ich (ffmpeg).

    python videa/nahraj.py /tmp/odkaz.txt vystup/videa "1,2"

Vystup pre kazde video N: video-N.mp4 (16:9, 1920x1080), video-N-reels.mp4
(9:16, 1080x1920), video-N.jpg (nahlad). Titulky su priamo v obraze (FB/IG
spustaju videa stlmene). Kurzor a zvyraznenia su vlozene do stranky skriptom,
nic sa v appke nemeni okrem stavu jednej zmluvy ukazkovej firmy (video 6).
Na verejnych strankach (index, cennik, prihlasenie) sa nic neodosiela.
"""
import asyncio
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.async_api import async_playwright

WEB = "https://predtendrom.sk"
APP = f"{WEB}/app.html"

INIT = r"""
try { localStorage.setItem('pt_admin_zariadenie','1'); localStorage.setItem('pt_cookie_consent','denied'); } catch(e) {}
(function(){
  function ready(fn){ if (document.body) fn(); else document.addEventListener('DOMContentLoaded', fn); }
  ready(function(){
    var m = window.__ptMobil;
    var css = document.createElement('style');
    css.textContent = `
      #odznak-trial{visibility:hidden!important}
      #__cap{position:fixed;left:50%;bottom:${m?'7%':'5%'};transform:translateX(-50%) translateY(12px);opacity:0;
        transition:opacity .35s, transform .35s;z-index:2147483646;max-width:${m?'90%':'78%'};text-align:center;
        background:rgba(11,18,32,.92);color:#fff;font:600 ${m?'19px':'27px'}/1.32 'IBM Plex Sans',Arial,sans-serif;
        padding:${m?'12px 16px':'16px 26px'};border-radius:12px;box-shadow:0 10px 30px rgba(0,0,0,.25);pointer-events:none}
      #__cap.on{opacity:1;transform:translateX(-50%) translateY(0)}
      #__cur{position:fixed;left:0;top:0;width:22px;height:22px;margin:-11px 0 0 -11px;border-radius:50%;
        background:rgba(178,83,19,.85);border:3px solid #fff;box-shadow:0 2px 8px rgba(0,0,0,.35);z-index:2147483647;
        transition:left .7s cubic-bezier(.4,0,.2,1), top .7s cubic-bezier(.4,0,.2,1), transform .15s;pointer-events:none;opacity:0}
      #__cur.klik{transform:scale(.7)}
      .__hl{position:absolute;border:4px solid #B25313;border-radius:10px;box-shadow:0 0 0 9999px rgba(11,18,32,.28);
        z-index:2147483640;pointer-events:none;transition:all .4s}
      #__karta{position:fixed;inset:0;z-index:2147483645;display:flex;align-items:center;justify-content:center;
        background:#0B1220;color:#F7F3EA;opacity:0;transition:opacity .45s;pointer-events:none;text-align:center;padding:6%}
      #__karta.on{opacity:1}
      #__karta.svetla{background:rgba(247,243,234,.97);color:#0B1220}
      #__karta .k-logo{font:italic ${m?'26px':'34px'} 'Instrument Serif',serif;color:#B25313}
      #__karta h1{font:400 ${m?'42px':'70px'}/1.08 'Instrument Serif',serif;margin:.35em 0 .25em}
      #__karta p{font:400 ${m?'18px':'26px'}/1.45 'IBM Plex Sans',sans-serif;opacity:.85}
      #__karta ol{text-align:left;margin:1em auto 0;max-width:${m?'92%':'760px'};font:500 ${m?'20px':'30px'}/1.45 'IBM Plex Sans';padding-left:1.3em}
      #__karta ol li{margin:.35em 0}
    `;
    document.head.appendChild(css);
    var cap = document.createElement('div'); cap.id='__cap'; document.body.appendChild(cap);
    var cur = document.createElement('div'); cur.id='__cur'; document.body.appendChild(cur);
    var k = document.createElement('div'); k.id='__karta'; document.body.appendChild(k);
    window.__pt = {
      cap: function(t){ cap.classList.remove('on'); setTimeout(function(){ cap.textContent=t; if(t) cap.classList.add('on'); }, t && cap.textContent ? 250 : 0); },
      cur: function(x,y){ cur.style.opacity=1; cur.style.left=x+'px'; cur.style.top=y+'px'; },
      klik: function(){ cur.classList.add('klik'); setTimeout(function(){cur.classList.remove('klik')},180); },
      hl: function(sel, pad){ document.querySelectorAll('.__hl').forEach(function(x){x.remove()});
        var e = typeof sel === 'string' ? document.querySelector(sel) : sel; if(!e) return false;
        var r = e.getBoundingClientRect(); pad = pad||8; var d=document.createElement('div'); d.className='__hl';
        d.style.left=(r.left+scrollX-pad)+'px'; d.style.top=(r.top+scrollY-pad)+'px';
        d.style.width=(r.width+2*pad)+'px'; d.style.height=(r.height+2*pad)+'px'; document.body.appendChild(d); return true; },
      unhl: function(){ document.querySelectorAll('.__hl').forEach(function(x){x.remove()}); },
      karta: function(html, svetla){ k.className = svetla ? 'svetla' : ''; k.innerHTML = html; void k.offsetWidth; k.classList.add('on'); },
      bezKarty: function(){ k.classList.remove('on'); }
    };
  });
})();
"""


class Rez:
    """Pomocnik pre jednu nahravku."""

    def __init__(self, pg, mobil):
        self.pg, self.mobil = pg, mobil

    async def w(self, s):
        await self.pg.wait_for_timeout(int(s * 1000))

    async def ide(self, url, cakat="networkidle"):
        try:
            await self.pg.goto(url, wait_until=cakat, timeout=45000)
        except Exception:
            await self.pg.goto(url, timeout=45000)
        await self.pg.wait_for_function("window.__pt !== undefined", timeout=15000)
        await self.w(1.2)

    async def cap(self, t, s=0.0):
        await self.pg.evaluate("t => window.__pt.cap(t)", t)
        await self.w(s)

    async def karta(self, nadpis, text="", s=3.5, cislo=None, body=None, svetla=False):
        html = f'<div><div class="k-logo">predtendrom{" · návod " + str(cislo) + " / 6" if cislo else ""}</div><h1>{nadpis}</h1>'
        if text:
            html += f"<p>{text}</p>"
        if body:
            html += "<ol>" + "".join(f"<li>{b}</li>" for b in body) + "</ol>"
        html += "</div>"
        await self.pg.evaluate("([h, s]) => window.__pt.karta(h, s)", [html, svetla])
        await self.w(s)
        await self.pg.evaluate("window.__pt.bezKarty()")
        await self.w(0.5)

    async def el(self, sel):
        loc = self.pg.locator(sel).first
        await loc.wait_for(state="visible", timeout=15000)
        return loc

    async def rolovat(self, sel, hore=None):
        hore = (90 if self.mobil else 120) if hore is None else hore
        await self.pg.evaluate("""([s, o]) => { const e = document.querySelector(s); if (!e) return;
            window.scrollTo({top: e.getBoundingClientRect().top + scrollY - o, behavior: 'smooth'}); }""", [sel, hore])
        await self.w(1.3)

    async def rolovat_o(self, px):
        await self.pg.evaluate("p => window.scrollBy({top: p, behavior: 'smooth'})", px)
        await self.w(1.2)

    async def kurzor_na(self, loc):
        await loc.scroll_into_view_if_needed()
        b = await loc.bounding_box()
        if b:
            await self.pg.evaluate("([x, y]) => window.__pt.cur(x, y)", [b["x"] + b["width"] / 2, b["y"] + b["height"] / 2])
            await self.w(0.85)

    async def klik(self, sel, po=1.2):
        try:
            loc = await self.el(sel)
            await self.kurzor_na(loc)
            await self.pg.evaluate("window.__pt.klik()")
            await loc.click(timeout=8000)
        except Exception as e:
            print("  klik zlyhal:", sel, type(e).__name__)
        await self.w(po)

    async def vyber(self, sel, hodnota, po=1.4):
        try:
            loc = await self.el(sel)
            await self.kurzor_na(loc)
            await self.pg.evaluate("window.__pt.klik()")
            await loc.select_option(hodnota, timeout=8000)
        except Exception as e:
            print("  vyber zlyhal:", sel, type(e).__name__)
        await self.w(po)

    async def pis(self, sel, text):
        try:
            loc = await self.el(sel)
            await self.kurzor_na(loc)
            await loc.click()
            await loc.type(text, delay=85)
        except Exception as e:
            print("  pisanie zlyhalo:", sel, type(e).__name__)
        await self.w(0.6)

    async def hl(self, sel, s=2.5, pad=8):
        try:
            loc = await self.el(sel)
            await loc.scroll_into_view_if_needed()
            await self.w(0.3)
        except Exception:
            print("  zvyraznenie: nenaslo", sel)
            return
        await self.pg.evaluate("([s, p]) => window.__pt.hl(s, p)", [sel, pad])
        await self.w(s)

    async def bez_hl(self):
        await self.pg.evaluate("window.__pt.unhl()")

    async def zalozka(self, z):
        await self.klik(f'[data-zalozka="{z}"]', po=2.2)

    async def koniec(self, s=5):
        await self.cap("")
        await self.karta("Vyskúšajte 14 dní zadarmo",
                         "Bez platobnej karty. Nové zmluvy z vášho odboru raz týždenne e-mailom.<br><b>predtendrom.sk</b>", s)


# ── scenare ──────────────────────────────────────────────────────────────

PRVY = "#riadky tr:first-child"


async def video1(r: Rez):
    await r.ide(WEB + "/")
    await r.karta("PredTendrom za 70 sekúnd", "Ktoré zmluvy úradov sa vo vašom odbore blížia ku koncu.", 3.5, cislo=1)
    await r.cap("Zmluvy úradov končia. Dátum konca je verejný.", 2)
    await r.rolovat_o(300)
    await r.w(2.5)
    await r.ide(APP)
    await r.zalozka("obsah")
    await r.cap("Vyberte odbor a kraj, v ktorých pracujete.")
    await r.rolovat("#f-kraj", 200)
    await r.vyber("#f-kraj", "Bratislavský kraj")
    await r.vyber("#f-sektor", "UPRATOVANIE", 1.8)
    await r.rolovat("#riadky")
    await r.cap("Kto zmluvu má, za koľko a do kedy.")
    await r.hl(f"{PRVY} td:nth-child(2)", 3)
    await r.hl(f"{PRVY} td:nth-child(4)", 2.5)
    await r.hl(f"{PRVY} td:nth-child(5)", 3)
    await r.bez_hl()
    await r.cap("Každý údaj si overíte v Centrálnom registri zmlúv.")
    sel = f'{PRVY} a[href*="crz.gov.sk"]'
    await r.hl(sel, 2.2)
    href = await r.pg.locator(sel).first.get_attribute("href")
    await r.bez_hl()
    await r.ide(href or WEB, cakat="load")
    await r.cap("Pôvodná zmluva v registri, aj s cenou.", 2.5)
    await r.rolovat_o(350)
    await r.w(2.5)
    await r.koniec()


async def video2(r: Rez):
    await r.ide(WEB + "/prihlasenie")
    await r.karta("Nastavte si odbor a kraj", "Prvé nastavenie po registrácii zaberie 2 minúty.", 3.5, cislo=2)
    await r.cap("Prihlásite sa e-mailom. Bez hesla, bez karty.")
    await r.pis('input[type="email"]', "vas@firma.sk")
    await r.hl('button[type="submit"]', 2.5)
    await r.bez_hl()
    await r.cap("Na e-mail vám príde kód. Zadáte ho a ste v appke.", 2.5)
    await r.ide(APP)
    await r.cap("V časti Môj výber označte, čo robíte a kde.")
    await r.klik("#mv-zmenit", 1.5)
    await r.klik('#mv-kraje label:has-text("Trnavský")', 1)
    await r.klik('#mv-sektory label:has-text("upratovanie – hygienický tovar")', 1.5)
    await r.cap("Kraje, odbory a veľkosť zákaziek. Zmeniť ich môžete kedykoľvek.", 2.5)
    await r.klik('#mv-kraje label:has-text("Trnavský")', 0.6)
    await r.klik('#mv-sektory label:has-text("upratovanie – hygienický tovar")', 0.8)
    await r.klik("#mv-ulozit", 2.5)
    await r.zalozka("dnes")
    await r.cap("Na obrazovke Dnes vidíte, čo sa vo vašom výbere blíži.")
    await r.rolovat(".dnes-karta", 100)
    await r.w(3.5)
    await r.cap("Zapnite si prehľad e-mailom. Raz týždenne vám pošleme nové zmluvy.")
    await r.rolovat("#odber-panel", 100)
    await r.vyber("#o-sektor", "UPRATOVANIE")
    await r.vyber("#o-kraj", "Bratislavský kraj")
    await r.vyber("#o-frekvencia", "tyzdenne")
    await r.hl("#o-zapnut", 3)
    await r.bez_hl()
    await r.koniec()


async def video3(r: Rez):
    await r.ide(APP)
    await r.karta("Ako čítať končiacu zmluvu", "Štyri údaje a jeden odkaz.", 3.5, cislo=3)
    await r.zalozka("obsah")
    await r.rolovat("#riadky")
    await r.cap("Predmet a firma, ktorá zmluvu dnes má.")
    await r.hl(f"{PRVY} td:nth-child(2)", 3)
    await r.cap("Úrad, ktorý zmluvu uzavrel.")
    await r.hl(f"{PRVY} td:nth-child(3)", 2.5)
    await r.cap("Hodnota zmluvy a dátum, kedy končí.")
    await r.hl(f"{PRVY} td:nth-child(4)", 2)
    await r.hl(f"{PRVY} td:nth-child(5)", 2.5)
    await r.bez_hl()
    await r.cap("Odkaz vedie na zmluvu v plnom znení, aj s cenami.")
    sel = f'{PRVY} a[href*="crz.gov.sk"]'
    await r.hl(sel, 2)
    href = await r.pg.locator(sel).first.get_attribute("href")
    await r.bez_hl()
    await r.ide(href or WEB, cakat="load")
    await r.rolovat_o(300)
    await r.w(3)
    await r.cap("")
    await r.karta("Keď zmluva skončí, úrad môže", "", 7, body=[
        "predĺžiť ju dodatkom,", "kúpiť službu bez súťaže (pri malej sume),", "vyhlásiť nové obstarávanie."], svetla=True)
    await r.cap("Ktorú možnosť vyberie, vopred nevie nikto. Dátum konca však poznáte.", 3)
    await r.ide(APP)
    await r.zalozka("dnes")
    await r.cap("Koniec zmluvy si uložte do kalendára. Pripomienka príde 30 dní vopred.")
    await r.hl("[data-dnes-ics]", 1.5)
    await r.bez_hl()
    await r.klik("[data-dnes-ics]", 2.5)
    await r.koniec()


async def video4(r: Rez):
    await r.ide(APP)
    await r.karta("Kto vám konkuruje", "Záložka Dodávatelia.", 3.5, cislo=4)
    await r.zalozka("dodavatelia")
    await r.cap("Firmy, ktoré dnes dodávajú úradom vo vašom odbore.")
    await r.rolovat("#s-sektor", 200)
    await r.vyber("#s-sektor", "UPRATOVANIE", 2)
    await r.rolovat("#riadky-f")
    await r.cap("Objem zmlúv, počet zmlúv a počet úradov.")
    await r.hl("#riadky-f tr:first-child", 3.5)
    await r.bez_hl()
    await r.cap("Kliknite na firmu: s ktorými úradmi má zmluvy a za koľko.")
    await r.klik("#riadky-f tr:nth-child(3) [data-profil]", 3)
    await r.rolovat_o(250)
    await r.w(3.5)
    await r.pg.keyboard.press("Escape")
    await r.w(1)
    await r.cap("Firmu si môžete sledovať. Uvidíte jej nové zmluvy.")
    await r.hl("#riadky-f tr:nth-child(3) [data-sleduj]", 3)
    await r.bez_hl()
    await r.cap("Celý zoznam si stiahnete do Excelu.")
    await r.rolovat("#export-f", 250)
    await r.klik("#export-f", 3)
    await r.koniec()


async def video5(r: Rez):
    await r.ide(APP)
    await r.karta("Za koľko to robia iní", "Ceny skôr, než napíšete ponuku.", 3.5, cislo=5)
    await r.zalozka("sutaze")
    await r.cap("Súťaže ÚVO: kto vyhral, za koľko a koľko bolo ponúk.")
    await r.rolovat("#u-typ", 200)
    await r.vyber("#u-typ", "vysledky", 2)
    await r.rolovat("#riadky-u")
    await r.hl("#riadky-u tr:first-child", 4)
    await r.hl("#riadky-u tr:nth-child(2)", 3)
    await r.bez_hl()
    await r.cap("Pri končiacich zmluvách vidíte cenu oproti mediánu odboru.")
    await r.zalozka("obsah")
    await r.rolovat("#mv-pouzit", 150)
    await r.klik("#mv-pouzit", 1.5)
    await r.vyber("#f-sektor", "OSTRAHA", 2)
    await r.rolovat("#riadky")
    sel = await r.pg.evaluate("""() => { const rr = [...document.querySelectorAll('#riadky tr')];
        const i = rr.findIndex(t => /oproti mediánu|mediánu sektora/.test(t.innerText)); return i < 0 ? 1 : i + 1; }""")
    await r.hl(f"#riadky tr:nth-child({sel}) td:nth-child(2)", 4)
    await r.cap("Mesačná cena pomôže porovnať zmluvy s rôznou dĺžkou.", 3)
    await r.bez_hl()
    await r.koniec()


async def video6(r: Rez):
    await r.ide(APP)
    await r.karta("Príprava 6 mesiacov vopred", "Čo urobiť, keď viete, že zmluva skončí o pol roka.", 3.5, cislo=6)
    await r.zalozka("obsah")
    await r.cap("Zmluvy, ktoré končia o 6 až 12 mesiacov.")
    await r.rolovat("#f-predstih", 200)
    await r.vyber("#f-predstih", "6-12", 2)
    await r.rolovat("#riadky")
    await r.hl(f"{PRVY} td:nth-child(5)", 3)
    await r.bez_hl()
    await r.cap("")
    await r.karta("Čo pripraviť skôr, než úrad vyhlási súťaž", "", 7, body=[
        "referencie z podobných zákaziek,", "certifikáty a oprávnenia,", "ľudí a kapacity,", "cenu, s ktorou viete obstáť."], svetla=True)
    await r.cap("Označte si zmluvu, na ktorú chcete dať ponuku.")
    await r.vyber(f"{PRVY} [data-crm-stav]", "ponuka", 2.5)
    await r.cap("Koniec zmlúv si dajte do kalendára. Nečakajte na Vestník.")
    await r.hl("#export-ics", 3)
    await r.bez_hl()
    await r.vyber(f"{PRVY} [data-crm-stav]", "", 0.8)
    await r.ide(WEB + "/cennik")
    await r.cap("Prvým 30 firmám: ročný plán Start za 240 € s kódom ZAKLADATEL.")
    await r.rolovat_o(500)
    await r.w(4)
    await r.koniec()


SCENARE = {1: video1, 2: video2, 3: video3, 4: video4, 5: video5, 6: video6}


def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], check=True)


async def nahraj(p, stav, n, mobil, cielovy_subor):
    tmp = Path(tempfile.mkdtemp())
    if mobil:
        vp, dpr, velkost = {"width": 432, "height": 768}, 2.5, {"width": 1080, "height": 1920}
    else:
        vp, dpr, velkost = {"width": 1280, "height": 720}, 1.5, {"width": 1920, "height": 1080}
    b = await p.chromium.launch()
    ctx = await b.new_context(viewport=vp, device_scale_factor=dpr, locale="sk-SK", storage_state=stav,
                              record_video_dir=str(tmp), record_video_size=velkost, accept_downloads=True,
                              is_mobile=mobil, has_touch=mobil)
    await ctx.add_init_script(f"window.__ptMobil = {str(mobil).lower()};" + INIT)
    pg = await ctx.new_page()
    t0 = time.monotonic()
    r = Rez(pg, mobil)
    zaciatok = [None]
    povodna = r.karta

    async def karta_s_casom(*a, **kw):
        if zaciatok[0] is None:
            zaciatok[0] = time.monotonic() - t0
        await povodna(*a, **kw)
    r.karta = karta_s_casom
    try:
        await SCENARE[n](r)
    finally:
        await ctx.close()
        await b.close()
    webm = next(tmp.glob("*.webm"))
    od = max(0.0, (zaciatok[0] or 0) - 0.1)
    ffmpeg("-ss", f"{od:.2f}", "-i", str(webm), "-c:v", "libx264", "-preset", "slow", "-crf", "24",
           "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an", "-r", "30", str(cielovy_subor))
    shutil.rmtree(tmp, ignore_errors=True)


async def main(odkaz_subor, vystup, ktore):
    out = Path(vystup)
    out.mkdir(parents=True, exist_ok=True)
    videa = [int(x) for x in ktore.split(",") if x.strip()] or list(SCENARE)
    odkaz = Path(odkaz_subor).read_text().strip()
    stav = str(Path(tempfile.mkdtemp()) / "stav.json")
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context()
        await ctx.add_init_script(INIT)
        pg = await ctx.new_page()
        await pg.goto(odkaz)
        await pg.wait_for_selector('[data-zalozka="obsah"]', state="visible", timeout=45000)
        await ctx.storage_state(path=stav)
        await b.close()
        for n in videa:
            for mobil in (False, True):
                ciel = out / (f"video-{n}-reels.mp4" if mobil else f"video-{n}.mp4")
                t = time.time()
                try:
                    await nahraj(p, stav, n, mobil, ciel)
                    print(f"video {n} {'9:16' if mobil else '16:9'}: hotovo za {time.time() - t:.0f} s")
                except Exception as e:
                    print(f"video {n} {'9:16' if mobil else '16:9'}: CHYBA {type(e).__name__}: {str(e)[:300]}")
            if (out / f"video-{n}.mp4").exists():
                ffmpeg("-ss", "1.5", "-i", str(out / f"video-{n}.mp4"), "-frames:v", "1", "-q:v", "3", str(out / f"video-{n}.jpg"))


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else ""))
