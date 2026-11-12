"""Vsetko, co mame v databaze o jednej obci (12. 11. 2026). LEN CITANIE.

Vystup je JSON SUBOR (nie log) — workflow export-sifrovany ho zasifruje a ulozi
do vetvy export-sifrovane (repo je verejne).

    OBEC="Horná Potôň" python obec_profil_export.py vystup.json
"""
import json
import os
import sys
import unicodedata


def norm(t):
    return "".join(c for c in unicodedata.normalize("NFKD", str(t or "").lower()) if not unicodedata.combining(c)).strip()


def vsetko(q, krok=1000):
    out, od = [], 0
    while True:
        r = q.range(od, od + krok - 1).execute().data or []
        out += r
        if len(r) < krok:
            return out
        od += krok


def skus(nazov, fn):
    try:
        return fn()
    except Exception as e:                      # tabulka/stlpec nemusi existovat
        return {"chyba": f"{type(e).__name__}: {str(e)[:200]}", "tabulka": nazov}


def main(cesta):
    from store import klient
    sb = klient()
    hladane = os.environ.get("OBEC", "").strip()
    reg = vsetko(sb.table("obce_register").select("*"))
    zhoda = [r for r in reg if norm(r.get("nazov")) == norm(hladane)] or \
            [r for r in reg if norm(hladane) in norm(r.get("nazov"))]
    out = {"hladane": hladane, "register": zhoda}
    if not zhoda:
        json.dump(out, open(cesta, "w"), ensure_ascii=False, indent=1)
        print("::notice::Obec nenajdena")
        return
    o = zhoda[0]
    ico, kod, nazov = str(o.get("ico") or ""), str(o.get("kod") or ""), o.get("nazov")
    T = sb.table
    # Register nema vzdy ICO: dohladat z CRZ (objednavatel "Obec <nazov>") a dotacii.
    if not ico:
        kand = {}
        for r in (T("contracts").select("authority_cin,authority_name").ilike("authority_name", f"%{nazov}%").limit(500).execute().data or []):
            if r.get("authority_cin") and norm(nazov) in norm(r.get("authority_name")) and "obec" in norm(r.get("authority_name")):
                kand[r["authority_cin"]] = kand.get(r["authority_cin"], 0) + 1
        for r in (T("subsidies").select("prijimatel_ico,prijimatel").ilike("prijimatel", f"%{nazov}%").limit(500).execute().data or []):
            if r.get("prijimatel_ico") and "obec" in norm(r.get("prijimatel")):
                kand[r["prijimatel_ico"]] = kand.get(r["prijimatel_ico"], 0) + 1
        out["ico_kandidati"] = kand
        if kand:
            ico = max(kand, key=kand.get)
    out["ico"] = ico
    kod6 = kod[-6:] if kod else ""
    # ICO je v tabulkach raz s nulami na zaciatku, raz bez (00305413 / 305413)
    ica = sorted({ico, ico.lstrip("0"), ico.lstrip("0").zfill(8)} - {""})
    D = {
        "contracts_ako_objednavatel": lambda: vsetko(T("contracts").select(
            "id,supplier_name,supplier_cin,subject,price_total,signed_on,effective_from,effective_to,sector,published_at")
            .in_("authority_cin", ica).order("signed_on", desc=True)),
        "contracts_ako_dodavatel": lambda: vsetko(T("contracts").select(
            "id,authority_name,authority_cin,subject,price_total,signed_on,effective_to").in_("supplier_cin", ica)),
        "opportunities": lambda: vsetko(T("opportunities").select("*").in_("authority_cin", ica)),
        "subsidies": lambda: vsetko(T("subsidies").select("*").in_("prijimatel_ico", ica).order("podpisane", desc=True)),
        "itms_vo": lambda: vsetko(T("itms_vo").select("*").in_("obstaravatel_ico", ica)),
        "itms_vo_podla_obce": lambda: vsetko(T("itms_vo").select("id,kod,nazov,stav,predpokladana_hodnota,obstaravatel_nazov,obstaravatel_ico,sektor")
            .ilike("obstaravatel_obec", f"%{nazov}%")),
        "uvo_vysledky": lambda: vsetko(T("uvo_vysledky").select("*").in_("obstaravatel_ico", ica)),
        "uvo_vyzvy": lambda: vsetko(T("uvo_vyzvy").select("*").in_("obstaravatel_ico", ica)),
        "obce_ziadatelia": lambda: vsetko(T("obce_ziadatelia").select("*").in_("obec_ico", ica)),
        "obec_poradcovia_agregat": lambda: vsetko(T("obec_poradcovia_agregat").select("*").ilike("obec_core", f"%{nazov}%")),
        "zmluvy_bez_sutaze": lambda: vsetko(T("zmluvy_bez_sutaze").select("*").in_("authority_ico", ica)),
        "dopyty": lambda: vsetko(T("dopyty").select("id,typ,nazov,stav,created_at").ilike("obec_nazov", f"%{nazov}%")),
        "vyzvy_semafor": lambda: vsetko(T("vyzvy_semafor").select("*").in_("kod_obce", [kod, kod6])),
        "ruz_financie": lambda: vsetko(T("ruz_financie").select("*").in_("supplier_cin", ica)),
        "starostovia": lambda: vsetko(T("obce_starostovia").select("rok,meno,priezvisko,titul_pred,subjekt,kod_obce").in_("kod_obce", [kod, kod6])),
        "kampan_obce_kontakt": lambda: vsetko(T("kampan_obce_kontakty").select("stav,dovod,zdroj").in_("ico", ica)),
        "kampan_obce_odoslane": lambda: vsetko(T("kampan_obce_odoslane").select("vlna,segment,stav,odoslane_at").in_("ico", ica)),
        "odber_obce_pocet": lambda: len(vsetko(T("odber_obce").select("id").in_("ico", ica))),
        "obce_ucty_pocet": lambda: len(vsetko(T("obce_ucty").select("id").in_("ico", ica))),
    }
    for k, fn in D.items():
        out[k] = skus(k, fn)
    # karty vyziev (vsetky, na lokalne vyhodnotenie podla kraja/okresu/velkosti)
    out["vyzvy_karty"] = skus("vyzvy_karty", lambda: vsetko(T("vyzvy_karty").select(
        "kod,nazov,poskytovatel,typ_ziadatela,kraje,okresy,len_nro,len_mrk,obyv_min,obyv_max,nfp_min,nfp_max,spoluucast_pct,uzavierka,signal_sektory")))
    json.dump(out, open(cesta, "w"), ensure_ascii=False, indent=1, default=str)
    print("::notice::Profil obce exportovany:", {k: (len(v) if isinstance(v, list) else v if isinstance(v, int) else "chyba")
                                                 for k, v in out.items() if k not in ("hladane", "register")})


if __name__ == "__main__":
    main(sys.argv[1])
