"""Export zoznamu obci a stavu e-mailovych kontaktov (11. 11. 2026). LEN CITANIE.

Pre kazdu obec SR (zoznam zvolenych starostov SU SR 2026, porovnanie s 2022):
kraj, okres, obec, kod obce, novy/staronovy starosta, stav kontaktu v kampani
(mame uradny / nepouzijeme / chyba), adresa alebo len domena (pri nepouzitych),
dovod a ci obec dostane e-mail vo vlne 1.

Vystup je JSON SUBOR (nie log). Workflow ho zasifruje verejnym klucom
.github/export-claude.pub a ulozi do vetvy export-sifrovane (repo je verejne).

    python obce_kontakty_export.py vystup.json
"""
import json
import sys
from datetime import date

import requests

from kampan_obce import SEGMENTY, _vsetky, ico_kluc, nacitaj_data
from obce_volby_analyza import starostovia, typ_starostu

DOVODY = {
    "vyzera ako osobna adresa": "osobná adresa zamestnanca (meno.priezvisko)",
    "verejna schranka bez nazvu obce": "verejná schránka (gmail, azet...) bez názvu obce",
    "adresa na domene obce, ale moze byt osobna": "na doméne obce, ale môže byť osobná",
    "vseobecna adresa, ale domena nesedi s obcou": "doména nepatrí obci (často externý obstarávateľ)",
    "domena nesedi s obcou (externy obstaravatel?)": "doména nepatrí obci (externý obstarávateľ)",
}


def dovod_text(d):
    return DOVODY.get(str(d or ""), str(d or "") or "na kontrolu")


def main(cesta):
    from config import USER_AGENT
    from store import klient
    sess = requests.Session()
    sess.headers["User-Agent"] = USER_AGENT
    s22, s26 = starostovia(sess, 2022), starostovia(sess, 2026)
    sb = klient()
    kontakty = _vsetky(sb, "kampan_obce_kontakty", "ico,obec,kraj,kod_obce,email,stav,dovod,odhlasene_at")
    ok = [k for k in kontakty if k["stav"] == "ok" and not k.get("odhlasene_at")]
    data = nacitaj_data(sb, [k["ico"] for k in ok], date.today())

    podla_kodu = {}
    for k in kontakty:
        if k.get("kod_obce"):
            podla_kodu.setdefault(k["kod_obce"], k)
    riadky = []

    def riadok(kod, zaklad, k):
        if not k:
            stav, adresa, dovod, vlna = "Chýba", "", "", ""
        elif k["stav"] == "ok" and not k.get("odhlasene_at"):
            stav, adresa, dovod = "Máme úradný", k["email"], ""
            d = data.get(k["ico"], {})
            seg = next((s for s in SEGMENTY if d.get(s)), None)
            vlna = "áno" if seg else "nie (bez konkrétneho údaja)"
        else:
            stav = "Nepoužijeme"
            adresa = "@" + k["email"].split("@")[-1]          # len domena, nie osobna adresa
            dovod = "odhlásená" if k.get("odhlasene_at") else dovod_text(k.get("dovod"))
            vlna = "nie"
        return {
            "kraj": zaklad.get("kraj") or (k or {}).get("kraj") or "",
            "okres": zaklad.get("okres") or "",
            "obec": zaklad.get("obec") or (k or {}).get("obec") or "",
            "kod_obce": kod or "",
            "ico": (k or {}).get("ico") or "",
            "starosta": {"novy": "nový", "staronovy": "staronový",
                         "bez_vysledku_2026": "voľby sa opakujú"}.get(typ_starostu(kod, s22, s26), "")
                        if kod else "",
            "stav": stav, "adresa": adresa, "dovod": dovod, "vlna1": vlna,
        }

    for kod in sorted(set(s22) | set(s26)):
        riadky.append(riadok(kod, s26.get(kod) or s22.get(kod) or {}, podla_kodu.get(kod)))
    for k in kontakty:                        # kontakty bez kodu obce
        if not k.get("kod_obce"):
            riadky.append(riadok(None, {}, k))
    with open(cesta, "w", encoding="utf-8") as f:
        json.dump(riadky, f, ensure_ascii=False)
    print(f"Riadkov: {len(riadky)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
