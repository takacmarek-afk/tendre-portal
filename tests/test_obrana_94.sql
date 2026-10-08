-- Test migracie 78 (obrana vlastnych zmluv, vlna 94).
-- Pusti sa po 72, 74, 75, 76, 77, 78:  su postgres -c "psql -q -d <db> -f tests/test_obrana_94.sql"
\set ON_ERROR_STOP on
\pset format unaligned
\pset tuples_only on
create or replace function public.je_zadarmo() returns boolean language sql immutable as $$ select false $$;
insert into public.contracts(id, supplier_cin, supplier_name, authority_cin, authority_name, subject, effective_to, price_total, sector) values
 (9101,'55555555','Moja firma','900001','Urad A','Upratovanie A', current_date+90,  40000,'UPRATOVANIE'),
 (9102,'55555555','Moja firma','900002','Urad B','Ostraha B',     current_date+200, 60000,'OSTRAHA'),
 (9103,'55555555','Moja firma','900003','Urad C','Dlha zmluva',   current_date+500, 60000,'OSTRAHA'),  -- mimo 12 mesiacov
 (9104,'55555555','Moja firma','900004','Urad D','Uz skoncila',   current_date-5,   60000,'OSTRAHA'),
 (9105,'66666666','Iny dodavatel','900001','Urad A','Cudzia',     current_date+90,  40000,'UPRATOVANIE')
on conflict (id) do update set supplier_cin=excluded.supplier_cin, authority_cin=excluded.authority_cin, effective_to=excluded.effective_to, sector=excluded.sector;
insert into public.opportunities(contract_id, sector, effective_to, odhad_vyhlasenia) values
 (9101,'UPRATOVANIE', current_date+90, current_date+15) on conflict (contract_id) do update set odhad_vyhlasenia=excluded.odhad_vyhlasenia;
-- Uvo: posledna sutaz Uradu A v sektore UPRATOVANIE mala 4 ponuky (starsia 9), dnes vyhlasena nova sutaz
insert into public.uvo_vysledky(oznamenie_id, vestnik, obstaravatel_ico, sektor, pocet_ponuk, podpisane, vitaz_ico) values
 (1,'1/2026','900001','UPRATOVANIE', 9, current_date-900, 'x1'),
 (2,'2/2026','900001','UPRATOVANIE', 4, current_date-300, 'x2'),
 (3,'3/2026','900001','OSTRAHA',     7, current_date-100, 'x3');
insert into public.uvo_vyzvy(oznamenie_id, vestnik, typ, obstaravatel_ico, sektor, nazov, lehota_ponuk, publikovane, url) values
 (11,'4/2026','sutaz','900001','UPRATOVANIE','Upratovacie sluzby 2027', now()+interval '20 days', current_date-5, 'https://example.org/y1'),
 (12,'4/2026','sutaz','900002','OSTRAHA','Stara sutaz', now()-interval '200 days', current_date-210, 'https://example.org/y2'),
 (13,'4/2026','predbezne','900002','OSTRAHA','Predbezne oznamenie', now()+interval '20 days', current_date-1, 'https://example.org/y3');
do $$
declare o1 uuid; o2 uuid; o3 uuid;
begin
  insert into auth.users(id,email) values
   ('f0000000-0000-0000-0000-000000000001','m1@t.sk'),
   ('f0000000-0000-0000-0000-000000000002','m2@t.sk'),
   ('f0000000-0000-0000-0000-000000000003','m3@t.sk'),
   ('f0000000-0000-0000-0000-000000000004','clen@t.sk') on conflict do nothing;
  insert into public.organizations(id,nazov,ico) values (gen_random_uuid(),'MOrg 1','55555555') returning id into o1;
  insert into public.organizations(id,nazov,ico) values (gen_random_uuid(),'MOrg 2','55555555x') returning id into o2;
  insert into public.organizations(id,nazov,ico) values (gen_random_uuid(),'MOrg 3',null) returning id into o3;
  insert into public.memberships(user_id,org_id,rola) values
   ('f0000000-0000-0000-0000-000000000001',o1,'owner'),
   ('f0000000-0000-0000-0000-000000000004',o1,'member'),
   ('f0000000-0000-0000-0000-000000000002',o2,'owner'),
   ('f0000000-0000-0000-0000-000000000003',o3,'owner');
  insert into public.subscriptions(org_id,plan,stav,trial_konci,obdobie_konci) values
   (o1,'growth','aktivne', now()-interval '5 days', now()+interval '20 days'),
   (o2,'growth','aktivne', now()-interval '5 days', now()+interval '20 days'),
   (o3,'start','aktivne',  now()-interval '5 days', now()+interval '20 days');
end $$;
create temp table orgy as select m.user_id, m.org_id from public.memberships m where m.user_id::text like 'f0000000-%';
create temp table v(nazov text, ocakavane text, skutocne text);
grant all on v to authenticated, anon;
grant select on orgy to authenticated;

-- e-mail (service_role): dostane len vlastnik org1; 9101 s vyzvou 11; 9102 ma len stary/predbezny -> bez vyzvy
insert into v select 'nove vyzvy: len zmluva 9101 pre m1', '9101|m1@t.sk|ok',
  (select string_agg(contract_id||'|'||email||'|'||(case when vyzva_id=(select id from public.uvo_vyzvy where oznamenie_id=11) then 'ok' else 'ina' end), ',') from public.obrana_nove_vyzvy() where email like 'm_@t.sk');
insert into v select 'pocet ponuk naposledy = najnovsi vysledok (4), nie 9 ani OSTRAHA 7', '4',
  (select pocet_ponuk_naposledy::text from public.obrana_nove_vyzvy() where contract_id=9101);
insert into v select 'clen (nie vlastnik/admin) nedostane e-mail', '0', (select count(*)::text from public.obrana_nove_vyzvy() where email='clen@t.sk');
select public.oznac_obrana_alerty(m.org_id, array[9101::bigint], array[(select id from public.uvo_vyzvy where oznamenie_id=11)]) from public.memberships m where m.user_id='f0000000-0000-0000-0000-000000000001';
select public.oznac_obrana_alerty(m.org_id, array[9101::bigint], array[(select id from public.uvo_vyzvy where oznamenie_id=11)]) from public.memberships m where m.user_id='f0000000-0000-0000-0000-000000000001';
insert into v select 'po oznaceni uz nic (a opakovane oznacenie nezlyha)', '0', (select count(*)::text from public.obrana_nove_vyzvy() where email like 'm_@t.sk');
insert into v select 'dedup: 1 zaznam', '1', (select count(*)::text from public.obrana_alerty_odoslane where contract_id=9101);

-- appka (authenticated)
set role authenticated;
select set_config('request.jwt.claim.sub','f0000000-0000-0000-0000-000000000001',false) \gset
create temp table a1 as select * from public.obrana_moje_zmluvy();
insert into v select 'appka: moje zmluvy 9101 a 9102 (nie 9103 dlha, 9104 skoncila, 9105 cudzia)', '9101,9102', (select string_agg(contract_id::text, ',' order by contract_id) from a1);
insert into v select 'appka: odhad vyhlasenia a vyzva pri 9101', 'true|Upratovacie sluzby 2027', (select (odhad_vyhlasenia is not null)::text||'|'||vyzva_nazov from a1 where contract_id=9101);
insert into v select 'appka: 9102 bez vyzvy (stara sutaz, predbezne)', 'null', (select coalesce(vyzva_id::text,'null') from a1 where contract_id=9102);
select set_config('request.jwt.claim.sub','f0000000-0000-0000-0000-000000000002',false) \gset
insert into v select 'org s inym ICO nevidi cudzie zmluvy', '0', (select count(*)::text from public.obrana_moje_zmluvy());
select set_config('request.jwt.claim.sub','f0000000-0000-0000-0000-000000000003',false) \gset
insert into v select 'org bez ICO / Start: nic', '0', (select count(*)::text from public.obrana_moje_zmluvy());
select set_config('request.jwt.claim.sub','',false) \gset
insert into v select 'anonymny prihlaseny bez sub: nic', '0', (select count(*)::text from public.obrana_moje_zmluvy());
do $$ begin perform public.obrana_nove_vyzvy(); insert into v values ('klient vola obrana_nove_vyzvy','zakazane','povolene'); exception when insufficient_privilege then insert into v values ('klient vola obrana_nove_vyzvy','zakazane','zakazane'); end $$;
do $$ begin perform public._obrana_zmluvy('55555555'); insert into v values ('klient vola _obrana_zmluvy','zakazane','povolene'); exception when insufficient_privilege then insert into v values ('klient vola _obrana_zmluvy','zakazane','zakazane'); end $$;
do $$ begin perform 1 from public.obrana_alerty_odoslane; insert into v values ('klient cita dedup tabulku','zakazane','povolene'); exception when insufficient_privilege then insert into v values ('klient cita dedup tabulku','zakazane','zakazane'); end $$;
set role anon;
do $$ begin perform public.obrana_moje_zmluvy(); insert into v values ('anon vola obrana_moje_zmluvy','zakazane','povolene'); exception when insufficient_privilege then insert into v values ('anon vola obrana_moje_zmluvy','zakazane','zakazane'); end $$;
reset role;
select case when ocakavane = skutocne then 'OK   ' else 'CHYBA' end || ' ' || nazov || case when ocakavane = skutocne then '' else '  [ocakavane=' || ocakavane || ' skutocne=' || coalesce(skutocne,'NULL') || ']' end from v;
select 'CELKOM CHYB: ' || count(*) from v where ocakavane is distinct from skutocne;
