\set ON_ERROR_STOP on
do $$ begin create role authenticated; exception when others then null; end $$;
do $$ begin create role anon; exception when others then null; end $$;
do $$ begin create role service_role; exception when others then null; end $$;
create table public.contracts(id int);
create function public.rpc_citaj_contracts_pre_analyzu_69() returns setof public.contracts language sql security definer as $f$ select * from public.contracts $f$;
\i supabase/101_audit_bezpecnost.sql
\i supabase/101_audit_bezpecnost.sql
do $$ begin
  if has_function_privilege('anon', 'public.rpc_citaj_contracts_pre_analyzu_69()', 'EXECUTE') then raise exception 'anon stale smie'; end if;
  if has_function_privilege('anon', 'public.anon_definer_funkcie()', 'EXECUTE') then raise exception 'kontrola verejna'; end if;
  if exists (select 1 from public.anon_definer_funkcie() where proname = 'rpc_citaj_contracts_pre_analyzu_69') then raise exception 'zoznam'; end if;
end $$;
select 'OK 101';
