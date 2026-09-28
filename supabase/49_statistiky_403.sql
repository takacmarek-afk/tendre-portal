-- =============================================================================
--  49 — ŠTATISTIKY LEN PRE ADMINA: nie prázdny výsledok, ale 403
--  Audit 27. 9. 2026 (P0.2): volanie API štatistík bežným používateľom má
--  vrátiť 403, nie prázdne dáta.
--
--  DOTERAZ: funkcie navstevnost_* a merania_* mali v tele `where
--  public.je_admin()` — bežný používateľ dostal 200 a prázdny zoznam.
--  Nič neuniklo (overené 28. 9. 2026 simuláciou ne-admin JWT: 0 riadkov
--  zo všetkých šiestich funkcií aj z tabuliek navstevy/udalosti, ktoré
--  majú len INSERT politiku), ale odpoveď neprezrádzala, že ide o zákaz.
--
--  TERAZ: public.vyzaduj_admina() vráti true pre admina a inak vyhodí
--  chybu s kódom 42501 (insufficient_privilege), ktorú PostgREST vracia
--  ako HTTP 403. Tento skript prepíše existujúce definície funkcií
--  (pg_get_functiondef) — nahradí v nich `public.je_admin()` za
--  `public.vyzaduj_admina()` a nič iné nemení.
--
--  POZOR: ak by sa niekedy znova spustili 27/45/46, vrátia pôvodné správanie
--  (prázdny výsledok). Potom treba spustiť aj tento skript. Spustiť sa dá
--  opakovane.
-- =============================================================================

create or replace function public.vyzaduj_admina()
returns boolean
language plpgsql
stable
security definer
set search_path = public
as $$
begin
    if not public.je_admin() then
        raise exception 'Len pre administrátora.' using errcode = '42501';
    end if;
    return true;
end;
$$;

revoke all on function public.vyzaduj_admina() from public;
revoke all on function public.vyzaduj_admina() from anon;
grant execute on function public.vyzaduj_admina() to authenticated;

do $$
declare
    f record;
    def text;
    pocet int := 0;
begin
    for f in
        select p.oid, p.proname
          from pg_proc p join pg_namespace n on n.oid = p.pronamespace
         where n.nspname = 'public'
           and p.proname in ('navstevnost_denne', 'navstevnost_stranky', 'navstevnost_referreri',
                             'merania_rebricek', 'merania_zdroje', 'merania_suhlas')
    loop
        def := pg_get_functiondef(f.oid);
        if position('public.je_admin()' in def) > 0 then
            execute replace(def, 'public.je_admin()', 'public.vyzaduj_admina()');
            pocet := pocet + 1;
        end if;
    end loop;
    raise notice 'Upravených funkcií: %', pocet;
end;
$$;

select string_agg(p.proname || '=' ||
       case when position('vyzaduj_admina' in pg_get_functiondef(p.oid)) > 0 then 'ok' else 'NEUPRAVENE' end,
       ', ' order by p.proname) as vysledok
  from pg_proc p join pg_namespace n on n.oid = p.pronamespace
 where n.nspname = 'public'
   and p.proname in ('navstevnost_denne', 'navstevnost_stranky', 'navstevnost_referreri',
                     'merania_rebricek', 'merania_zdroje', 'merania_suhlas');
