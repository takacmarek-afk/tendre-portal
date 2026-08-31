"""Klient na CRZ sync API.

Strankovanie ide cez hlavicku `Link: <url>; rel='next'`.
Limit je 60 poziadaviek/min na IP bez autentifikacie, riadime sa hlavickou
X-RateLimit-Remaining. Klasifikujeme priebezne a dalej posielame len zhody,
takze pamat nenarasta ani pri stotisicoch zaznamov.
"""
import re
import time
import logging

import requests

from config import CRZ_SYNC_URL, USER_AGENT
from classify import klasifikuj

log = logging.getLogger("crz")

LINK_NEXT = re.compile(r"<([^>]+)>\s*;\s*rel=['\"]?next['\"]?")


def _next_url(link_header: str):
    if not link_header:
        return None
    m = LINK_NEXT.search(link_header)
    return m.group(1) if m else None


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _date(v):
    return str(v)[:10] if v else None


def _riadok(z, sector, score):
    """Prevedie zaznam z API na dict so stlpcami tabulky contracts."""
    dep = z.get("department") or {}
    return {
        "id": z.get("id"),
        "contract_identifier": z.get("contract_identifier"),
        "authority_name": z.get("contracting_authority_name"),
        "authority_cin": str(z.get("contracting_authority_cin") or "").strip() or None,
        "authority_address": z.get("contracting_authority_formatted_address"),
        "supplier_name": z.get("supplier_name"),
        "supplier_cin": str(z.get("supplier_cin") or "").strip() or None,
        "subject": z.get("subject"),
        "subject_description": z.get("subject_description"),
        "signed_on": _date(z.get("signed_on")),
        "effective_from": _date(z.get("effective_from")),
        "effective_to": _date(z.get("effective_to")),
        "effective_note": z.get("effective_note"),
        "price": _num(z.get("contract_price_amount")),
        "price_total": _num(z.get("contract_price_total_amount")),
        "status_id": z.get("status_id"),
        "type_id": z.get("type_id"),
        "published_at": z.get("published_at"),
        "procurement_url": z.get("procurement_url"),
        "department": dep.get("name") if isinstance(dep, dict) else None,
        "sector": sector,
        "class_score": score,
        "src_updated_at": z.get("updated_at") or z.get("changed_at"),
    }


def sync(since: str, on_batch, time_budget_s: int):
    """Stahuje od `since`, po kazdej strane vola on_batch(riadky, checkpoint).

    Vracia (stiahnutych, zaradenych, checkpoint, dokoncene).
    `dokoncene=False` znamena, ze sa minul casovy rozpocet a dalsi beh
    plynulo nadviaze na ulozenom checkpointe.
    """
    url, params = CRZ_SYNC_URL, {"since": since}
    headers = {"User-Agent": USER_AGENT}
    session = requests.Session()

    t0 = time.time()
    fetched = kept = page = chyby = 0
    checkpoint = since

    while url:
        if time.time() - t0 > time_budget_s:
            log.warning("Casovy rozpocet vycerpany na checkpointe %s", checkpoint)
            return fetched, kept, checkpoint, False

        try:
            r = session.get(url, params=params, headers=headers, timeout=60)
        except requests.RequestException as e:
            chyby += 1
            if chyby > 5:
                log.error("Prilis vela sietovych chyb: %s", e)
                return fetched, kept, checkpoint, False
            log.warning("Sietova chyba (%s/5): %s — cakam 15 s", chyby, e)
            time.sleep(15)
            continue

        if r.status_code == 429:
            log.warning("Rate limit, cakam 60 s")
            time.sleep(60)
            continue
        if r.status_code >= 500:
            chyby += 1
            if chyby > 5:
                log.error("Server opakovane zlyhava (%s)", r.status_code)
                return fetched, kept, checkpoint, False
            time.sleep(20)
            continue
        if r.status_code != 200:
            log.error("HTTP %s: %s", r.status_code, r.text[:300])
            return fetched, kept, checkpoint, False

        chyby = 0
        params = None

        try:
            data = r.json()
        except ValueError:
            log.error("Odpoved nie je JSON: %s", r.text[:300])
            return fetched, kept, checkpoint, False

        batch = data if isinstance(data, list) else data.get("data") or data.get("items") or []
        if not batch:
            break

        riadky = []
        for z in batch:
            if not isinstance(z, dict) or z.get("id") is None:
                continue
            sector, score = klasifikuj(z.get("subject"), z.get("subject_description"))
            if sector:
                riadky.append(_riadok(z, sector, score))

        fetched += len(batch)
        kept += len(riadky)
        page += 1

        last = batch[-1]
        checkpoint = last.get("updated_at") or last.get("changed_at") or checkpoint
        on_batch(riadky, checkpoint)

        if page % 25 == 0:
            log.info("strana %s | stiahnute %s | zaradene %s | %s",
                     page, fetched, kept, checkpoint)

        zvysok = r.headers.get("X-RateLimit-Remaining")
        if zvysok is not None and zvysok.isdigit() and int(zvysok) <= 2:
            time.sleep(20)
        else:
            time.sleep(1.05)

        url = _next_url(r.headers.get("Link", ""))

    return fetched, kept, checkpoint, True
