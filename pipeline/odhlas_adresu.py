"""Ručné odhlásenie jednej adresy zo všetkých rozosielaní (16. 11. 2026).

Adresa nejde do logu ani do vstupov (repo je verejné): workflow dostane len
SHA-256 malými písmenami zapísanej adresy (premenná HASH). Skript prejde
tabuľky s adresami, vypíše len názov tabuľky, počet zhôd a dátumy/stavy
a s ZAPIS=1 adresu všade odhlási.
"""
import hashlib
import os

from supabase import create_client
from strankuj import vsetky

H = os.environ.get("HASH", "").strip().lower()
ICA = {i.strip().zfill(8) for i in os.getenv("ICA", "").split(",") if i.strip()}
ZAPIS = os.getenv("ZAPIS") == "1"
sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])


def h(e):
    return hashlib.sha256((e or "").strip().lower().encode()).hexdigest()


# tabulka -> (stlpec s adresou, kluc, stlpce na vypis, odhlasenie)
TAB = {
    "kampan_obce_kontakty": ("email", "ico", "ico,stav,odhlasene_at", {"odhlasene_at": "now()", "dovod": "odhlasenie mailto"}),
    "kampan_obce_odoslane": ("email", "id", "id,vlna,segment,stav,odoslane_at", None),
    "oslovenie_firiem_kontakty": ("email", "ico", "ico,nazov,stav,segment,kraj,odhlasene_at", {"odhlasene_at": "now()", "stav": "odpovedal"}),
    "oslovenie_firiem_odoslane": ("email", "id", "id,krok,stav,odoslane_at", None),
    "odber_firmy": ("email", "id", "id,sektor,kraj,zdroj,potvrdeny,odhlaseny_at,krok", {"odhlaseny_at": "now()"}),
    "odber": ("email", "id", "*", None),
    "odber_obce": ("email", "id", "*", None),
    "kampan_pilot": ("email_obce", "ico", "mesiac,ico,variant,vytvorene_at", None),
    "obce_web_kontakty": ("email", "id", "*", None),
}
riadky = []
for t, (col, kluc, stlpce, odhl) in TAB.items():
    try:
        rows = vsetky(lambda o, d: sb.table(t).select(f"{col},{stlpce}" if stlpce != "*" else "*")
                      .order(kluc).range(o, d).execute())
    except Exception as e:
        riadky.append(f"{t}: nedostupne ({type(e).__name__})")
        continue
    zhody = [r for r in rows if (H and h(r.get(col)) == H)
             or (ICA and str(r.get("ico") or "").zfill(8) in ICA and t.startswith("oslovenie_firiem_kontakty"))]
    if not zhody:
        riadky.append(f"{t}: 0")
        continue
    info = [{k: v for k, v in r.items() if k not in (col, "email", "email_obce", "telo_text", "token", "meno")} for r in zhody]
    riadky.append(f"{t}: {len(zhody)} {info}"[:600])
    if ZAPIS and odhl:
        for r in zhody:
            sb.table(t).update(odhl).eq(kluc, r[kluc]).execute()
        riadky.append(f"  -> {t}: odhlasene {len(zhody)}")
print("\n".join(riadky))
print("::notice title=Adresa::" + "%0A".join(riadky))
