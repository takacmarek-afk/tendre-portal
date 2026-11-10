-- Test migracie 95 na PRAZDNEJ databaze so zjednodusenymi tabulkami.
-- createdb t95 && su postgres -c "cd <repo> && psql -q -X -At -d t95 -f tests/test_kontrola_trh_95.sql"
\set ON_ERROR_STOP on
do $$ begin create role authenticated; exception when others then null; end $$;
do $$ begin create role anon; exception when others then null; end $$;
do $$ begin create role service_role; exception when others then null; end $$;
create table public.contracts(id bigint primary key, supplier_cin text, authority_cin text, sector text, signed_on date, effective_from date, effective_to date, price_total numeric);
create table public.dodavatelia(supplier_cin text primary key, hlavny_sektor text);
create table public.opportunities(contract_id bigint, sector text, kraj text, authority_cin text, effective_to date, price_total numeric);
create table public.uvo_vysledky(sektor text, podpisane date, pocet_ponuk int, nuts text);
create table public.uvo_vyzvy(typ text, sektor text, lehota_ponuk timestamptz, nuts text);
-- zjednodusena povodna funkcia (len tvar odpovede)
create function public.kontrola_zmluv_ico(p_ico text) returns jsonb language sql as
$f$ select case when p_ico ~ '^\d{8}$' then jsonb_build_object('ok', true, 'ico', p_ico) else jsonb_build_object('ok', false) end $f$;
\i supabase/95_kontrola_trh_firmy.sql
\i supabase/95_kontrola_trh_firmy.sql
insert into public.contracts values
 (1,'123456','A1','OSTRAHA',current_date-100,null,current_date+200,50000),     -- moja zmluva, urad A1
 (2,'999','A1','OSTRAHA',current_date-100,null,current_date+100,80000),         -- cudzia, konci do roka
 (3,'999','A2','OSTRAHA',current_date-100,null,current_date+100,30000),         -- cudzia, iny kraj
 (4,'999','A1','OSTRAHA',current_date-100,null,current_date+500,10000);         -- cudzia, konci neskor
insert into public.dodavatelia values ('00123456','OSTRAHA');
insert into public.opportunities values
 (1,'OSTRAHA','Bratislavský kraj','A1',current_date+200,50000),
 (2,'OSTRAHA','Bratislavský kraj','A1',current_date+100,80000),
 (3,'OSTRAHA','Košický kraj','A2',current_date+100,30000),
 (4,'OSTRAHA','Bratislavský kraj','A1',current_date+500,10000);
insert into public.uvo_vysledky values ('OSTRAHA',current_date-30,1,'SK010'),('OSTRAHA',current_date-30,3,'SK0101'),
 ('OSTRAHA',current_date-30,1,'SK042'),('OSTRAHA',current_date-900,1,'SK010'),('IT_TECHNIKA',current_date-30,1,'SK010');
insert into public.uvo_vyzvy values ('sutaz','OSTRAHA',now()+interval '5 days','SK010'),('sutaz','OSTRAHA',now()-interval '1 day','SK010'),
 ('predbezne','OSTRAHA',now()+interval '5 days','SK010'),('sutaz','OSTRAHA',now()+interval '5 days','SK042');
do $$ declare r jsonb; t jsonb; begin
  r := public.kontrola_zmluv_ico('00123456'); t := r->'trh';
  assert r->>'ok' = 'true', r::text;
  assert t->>'sektor' = 'OSTRAHA', t::text;
  assert t->'kraje' = '["Bratislavský kraj"]'::jsonb, t::text;
  assert (t->>'prilezitosti_12m')::int = 1 and (t->>'prilezitosti_objem')::numeric = 80000, t::text;
  assert (t->>'vysledkov_24m')::int = 2 and (t->>'jedna_ponuka_24m')::int = 1, t::text;
  assert (t->>'otvorene_sutaze')::int = 1, t::text;
  r := public.kontrola_zmluv_ico('11111111');   -- firma bez zmluv: trh null, odpoved ok
  assert r->>'ok' = 'true' and (r->'trh' is null or r->'trh' = 'null'::jsonb), r::text;
  assert (public.kontrola_zmluv_ico('x')->>'ok') = 'false';
  raise notice 'test_kontrola_trh_95 OK';
end $$;
