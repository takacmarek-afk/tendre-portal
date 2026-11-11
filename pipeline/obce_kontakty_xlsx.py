"""Excel 'Obce a e-mailove kontakty' a jeho odoslanie Marekovi (11. 11. 2026).

Zostavi zosit z exportu obce_kontakty_export.py a posle ho cez Zoho na
info@predtendrom.sk (preposiela sa Marekovi). Subor nejde do repozitara ani
do artefaktov (repo je verejne).

    python obce_kontakty_xlsx.py [--nasucho]

Premenne: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, ZOHO_SMTP_PASSWORD.
"""
import argparse
import json
import os
import smtplib
import ssl
import sys
import tempfile
from datetime import date
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

F = "Arial"
STAVY = ("Nepoužijeme", "Chýba", "Máme úradný")


def zosit(riadky, cesta):
    poradie = {s: i for i, s in enumerate(STAVY)}
    r = sorted(riadky, key=lambda x: (poradie[x["stav"]], x["kraj"] or "ž", x["okres"], x["obec"]))
    N, B = Font(name=F, size=10), Font(name=F, bold=True)
    HDR, HF = PatternFill("solid", fgColor="0B1220"), Font(name=F, bold=True, color="FFFFFF", size=10)
    YEL = PatternFill("solid", fgColor="FFF2B3")
    FARBA = {"Nepoužijeme": "F9ECE7", "Chýba": "F0EFEC", "Máme úradný": "E5F4E4"}
    wb = Workbook()
    s = wb.active
    s.title = "Súhrn"
    o = wb.create_sheet("Obce")
    hl = ["Kraj", "Okres", "Obec", "Kód obce (ŠÚ SR)", "IČO", "Starosta 2026", "Stav e-mailu",
          "Doterajšia adresa", "Prečo ju nepoužijeme", "Dostane e-mail vo vlne 1",
          "Úradný e-mail obce (doplniť)", "Zdroj (doplniť)", "Poznámka"]
    o.append(hl)
    for c in range(1, len(hl) + 1):
        x = o.cell(1, c)
        x.font, x.alignment = HF, Alignment(wrap_text=True, vertical="center")
        x.fill = HDR if c <= 10 else PatternFill("solid", fgColor="B25313")
    for x in r:
        o.append([x["kraj"], x["okres"], x["obec"], x["kod_obce"], x["ico"], x["starosta"], x["stav"],
                  x["adresa"], x["dovod"], x["vlna1"] or "", None, None, None])
    n = len(r) + 1
    for row in o.iter_rows(min_row=2, max_row=n):
        for c in row:
            c.font = N
        row[6].fill = PatternFill("solid", fgColor=FARBA[row[6].value])
        for c in row[10:13]:
            c.fill = YEL
    for i, w in enumerate([20, 18, 30, 14, 11, 14, 15, 32, 42, 22, 34, 18, 30], 1):
        o.column_dimensions[get_column_letter(i)].width = w
    o.row_dimensions[1].height = 32
    o.freeze_panes, o.auto_filter.ref = "D2", f"A1:M{n}"
    dv = DataValidation(type="list", allow_blank=True,
                        formula1='"web obce,telefonát na úrad,e-mail od obce,register MV SR,iné"')
    o.add_data_validation(dv)
    dv.add(f"L2:L{n}")

    s["A1"] = "Obce a e-mailové kontakty pre kampaň po voľbách 2026"
    s["A1"].font = Font(name=F, bold=True, size=14)
    s["A2"] = (f"Stav k {date.today():%d. %m. %Y}. Zdroj e-mailov: Vestník verejného obstarávania (ÚVO). "
               "Starostovia: výsledky volieb ŠÚ SR 2022 a 2026.")
    s["A2"].font = Font(name=F, size=10, italic=True)
    s.append([])
    s.append(["Kraj", "Obcí spolu", "Máme úradný", "Nepoužijeme", "Chýba", "Na doplnenie", "Doplnené",
              "Zostáva doplniť"])
    for c in range(1, 9):
        x = s.cell(4, c)
        x.font, x.fill, x.alignment = HF, HDR, Alignment(wrap_text=True, horizontal="center")
    A, G, K = f"Obce!$A$2:$A${n}", f"Obce!$G$2:$G${n}", f"Obce!$K$2:$K${n}"
    kraje = sorted({x["kraj"] for x in r if x["kraj"]})

    def riadok_kraja(R, kriterium):
        s.cell(R, 2, f"=COUNTIFS({A},{kriterium})")
        for c, st in ((3, "Máme úradný"), (4, "Nepoužijeme"), (5, "Chýba")):
            s.cell(R, c, f'=COUNTIFS({A},{kriterium},{G},"{st}")')
        s.cell(R, 6, f"=D{R}+E{R}")
        s.cell(R, 7, f'=COUNTIFS({A},{kriterium},{G},"<>Máme úradný",{K},"?*")')
        s.cell(R, 8, f"=F{R}-G{R}")

    for i, k in enumerate(kraje):
        s.cell(5 + i, 1, k)
        riadok_kraja(5 + i, f"$A{5 + i}")
    T = 5 + len(kraje)
    s.cell(T, 1, "Bez kraja (obec sa nedala priradiť)")
    riadok_kraja(T, '""')
    Z = T + 1
    s.cell(Z, 1, "Spolu")
    for c in range(2, 9):
        L = get_column_letter(c)
        s.cell(Z, c, f"=SUM({L}5:{L}{T})")
    for row in s.iter_rows(min_row=5, max_row=Z):
        for c in row:
            c.font = N
    for c in range(1, 9):
        s.cell(Z, c).font = Font(name=F, bold=True, size=10)
        s.cell(Z, c).border = Border(top=Side(style="thin"))
    Q = Z + 2
    s.cell(Q, 1, "Podľa starostu").font = B
    for c, t in enumerate(["Starosta 2026", "Obcí", "Máme úradný", "Nepoužijeme", "Chýba"], 1):
        x = s.cell(Q + 1, c, t)
        x.font, x.fill = HF, HDR
    F_ = f"Obce!$F$2:$F${n}"
    for i, t in enumerate(["nový", "staronový", "voľby sa opakujú"]):
        R = Q + 2 + i
        s.cell(R, 1, t)
        s.cell(R, 2, f"=COUNTIFS({F_},$A{R})")
        for c, st in ((3, "Máme úradný"), (4, "Nepoužijeme"), (5, "Chýba")):
            s.cell(R, c, f'=COUNTIFS({F_},$A{R},{G},"{st}")')
        for c in range(1, 6):
            s.cell(R, c).font = N
    L0 = Q + 7
    legenda = [
        ("Ako dopĺňať", True),
        ("1. V hárku Obce vyfiltrujte stĺpec „Stav e-mailu“ na Chýba alebo Nepoužijeme (sú na začiatku zoznamu).", False),
        ("2. Do žltých stĺpcov K až M doplňte úradný e-mail obce, odkiaľ je a prípadnú poznámku. Ostatné stĺpce nemeňte.", False),
        ("3. Hľadáme všeobecnú adresu úradu (obec@…, podatelna@…, ou@…), nie osobnú adresu starostu či zamestnanca a nie adresu externej firmy.", False),
        ("4. Najlepší zdroj je kontakt na webe obce. Súhrn vyššie sa po doplnení prepočíta sám (stĺpec Doplnené).", False),
        ("Príklad vyplnenia: K = obec@hran.sk, L = web obce, M = na webe uvedená ako kontakt obecného úradu", False),
        ("Stav e-mailu: Máme úradný = použijeme v kampani; Nepoužijeme = máme adresu, ale nie úradnú (ukazujeme len doménu); "
         "Chýba = žiadnu adresu nemáme.", False),
    ]
    for i, (t, b) in enumerate(legenda):
        s.cell(L0 + i, 1, t).font = Font(name=F, bold=b, size=11 if b else 10)
    s.cell(L0 + 5, 1).fill = YEL
    s.column_dimensions["A"].width = 36
    for c in "BCDEFGH":
        s.column_dimensions[c].width = 14
    s.row_dimensions[4].height = 30
    wb.calculation.fullCalcOnLoad = True      # vzorce sa prepocitaju pri otvoreni v Exceli
    wb.save(cesta)
    return {st: sum(1 for x in r if x["stav"] == st) for st in STAVY}


def posli(heslo, cesta, pocty):
    m = EmailMessage()
    m["From"], m["To"] = "PredTendrom.sk <marek@predtendrom.sk>", "info@predtendrom.sk"
    m["Subject"] = "Obce a e-mailové kontakty (Excel na doplnenie)"
    m["Date"], m["Message-ID"] = formatdate(localtime=True), make_msgid(domain="predtendrom.sk")
    m["Auto-Submitted"] = "auto-generated"
    m.set_content(
        "Ahoj Marek,\n\nv prílohe je zoznam všetkých obcí a stav e-mailových kontaktov pre kampaň:\n"
        f"- máme úradný e-mail: {pocty['Máme úradný']}\n"
        f"- adresu máme, ale nepoužijeme ju: {pocty['Nepoužijeme']}\n"
        f"- e-mail chýba: {pocty['Chýba']}\n\n"
        "Žlté stĺpce v hárku Obce sú na doplnenie, návod je v hárku Súhrn.\n"
        "Vyplnený súbor mi pošli späť a adresy pridám do kampane.\n\n-- Claude, PredTendrom.sk")
    with open(cesta, "rb") as f:
        m.add_attachment(f.read(), maintype="application",
                         subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                         filename="obce-emailove-kontakty.xlsx")
    with smtplib.SMTP_SSL("smtp.zoho.eu", 465, timeout=60, context=ssl.create_default_context()) as sm:
        sm.login("marek@predtendrom.sk", heslo)
        sm.send_message(m)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--nasucho", action="store_true")
    a = ap.parse_args(argv)
    import obce_kontakty_export
    with tempfile.TemporaryDirectory() as d:
        j, x = os.path.join(d, "obce.json"), os.path.join(d, "obce.xlsx")
        obce_kontakty_export.main(j)
        with open(j, encoding="utf-8") as f:
            pocty = zosit(json.load(f), x)
        print("Pocty:", pocty)
        if a.nasucho:
            print("NASUCHO, neposlane.")
            return 0
        posli(os.environ["ZOHO_SMTP_PASSWORD"], x, pocty)
        print("Poslane na info@predtendrom.sk.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
