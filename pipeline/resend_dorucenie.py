"""Dorucitelnost e-mailov cez Resend za 30 dni (audit 11. 11. 2026). LEN CITANIE.

Vypise pocty podla posledneho stavu (delivered, bounced, complained, ...) a podla
typu e-mailu (predmet bez osobnych udajov). Ziadne adresy (logy su verejne).

    RESEND_ADMIN_KEY=... python resend_dorucenie.py
"""
import os
import re
from collections import Counter
from datetime import datetime, timedelta, timezone

import requests

from limit_emailov import MAX_STRAN, _cas


def typ(predmet):
    """Predmet -> typ bez mien a cisel (napr. 'PredTendrom.sk — N nových príležitostí')."""
    p = re.sub(r"\d[\d\s.,]*", "N ", str(predmet or ""))
    p = re.sub(r"\S+@\S+", "@", p)
    return p[:60].strip()


def main():
    kluc = os.environ["RESEND_ADMIN_KEY"]
    od = datetime.now(timezone.utc) - timedelta(days=30)
    stavy, typy, zle = Counter(), Counter(), Counter()
    po = None
    for _ in range(MAX_STRAN):
        params = {"limit": 100, **({"after": po} if po else {})}
        r = requests.get("https://api.resend.com/emails", params=params, timeout=30,
                         headers={"Authorization": f"Bearer {kluc}"})
        r.raise_for_status()
        d = r.json()
        data = d.get("data") or []
        koniec = False
        for e in data:
            c = _cas(e["created_at"])
            if (c.tzinfo and c < od) or (not c.tzinfo and c.replace(tzinfo=timezone.utc) < od):
                koniec = True
                break
            s = e.get("last_event") or "?"
            t = typ(e.get("subject"))
            stavy[s] += 1
            typy[(t, s)] += 1
            if s not in ("delivered", "opened", "clicked", "sent", "scheduled"):
                zle[t] += 1
        if koniec or not d.get("has_more") or not data:
            break
        po = data[-1]["id"]
    print("== Stav za 30 dni:", dict(stavy.most_common()))
    print("== Podla typu a stavu:")
    for (t, s), n in sorted(typy.items(), key=lambda x: -x[1])[:40]:
        print(f"{n:5d}  {s:12s} {t}")
    if zle:
        print("== Problemove typy:", dict(zle.most_common()))


if __name__ == "__main__":
    main()
