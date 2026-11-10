"""Kolko novych sutazi z Vestnika UVO by islo do bezplatneho tyzdenneho prehladu (len pocty)."""
import os
from collections import Counter
from datetime import date, timedelta
from supabase import create_client
from strankuj import vsetky

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
d = date.today()
r = vsetky(lambda a, b: sb.table("uvo_vyzvy").select("sektor,nuts,lehota_ponuk,publikovane,typ")
           .eq("typ", "sutaz").gte("publikovane", (d - timedelta(days=8)).isoformat()).order("id").range(a, b).execute())
ok = [x for x in r if (x.get("lehota_ponuk") or "") >= (d + timedelta(days=3)).isoformat()]
riadky = [f"Sutazi za 8 dni: {len(r)}, s lehotou aspon 3 dni: {len(ok)}, bez sektora {sum(1 for x in ok if not x.get('sektor'))}, bez NUTS {sum(1 for x in ok if not x.get('nuts'))}",
          "Podla sektora: " + ", ".join(f"{k} {v}" for k, v in Counter(x.get('sektor') for x in ok).most_common(20)),
          "Podla kraja (NUTS3): " + ", ".join(f"{k} {v}" for k, v in Counter((x.get('nuts') or '')[:5] for x in ok).most_common(10)),
          "Najnovsie publikovane: " + max((x.get("publikovane") or "" for x in r), default="-")]
print("\n".join(riadky))
print("::notice title=Vyzvy::" + "%0A".join(riadky))
