-- Test migracie 77 (upozornenie na koniec zmluvy sledovanej firmy, vlna 93).
-- Pusti sa po 72, 74, 75, 76, 77:  su postgres -c "psql -q -d <db> -f tests/test_upozornenie_93.sql"
\set ON_ERROR_STOP on
\pset format unaligned
\pset tuples_only on
create or replace function public.je_zadarmo() returns boolean language sql immutable as $$ select false $$;
insert into public.contracts(id, supplier_cin, supplier_name, authority_name, subject, effective_to, price_total) values
 (9001,'11111111','Konkurent A','Urad 1','Upratovanie 1', current_date+30,  50000),
 (9002,'11111111','Konkurent A','Urad 2','Upratovanie 2', current_date+300, 70000),  -- mimo okna 180 dni
 (9003,'11111111','Konkurent A','Urad 3','Mala zmluva',   current_date+20,  1000),    -- pod 5000
 (9004,'11111111','Konkurent A','Urad 4','Uz skoncila',   current_date-3,   90000),
 (9005,'22222222','Konkurent B','Urad 5','Ostraha 5',     current_date+60,  80000),
 (9006,'33333333','Nesledovany','Urad 6','Cudzia',        current_date+60,  80000)
on conflict (id) do update set supplier_cin=excluded.supplier_cin, effective_to=excluded.effective_to, price_total=excluded.price_total;
do $$
declare o1 uuid; o2 uuid; o3 uuid;
begin
  insert into auth.users(id,email) values
   ('e0000000-0000-0000-0000-000000000001','o1@t.sk'),
   ('e0000000-0000-0000-0000-000000000002','o2@t.sk'),
   ('e0000000-0000-0000-0000-000000000003','o3@t.sk'),
   ('e0000000-0000-0000-0000-000000000004','clen@t.sk') on conflict do nothing;
  insert into public.organizations(id,nazov) values (gen_random_uuid(),'GOrg 1') returning id into o1;
  insert into public.organizations(id,nazov) values (gen_random_uuid(),'GOrg 2') returning id into o2;
  insert into public.organizations(id,nazov) values (gen_random_uuid(),'GOrg 3') returning id into o3;
  insert into public.memberships(user_id,org_id,rola) values
   ('e0000000-0000-0000-0000-000000000001',o1,'owner'),
   ('e0000000-0000-0000-0000-000000000004',o1,'member'),
   ('e0000000-0000-0000-0000-000000000002',o2,'owner'),
   ('e0000000-0000-0000-0000-000000000003',o3,'owner');
  -- o1 Growth aktivne, o2 Start aktivne (nema Pro), o3 Growth ale skoncene
  insert into public.subscriptions(org_id,plan,stav,trial_konci,obdobie_konci) values
   (o1,'growth','aktivne', now()-interval '5 days', now()+interval '20 days'),
   (o2,'start','aktivne',  now()-interval '5 days', now()+interval '20 days'),
   (o3,'growth','aktivne', now()-interval '50 days', now()-interval '2 days');
  insert into public.sledovane_ico(org_id,ico,nazov) values
   (o1,'11111111','Konkurent A (nazov v zozname)'), (o1,'22222222',null),
   (o2,'11111111',null), (o3,'11111111',null);
end $$;
create temp table v(nazov text, ocakavane text, skutocne text);
insert into v select 'org1: zmluvy 9001 a 9005 (nie 9002 okno, 9003 cena, 9004 skoncila, 9006 cudzia)', '9001,9005',
  (select string_agg(contract_id::text, ',' order by contract_id) from public.sledovane_konciace_alerty() where email='o1@t.sk');
insert into v select 'iba vlastnik/admin dostane e-mail (clen nie)', '0',
  (select count(*)::text from public.sledovane_konciace_alerty() where email='clen@t.sk');
insert into v select 'Start nema Pro -> ziadny alert', '0', (select count(*)::text from public.sledovane_konciace_alerty() where email='o2@t.sk');
insert into v select 'skoncene predplatne -> ziadny alert', '0', (select count(*)::text from public.sledovane_konciace_alerty() where email='o3@t.sk');
insert into v select 'nazov firmy z dodavatelia/sledovane', 'Konkurent A',
  (select split_part(nazov_firmy,' (',1) from public.sledovane_konciace_alerty() where contract_id=9001 and email='o1@t.sk');
insert into v select 'siroke okno 365 dni prinesie aj 9002', '9001,9002,9005',
  (select string_agg(contract_id::text, ',' order by contract_id) from public.sledovane_konciace_alerty(365) where email='o1@t.sk');
-- po oznaceni 9001 uz nepride, 9005 ano
select public.oznac_sledovane_alerty(m.org_id, array['11111111'], array[9001::bigint]) from public.memberships m where m.user_id='e0000000-0000-0000-0000-000000000001';
insert into v select 'po oznaceni 9001 ostava 9005', '9005',
  (select string_agg(contract_id::text, ',' order by contract_id) from public.sledovane_konciace_alerty() where email='o1@t.sk');
-- opakovane oznacenie nezlyha
select public.oznac_sledovane_alerty(m.org_id, array['11111111'], array[9001::bigint]) from public.memberships m where m.user_id='e0000000-0000-0000-0000-000000000001';
insert into v select 'opakovane oznacenie bez chyby, 1 zaznam', '1', (select count(*)::text from public.sledovane_alerty_odoslane where contract_id=9001);
-- pristup klienta
grant all on v to authenticated, anon;
set role authenticated;
do $$ begin perform public.sledovane_konciace_alerty(); insert into v values ('klient vola sledovane_konciace_alerty','zakazane','povolene'); exception when insufficient_privilege then insert into v values ('klient vola sledovane_konciace_alerty','zakazane','zakazane'); end $$;
do $$ begin perform 1 from public.sledovane_alerty_odoslane; insert into v values ('klient cita tabulku dedupu','zakazane','povolene'); exception when insufficient_privilege then insert into v values ('klient cita tabulku dedupu','zakazane','zakazane'); end $$;
reset role;
select case when ocakavane = skutocne then 'OK   ' else 'CHYBA' end || ' ' || nazov || case when ocakavane = skutocne then '' else '  [ocakavane=' || ocakavane || ' skutocne=' || coalesce(skutocne,'NULL') || ']' end from v;
select 'CELKOM CHYB: ' || count(*) from v where ocakavane is distinct from skutocne;
