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


# ── Lievik za 7 dni (9. 11. 2026): kde ludia odpadavaju ─────────────────────
def pocet(tabulka, filtre, stlpec="*"):
    try:
        return filtre(sb.table(tabulka).select(stlpec, count="exact")).limit(1).execute().count or 0
    except Exception as e:   # tabulka/stlpec v starsej DB chyba -> lievik nespadne cely
        return f"? ({type(e).__name__})"


z_emailu = len({n["session_id"] or n["id"] for n in n7 if n.get("utm_source") == "email"})
kontrola = len({n["session_id"] or n["id"] for n in n7 if (n.get("cesta") or "").startswith("/kontrola")})
seo = len({n["session_id"] or n["id"] for n in n7 if (n.get("cesta") or "").startswith("/konciace-zmluvy")})
lievik = [
    ("e-maily odoslane", pocet("oslovenie_firiem_odoslane", lambda q: q.eq("stav", "odoslane").gte("odoslane_at", od7), "id")),
    ("navstevy z e-mailu", z_emailu),
    ("navstevy /konciace-zmluvy", seo),
    ("navstevy /kontrola", kontrola),
    ("nove firmy (skuska)", pocet("events", lambda q: q.eq("typ", "org_vytvorena").gte("created_at", od7))),
    ("kolegovia pripojeni", pocet("events", lambda q: q.eq("typ", "kolega_pripojeny_domenou").gte("created_at", od7))),
    ("vyber nastaveny/zmeneny", pocet("nastavenia_pouzivatela", lambda q: q.gte("upravene_at", od7), "user_id")),
    ("platba zacata", pocet("platby", lambda q: q.gte("created_at", od7), "reference")),
    ("platba zaplatena", pocet("platby", lambda q: q.eq("stav", "zaplatena").gte("created_at", od7), "reference")),
]
riadky.append("LIEVIK 7 dni: " + " → ".join(f"{k} {v}" for k, v in lievik))
riadky.append(f"Zaplatenych platieb spolu: {pocet('platby', lambda q: q.eq('stav', 'zaplatena'), 'reference')}")
print("\n".join(riadky))
print("::notice title=Prehlad navstev::" + "%0A".join(riadky))
