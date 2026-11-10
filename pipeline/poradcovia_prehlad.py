"""Prehlad grantovych poradcov (sprostredkovatelia) pre cielene oslovenie.

Len suhrnne pocty a nazvy firiem (verejne udaje z CRZ), ziadne e-maily.
"""
import os
from supabase import create_client
from strankuj import vsetky


def ico8(x):
    d = "".join(ch for ch in str(x or "") if ch.isdigit())
    return d.zfill(8) if d else ""


sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
por = vsetky(lambda a, b: sb.table("sprostredkovatelia").select("kluc,sprostredkovatel,supplier_cin,obci,zmluv,kraje,posledna_zmluva")
             .order("kluc").range(a, b).execute())
kont = vsetky(lambda a, b: sb.table("oslovenie_firiem_kontakty").select("ico,stav,segment").order("ico").range(a, b).execute())
ods = vsetky(lambda a, b: sb.table("oslovenie_firiem_odoslane").select("ico").order("ico").range(a, b).execute())
org = {ico8(r["ico"]) for r in sb.table("organizations").select("ico").execute().data if r.get("ico")}
k_ok = {ico8(k["ico"]): k for k in kont if k["stav"] == "ok"}
oslov = {ico8(o["ico"]) for o in ods}
riadky = []
for prah in (1, 2, 3, 5, 10):
    v = [p for p in por if (p.get("obci") or 0) >= prah]
    s_ico = [p for p in v if ico8(p.get("supplier_cin"))]
    s_mail = [p for p in s_ico if ico8(p["supplier_cin"]) in k_ok]
    riadky.append(f"obci>={prah}: poradcov {len(v)}, s ICO {len(s_ico)}, s e-mailom z Vestnika {len(s_mail)}, "
                  f"uz osloveni {sum(1 for p in s_mail if ico8(p['supplier_cin']) in oslov)}, maju ucet {sum(1 for p in s_ico if ico8(p['supplier_cin']) in org)}")
top = sorted(por, key=lambda p: -(p.get("obci") or 0))[:15]
riadky.append("TOP 15 (obci/zmluv/e-mail?): " + "; ".join(
    f"{p['sprostredkovatel'][:40]} {p.get('obci')}/{p.get('zmluv')}/{'ano' if ico8(p.get('supplier_cin')) in k_ok else 'nie'}" for p in top))
print("\n".join(riadky))
print("::notice title=Poradcovia::" + "%0A".join(riadky))
