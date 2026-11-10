"""Parovanie obstaravani z eurofondov (itms_vo) s vyhlasenymi sutazami vo Vestniku (uvo_vyzvy).

Obstaravanie v ITMS "Pripravované" je zakazka, ktoru urad este nevyhlasil. Ked ju
vyhlasi, objavi sa vo Vestniku pod tym istym ICO obstaravatela. ITMS stav meni
s oneskorenim (alebo vobec), preto parujeme sami: rovnake ICO, sutaz zverejnena
po zalozeni v ITMS a podobny nazov (alebo hodnota).

Pouzitie: `paruj(itms, vyzvy)` (cista funkcia, testy) a `--analyza` (len citanie,
pocty a vzorka verejnych nazvov do logu).
"""
import re
import sys
import unicodedata
from collections import Counter, defaultdict

PRAH = 0.5
_STOP = {"a", "na", "v", "vo", "pre", "s", "so", "z", "zo", "k", "do", "o", "pri", "od", "obce", "obec", "mesta",
         "mesto", "stavebne", "prace", "praca", "dodavka", "dodanie", "zakazka", "cast", "projekt", "projektu",
         "c", "ii", "i", "iii", "sk", "the", "and", "-", "–"}


def _norm(t):
    t = unicodedata.normalize("NFKD", str(t or "").lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def tokeny(t):
    return {w for w in re.findall(r"[a-z0-9]{3,}", _norm(t)) if w not in _STOP}


def ico_kluc(ico):
    return re.sub(r"\D", "", str(ico or "")).lstrip("0")


def podobnost(itms, vyzva):
    """0..1: zhoda nazvu (podiel slov ITMS nazvu, ktore su vo vyzve) + bonus za hodnotu."""
    a = tokeny(itms.get("nazov"))
    b = tokeny(" ".join(filter(None, [vyzva.get("nazov"), vyzva.get("cast_nazov")])))
    if not a or not b:
        s = 0.0
    else:
        s = len(a & b) / min(len(a), len(b))
    h1, h2 = float(itms.get("predpokladana_hodnota") or 0), float(vyzva.get("predpokladana_hodnota") or 0)
    if h1 > 0 and h2 > 0 and 0.75 <= h2 / h1 <= 1.33:
        s += 0.25
    return min(s, 1.0)


def paruj(itms, vyzvy, prah=PRAH):
    """-> [(itms_row, vyzva_row, skore)] najlepsia vyzva pre kazde ITMS obstaravanie.
    Vyzva musi byt zverejnena po zalozeni obstaravania v ITMS (alebo najviac 30 dni pred)."""
    podla_ico = defaultdict(list)
    for v in vyzvy:
        if v.get("typ") == "sutaz" and ico_kluc(v.get("obstaravatel_ico")):
            podla_ico[ico_kluc(v["obstaravatel_ico"])].append(v)
    out = []
    for r in itms:
        kand = podla_ico.get(ico_kluc(r.get("obstaravatel_ico")), [])
        zal = str(r.get("itms_created_at") or "")[:10]
        naj, naj_s = None, 0.0
        for v in kand:
            pub = str(v.get("publikovane") or "")[:10]
            if zal and pub and pub < _minus30(zal):
                continue
            s = podobnost(r, v)
            if s > naj_s:
                naj, naj_s = v, s
        if naj and naj_s >= prah:
            out.append((r, naj, round(naj_s, 2)))
    return out


def _minus30(iso):
    from datetime import date, timedelta
    try:
        return (date.fromisoformat(iso) - timedelta(days=30)).isoformat()
    except ValueError:
        return "0000"


def analyza():
    import os
    from supabase import create_client
    from strankuj import vsetky
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
    itms = vsetky(lambda a, b: sb.table("itms_vo").select(
        "id,nazov,stav,obstaravatel_ico,obstaravatel_nazov,predpokladana_hodnota,itms_created_at,itms_updated_at,sektor,kraj")
        .order("id").range(a, b).execute())
    vyzvy = vsetky(lambda a, b: sb.table("uvo_vyzvy").select(
        "oznamenie_id,typ,obstaravatel_ico,nazov,cast_nazov,predpokladana_hodnota,publikovane,lehota_ponuk,url")
        .order("id").range(a, b).execute())
    print(f"ITMS {len(itms)}, vyzvy vo Vestniku {len(vyzvy)} "
          f"(od {min(str(v.get('publikovane')) for v in vyzvy)} do {max(str(v.get('publikovane')) for v in vyzvy)})")
    print("ITMS stavy:", dict(Counter(r.get("stav") for r in itms).most_common()))
    ico_v = {ico_kluc(v.get("obstaravatel_ico")) for v in vyzvy if v.get("typ") == "sutaz"}
    print("ITMS s obstaravatelom, ktory ma vo Vestniku aspon 1 sutaz:",
          dict(Counter(r.get("stav") for r in itms if ico_kluc(r.get("obstaravatel_ico")) in ico_v)))
    for prah in (0.4, 0.5, 0.6, 0.75):
        p = paruj(itms, vyzvy, prah)
        print(f"prah {prah}: sparovanych {len(p)}, podla stavu {dict(Counter(r.get('stav') for r, _, _ in p))}")
    p = paruj(itms, vyzvy, PRAH)
    print("\nVZORKA (stav | skore | ITMS nazov || Vestnik nazov):")
    for r, v, s in sorted(p, key=lambda x: x[2])[:: max(1, len(p) // 30)][:30]:
        print(f"{r.get('stav')[:12]:12} | {s} | {str(r.get('nazov'))[:70]} || {str(v.get('nazov'))[:70]}")
    prip = [x for x in p if x[0].get("stav") == "Pripravované"]
    print(f"\n'Pripravované' v ITMS, ale uz vyhlasene vo Vestniku: {len(prip)}")
    for r, v, s in prip[:15]:
        print(f"  {s} | {str(r.get('nazov'))[:60]} || {str(v.get('nazov'))[:60]} | {v.get('publikovane')}")
    return 0


if __name__ == "__main__":
    if "--analyza" in sys.argv or len(sys.argv) == 1:
        sys.exit(analyza())
