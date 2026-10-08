"""Cele citanie tabulky po strankach.

PREC: PostgREST (Supabase) vracia najviac 1 000 riadkov na jeden dotaz a
NEHLASI chybu — rozdiel je potichu orezany. Overene 8. 10. 2026 na zivej
databaze: `opportunities` ma 1 142 riadkov, dotaz bez stranok vratil 1 000.
Kazde citanie, ktore moze prekrocit tisic riadkov, musi ist cez tuto funkciu.

Pouzitie:  vsetky(lambda od, do: sb.table("x").select("a,b").order("a").range(od, do).execute())
Dotaz MUSI mat `.order()` na unikatnom (alebo zlozenom unikatnom) kluci, inak
sa riadky medzi strankami mozu opakovat alebo vynechat.
"""

STRANKA = 1000


def vsetky(dotaz_fn, stranka: int = STRANKA):
    vysledok, od = [], 0
    while True:
        davka = dotaz_fn(od, od + stranka - 1).data or []
        vysledok.extend(davka)
        if len(davka) < stranka:
            return vysledok
        od += stranka
