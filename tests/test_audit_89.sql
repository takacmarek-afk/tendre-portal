-- Test migracie 75 (audit 8. 10. 2026). Pusti sa po migraciach 72, 74 a 75:
--   su postgres -c "psql -q -d <db> -f tests/test_audit_89.sql"
\set ON_ERROR_STOP on
\pset format unaligned
\pset tuples_only on
create or replace function public.je_zadarmo() returns boolean language sql immutable as $$ select false $$;
insert into public.contracts(id) select g from generate_series(1,40) g on conflict do nothing;
insert into public.opportunities(contract_id, kraj, sector, effective_to) values
 (1,'Bratislavsk kraj','UPRATOVANIE', current_date+100),
 (2,'Bratislavsk kraj','OSTRAHA', current_date+100),
 (3,'Kosick kraj','UPRATOVANIE', current_date+100),
 (4,'Nitriansk kraj','STRAVOVANIE', current_date+100),
 (5,'Bratislavsk kraj','IT', current_date+100) on conflict do nothing;
insert into public.subsidies(contract_id, kraj, sektor_odhad) values
 (11,'Bratislavsk kraj',null),(12,'Kosick kraj','UPRATOVANIE'),(13,'Nitriansk kraj',null),(14,'Bratislavsk kraj','IT') on conflict do nothing;
do $$
declare p record; u uuid; o uuid; i int := 0;
begin
  for p in select * from (values ('growth','aktivne', now()+interval '10 days', now()+interval '20 days'),
                                 ('start','aktivne', now()+interval '10 days', now()+interval '20 days'),
                                 ('start','aktivne', now()+interval '10 days', now()-interval '1 day'),
                                 ('team','aktivne', now()+interval '10 days', now()+interval '5 days')) v(plan,stav,tk,ok)
  loop
    i := i+1;
    u := ('c0000000-0000-0000-0000-00000000000'||i)::uuid;
    insert into auth.users(id,email) values (u, 'u'||i||'@t.sk') on conflict do nothing;
    insert into public.organizations(id,nazov) values (gen_random_uuid(), 'Org '||i) returning id into o;
    insert into public.memberships(user_id,org_id,rola) values (u,o,'owner');
    insert into public.subscriptions(org_id,plan,stav,trial_konci,obdobie_konci) values (o,p.plan,p.stav,p.tk,p.ok);
    insert into public.nastavenia_pouzivatela(user_id,kraje,sektory) values (u, array['Bratislavsk kraj'], array['UPRATOVANIE','OSTRAHA']) on conflict do nothing;
  end loop;
end $$;
grant select on auth.users to authenticated;
-- memberships vidi pouzivatel len svoje (RLS), preto si id organizacii zapamatame vopred.
create temp table orgy as select m.user_id, m.org_id from public.memberships m where m.user_id::text like 'c0000000-%';
grant select on orgy to authenticated;
create temp table v(nazov text, ocakavane text, skutocne text);
-- Povodna (pomala) verzia z migracie 68 - referencia pre porovnanie vysledkov.
create function public._stara_skryte_pocty() returns jsonb language plpgsql stable security definer set search_path = '' as $f$
declare p bigint; d bigint;
begin
  select count(*) into p from public.opportunities o
   where (o.effective_to is null or o.effective_to >= current_date)
     and not (public.start_kraj_ok(o.kraj) and public.start_sektor_ok(o.sector, false));
  select count(*) into d from public.subsidies s
   where not (public.start_kraj_ok(s.kraj) and public.start_sektor_ok(s.sektor_odhad, true));
  return jsonb_build_object('start', true, 'prilezitosti', p, 'dotacie', d);
end $f$;
grant execute on function public._stara_skryte_pocty() to authenticated;
grant all on v to authenticated;
set role authenticated;

select set_config('request.jwt.claim.sub','c0000000-0000-0000-0000-000000000001',false) \gset
insert into v select 'growth: skryte pocty', 'false|0|0',
  (select concat_ws('|', r->>'start', r->>'prilezitosti', r->>'dotacie') from (select public.start_skryte_pocty() r) x);
select set_config('request.jwt.claim.sub','c0000000-0000-0000-0000-000000000002',false) \gset
-- Start (BA + UPRATOVANIE/OSTRAHA): viditelne prilezitosti 1,2 -> skryte 3; dotacie viditelna 11 -> skryte 3
insert into v select 'start: skryte pocty = povodna verzia', (select concat_ws('|', r->>'start', r->>'prilezitosti', r->>'dotacie') from (select public._stara_skryte_pocty() r) x),
  (select concat_ws('|', r->>'start', r->>'prilezitosti', r->>'dotacie') from (select public.start_skryte_pocty() r) x);
insert into v select 'start: skryte pocty nie su 0', 'true',
  ((select (public.start_skryte_pocty()->>'prilezitosti')::int > 0))::text;
select set_config('request.jwt.claim.sub','c0000000-0000-0000-0000-000000000003',false) \gset
insert into v select 'start po obdobi: skryte pocty', 'false|0|0',
  (select concat_ws('|', r->>'start', r->>'prilezitosti', r->>'dotacie') from (select public.start_skryte_pocty() r) x);

-- odber: cudzia organizacia sa odmietne, vlastna alebo NULL prejde
select set_config('request.jwt.claim.sub','c0000000-0000-0000-0000-000000000002',false) \gset
select set_config('request.jwt.claims','{"sub":"c0000000-0000-0000-0000-000000000002","email":"u2@t.sk","role":"authenticated"}',false) \gset
do $$
declare cudzia uuid; vlastna uuid; ok1 boolean := false; ok2 boolean := false; ok3 boolean := false;
begin
  select m.org_id into cudzia from orgy m where m.user_id = 'c0000000-0000-0000-0000-000000000001';
  select m.org_id into vlastna from orgy m where m.user_id = 'c0000000-0000-0000-0000-000000000002';
  begin
    insert into public.odber(user_id, org_id, sektor, kraj, email) values ('c0000000-0000-0000-0000-000000000002', cudzia, 'IT', 'Bratislavsk kraj', 'u2@t.sk');
  exception when others then ok1 := true; end;
  begin
    insert into public.odber(user_id, org_id, sektor, kraj, email) values ('c0000000-0000-0000-0000-000000000002', vlastna, 'IT', 'Bratislavsk kraj', 'u2@t.sk');
    ok2 := true;
    update public.odber set org_id = null where user_id = 'c0000000-0000-0000-0000-000000000002';
    ok3 := true;
  exception when others then raise notice 'odber chyba: %', sqlerrm; end;
  insert into v values ('odber: cudzia org odmietnuta', 'true', ok1::text);
  insert into v values ('odber: vlastna org a NULL prejdu', 'true|true', ok2::text||'|'||ok3::text);
end $$;

reset role;

-- referrer: query a fragment sa odstrania
insert into public.navstevy(cesta, referrer) values ('/test-audit89', 'https://predtendrom.sk/prihlasenie?token=TAJNE#x');
insert into v select 'navstevy: referrer bez query', 'https://predtendrom.sk/prihlasenie',
  (select referrer from public.navstevy where cesta = '/test-audit89');
delete from public.navstevy where cesta = '/test-audit89';

-- prvych_100_dni_suhrn: nazov nad 80 znakov sa ignoruje
insert into v select 'suhrn: dlhy nazov', 'f|f',
  (select concat_ws('|', najdena, ma_data) from public.prvych_100_dni_suhrn(repeat('a', 5000), null));

-- platba: Team sa nezmeni na Growth, Growth ostava, chybajuci subscriptions riadok zlyha
do $$
declare ot uuid; og uuid; r1 uuid := gen_random_uuid(); r2 uuid := gen_random_uuid(); r3 uuid := gen_random_uuid(); orgx uuid; chyba boolean := false;
begin
  select m.org_id into ot from public.memberships m where m.user_id = 'c0000000-0000-0000-0000-000000000004';
  select m.org_id into og from public.memberships m where m.user_id = 'c0000000-0000-0000-0000-000000000001';
  insert into public.platby(reference, org_id, plan, obdobie, suma, stav) values (r1, ot, 'growth', 'mesiac', 89, 'vytvorena'), (r2, og, 'start', 'mesiac', 34, 'vytvorena');
  perform public.spracuj_platbu_stripe(r1, 'zaplatena', 'ok');
  perform public.spracuj_platbu_stripe(r2, 'zaplatena', 'ok');
  insert into v values ('platba: Team ostava Team', 'team', (select plan from public.subscriptions where org_id = ot));
  insert into v values ('platba: Growth + Start sa prepise na Start (bez zmeny logiky)', 'start', (select plan from public.subscriptions where org_id = og));
  insert into public.organizations(id, nazov) values (gen_random_uuid(), 'Bez predplatneho') returning id into orgx;
  delete from public.subscriptions where org_id = orgx;
  insert into public.platby(reference, org_id, plan, obdobie, suma, stav) values (r3, orgx, 'start', 'mesiac', 34, 'vytvorena');
  begin perform public.spracuj_platbu_stripe(r3, 'zaplatena', 'ok'); exception when others then chyba := true; end;
  insert into v values ('platba: chybajuce predplatne zlyha nahlas', 'true', chyba::text);
end $$;

drop function if exists public._stara_skryte_pocty();
select case when ocakavane = skutocne then 'OK   ' else 'FAIL ' end || nazov
       || case when ocakavane = skutocne then '' else ' (ocakavane ' || ocakavane || ', skutocne ' || coalesce(skutocne,'NULL') || ')' end from v;
select case when count(*) filter (where ocakavane is distinct from skutocne) = 0
            then 'VSETKO OK (' || count(*) || ' kontrol)' else 'NIEKTORE KONTROLY ZLYHALI' end from v;
