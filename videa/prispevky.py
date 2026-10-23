"""Plan prispevkov na FB/IG: 8 tyzdnov pre firmy (od 26. 10. 2026) a 4 tyzdne pre obce (od 24. 11.).

    python videa/prispevky.py cisla.json vystup/prispevky

Vytvori prispevky.json (datum, cas, text, obrazok/video) a karty.json pre karty.py.
Pravidla: ziadne predpovede tendrov, len verejne udaje o uradoch a zmluvach,
vzdy zdroj a datum udajov, ziadne mena ludi.
"""
import json
import sys
from datetime import date, timedelta
from pathlib import Path

KRATKE = {"Bratislavský kraj": "Bratislavský", "Trnavský kraj": "Trnavský", "Trenčiansky kraj": "Trenčiansky",
          "Nitriansky kraj": "Nitriansky", "Žilinský kraj": "Žilinský", "Banskobystrický kraj": "Banskobystrický",
          "Prešovský kraj": "Prešovský", "Košický kraj": "Košický"}


def eur(v):
    return f"{round(float(v)):,}".replace(",", " ") + " €"


def dsk(iso):
    d = date.fromisoformat(str(iso)[:10])
    return f"{d.day}. {d.month}. {d.year}"


def main(cisla_subor, vystup):
    c = json.loads(Path(cisla_subor).read_text())
    stav = dsk(c["stav_k"])
    zdroj = f"Zdroj: Centrálny register zmlúv, spracoval PredTendrom.sk, stav {stav}"
    zdroj_kratko = f"Zdroj: Centrálny register zmlúv, stav {stav}."
    s = c["sektory"]
    start = date(2026, 10, 26)
    karty, posty = [], []

    def post(den, cas, nazov, text, karta=None, video=None, pre="firmy"):
        p = {"datum": den.isoformat(), "cas": cas, "pre": pre, "nazov": nazov, "text": text.strip()}
        if karta:
            karta = dict(karta, subor=f"{den.isoformat()}-{karta['typ']}", zdroj=karta.get("zdroj", zdroj))
            karty.append(karta)
            p["obrazok"] = karta["subor"] + ".png"
        if video:
            p["video"] = video
        posty.append(p)

    def zmluva(sektor, i=0):
        return c["najvacsie_6_12_mes"][sektor][i]

    def kraje(sektor):
        return [[KRATKE.get(k, k), v] for k, v in s[sektor]["kraje"].items()]

    # ── pondelok: cislo tyzdna ───────────────────────────────────────────
    spolu = f"{c['zmluv_spolu']:,}".replace(",", " ")
    up, os_, st, ze, sp = s["UPRATOVANIE"], s["OSTRAHA"], s["STRAVOVANIE"], s["ZELEN_ZIMNA_UDRZBA"], s["STAVEBNE_PRACE"]
    pondelky = [
        ("Upratovanie: koľko zmlúv končí", {"typ": "cislo", "kicker": "Číslo týždňa · upratovanie", "cislo": str(up["zmluv"]),
          "nadpis": "zmlúv úradov na upratovanie sa skončí do 12 mesiacov.",
          "pod": f"Ide o {up['uradov']} úradov po celom Slovensku. Medián zmluvy je {eur(up['median'])}."},
         f"""{up['zmluv']} zmlúv úradov na upratovanie sa skončí v najbližších 12 mesiacoch. Ide o {up['uradov']} úradov po celom Slovensku, medián zmluvy je {eur(up['median'])}.

Kto ich dnes má, za koľko a do kedy, je verejné v Centrálnom registri zmlúv. My to dávame na jedno miesto.

{zdroj_kratko} Viac na predtendrom.sk"""),
        ("Ostraha po krajoch", {"typ": "stlpce", "kicker": "Ostraha po krajoch", "nadpis": "Kde končia zmluvy úradov na ostrahu",
          "riadky": kraje("OSTRAHA"), "pod": f"{os_['zmluv']} zmlúv do 12 mesiacov, medián {eur(os_['median'])}."},
         f"""Zmluvy úradov na ostrahu, ktoré sa skončia do 12 mesiacov, podľa krajov. Najviac ich je v Bratislavskom kraji, spolu {os_['zmluv']} zmlúv s mediánom {eur(os_['median'])}.

Pri každej je úrad, dodávateľ, suma a dátum konca. Všetko overiteľné v registri.

{zdroj_kratko} predtendrom.sk"""),
        ("Stravovanie: najväčší odbor", {"typ": "cislo", "kicker": "Číslo týždňa · stravovanie", "cislo": str(st["zmluv"]),
          "nadpis": "zmlúv úradov na stravovanie končí do 12 mesiacov.",
          "pod": f"{st['uradov']} úradov a organizácií. Medián zmluvy je {eur(st['median'])}."},
         f"""Stravovanie je odbor s najviac končiacimi zmluvami: {st['zmluv']} zmlúv u {st['uradov']} úradov a organizácií do 12 mesiacov. Medián zmluvy je {eur(st['median'])}.

Najviac ich je v Trenčianskom a Žilinskom kraji.

{zdroj_kratko} predtendrom.sk"""),
        ("Končiaca zmluva týždňa: upratovanie", {"typ": "zmluva", "kicker": "Končiaca zmluva týždňa",
          "nadpis": "Najväčšia zmluva na upratovanie, ktorá končí za 6 až 12 mesiacov",
          "urad": zmluva("UPRATOVANIE")["authority_name"].strip(), "predmet": zmluva("UPRATOVANIE")["subject"][:90],
          "suma": eur(zmluva("UPRATOVANIE")["price_total"]), "koniec": "končí " + dsk(zmluva("UPRATOVANIE")["effective_to"])},
         f"""Končiaca zmluva týždňa: {zmluva('UPRATOVANIE')['authority_name'].strip()}, upratovacie služby za {eur(zmluva('UPRATOVANIE')['price_total'])}, koniec {dsk(zmluva('UPRATOVANIE')['effective_to'])}.

Čo úrad urobí potom, vopred nevie nikto. Dátum konca je však verejný a kto ho pozná, má čas sa pripraviť.

{zdroj_kratko} predtendrom.sk"""),
        ("Zeleň a zimná údržba", {"typ": "cislo", "kicker": "Číslo týždňa · zeleň a zimná údržba", "cislo": str(ze["zmluv"]),
          "nadpis": "zmlúv úradov na zeleň a zimnú údržbu končí do roka.",
          "pod": f"{ze['do_90_dni']} z nich už do 90 dní. Medián zmluvy je {eur(ze['median'])}."},
         f"""Zima sa blíži a s ňou aj koniec zmlúv: {ze['zmluv']} zmlúv úradov na zeleň a zimnú údržbu skončí do 12 mesiacov, {ze['do_90_dni']} z nich už do 90 dní. Medián zmluvy je {eur(ze['median'])}.

{zdroj_kratko} predtendrom.sk"""),
        ("Stavebné práce po krajoch", {"typ": "stlpce", "kicker": "Stavebné práce po krajoch", "nadpis": "Kde končia zmluvy úradov na stavebné práce",
          "riadky": kraje("STAVEBNE_PRACE"), "pod": f"{sp['zmluv']} zmlúv do 12 mesiacov, medián {eur(sp['median'])}."},
         f"""Stavebné práce: {sp['zmluv']} zmlúv úradov sa skončí do 12 mesiacov, medián {eur(sp['median'])}. Takto sú rozdelené po krajoch.

{zdroj_kratko} predtendrom.sk"""),
        ("Končiaca zmluva týždňa: ostraha", {"typ": "zmluva", "kicker": "Končiaca zmluva týždňa",
          "nadpis": "Zmluva na ostrahu, ktorá končí na jar 2027",
          "urad": zmluva("OSTRAHA", 2)["authority_name"].strip(), "predmet": zmluva("OSTRAHA", 2)["subject"][:90],
          "suma": eur(zmluva("OSTRAHA", 2)["price_total"]), "koniec": "končí " + dsk(zmluva("OSTRAHA", 2)["effective_to"])},
         f"""Končiaca zmluva týždňa: {zmluva('OSTRAHA', 2)['authority_name'].strip()}, strážna služba za {eur(zmluva('OSTRAHA', 2)['price_total'])}, koniec {dsk(zmluva('OSTRAHA', 2)['effective_to'])}.

Celú zmluvu aj s cenou si nájdete v Centrálnom registri zmlúv.

{zdroj_kratko} predtendrom.sk"""),
        ("Spolu za všetky odbory", {"typ": "cislo", "kicker": "Číslo týždňa · všetky odbory", "cislo": spolu,
          "nadpis": "zmlúv úradov končí v najbližších 12 mesiacoch.",
          "pod": f"{c['uradov_spolu']} úradov v 14 odboroch. Každú zmluvu si overíte v registri."},
         f"""Na konci roka jedno číslo: {spolu} zmlúv úradov sa skončí v najbližších 12 mesiacoch. Ide o {c['uradov_spolu']} úradov v 14 odboroch, od upratovania po IT.

Ktoré sú z vášho odboru a kraja, uvidíte na predtendrom.sk.

{zdroj_kratko}"""),
    ]

    # ── piatok: tip ──────────────────────────────────────────────────────
    piatky = [
        ("Tri možnosti úradu", {"typ": "tip", "kicker": "Tip na piatok", "nadpis": "Keď úradu končí zmluva, má tri možnosti",
          "body": ["predĺži ju dodatkom,", "kúpi službu bez súťaže (pri malej sume),", "vyhlási nové obstarávanie."],
          "pod": "Ktorú vyberie, vopred nevie nikto. Dátum konca je však verejný.", "zdroj": "predtendrom.sk"},
         """Keď úradu končí zmluva, má tri možnosti:
1. predĺži ju dodatkom,
2. kúpi službu bez súťaže (pri malej sume),
3. vyhlási nové obstarávanie.

Ktorú vyberie, nevie nikto vopred. Ale dátum konca je verejný a kto ho pozná, má čas sa pripraviť."""),
        ("Zmluva úradu zadarmo", {"typ": "tip", "kicker": "Tip na piatok", "nadpis": "Kde nájdete každú zmluvu úradu zadarmo",
          "body": ["Otvorte crz.gov.sk (Centrálny register zmlúv).", "Vyhľadajte úrad alebo predmet zmluvy.",
                   "Otvorte zmluvu aj prílohy v PDF.", "Pozrite si cenu, rozsah a dátum konca."], "zdroj": "predtendrom.sk"},
         """Každá zmluva úradu je zverejnená v Centrálnom registri zmlúv, aj s cenou:
1. otvorte crz.gov.sk,
2. vyhľadajte úrad alebo predmet,
3. otvorte zmluvu a prílohy,
4. pozrite si cenu, rozsah a dátum konca.

Ak to nechcete robiť po jednej, PredTendrom ich zbiera za vás."""),
        ("Referencie vopred", {"typ": "tip", "kicker": "Tip na piatok", "nadpis": "Referencie: čo si pripraviť skôr, než príde súťaž",
          "body": ["zoznam podobných zákaziek za posledné roky,", "sumy a obdobie plnenia,", "potvrdenia od objednávateľov,",
                   "kontakt, ktorý to vie potvrdiť."], "zdroj": "predtendrom.sk"},
         """Referencie sa zháňajú najdlhšie. Pripravte si ich skôr, než úrad vyhlási súťaž:
• zoznam podobných zákaziek,
• sumy a obdobie plnenia,
• potvrdenia od objednávateľov,
• kontakt, ktorý to vie potvrdiť.

Čo presne úrad žiada, vždy určí až súťažné podklady."""),
        ("Zakladajúca ponuka", {"typ": "tip", "kicker": "Pre prvých 30 firiem", "nadpis": "Plán Start za 240 € ročne namiesto 340 €",
          "body": ["cena platí 2 roky,", "kód ZAKLADATEL zadáte pri ročnej platbe,", "najprv 14 dní zadarmo, bez karty,",
                   "do 30 dní vrátime peniaze, ak nebudete spokojní."], "cislovane": False, "zdroj": "predtendrom.sk/cennik"},
         """Pre prvých 30 firiem máme zakladajúcu cenu: ročný plán Start za 240 € namiesto 340 €, cena platí 2 roky.

Najprv si to vyskúšajte 14 dní zadarmo, bez karty. Pri ročnej platbe zadáte kód ZAKLADATEL. Ak do 30 dní nebudete spokojní, vrátime celú sumu.

predtendrom.sk/cennik"""),
        ("Čo sledovať v zmluve", {"typ": "tip", "kicker": "Tip na piatok", "nadpis": "Štyri veci, ktoré si v zmluve úradu prečítajte",
          "body": ["dátum konca a či sa dá predĺžiť,", "cenu, ideálne jednotkovú (za m², hodinu, obed),",
                   "rozsah: koľko budov, plôch alebo ľudí,", "výpovednú lehotu."], "zdroj": "predtendrom.sk"},
         """Zmluva úradu povie viac než len sumu. Prečítajte si:
1. dátum konca a možnosť predĺženia,
2. jednotkovú cenu (za m², hodinu, obed),
3. rozsah: koľko budov, plôch alebo ľudí,
4. výpovednú lehotu.

Odkaz na každú zmluvu nájdete pri nej v PredTendrom."""),
        ("Kde sa súťaž objaví", {"typ": "tip", "kicker": "Tip na piatok", "nadpis": "Kde sa objaví súťaž, keď ju úrad vyhlási",
          "body": ["vo Vestníku verejného obstarávania (ÚVO),", "na profile obstarávateľa na stránke ÚVO,",
                   "v systéme, cez ktorý úrad súťaží (napríklad EVO alebo Josephine)."], "zdroj": "predtendrom.sk"},
         """Keď úrad súťaž vyhlási, nájdete ju:
1. vo Vestníku verejného obstarávania (ÚVO),
2. na profile obstarávateľa na stránke ÚVO,
3. v systéme, cez ktorý úrad súťaží (napríklad EVO alebo Josephine).

Lehoty bývajú krátke. Kto sa pripravuje vopred, nestráca čas."""),
        ("Jednotková cena", {"typ": "tip", "kicker": "Tip na piatok", "nadpis": "Celková suma klame. Pozerajte cenu za mesiac.",
          "body": ["48 000 € na 24 mesiacov = 2 000 € mesačne,", "30 000 € na 12 mesiacov = 2 500 € mesačne,",
                   "menšia zmluva tu má vyššiu mesačnú cenu."], "cislovane": False, "zdroj": "Ilustračný príklad · predtendrom.sk"},
         """Dve zmluvy, dve sumy: 48 000 € a 30 000 €. Ktorá je drahšia?

Prvá je na 24 mesiacov, teda 2 000 € mesačne. Druhá na 12 mesiacov, teda 2 500 € mesačne.

Pred tvorbou ponuky porovnávajte cenu za mesiac alebo za jednotku. PredTendrom ju pri zmluvách počíta za vás. (Ilustračný príklad.)"""),
        ("Plán na január", {"typ": "tip", "kicker": "Tip na nový rok", "nadpis": "Tri kroky na január",
          "body": ["Vyberte 5 zmlúv vo svojom odbore, ktoré končia v roku 2027.", "Pripravte si k nim referencie a cenu.",
                   "Zapnite si týždenný prehľad, nech vám nič neujde."], "zdroj": "predtendrom.sk"},
         """Tri kroky na január:
1. vyberte 5 zmlúv vo svojom odbore, ktoré končia v roku 2027,
2. pripravte si k nim referencie a cenu,
3. zapnite si týždenný prehľad, nech vám nič neujde.

Pekné sviatky. predtendrom.sk"""),
    ]

    # ── streda: video ────────────────────────────────────────────────────
    stredy = [
        (1, "Za 70 sekúnd: ktoré zmluvy úradov vo vašom odbore a kraji sa blížia ku koncu. Kto ich má, za koľko a do kedy. predtendrom.sk"),
        (3, "Ako čítať končiacu zmluvu: štyri údaje a jeden odkaz do registra. Návod na 80 sekúnd."),
        (4, "Kto vám konkuruje? V záložke Dodávatelia vidíte, ktoré firmy dodávajú úradom vo vašom odbore, koľkým úradom a za koľko."),
        (6, "Zmluva končí o 8 mesiacov. Čo teraz? Referencie, certifikáty, kapacity a cena. Návod na 90 sekúnd."),
        (2, "Prvé nastavenie trvá 2 minúty: odbor, kraj a týždenný prehľad e-mailom. 14 dní zadarmo, bez karty."),
        (5, "Za koľko to robia iní? Ceny zo súťaží ÚVO a z končiacich zmlúv, skôr než napíšete ponuku."),
        (1, "Ešte raz, pre tých, čo sa pridali neskôr: PredTendrom za 70 sekúnd. predtendrom.sk"),
        (3, "Pred sviatkami jeden tip: otvorte si jednu zmluvu, ktorá vás zaujíma, a prečítajte si ju celú. Ako na to, je v tomto videu."),
    ]

    for t in range(8):
        po = start + timedelta(days=7 * t)
        n, k, txt = pondelky[t]
        post(po, "08:30", n, txt, karta=k)
        v, vt = stredy[t]
        post(po + timedelta(days=2), "12:00", f"Video {v}", vt, video=f"video-{v}-reels.mp4")
        n, k, txt = piatky[t]
        post(po + timedelta(days=4), "09:00", n, txt, karta=k)

    # ── obce: utorky od 24. 11. ──────────────────────────────────────────
    prog = [p for p in c["obce_programy"] if p.get("obci_90d")][:7]
    skratky = {"Ministerstvo investícií, regionálneho rozvoja a informatizácie Slovenskej republiky": "MIRRI",
               "Ministerstvo kultúry Slovenskej republiky": "Ministerstvo kultúry",
               "Ministerstvo práce, sociálnych vecí a rodiny SR": "Ministerstvo práce",
               "Ministerstvo dopravy SR": "Ministerstvo dopravy",
               "Ministerstvo životného prostredia SR": "Ministerstvo živ. prostredia",
               "Ministerstvo obrany SR": "Ministerstvo obrany", "Fond na podporu umenia": "Fond na podporu umenia"}
    obce = [
        ("Kto rozdáva peniaze obciam", {"typ": "stlpce", "kicker": "Pre obce a mestá", "nadpis": "Kto za posledné 3 mesiace podpísal dotácie s najviac obcami",
          "riadky": [[skratky.get(p["poskytovatel"], p["poskytovatel"][:26]), p["obci_90d"]] for p in prog],
          "pod": "Počet obcí s novou zmluvou o dotácii za 90 dní."},
         f"""Kto práve teraz dáva peniaze obciam? Za posledné 3 mesiace podpísal {prog[0]['poskytovatel']} zmluvy s {prog[0]['obci_90d']} obcami, medián {eur(prog[0]['median_dotacie'])}.

Prehľad programov, ktoré teraz platia, nájdete zadarmo a bez registrácie na predtendrom.sk/obce.

{zdroj_kratko}"""),
        ("Zmluvy, ktoré obec zdedila", {"typ": "tip", "kicker": "Pre starostov", "nadpis": "Zmluvy, ktoré sa oplatí v obci skontrolovať",
          "body": ["odvoz odpadu,", "stravovanie a upratovanie v škole a škôlke,", "údržba zelene a zimná údržba,", "verejné osvetlenie."],
          "pod": "Pozrite sa, kedy končia. Na novú súťaž treba mesiace.", "cislovane": False, "zdroj": "predtendrom.sk/starosta"},
         """Nový rok je dobrý čas pozrieť sa, ktoré zmluvy obec má a kedy končia: odvoz odpadu, stravovanie a upratovanie v škole a škôlke, údržba zelene, verejné osvetlenie.

Na prípravu novej súťaže treba mesiace. Zoznam zmlúv vašej obce podľa IČO nájdete zadarmo na predtendrom.sk/starosta"""),
        ("Viac ponúk na súťaž", {"typ": "tip", "kicker": "Pre obce a mestá", "nadpis": "Ako dostať na súťaž viac ponúk",
          "body": ["Oznámte zákazku s dostatočným predstihom.", "Opíšte predmet jasne a merateľne.",
                   "Nežiadajte viac referencií a obratu, než zákazka naozaj potrebuje."], "zdroj": "predtendrom.sk/starosta"},
         """Viac ponúk zvyčajne znamená lepšiu cenu. Pomáha:
1. oznámiť zákazku s dostatočným predstihom,
2. opísať predmet jasne a merateľne,
3. nežiadať viac referencií a obratu, než zákazka naozaj potrebuje.

Nie je to právne poradenstvo, pravidlá určuje zákon o verejnom obstarávaní."""),
        ("Mesačný prehľad pre obec", {"typ": "tip", "kicker": "Pre obce a mestá · zadarmo", "nadpis": "Mesačný prehľad dotácií e-mailom",
          "body": ["programy, z ktorých teraz chodia peniaze obciam,", "výzvy, ktoré sme našli,", "raz mesačne, odhlásenie jedným klikom."],
          "cislovane": False, "zdroj": "predtendrom.sk/obce"},
         """Pre obce a mestá posielame raz mesačne zadarmo prehľad: z ktorých programov práve chodia peniaze obciam a aké výzvy sme našli.

Prihlásenie zaberie minútu: predtendrom.sk/obce"""),
    ]
    for t, (n, k, txt) in enumerate(obce):
        post(date(2026, 11, 24) + timedelta(days=7 * t), "09:00", n, txt, karta=k, pre="obce")

    posty.sort(key=lambda p: (p["datum"], p["cas"]))
    out = Path(vystup)
    out.mkdir(parents=True, exist_ok=True)
    (out / "prispevky.json").write_text(json.dumps(posty, ensure_ascii=False, indent=1))
    (out / "karty.json").write_text(json.dumps(karty, ensure_ascii=False, indent=1))
    print(len(posty), "prispevkov,", len(karty), "kariet")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
