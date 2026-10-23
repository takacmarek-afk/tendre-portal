"""Pripravi ukazkovy ucet pre nahravanie videi a vytvori jednorazovy prihlasovaci odkaz.

Ucet: demo@predtendrom.sk, firma "Ukážková firma s.r.o." (bez ICO), plan Growth,
Moj vyber Bratislavsky kraj + upratovanie. Ucet nema heslo; prihlasuje sa len
jednorazovym odkazom, ktory skript zapise do suboru (nikdy nie do logu, repo je verejne).

    python videa/pripravit_demo.py /tmp/odkaz.txt

Premenne: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY.
"""
import os
import sys
from datetime import datetime, timedelta, timezone

from supabase import create_client

EMAIL = "demo@predtendrom.sk"
FIRMA = "Ukážková firma s.r.o."
KRAJE = ["Bratislavský kraj"]
SEKTORY = ["UPRATOVANIE"]


def main(cesta: str) -> int:
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])

    uid = None
    strana = 1
    while uid is None:
        users = sb.auth.admin.list_users(page=strana, per_page=200)
        if not users:
            break
        for u in users:
            if (u.email or "").lower() == EMAIL:
                uid = u.id
        strana += 1
    if uid is None:
        uid = sb.auth.admin.create_user({"email": EMAIL, "email_confirm": True}).user.id
        print("Ukazkovy ucet vytvoreny.")

    clen = sb.table("memberships").select("org_id").eq("user_id", uid).execute().data
    if clen:
        org = clen[0]["org_id"]
    else:
        org = sb.table("organizations").insert({"nazov": FIRMA}).execute().data[0]["id"]
        sb.table("memberships").insert({"user_id": uid, "org_id": org, "rola": "owner"}).execute()
        print("Ukazkova firma vytvorena.")

    do = (datetime.now(timezone.utc) + timedelta(days=5 * 365)).isoformat()
    sb.table("subscriptions").upsert({"org_id": org, "plan": "growth", "stav": "aktivne",
                                      "obdobie_konci": do}, on_conflict="org_id").execute()
    sb.table("nastavenia_pouzivatela").upsert({"user_id": uid, "kraje": KRAJE, "sektory": SEKTORY},
                                              on_conflict="user_id").execute()

    odkaz = sb.auth.admin.generate_link({
        "type": "magiclink", "email": EMAIL,
        "options": {"redirect_to": "https://predtendrom.sk/app.html"},
    }).properties.action_link
    with open(cesta, "w") as f:
        f.write(odkaz)
    print("Prihlasovaci odkaz pripraveny (v subore, nie v logu).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
