"""Citanie a zapis do Supabase.

Ide cez REST API so service_role klucom, nie priamym pripojenim na Postgres.
Dovod: nepotrebujeme heslo k databaze ani riesit IPv6, ktore Supabase
pri priamom pripojeni vyzaduje a GitHub Actions ho nemaju.

service_role kluc obchadza Row Level Security. Preto zije VYHRADNE
v GitHub Secrets a nikdy sa nedostane do prehliadaca.
"""
import os
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
    takze ich su jednotky tisic, nie miliony."""
    stlpce = ("id, authority_name, authority_cin, supplier_name, supplier_cin, "
              "subject, subject_description, effective_to, price_total, "
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

def nahrad_opportunities(sb, df: pd.DataFrame):
    """Prilezitosti su klzave okno, prepocitavaju sa cele. Preto zmazat a vlozit
    je spravnejsie nez upsert — inak by tam zostavali stare zaznamy mimo okna."""
    sb.table("opportunities").delete().neq("contract_id", -1).execute()
    if df.empty:
        return 0

    zaznamy = df.where(pd.notna(df), None).to_dict("records")
    for z in zaznamy:
        for k, v in list(z.items()):
            if hasattr(v, "item"):          # numpy typy REST nezje
                z[k] = v.item()
            elif isinstance(v, pd.Timestamp):
                z[k] = v.strftime("%Y-%m-%d")

    for i in range(0, len(zaznamy), DAVKA):
        sb.table("opportunities").insert(zaznamy[i:i + DAVKA]).execute()
    return len(zaznamy)
