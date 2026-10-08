-- Test migracie 74: stlpce vyplatene/vyplatene_fy a prvych_100_dni_suhrn bez vyplatenych.
-- Pusti sa na databaze po migracii 74:
--   su postgres -c "psql -q -d <db> -f tests/test_vyplatene_dotacie.sql"
\set ON_ERROR_STOP on
\pset format unaligned
\pset tuples_only on
delete from public.subsidies where contract_id in (90000011, 90000012, 90000013, 90000111);
delete from public.contracts where id in (90000011, 90000012, 90000013, 90000111);
create temp table v(nazov text, ocakavane text, skutocne text);

insert into v select 'stlpec vyplatene existuje a je not null', 'boolean|NO',
  (select data_type || '|' || is_nullable from information_schema.columns
    where table_schema = 'public' and table_name = 'subsidies' and column_name = 'vyplatene');
insert into v select 'stlpec vyplatene_fy existuje', 'text',
  (select data_type from information_schema.columns
    where table_schema = 'public' and table_name = 'subsidies' and column_name = 'vyplatene_fy');

insert into public.contracts(id) values (90000011), (90000012), (90000013), (90000111);

-- Tri dotacie pre Obec Testovacia Lehota: jedna vyplatena, dve nie.
insert into public.subsidies(contract_id, prijimatel, kraj, suma, okno_od, okno_do, vyplatene, vyplatene_fy)
values (90000011, 'Obec Testovacia Lehota', 'Zilinsky kraj', 10000, current_date + 10, current_date + 300, true,  'FY2025'),
       (90000012, 'Obec Testovacia Lehota', 'Zilinsky kraj', 20000, current_date + 10, current_date + 300, false, null),
       (90000013, 'Obec Testovacia Lehota', 'Zilinsky kraj', 30000, current_date + 10, current_date + 300, false, null);

insert into v select 'vyplatena sa do suhrnu nepocita', '2|50000',
  (select pocet_dotacii_bezi || '|' || objem_dotacii_bezi::bigint
     from public.prvych_100_dni_suhrn('Testovacia Lehota', null));
insert into v select 'obec s dotaciami ma_data', 't|t',
  (select concat_ws('|', najdena, ma_data) from public.prvych_100_dni_suhrn('Testovacia Lehota', null));

-- Predvolena hodnota pre riadky bez udaju.
insert into public.subsidies(contract_id, prijimatel, kraj, suma) values (90000111, 'Obec Testovacia Lehota', 'Zilinsky kraj', 5000)
  on conflict do nothing;
insert into v select 'predvolene vyplatene = false', 'false',
  (select vyplatene::text from public.subsidies where contract_id = 90000111);

delete from public.subsidies where contract_id in (90000011, 90000012, 90000013, 90000111);
delete from public.contracts where id in (90000011, 90000012, 90000013, 90000111);

select case when ocakavane = skutocne then 'OK   ' else 'CHYBA' end || ' ' || nazov
       || case when ocakavane = skutocne then '' else '  (ocakavane=' || ocakavane || ', skutocne=' || coalesce(skutocne,'NULL') || ')' end
  from v;
select case when count(*) filter (where ocakavane is distinct from skutocne) = 0
            then 'VSETKO OK (' || count(*) || ' kontrol)' else 'NIEKTORE KONTROLY ZLYHALI' end from v;
