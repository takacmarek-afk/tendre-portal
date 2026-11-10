-- =============================================================================
--  101 - AUDIT 10. 11. 2026: ZABUDNUTA FUNKCIA A KONTROLA VEREJNYCH FUNKCII
--  Vloz do Supabase: SQL Editor -> New query -> Run. Spustit sa da opakovane.
-- =============================================================================
--  1) rpc_citaj_contracts_pre_analyzu_69 (jednorazova analyza, nie je v repozitari)
--     vracala celu tabulku contracts cez SECURITY DEFINER a smel ju volat aj
--     anonymny navstevnik. Odoberame pravo volat ju komukolvek okrem servisu.
--     Funkciu nemazeme (ziadne data sa nemenia), len ju zamykame.
--  2) anon_definer_funkcie(): zoznam SECURITY DEFINER funkcii, ktore smie volat
--     anon. Denna kontrola (pipeline/zdravie_dat.py) upozorni na nove.
-- =============================================================================

do $$
begin
    if exists (select 1 from pg_proc p join pg_namespace n on n.oid = p.pronamespace
                where n.nspname = 'public' and p.proname = 'rpc_citaj_contracts_pre_analyzu_69') then
        execute 'revoke all on function public.rpc_citaj_contracts_pre_analyzu_69() from public, anon, authenticated';
    end if;
end $$;

create or replace function public.anon_definer_funkcie()
returns table (proname name)
language sql
stable
security definer
set search_path = ''
as $$
    select p.proname
      from pg_catalog.pg_proc p
      join pg_catalog.pg_namespace n on n.oid = p.pronamespace
     where n.nspname = 'public'
       and p.prosecdef
       and has_function_privilege('anon', p.oid, 'EXECUTE')
     order by 1;
$$;

revoke all on function public.anon_definer_funkcie() from public, anon, authenticated;
grant execute on function public.anon_definer_funkcie() to service_role;

select 'Migracia 101 hotova: zabudnuta funkcia zamknuta, kontrola verejnych funkcii.' as vysledok;
