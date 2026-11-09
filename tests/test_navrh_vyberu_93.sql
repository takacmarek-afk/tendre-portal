-- Test migracie 93 (navrh_vyberu) na PRAZDNEJ databaze so zjednodusenymi tabulkami.
-- createdb t93 && su postgres -c "cd <repo> && psql -q -X -At -d t93 -f tests/test_navrh_vyberu_93.sql"
\set ON_ERROR_STOP on
do $$ begin create role authenticated; exception when others then null; end $$;
do $$ begin create role anon; exception when others then null; end $$;
create schema auth;
create function auth.uid() returns uuid language sql as $f$ select current_setting('t.uid')::uuid $f$;
create table public.organizations(id uuid primary key, ico text);
create table public.memberships(user_id uuid, org_id uuid);
create table public.contracts(id bigint primary key, sector text, authority_cin text, supplier_cin text, signed_on date, effective_from date);
create table public.opportunities(contract_id bigint, authority_cin text, kraj text, refreshed_at timestamptz default now());
\i supabase/93_navrh_vyberu.sql
insert into public.organizations values ('00000000-0000-0000-0000-000000000001','00123456'),('00000000-0000-0000-0000-000000000002','99999999');
insert into public.memberships values ('10000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000001'),('10000000-0000-0000-0000-000000000002','00000000-0000-0000-0000-000000000002');
insert into public.contracts values
 (1,'STAVEBNE_PRACE','A1','123456',current_date-100,null),
 (2,'STAVEBNE_PRACE','A2','00123456',current_date-200,null),
 (3,'STAVEBNE_PRACE','A1','00123456',current_date-300,null),
 (4,'ODPAD','A3','00123456',null,current_date-50),
 (5,'IT_TECHNIKA','A1','00123456',current_date-3000,null),
 (6,'UPRATOVANIE','A9','00123456',current_date-10,null),
 (7,'UPRATOVANIE','A9','00123456',current_date-10,null),
 (8,'STAVEBNE_PRACE','A1','77777777',current_date-10,null);
insert into public.opportunities values (100,'A1','Prešovský kraj'),(101,'A2','Košický kraj'),(102,'A3','Košický kraj'),(103,'A1','Prešovský kraj');
do $$ declare r jsonb; begin
  perform set_config('t.uid','10000000-0000-0000-0000-000000000001',false);
  r := public.navrh_vyberu();
  assert r->>'zmluv' = '6', r::text;                                  -- bez cudzej a bez 8-rocnej zmluvy
  assert r->'sektory' = '["STAVEBNE_PRACE","UPRATOVANIE"]'::jsonb, r::text;
  assert r->'kraje' = '["Košický kraj","Prešovský kraj"]'::jsonb, r::text;  -- A9 bez kraja sa nehada
  perform set_config('t.uid','10000000-0000-0000-0000-000000000002',false);
  r := public.navrh_vyberu();
  assert r = '{"zmluv":0,"sektory":[],"kraje":[]}'::jsonb, r::text;
  raise notice 'test_navrh_vyberu_93 OK';
end $$;
