-- Test migracie 94 na PRAZDNEJ databaze so zjednodusenymi tabulkami.
-- createdb t94 && su postgres -c "cd <repo> && psql -q -X -At -d t94 -f tests/test_kolega_z_domeny_94.sql"
\set ON_ERROR_STOP on
do $$ begin create role authenticated; exception when others then null; end $$;
do $$ begin create role anon; exception when others then null; end $$;
create schema auth;
create function auth.uid() returns uuid language sql as $f$ select nullif(current_setting('t.uid', true), '')::uuid $f$;
create table auth.users(id uuid primary key, email text, email_confirmed_at timestamptz);
create table public.organizations(id uuid primary key, ico text);
create table public.memberships(user_id uuid, org_id uuid, rola text);
create table public.events(org_id uuid, user_id uuid, typ text, detail jsonb);
\i supabase/94_kolega_z_domeny.sql
insert into auth.users values
 ('00000000-0000-0000-0000-00000000000a','erik@firma.sk',now()),
 ('00000000-0000-0000-0000-00000000000b','jana@FIRMA.sk',now()),
 ('00000000-0000-0000-0000-00000000000c','tretia@firma.sk',now()),
 ('00000000-0000-0000-0000-00000000000d','cudzi@ina.sk',now()),
 ('00000000-0000-0000-0000-00000000000e','neoverena@firma.sk',null),
 ('00000000-0000-0000-0000-00000000000f','owner@gmail.com',now()),
 ('00000000-0000-0000-0000-000000000010','iny@gmail.com',now());
insert into public.organizations values ('10000000-0000-0000-0000-000000000001','36177083'),('10000000-0000-0000-0000-000000000002','11111111');
insert into public.memberships values ('00000000-0000-0000-0000-00000000000a','10000000-0000-0000-0000-000000000001','owner'),
 ('00000000-0000-0000-0000-00000000000f','10000000-0000-0000-0000-000000000002','owner');
create function pripoj(u text, ico text) returns text language plpgsql as $f$
begin perform set_config('t.uid', u, false); return public.pripoj_sa_k_firme(ico)->>'kod'; end $f$;
do $$ begin
  assert pripoj('00000000-0000-0000-0000-00000000000d','36177083') = 'INA_DOMENA';     -- cudzia domena, IČO nestaci
  assert pripoj('00000000-0000-0000-0000-00000000000e','36177083') = 'INA_DOMENA';     -- neovereny e-mail
  assert pripoj('00000000-0000-0000-0000-000000000010','11111111') = 'INA_DOMENA';     -- gmail k gmailu nie
  assert pripoj('00000000-0000-0000-0000-00000000000b','99999999') = 'INA_DOMENA';     -- ina firma
  assert pripoj('00000000-0000-0000-0000-00000000000b','SK 36 177 083') = 'PRIPOJENY';
  assert pripoj('00000000-0000-0000-0000-00000000000b','36177083') = 'UZ_V_FIRME';
  assert pripoj('00000000-0000-0000-0000-00000000000c','36177083') = 'MIESTA_PLNE';    -- 1 kolega navyse
  assert (select rola from public.memberships where user_id='00000000-0000-0000-0000-00000000000b') = 'member';
  assert (select count(*) from public.events where typ='kolega_pripojeny_domenou') = 1;
  raise notice 'test_kolega_z_domeny_94 OK';
end $$;
