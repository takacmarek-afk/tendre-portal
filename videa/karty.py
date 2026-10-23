"""Grafiky pre FB/IG (1080x1350) z jednoduchych specifikacii v JSON.

    python videa/karty.py prispevky.json vystup/karty

Kazda polozka: {"subor": "t1-po", "typ": "cislo"|"stlpce"|"zmluva"|"tip"|"text", ...}
Pisma a farby su z webu (public/fonts, farby zo style.css). Renderuje Chromium
(Playwright) cez lokalny server nad public/, aby sa nacitali pisma.
"""
import asyncio
import html
import json
import sys
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.async_api import async_playwright

PUBLIC = Path(__file__).resolve().parent.parent / "public"
e = html.escape

LOGO = """<div class="logo"><svg width="46" height="46" viewBox="0 0 40 40" fill="none">
<path d="M4 30 L14 22 L24 14 L34 8" stroke="#B25313" stroke-width="2.5" stroke-linecap="round" opacity="0.35"/>
<circle cx="4" cy="30" r="2.5" fill="#B25313" opacity="0.35"/><circle cx="14" cy="22" r="2.5" fill="#B25313" opacity="0.5"/>
<circle cx="24" cy="14" r="3" fill="#B25313" opacity="0.75"/><circle cx="34" cy="8" r="4.5" fill="#B25313"/></svg>
<span>predtendrom</span></div>"""

CSS = """
@import url(/fonts/fonts.css);
*{box-sizing:border-box;margin:0;padding:0}
html,body{width:1080px;height:1350px}
body{background:#F7F3EA;color:#0B1220;font-family:'IBM Plex Sans',sans-serif;padding:84px 88px;display:flex;flex-direction:column}
body.tmava{background:#0B1220;color:#F7F3EA}
.logo{display:flex;align-items:center;gap:14px;font:italic 44px 'Instrument Serif',serif}
.kicker{margin-top:70px;font:600 28px/1.2 'IBM Plex Mono',monospace;letter-spacing:.06em;text-transform:uppercase;color:#B25313}
.velke{font:400 290px/0.9 'Instrument Serif',serif;margin-top:36px;letter-spacing:-.02em}
.stredne{font:400 150px/0.95 'Instrument Serif',serif;margin-top:30px}
h1{font:600 58px/1.18 'IBM Plex Sans',sans-serif;margin-top:34px;letter-spacing:-.01em}
h2{font:600 72px/1.12 'IBM Plex Sans',sans-serif;margin-top:40px;letter-spacing:-.015em}
p.pod{font:400 36px/1.4 'IBM Plex Sans',sans-serif;color:#6B6558;margin-top:26px}
body.tmava p.pod{color:#C9C2B3}
ol,ul{margin-top:40px;padding-left:0;list-style:none;counter-reset:k}
li{font:400 40px/1.35 'IBM Plex Sans',sans-serif;margin-top:26px;padding-left:76px;position:relative}
ol li::before{counter-increment:k;content:counter(k);position:absolute;left:0;top:-4px;width:52px;height:52px;border-radius:50%;
  background:#B25313;color:#fff;font:600 28px/52px 'IBM Plex Sans';text-align:center}
ul li::before{content:'';position:absolute;left:12px;top:20px;width:18px;height:18px;border-radius:50%;background:#B25313}
.riadky{margin-top:46px}
.riadok{display:grid;grid-template-columns:300px 1fr 90px;align-items:center;gap:22px;margin-top:20px;font:400 32px 'IBM Plex Sans'}
.bar{height:38px;background:#B25313;border-radius:4px}
.riadok b{font-weight:600;text-align:right}
.box{margin-top:44px;border:2px solid #E4DFD2;border-radius:18px;padding:44px;background:#fff}
.box .urad{font:600 44px/1.2 'IBM Plex Sans'}
.box .predmet{font:400 34px/1.35 'IBM Plex Sans';color:#6B6558;margin-top:16px}
.box .suma{font:400 130px/1 'Instrument Serif',serif;margin-top:34px}
.box .koniec{font:600 34px 'IBM Plex Sans';margin-top:18px;color:#B25313}
.spacer{flex:1}
.zdroj{font:400 25px/1.45 'IBM Plex Sans';color:#6B6558;border-top:2px solid #E4DFD2;padding-top:26px;display:flex;justify-content:space-between;gap:30px}
body.tmava .zdroj{color:#C9C2B3;border-color:#2A3446}
.zdroj b{color:#B25313;font-weight:600;white-space:nowrap}
.strana{font:600 26px 'IBM Plex Mono';color:#6B6558}
"""


def telo(k: dict) -> str:
    t = k["typ"]
    out = [LOGO]
    if k.get("kicker"):
        out.append(f'<div class="kicker">{e(k["kicker"])}</div>')
    if t == "cislo":
        out.append(f'<div class="velke">{e(k["cislo"])}</div>')
        out.append(f'<h1>{e(k["nadpis"])}</h1>')
        if k.get("pod"):
            out.append(f'<p class="pod">{e(k["pod"])}</p>')
    elif t == "stlpce":
        out.append(f'<h1>{e(k["nadpis"])}</h1>')
        mx = max(v for _, v in k["riadky"]) or 1
        rr = "".join(f'<div class="riadok"><span>{e(n)}</span><div class="bar" style="width:{max(2, round(100 * v / mx))}%"></div><b>{v}</b></div>'
                     for n, v in k["riadky"])
        out.append(f'<div class="riadky">{rr}</div>')
        if k.get("pod"):
            out.append(f'<p class="pod">{e(k["pod"])}</p>')
    elif t == "zmluva":
        out.append(f'<h1>{e(k["nadpis"])}</h1>')
        out.append(f'<div class="box"><div class="urad">{e(k["urad"])}</div><div class="predmet">{e(k["predmet"])}</div>'
                   f'<div class="suma">{e(k["suma"])}</div><div class="koniec">{e(k["koniec"])}</div></div>')
        if k.get("pod"):
            out.append(f'<p class="pod">{e(k["pod"])}</p>')
    elif t in ("tip", "text"):
        out.append(f'<h2>{e(k["nadpis"])}</h2>')
        if k.get("body"):
            tag = "ol" if k.get("cislovane", True) else "ul"
            out.append(f'<{tag}>' + "".join(f"<li>{e(x)}</li>" for x in k["body"]) + f'</{tag}>')
        if k.get("pod"):
            out.append(f'<p class="pod">{e(k["pod"])}</p>')
    out.append('<div class="spacer"></div>')
    zdroj = k.get("zdroj", "")
    prava = k.get("strana") and f'<span class="strana">{e(k["strana"])}</span>' or "<b>predtendrom.sk</b>"
    out.append(f'<div class="zdroj"><span>{e(zdroj)}</span>{prava}</div>')
    trieda = ' class="tmava"' if k.get("tmava") else ""
    return f"<!doctype html><html lang='sk'><head><meta charset='utf-8'><style>{CSS}</style></head><body{trieda}>{''.join(out)}</body></html>"


async def render(karty, vystup: Path):
    vystup.mkdir(parents=True, exist_ok=True)
    tmp = PUBLIC / "_karty_tmp"
    tmp.mkdir(exist_ok=True)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(PUBLIC)))
    srv.RequestHandlerClass.log_message = lambda *a: None
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        async with async_playwright() as p:
            b = await p.chromium.launch()
            pg = await b.new_page(viewport={"width": 1080, "height": 1350})
            for k in karty:
                (tmp / f"{k['subor']}.html").write_text(telo(k), encoding="utf-8")
                await pg.goto(f"http://127.0.0.1:{srv.server_port}/_karty_tmp/{k['subor']}.html")
                await pg.evaluate("document.fonts.ready")
                await pg.wait_for_timeout(150)
                await pg.screenshot(path=str(vystup / f"{k['subor']}.png"))
            await b.close()
    finally:
        srv.shutdown()
        for f in tmp.glob("*"):
            f.unlink()
        tmp.rmdir()


if __name__ == "__main__":
    asyncio.run(render(json.loads(Path(sys.argv[1]).read_text()), Path(sys.argv[2])))
