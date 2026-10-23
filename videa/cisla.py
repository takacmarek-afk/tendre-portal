"""Cisla pre prispevky na FB/IG (firmy aj obce). Len agregaty a verejne udaje o uradoch.

    python videa/cisla.py vystup/cisla/cisla.json
"""
import json
import os
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))
from strankuj import vsetky  # noqa: E402
from supabase import create_client  # noqa: E402


def main(cesta):
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
    dnes = date.today()
    do = (dnes + timedelta(days=365)).isoformat()
    opp = vsetky(lambda a, b: sb.table("opportunities")
                 .select("contract_id,sector,kraj,authority_name,subject,price_total,effective_to,cena_neuvedena,odkaz")
                 .gte("effective_to", dnes.isoformat()).lte("effective_to", do)
                 .order("contract_id").range(a, b).execute())
    sektory = defaultdict(list)
    for o in opp:
        sektory[o["sector"]].append(o)
    vysl = {"stav_k": dnes.isoformat(), "zmluv_spolu": len(opp),
            "uradov_spolu": len({o["authority_name"] for o in opp}), "sektory": {}}
    for s, rr in sorted(sektory.items(), key=lambda x: -len(x[1])):
        ceny = [float(o["price_total"]) for o in rr if o.get("price_total") and not o.get("cena_neuvedena")]
        vysl["sektory"][s] = {
            "zmluv": len(rr), "uradov": len({o["authority_name"] for o in rr}),
            "median": round(statistics.median(ceny)) if ceny else None,
            "kraje": dict(Counter(o["kraj"] for o in rr if o.get("kraj")).most_common()),
            "do_90_dni": sum(1 for o in rr if o["effective_to"] <= (dnes + timedelta(days=90)).isoformat()),
        }

    def naj(od, do_, sektor=None):
        kand = [o for o in opp if od <= o["effective_to"] <= do_ and o.get("price_total")
                and not o.get("cena_neuvedena") and (sektor is None or o["sector"] == sektor)]
        kand.sort(key=lambda o: -float(o["price_total"]))
        return [{k: o.get(k) for k in ("authority_name", "subject", "price_total", "effective_to", "sector", "kraj", "odkaz")}
                for o in kand[:5]]
    vysl["najvacsie_6_12_mes"] = {s: naj((dnes + timedelta(days=180)).isoformat(), do, s)
                                  for s in ("UPRATOVANIE", "OSTRAHA", "STRAVOVANIE", "ZELEN_ZIMNA_UDRZBA")}
    vysl["najvacsie_1_3_mes"] = naj((dnes + timedelta(days=30)).isoformat(), (dnes + timedelta(days=90)).isoformat())

    # ── obce ──
    prog = sb.table("aktivne_programy").select("*").order("obci_90d", desc=True).limit(15).execute().data
    vysl["obce_programy"] = prog
    vyz = sb.table("vyzvy").select("nazov,poskytovatel,uzavretie,pre_obce,url").eq("pre_obce", True) \
        .gte("uzavretie", dnes.isoformat()).order("uzavretie").limit(40).execute().data
    vysl["obce_vyzvy_otvorene"] = vyz
    vysl["obce_vyzvy_pocet"] = len(vyz)
    vysl["obci_v_registri"] = sb.table("obce_register").select("kod", count="exact").limit(1).execute().count
    sub = vsetky(lambda a, b: sb.table("subsidies").select("contract_id,poskytovatel,suma,podpisane,kraj")
                 .gte("podpisane", (dnes - timedelta(days=365)).isoformat()).order("contract_id").range(a, b).execute())
    vysl["dotacie_12m"] = {"zmluv": len(sub), "objem": round(sum(float(x["suma"] or 0) for x in sub)),
                           "poskytovatelia": Counter(x["poskytovatel"] for x in sub).most_common(10),
                           "kraje": dict(Counter(x["kraj"] for x in sub if x.get("kraj")).most_common())}
    Path(cesta).parent.mkdir(parents=True, exist_ok=True)
    Path(cesta).write_text(json.dumps(vysl, ensure_ascii=False, indent=1, default=str))
    print("Cisla ulozene:", len(opp), "zmluv,", len(sub), "dotacii")


if __name__ == "__main__":
    main(sys.argv[1])
