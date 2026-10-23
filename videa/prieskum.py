"""Prieskum appky pre scenare videi: snimky obrazoviek a zoznam ovladacich prvkov.

    python videa/prieskum.py /tmp/odkaz.txt videa/vystup/prieskum
"""
import asyncio
import json
import sys
from pathlib import Path

from playwright.async_api import async_playwright

INIT = """
try { localStorage.setItem('pt_admin_zariadenie','1'); localStorage.setItem('pt_cookie_consent','denied'); } catch(e) {}
"""

PRVKY = """
() => Array.from(document.querySelectorAll('button, a, input, select, [data-zalozka], li[data-id], tr[data-id]'))
  .filter(e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; })
  .slice(0, 160)
  .map(e => ({tag: e.tagName.toLowerCase(), id: e.id || null,
              cls: (e.className && e.className.baseVal === undefined ? String(e.className) : '').slice(0, 80),
              data: Object.assign({}, e.dataset),
              text: (e.innerText || e.value || e.getAttribute('aria-label') || '').trim().slice(0, 70)}))
"""


async def snimka(pg, out, meno, zoznam=True):
    await pg.wait_for_timeout(2500)
    await pg.screenshot(path=str(out / f"{meno}.png"), full_page=False)
    await pg.screenshot(path=str(out / f"{meno}-cela.png"), full_page=True)
    if zoznam:
        (out / f"{meno}.json").write_text(json.dumps(await pg.evaluate(PRVKY), ensure_ascii=False, indent=1))


async def main(odkaz_subor, vystup):
    out = Path(vystup)
    out.mkdir(parents=True, exist_ok=True)
    odkaz = Path(odkaz_subor).read_text().strip()
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context(viewport={"width": 1280, "height": 720}, locale="sk-SK")
        await ctx.add_init_script(INIT)
        pg = await ctx.new_page()
        pg.on("console", lambda m: m.type == "error" and print("konzola:", m.text[:200]))

        await pg.goto("https://predtendrom.sk/")
        await snimka(pg, out, "01-index")
        await pg.goto("https://predtendrom.sk/cennik")
        await snimka(pg, out, "02-cennik", zoznam=False)

        await pg.goto(odkaz)
        await pg.wait_for_url("**/app**", timeout=30000)
        await pg.wait_for_timeout(4000)
        await snimka(pg, out, "10-app-start")

        for z in ["dnes", "obsah", "sutaze", "dodavatelia"]:
            try:
                await pg.click(f'[data-zalozka="{z}"]', timeout=5000)
                await snimka(pg, out, f"20-{z}")
            except Exception as e:
                print("zalozka", z, "zlyhala:", type(e).__name__)

        # detail prvej zmluvy v Konciacich zmluvach
        try:
            await pg.click('[data-zalozka="obsah"]')
            await pg.wait_for_timeout(2500)
            riadok = pg.locator("#zoznam-z li, #zoznam li, main li").first
            await riadok.click(timeout=5000)
            await snimka(pg, out, "30-detail-zmluvy")
        except Exception as e:
            print("detail zlyhal:", type(e).__name__)

        try:
            await pg.click("#mv-zmenit", timeout=5000)
            await snimka(pg, out, "40-moj-vyber")
            await pg.keyboard.press("Escape")
        except Exception as e:
            print("moj vyber zlyhal:", type(e).__name__)

        try:
            await pg.click('[data-zalozka="dodavatelia"]')
            await pg.wait_for_timeout(2500)
            await pg.locator("#zoznam-f li, #zoznam-f tr, #dodavatelia li").first.click(timeout=5000)
            await snimka(pg, out, "50-detail-dodavatela")
        except Exception as e:
            print("dodavatel zlyhal:", type(e).__name__)

        (out / "html-app.html").write_text(await pg.content())
        await b.close()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], sys.argv[2]))
