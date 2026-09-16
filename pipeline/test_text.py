"""Test ocistenia textu z CRZ. Spusti: python test_text.py

PRECO EXISTUJE: 16. 9. 2026 bol na DRUHOM RIADKU prvej obrazovky aplikacie
tento text, vratane chybajucej bodkocirky a chybajucej medzery:

    Zmluva o dielo - &quot;Obnova ulice Sv.Štefana Veľký Meder&quot

Externy audit to oznacil za najviditelnejsi signal "toto je nedokoncene"
v celom produkte a mal pravdu.
"""
import score
import crz

def hlavicka(t):
    print("\n" + "=" * 66 + "\n" + t + "\n" + "=" * 66)


hlavicka("1. HTML entity")
pripady = {
    # Presne ten retazec zo stranky, vratane utatej poslednej entity.
    'Zmluva o dielo - &quot;Obnova ulice Sv.Štefana Veľký Meder&quot':
        'Zmluva o dielo - "Obnova ulice Sv. Štefana Veľký Meder"',
    'Chodníky &amp; cesty': 'Chodníky & cesty',
    '&lt;test&gt;': '<test>',
    '&#39;jednoduche&#39;': "'jednoduche'",
    # Dvojite zakodovanie — jedno kolo by nechalo &quot; v texte.
    '&amp;quot;dvojito&amp;quot;': '"dvojito"',
    # Nezlomitelna medzera sa ma stat obycajnou.
    'a&nbsp;b': 'a b',
}
for vstup, ocakavane in pripady.items():
    dostal = score.vycisti_predmet(vstup)
    assert dostal == ocakavane, f"{vstup!r}\n  dostal   {dostal!r}\n  cakal    {ocakavane!r}"
    print(f"  OK  {vstup[:52]:52} -> {dostal[:40]}")

hlavicka("2. Medzera po bodke sa doplna LEN pred velkym pismenom")
# Pravne formy sa NESMU rozbit — tych je v databaze desattisice.
nesmie_sa_zmenit = ['s.r.o.', 'a.s.', 'spol. s r.o.', 'č.12', 'SK.NACE',
                    'v.o.s.', 'k.s.', 'n.o.', '1.500 m2']
for t in nesmie_sa_zmenit:
    assert score._BODKA_BEZ_MEDZERY.sub(r"\1. \2", t) == t, t
    print(f"  OK  {t:16} nezmenene")
ma_sa_zmenit = {'Sv.Štefana': 'Sv. Štefana', 'ul.Hlavná': 'ul. Hlavná',
                'č.Z234/2026': 'č. Z234/2026', 'dielo.Obnova': 'dielo. Obnova'}
for t, o in ma_sa_zmenit.items():
    v = score._BODKA_BEZ_MEDZERY.sub(r"\1. \2", t)
    assert v == o, f"{t} -> {v}, cakal {o}"
    print(f"  OK  {t:16} -> {v}")

hlavicka("3. Ocistenie sa deje uz pri ukladani (crz._text)")
assert crz._text('&quot;X&quot;') == '"X"'
assert crz._text(None) is None, "None musi prejst nedotknute"
assert crz._text(123) == 123, "cislo sa nesmie previest na text"
print("  OK: entity ocistene, None a cisla nedotknute")

hlavicka("4. Ziadna vstupna hodnota nesmie vyhodit vynimku")
for zle in [None, '', '   ', '&', '&&&', '&#xxx;', '&quot', 0, 1.5, float('nan')]:
    score.vycisti_predmet(zle)
    crz._text(zle)
print("  OK: 10 hranicnych hodnot prezilo")

hlavicka("5. Koncova bodka: skratky sa NESMU okresat (chyba O1)")
# Stary `.strip(" .:;-")` robil dve skody: odsekol `;` z koncovej HTML
# entity (co vypadalo ako orezavanie textu o jeden znak a poslal ma
# hladat chybu do stahovania), a odsekaval koncovu bodku pravnych foriem.
pripady = {
    'Dodávka potravín pre ŠJ s.r.o.': 'Dodávka potravín pre ŠJ s.r.o.',
    'Služby a.s.':                     'Služby a.s.',
    'Poradenstvo n.o.':                'Poradenstvo n.o.',
    'Doprava v.o.s.':                  'Doprava v.o.s.',
    # Bezna koncova bodka sa odrezat MA.
    'Zmluva č. 15/2026.':              'Zmluva č. 15/2026',
    'Oprava ciest - II. etapa.':        'Oprava ciest - II. etapa',
    'Nákup techniky:':                 'Nákup techniky',
    # A entita s bodkocirkou uz nesmie o ten znak prist.
    'Zmluva - &quot;Obnova&quot;':      'Zmluva - "Obnova"',
}
for vstup, ocakavane in pripady.items():
    dostal = score.vycisti_predmet(vstup)
    assert dostal == ocakavane, f"{vstup!r} -> {dostal!r}, cakal {ocakavane!r}"
    print(f"  OK  {vstup[:44]:46} -> {dostal[:40]}")

print("\nVSETKY TESTY PRESLI\n")
