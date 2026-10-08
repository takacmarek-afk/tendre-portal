-- Test migracie 72: pravidla pristupu davaju rovnake vysledky ako pred opravou
-- a vyhodnocuju sa raz na dotaz. Pusti sa na cistej databaze po migracii 72:
--   su postgres -c "psql -q -d <db> -f tests/test_rychle_politiky.sql"
\set ON_ERROR_STOP on
\pset format unaligned
\pset tuples_only on
create or replace function public.je_zadarmo() returns boolean language sql immutable as $$ select false $$;
insert into public.contracts(id) select g from generate_series(1,40) g;
insert into public.opportunities(contract_id, kraj, sector, effective_to) values
 (1,'Bratislavský kraj','UPRATOVANIE', current_date+100),
 (2,'Bratislavský kraj','OSTRAHA', current_date+100),
 (3,'Košický kraj','UPRATOVANIE', current_date+100),
 (4,'Nitriansky kraj','STRAVOVANIE', current_date+100),
 (5,'Bratislavský kraj','IT', current_date+100);
insert into public.subsidies(contract_id, kraj, sektor_odhad) values
 (11,'Bratislavský kraj',null),(12,'Košický kraj','UPRATOVANIE'),(13,'Nitriansky kraj',null),(14,'Bratislavský kraj','IT');
insert into public.obce_ziadatelia(contract_id,obec,kraj) values (21,'X','Bratislavský kraj'),(22,'Y','Nitriansky kraj');
do $$
declare p record; u uuid; o uuid; i int := 0;
begin
  for p in select * from (values ('growth','aktivne', now()+interval '10 days', now()+interval '20 days'),
                                 ('start','aktivne', now()+interval '10 days', now()+interval '20 days'),
                                 ('start','aktivne', now()+interval '10 days', now()-interval '1 day')) v(plan,stav,tk,ok)
  loop
    i := i+1;
    u := ('c0000000-0000-0000-0000-00000000000'||i)::uuid;
    insert into auth.users(id,email) values (u, 'u'||i||'@t.sk');
    insert into public.organizations(id,nazov) values (gen_random_uuid(), 'Org '||i) returning id into o;
    insert into public.memberships(user_id,org_id,rola) values (u,o,'owner');
    insert into public.subscriptions(org_id,plan,stav,trial_konci,obdobie_konci) values (o,p.plan,p.stav,p.tk,p.ok);
    insert into public.nastavenia_pouzivatela(user_id,kraje,sektory) values (u, array['Bratislavský kraj'], array['UPRATOVANIE','OSTRAHA']);
  end loop;
end $$;
grant select on auth.users to authenticated;
create temp table vysledky(nazov text, ocakavane text, skutocne text);
grant all on vysledky to authenticated;
set role authenticated;

select set_config('request.jwt.claim.sub','c0000000-0000-0000-0000-000000000001',false) \gset
insert into vysledky select 'growth: prilezitosti', '5', count(*)::text from public.opportunities;
insert into vysledky select 'growth: dotacie', '4', count(*)::text from public.subsidies;
insert into vysledky select 'growth: ziadatelia', '2', count(*)::text from public.obce_ziadatelia;

select set_config('request.jwt.claim.sub','c0000000-0000-0000-0000-000000000002',false) \gset
-- Start: kraj Bratislavsky + sektor UPRATOVANIE/OSTRAHA -> prilezitosti 1, 2
-- dotacie: (11 BA null) ano, (14 BA IT) nie -> 1; ziadatelia: BA -> 1
insert into vysledky select 'start: prilezitosti', '2', count(*)::text from public.opportunities;
insert into vysledky select 'start: dotacie', '1', count(*)::text from public.subsidies;
insert into vysledky select 'start: ziadatelia', '1', count(*)::text from public.obce_ziadatelia;

select set_config('request.jwt.claim.sub','c0000000-0000-0000-0000-000000000003',false) \gset
-- Start s vyprsanym obdobim: nic
insert into vysledky select 'start po obdobi: prilezitosti', '0', count(*)::text from public.opportunities;
insert into vysledky select 'start po obdobi: dotacie', '0', count(*)::text from public.subsidies;

reset role;
select case when ocakavane = skutocne then 'OK   ' else 'FAIL ' end || nazov || ' (ocakavane ' || ocakavane || ', skutocne ' || skutocne || ')' from vysledky;

-- Pravidla maju InitPlan (vyhodnotenie raz na dotaz), nie volanie na riadok
select case when pg_get_expr(polqual, polrelid) ~ 'SELECT ma_aktivny_pristup' then 'OK   ' else 'FAIL ' end
       || 'opp_select pouziva InitPlan'
  from pg_policy where polname = 'opp_select';
select case when pg_get_expr(polqual, polrelid) ~ 'SELECT ma_pristup_k_dotaciam' then 'OK   ' else 'FAIL ' end
       || 'subsidies_select pouziva InitPlan'
  from pg_policy where polname = 'subsidies_select';
select case when pg_get_expr(polqual, polrelid) ~ 'SELECT ma_aktivny_pristup' then 'OK   ' else 'FAIL ' end
       || 'contracts_select pouziva InitPlan'
  from pg_policy where polname = 'contracts_select';
