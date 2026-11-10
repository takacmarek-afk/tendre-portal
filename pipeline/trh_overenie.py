"""Overenie trhu firmy z /kontrola na par IČO (len pocty, verejne udaje z CRZ)."""
import json
import os
from supabase import create_client

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
ica = ["36177083", "36034762", "31411801", "35697270"]
riadky = []
for ico in ica:
    try:
        d = sb.rpc("kontrola_zmluv_ico", {"p_ico": ico}).execute().data or {}
        riadky.append(f"{ico}: do12m {d.get('pocet_do_12_mesiacov')} | trh {json.dumps(d.get('trh'), ensure_ascii=False)}")
    except Exception as e:
        riadky.append(f"{ico}: CHYBA {type(e).__name__} {str(e)[:120]}")
print("\n".join(riadky))
print("::notice title=Trh::" + "%0A".join(riadky))
