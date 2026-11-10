-- Test migracie 99 (createdb t99; psql -d t99 -f tests/test_eurofondy_vyhlasene_99.sql)
\set ON_ERROR_STOP on
do $$ begin create role authenticated; exception when others then null; end $$;
do $$ begin create role anon; exception when others then null; end $$;
create extension if not exists pgcrypto;
create schema if not exists extensions;
create schema if not exists auth;
create function auth.uid() returns uuid language sql as $f$ select '00000000-0000-0000-0000-000000000001'::uuid $f$;
create function public.ma_pro() returns boolean language sql as $f$ select true $f$;
create function public.ma_pro_pre_org(p uuid) returns boolean language sql as $f$ select p = '00000000-0000-0000-0000-0000000000aa'::uuid $f$;
create table auth.users(id uuid primary key, email text);
create table public.memberships(user_id uuid, org_id uuid);
create table public.nastavenia_pouzivatela(user_id uuid primary key, kraje text[] not null default '{}', sektory text[] not null default '{}');
do $$ begin create role service_role; exception when others then null; end $$;
create table public.contracts(id bigint primary key, supplier_cin text, authority_cin text, sector text, signed_on date, effective_from date, effective_to date, price_total numeric);
create table public.dodavatelia(supplier_cin text primary key, hlavny_sektor text);
create table public.opportunities(contract_id bigint, sector text, kraj text, authority_cin text, effective_to date, price_total numeric);
create table public.uvo_vysledky(sektor text, podpisane date, pocet_ponuk int, nuts text);
create table public.uvo_vyzvy(typ text, sektor text, lehota_ponuk timestamptz, nuts text);
\i supabase/97_itms_obstaravania.sql
\i supabase/98_eurofondy_pripravovane.sql
\i supabase/99_eurofondy_vyhlasene.sql
\i supabase/99_eurofondy_vyhlasene.sql
insert into public.itms_vo(id, nazov, stav, sektor, kraj, predpokladana_hodnota, itms_updated_at) values
 (1,'A','Pripravované','STAVEBNE_PRACE','Košický kraj',100,now()),
 (2,'B','Pripravované','STAVEBNE_PRACE','Košický kraj',200,now());
update public.itms_vo set vyhlasene_zistene_at = now(), vyhlasene_url = 'https://www.uvo.gov.sk/x' where id = 2;
select 'pripravovane: ' || (public.itms_pripravovane(array['STAVEBNE_PRACE'], array['Košický kraj'])->>'pocet');
do $$ begin
  if (public.itms_pripravovane(array['STAVEBNE_PRACE'], null)->>'pocet')::int <> 1 then raise exception 'vyhlasene sa ratalo'; end if;
end $$;
insert into auth.users values ('00000000-0000-0000-0000-000000000001','a@x.sk'),('00000000-0000-0000-0000-000000000002','b@x.sk');
insert into public.memberships values ('00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-0000000000aa'),
 ('00000000-0000-0000-0000-000000000002','00000000-0000-0000-0000-0000000000bb');   -- b bez pristupu
insert into public.nastavenia_pouzivatela values ('00000000-0000-0000-0000-000000000001','{Košický kraj}','{STAVEBNE_PRACE}'),
 ('00000000-0000-0000-0000-000000000002','{}','{STAVEBNE_PRACE}');
update public.itms_vo set vyhlasene_lehota = now() + interval '10 days' where id = 2;
do $$ begin
  if (select count(*) from public.eurofondy_vyhlasene_alerty(7)) <> 1 then raise exception 'alert: zly pocet'; end if;
  insert into public.eurofondy_alerty_odoslane values ('00000000-0000-0000-0000-000000000001', 2);
  if (select count(*) from public.eurofondy_vyhlasene_alerty(7)) <> 0 then raise exception 'alert: duplicita'; end if;
end $$;
select 'OK 99';
