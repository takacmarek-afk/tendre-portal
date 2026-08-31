import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mock_crz import start
start()

import config
config.CRZ_SYNC_URL = "http://127.0.0.1:8899/sync"
import crz, score
crz.CRZ_SYNC_URL = config.CRZ_SYNC_URL
crz.time.sleep = lambda *_: None
import pandas as pd

# ── 1. sync + klasifikacia ──
riadky = []
crz.sync("2022-01-01T00:00:00Z", lambda r, cp: riadky.extend(r), 120)
print(f"1) sync+klasifikacia : {len(riadky)} zaradenych zaznamov")
assert riadky

# stlpce musia presne sediet so schemou v Postgrese
SCHEMA = {"id","contract_identifier","authority_name","authority_cin","authority_address",
 "supplier_name","supplier_cin","subject","subject_description","signed_on","effective_from",
 "effective_to","effective_note","price","price_total","status_id","type_id","published_at",
 "procurement_url","department","sector","class_score","src_updated_at"}
navyse = set(riadky[0]) - SCHEMA
print(f"2) stlpce contracts  : {len(riadky[0])} | navyse oproti scheme: {navyse or 'ziadne'}")
assert not navyse, navyse

df = pd.DataFrame(riadky)
falosne = df[df.subject.str.contains("ajomn|oistn|ancelarskych", na=False)]
print(f"3) falosne zhody     : {len(falosne)} (ocakavane 0)")
assert len(falosne) == 0

# ── 2. skorovanie ──
t = score.prilezitosti(df)
print(f"4) prilezitosti      : {len(t)} riadkov")
assert not t.empty
assert t.dni_do_konca.between(90, 180).all(), "okno predikcie nesedi"
assert t.skore.is_monotonic_decreasing, "vystup musi byt zoradeny"

OPP = {"contract_id","sector","cpv","authority_name","authority_cin","department","subject",
 "subject_description","effective_to","dni_do_konca","odhad_vyhlasenia","price_total",
 "supplier_name","top_dodavatel","podiel_top_dodavatela","historicky_pocet",
 "pocet_dodavatelov","riziko","skore","okres_kod"}
print(f"5) stlpce opportunities: {len(t.columns)} | navyse: {set(t.columns)-OPP or 'ziadne'}")
assert set(t.columns) == OPP

# ── 3. serializacia pre REST (numpy typy JSON nezje) ──
import json
zaznamy = t.where(pd.notna(t), None).to_dict("records")
for z in zaznamy:
    for k, v in list(z.items()):
        if hasattr(v, "item"): z[k] = v.item()
        elif isinstance(v, pd.Timestamp): z[k] = v.strftime("%Y-%m-%d")
try:
    json.dumps(zaznamy)
    print(f"6) JSON serializacia : OK ({len(zaznamy)} zaznamov)")
except TypeError as e:
    print(f"6) JSON serializacia : ZLYHALA — {e}"); raise

print(f"7) riziko/skore      : {t.riziko.value_counts().to_dict()} | skore {t.skore.min()}-{t.skore.max()}")
print("\nVSETKY KONTROLY PRESLI")
