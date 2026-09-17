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

# Vzor tu bol povodne "ajomn|oistn|ancelarskych" a test padal na 20 riadkoch
# "Dodavka kancelarskych potrieb". Nebola to chyba klasifikatora, ale chyba
# TESTU: kancelarske potreby su nas sektor TLAC_KANCELARIA, tie tam patria.
# Vyradit treba najom KANCELARSKYCH PRIESTOROV, nie dodavku potrieb — a to
# uz riesi slovo "najom". Vzor som preto zuzil na to, co vyradene byt musi,
# a pridal opacnu kontrolu, ze spravna zhoda sa nestratila.
falosne = df[df.subject.str.contains("ajomn|oistn", na=False)]
print(f"3) falosne zhody     : {len(falosne)} (ocakavane 0)")
assert len(falosne) == 0, falosne.subject.head().tolist()

potreby = df[df.subject.str.contains("ancelarskych potrieb", na=False)]
print(f"3b) kancelarske potreby: {len(potreby)} zaradenych "
      f"do {sorted(potreby.sector.unique()) if len(potreby) else '—'}")
assert len(potreby) > 0, "dodavka kancelarskych potrieb sa nesmie vyradit"

# ── 2. skorovanie ──
t = score.prilezitosti(df)
print(f"4) prilezitosti      : {len(t)} riadkov")
assert not t.empty
assert t.dni_do_konca.between(90, 180).all(), "okno predikcie nesedi"
assert t.skore.is_monotonic_decreasing, "vystup musi byt zoradeny"

# Zoznam stlpcov bol zastarany o cely rad zmien: chybali tu regiony
# (mesto, kraj), karta incumbenta (dodavatel_od, dodavatel_zmluv_celkom),
# priznak neuvedenej ceny a cely cenovy benchmark. Test teda padal aj vtedy,
# ked bolo vsetko v poriadku — a to je horsie nez ziadny test, pretoze
# to naucí clovka vysledok ignorovat.
ZAKLAD = {"contract_id","sector","cpv","authority_name","authority_cin","department",
 "subject","subject_description","effective_to","dni_do_konca","odhad_vyhlasenia",
 "price_total","supplier_name","top_dodavatel","podiel_top_dodavatela",
 "historicky_pocet","pocet_dodavatelov","riziko","skore","okres_kod",
 "mesto","kraj","dodavatel_od","dodavatel_zmluv_celkom","cena_neuvedena",
 "typicka_dlzka_dni","odkaz"}
# Pro stlpce, ktore score.rozdel_na_start_a_pro() odkroji do ceny_prilezitosti
PRO = {"porovnavacia_cena","zaklad","median_cena","odchylka_pct","vzoriek",
 "q1","q3","rozptyl","spolahlivy"}
# #13 (17.9.2026): Pro stlpce pre sanca_na_vyhru, odkrojene este PRED
# rozdel_na_start_a_pro() — viz score.rozdel_na_sancu(). `riziko` je uz
# v ZAKLAD (existujuci free stlpec), tu NIE JE duplicitne — rozdel_na_sancu()
# ho do sanca_na_vyhru len SKOPIRUJE, z verejnej tabulky ho neodoberá.
SANCA = {"supplier_cin", "top_dodavatel_cin", "top_dodavatel_pravnicky",
         "podiel_top_dodavatela_pravnicky"}
OPP = ZAKLAD | PRO | SANCA
chyba = OPP - set(t.columns)
navyse = set(t.columns) - OPP
print(f"5) stlpce opportunities: {len(t.columns)} | chybaju: {chyba or 'ziadne'} "
      f"| navyse: {navyse or 'ziadne'}")
assert not chyba, f"chybaju stlpce: {chyba}"
assert not navyse, f"nove stlpce, doplnte ich do schemy aj do testu: {navyse}"

# Rozdelenie na sancu (#13) musi byt PRVE — presne ako v main.py — inak by
# rozdel_na_start_a_pro() nevedelo o SANCA stlpcoch a necham ich unikat
# do verejnej tabulky (rovnaka diera, aka uz raz bola s cenovym benchmarkom).
t_bez_sance, sancaDf = score.rozdel_na_sancu(t)
unik_sanca_v_tabulke = SANCA & set(t_bez_sance.columns)
print(f"5a) po rozdel_na_sancu: {len(t_bez_sance.columns)} stlpcov v tabulke, "
      f"{len(sancaDf)} riadkov v sanca_na_vyhru | SANCA stlpce v tabulke: "
      f"{unik_sanca_v_tabulke or 'ziadne'}")
assert not unik_sanca_v_tabulke, (
    f"SANCA stlpce neboli odstranene z tabulky: {unik_sanca_v_tabulke}")
assert "riziko" in t_bez_sance.columns, (
    "riziko je FREE stlpec, rozdel_na_sancu ho nesmie odobrat z tabulky")
assert SANCA <= set(sancaDf.columns), "sanca_na_vyhru nema vsetky ocakavane stlpce"

# Rozdelenie na Start a Pro musi Pro stlpce z verejnej tabulky odobrat.
# Prave tato diera raz uz bola: Pro data sa dali vytiahnut cez ?select=*.
# POZOR: vstupom je uz t_bez_sance (po odkrojeni #13), presne ako v main.py.
startDf, proDf = score.rozdel_na_start_a_pro(t_bez_sance)
unik = PRO & set(startDf.columns) - {"contract_id"}
unik_sanca = SANCA & set(startDf.columns)
print(f"5b) Start vrstva: {len(startDf.columns)} stlpcov | "
      f"Pro stlpce v nej: {unik or 'ziadne'} | Sanca stlpce v nej: "
      f"{unik_sanca or 'ziadne'}")
assert not unik, f"Pro stlpce presakuju do verejnej vrstvy: {unik}"
assert not unik_sanca, f"Sanca stlpce presakuju do verejnej vrstvy: {unik_sanca}"

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
