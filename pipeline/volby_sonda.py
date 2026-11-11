"""Sonda formatu CSV volieb 2026 (len hlavicka a pocet riadkov)."""
import requests
from volby import URL, dekoduj
for tab in ("tab04d", "tab04x"):
    for rok in (2026,):
        u = URL.format(rok=rok, tab=tab)
        r = requests.get(u, timeout=60)
        print(u, r.status_code, r.headers.get("content-type"), len(r.content))
        if r.ok:
            t = dekoduj(r.content)
            riadky = t.splitlines()
            print("riadkov:", len(riadky))
            for x in riadky[:4]:
                print("  |", x[:300])
idx = requests.get("https://volby.statistics.sk/opendata/oso/2026/", timeout=60)
print("index", idx.status_code, idx.text[:1500])
