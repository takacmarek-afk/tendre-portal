"""Prehlad navstevnosti a lievika (len suhrnne cisla, ziadne e-maily ani IP).

Navstevy prihlaseneho admina (zariadenie s pt_admin_zariadenie) sa do tabulky
navstevy vobec nezapisuju, takze cisla su bez Mareka na zariadeniach, kde sa
aspon raz prihlasil do appky.
"""
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from supabase import create_client
from strankuj import vsetky

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
od = (datetime.now(timezone.utc) - timedelta(days=21)).isoformat()
nav = vsetky(lambda a, b: sb.table("navstevy").select("id,cesta,referrer,session_id,utm_source,created_at")
             .gte("created_at", od).order("id").range(a, b).execute())
riadky = []
dni = defaultdict(set)
zobr = Counter()
for n in nav:
    d = n["created_at"][:10]
    dni[d].add(n["session_id"] or n["id"])
    zobr[d] += 1
riadky.append("Den | navstev (session) | zobrazeni")
for d in sorted(dni):
    riadky.append(f"{d} | {len(dni[d])} | {zobr[d]}")
od7 = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
n7 = [n for n in nav if n["created_at"] >= od7]
zdroj = defaultdict(set)
stranky = defaultdict(set)
for n in n7:
    s = n.get("utm_source") or (re.sub(r"^https?://([^/]+).*$", r"\1", n["referrer"]) if n.get("referrer") else "(priamo)")
    zdroj[s].add(n["session_id"] or n["id"])
    stranky[n["cesta"]].add(n["session_id"] or n["id"])
riadky.append(f"Poslednych 7 dni: {len({n['session_id'] or n['id'] for n in n7})} navstev, {len(n7)} zobrazeni")
riadky.append("Zdroje 7 dni: " + ", ".join(f"{k} {len(v)}" for k, v in sorted(zdroj.items(), key=lambda x: -len(x[1]))[:12]))
riadky.append("Stranky 7 dni: " + ", ".join(f"{k} {len(v)}" for k, v in sorted(stranky.items(), key=lambda x: -len(x[1]))[:15]))
ud = vsetky(lambda a, b: sb.table("udalosti").select("id,nazov").gte("created_at", od7).order("id").range(a, b).execute())
riadky.append("Udalosti 7 dni: " + ", ".join(f"{k} {v}" for k, v in Counter(u["nazov"] for u in ud).most_common()))
try:
    k = sb.rpc("onboarding_kandidati", {}).execute().data or []
    riadky.append(f"Novi pouzivatelia od 23. 10. (bez Mareka a demo): {len(k)}; s nastavenym vyberom {sum(1 for x in k if x.get('ma_vyber'))}; zaplatenych {sum(1 for x in k if x.get('zaplatene'))}")
except Exception as e:
    riadky.append(f"onboarding_kandidati zlyhalo: {type(e).__name__}")
odh = sb.table("oslovenie_firiem_kontakty").select("ico", count="exact").not_.is_("odhlasene_at", "null").limit(1).execute().count
ods = sb.table("oslovenie_firiem_odoslane").select("id", count="exact").eq("stav", "odoslane").limit(1).execute().count
riadky.append(f"Oslovenie firiem: odoslanych {ods}, odhlasenych firiem {odh}")
print("\n".join(riadky))
print("::notice title=Prehlad navstev::" + "%0A".join(riadky))
