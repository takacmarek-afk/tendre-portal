"""Sonda ITMS21+ Open Data API: ktore endpointy existuju a ake polia vracaju (len kluce a pocty)."""
import json
import requests

BASE = "https://api.itms21.sk/public"
CESTY = ["/v1/projekt?limit=2", "/v1/projekt", "/v3/api-docs", "/v1/api-docs", "/swagger-ui/index.html",
         "/v1/verejneObstaravanie?limit=2", "/v1/verejne-obstaravanie?limit=2", "/v1/verejneObstaravania?limit=2",
         "/v1/zmluvaVerejneObstaravanie?limit=2", "/v1/ziadostONfp?limit=2", "/v1/zonfp?limit=2", "/v1/vyzva?limit=2",
         "/v1/subjekt?limit=2", "/v1/dodavatel?limit=2"]
out = []
for c in CESTY:
    try:
        r = requests.get(BASE + c, timeout=30, headers={"Accept": "application/json"})
        info = f"{r.status_code} {r.headers.get('content-type', '')[:30]} {len(r.content)}B"
        try:
            d = r.json()
            if isinstance(d, dict):
                info += " dict keys=" + ",".join(list(d)[:15])
                for k in ("content", "data", "items", "paths"):
                    if k in d and isinstance(d[k], (list, dict)):
                        v = d[k]
                        if isinstance(v, list) and v and isinstance(v[0], dict):
                            info += f" | {k}[0] keys=" + ",".join(list(v[0])[:40])
                        elif isinstance(v, dict):
                            info += f" | {k} keys=" + ",".join(list(v)[:60])
            elif isinstance(d, list):
                info += f" list n={len(d)}" + (" [0] keys=" + ",".join(list(d[0])[:40]) if d and isinstance(d[0], dict) else "")
        except Exception:
            pass
        out.append(f"{c} -> {info}")
    except Exception as e:
        out.append(f"{c} -> CHYBA {type(e).__name__}")
print("\n".join(out))
for i in range(0, len(out), 5):
    print("::notice title=ITMS " + str(i) + "::" + "%0A".join(o[:600] for o in out[i:i + 5]))
