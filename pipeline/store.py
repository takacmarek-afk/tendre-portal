"""Citanie a zapis do Supabase.

Ide cez REST API so service_role klucom, nie priamym pripojenim na Postgres.
Dovod: nepotrebujeme heslo k databaze ani riesit IPv6, ktore Supabase
pri priamom pripojeni vyzaduje a GitHub Actions ho nemaju.

service_role kluc obchadza Row Level Security. Preto zije VYHRADNE
v GitHub Secrets a nikdy sa nedostane do prehliadaca.
"""
import os
import math
import logging

import pandas as pd
from supabase import create_client

log = logging.getLogger("store")

DAVKA = 500          # kolko riadkov naraz posielame
STRANA = 1000        # kolko riadkov naraz citame


def klient():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise SystemExit(
            "Chybaju premenne SUPABASE_URL alebo SUPABASE_SERVICE_ROLE_KEY. "
            "Nastav ich v GitHub Secrets."
        )
    return create_client(url, key)


# ── checkpoint synchronizacie ──────────────────────────────────────────────

def get_meta(sb, key, default=None):
    r = sb.table("pipeline_meta").select("value").eq("key", key).execute()
    return r.data[0]["value"] if r.data else default


def set_meta(sb, key, value):
    sb.table("pipeline_meta").upsert(
        {"key": key, "value": str(value), "updated_at": "now()"},
        on_conflict="key",
    ).execute()


# ── zmluvy ─────────────────────────────────────────────────────────────────

def upsert_contracts(sb, rows):
    """rows = zoznam dictov so stlpcami tabulky contracts."""
    if not rows:
        return 0
    ulozene = 0
    for i in range(0, len(rows), DAVKA):
        kus = rows[i:i + DAVKA]
        sb.table("contracts").upsert(kus, on_conflict="id").execute()
        ulozene += len(kus)
    return ulozene


def nacitaj_contracts(sb) -> pd.DataFrame:
    """Stiahne vsetky ulozene zmluvy. Su to len zaznamy zaradene do sektorov,
    takze ich su desiatky tisic, nie miliony.

    POZOR NA ZOZNAM STLPCOV: co tu nie je, to sa v prepocte tvari ako prazdne
    a filtre to potichu vyhodia. Chybajuce `signed_on` a `effective_from` nam
    uz raz spravili prazdnu tabulku dotacii s vysledkom "dotacie=0" bez jedinej
    chybovej hlasky. Ked pridas do prepoctu novy stlpec, pridaj ho aj sem.
    """
    stlpce = ("id, authority_name, authority_cin, authority_address, "
              "supplier_name, supplier_cin, "
              "subject, subject_description, signed_on, effective_from, "
              "effective_to, price, price_total, "
              "status_id, sector, class_score, department, contract_identifier, "
              "procurement_url")
    vsetko, od = [], 0
    while True:
        r = (sb.table("contracts").select(stlpce)
               .order("id").range(od, od + STRANA - 1).execute())
        if not r.data:
            break
        vsetko.extend(r.data)
        if len(r.data) < STRANA:
            break
        od += STRANA
    log.info("Nacitanych %s zmluv z databazy", len(vsetko))
    return pd.DataFrame(vsetko)


def pocet_contracts(sb) -> int:
    r = sb.table("contracts").select("id", count="exact", head=True).execute()
    return r.count or 0


# ── prilezitosti ───────────────────────────────────────────────────────────

def _hodnota(v):
    """Prevedie jednu hodnotu z pandas na nieco, co znesie JSON.

    Pozor na pascu: `df.where(pd.notna(df), None)` vyzera, ze prazdne hodnoty
    zmeni na None, ale v ciselnom stlpci ich pandas potichu prevedie spat na
    NaN. A NaN ani nekonecno sa do JSON zapisat neda — REST zahlasi
    "Out of range float values are not JSON compliant" a cely beh spadne.
    Preto sa kazda hodnota kontroluje jednotlivo.
    """
    if v is None:
        return None
    try:
        if pd.isna(v):          # zachyti NaN, NaT aj pd.NA
            return None
    except (TypeError, ValueError):
        pass                    # zoznamy a slovniky pd.isna nezvlada, to nevadi

    if isinstance(v, pd.Timestamp):
        return v.strftime("%Y-%m-%d")
    if hasattr(v, "item"):      # numpy int64/float64 -> obycajny Python typ
        v = v.item()
    if isinstance(v, float) and not math.isfinite(v):
        return None
    return v


def _nahrad_tabulku(sb, tabulka: str, df: pd.DataFrame, kluc: str = "contract_id"):
    """Zmaze obsah a vlozi novy. Pouziva sa pre odvodene tabulky, ktore su
    klzavym oknom — upsert by v nich nechaval stare zaznamy mimo okna.

    PostgREST nepovoli DELETE bez podmienky, preto tu je `neq`. Podmienka
    musi sedet na stlpec, ktory tabulka naozaj MA — `dodavatelia` a
    `ceny_sektor` nemaju contract_id, ich klucom je ICO resp. nazov sektora.
    """
    if kluc == "contract_id":
        sb.table(tabulka).delete().neq(kluc, -1).execute()
    else:
        sb.table(tabulka).delete().neq(kluc, "__nikdy__").execute()

    if df is None or df.empty:
        return 0

    zaznamy = [
        {k: _hodnota(v) for k, v in riadok.items()}
        for riadok in df.to_dict("records")
    ]

    for i in range(0, len(zaznamy), DAVKA):
        sb.table(tabulka).insert(zaznamy[i:i + DAVKA]).execute()
    return len(zaznamy)


def nahrad_opportunities(sb, df: pd.DataFrame):
    return _nahrad_tabulku(sb, "opportunities", df)


def nahrad_subsidies(sb, df: pd.DataFrame):
    return _nahrad_tabulku(sb, "subsidies", df)


# Stlpce, ktore tabulka `dodavatelia` naozaj ma. Analytika pocita aj
# `zmluv_v_historii` a podobne pomocne veci — tie by REST odmietol.
STLPCE_DODAVATELIA = (
    "supplier_cin", "dodavatel", "hlavny_sektor", "zmluv", "objem_eur",
    "priemerna_zmluva_eur", "uradov", "sektorov", "zmluv_s_navysenim",
    "podiel_zmluv_s_navysenim", "priemerne_navysenie_pct",
    "prva_zmluva", "posledna_zmluva",
)


def nahrad_dodavatelia(sb, df: pd.DataFrame, limit: int = 5000):
    """Profily dodavatelov. Limit je tam kvoli 500 MB na Supabase free —
    dodavatelov s troma a viac zmluvami su desiatky tisic a chvost s malym
    objemom nikoho nezaujima. df prichadza usporadany podla objemu."""
    if df is None or df.empty:
        return _nahrad_tabulku(sb, "dodavatelia", df, kluc="supplier_cin")
    d = df.head(limit).copy()
    d = d[[c for c in STLPCE_DODAVATELIA if c in d.columns]]
    for stlpec in ("zmluv", "uradov", "sektorov", "zmluv_s_navysenim"):
        if stlpec in d.columns:
            d[stlpec] = pd.to_numeric(d[stlpec], errors="coerce").astype("Int64")
    return _nahrad_tabulku(sb, "dodavatelia", d, kluc="supplier_cin")


def nahrad_ceny_sektor(sb, df: pd.DataFrame):
    """Medianne mesacne ceny per sektor."""
    if df is None or df.empty:
        return _nahrad_tabulku(sb, "ceny_sektor", df, kluc="sector")
    d = df[["sector", "median_mesacna", "vzoriek"]].copy()
    d["vzoriek"] = pd.to_numeric(d["vzoriek"], errors="coerce").astype("Int64")
    return _nahrad_tabulku(sb, "ceny_sektor", d, kluc="sector")
