"""Test _najdi_spoluucast() (pipeline/vyzvy.py) — najkritickejsia cast tejto
vlny, presne preto, ze NIKDY nesmie vymysliet ani nespravne priradit cislo.

Spustenie:  python test_vyzvy.py
"""
import vyzvy


def hlavicka(t):
    print("\n" + "=" * 66)
    print(t)
    print("=" * 66)


hlavicka("Veta so spoluucastou AJ percentom v tej istej vete -> najde sa")
t = ("Žiadateľ musí zabezpečiť finančnú spoluúčasť vo výške najmenej 5 % "
     "z celkových oprávnených výdavkov projektu.")
vysledok = vyzvy._najdi_spoluucast(t)
assert vysledok == t, vysledok
print("OK:", vysledok)

hlavicka("Ziadna zmienka o spoluucasti -> None")
vysledok = vyzvy._najdi_spoluucast(
    "Vážení príjemcovia, zverejňujeme usmernenie k výzve MoF 8/2026.")
assert vysledok is None, vysledok
print("OK: None")

hlavicka("Spoluucast spomenuta, ale BEZ percenta -> None (nikdy nehadat)")
vysledok = vyzvy._najdi_spoluucast("Projekt vyžaduje finančnú spoluúčasť žiadateľa.")
assert vysledok is None, vysledok
print("OK: None")

hlavicka("Percento v INEJ vete nez spoluucast -> None (nespajaj nesuvisiace)")
vysledok = vyzvy._najdi_spoluucast(
    "Miera nezamestnanosti v regióne je 12 %. "
    "Výzva podporuje spolufinancovanie projektov v oblasti kultúry.")
assert vysledok is None, vysledok
print("OK: None (12 % o nezamestnanosti sa nesmie priradit k spolufinancovaniu)")

hlavicka("Viac vstupnych textov naraz (nazov + popis clanku)")
vysledok = vyzvy._najdi_spoluucast("Výzva na obnovu", "Spolufinancovanie zo strany obce je 10%.")
assert vysledok == "Výzva na obnovu Spolufinancovanie zo strany obce je 10%.", vysledok
print("OK:", vysledok)

hlavicka("Velmi dlha veta sa oreze na 300 znakov + elipsu")
dlha = "Spoluúčasť vo výške 7 % je nutná, " + "text " * 80 + "koniec vety."
vysledok = vyzvy._najdi_spoluucast(dlha)
assert vysledok is not None and vysledok.endswith("…") and len(vysledok) == 301, vysledok
print("OK: orezane na", len(vysledok), "znakov")

hlavicka("Prazdny/None vstup -> None, nic nespadne")
assert vyzvy._najdi_spoluucast() is None
assert vyzvy._najdi_spoluucast(None, "") is None
print("OK")

print("\nVsetky testy prebehli.")
