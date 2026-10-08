-- Test migracie 73: hladanie v registri obci a prvych_100_dni_suhrn(ma_data, okres).
-- Pusti sa na cistej databaze po migracii 73 a po naplneni obce_register:
--   su postgres -c "psql -q -d <db> -f tests/test_register_obci.sql"
\set ON_ERROR_STOP on
\pset format unaligned
\pset tuples_only on
delete from public.opportunities where contract_id = 90000001;
delete from public.contracts where id = 90000001;
create temp table v(nazov text, ocakavane text, skutocne text);

-- obce z registra sa najdu aj bez zmluvy/dotacie (Trnavka je v dvoch krajoch)
insert into v select 'hladaj: Trnavka bez diakritiky', 'Trnavský kraj|Košický kraj',
  (select string_agg(kraj, '|' order by kraj desc) from public.hladaj_obec('trnavka') where nazov = 'Trnávka');
insert into v select 'hladaj: Revucka', 'Revúcka Lehota',
  (select string_agg(nazov, '|') from public.hladaj_obec('Revucka') where nazov = 'Revúcka Lehota');
insert into v select 'hladaj: nezmysel', '0', (select count(*)::text from public.hladaj_obec('xqzvw'));
insert into v select 'hladaj: prazdny retazec', '0', (select count(*)::text from public.hladaj_obec('  '));
insert into v select 'hladaj: limit 25', '25', (select count(*)::text from public.hladaj_obec('a'));
insert into v select 'hladaj: presna zhoda prva', 'Malacky',
  (select nazov from public.hladaj_obec('malacky') limit 1);

-- suhrn pre obec iba z registra
insert into v select 'suhrn: Revucka Lehota najdena', 't|f|Banskobystrický kraj|Okres Revúca|0|0',
  (select concat_ws('|', najdena, ma_data, kraj, okres, pocet_konciacich, pocet_dotacii_bezi)
     from public.prvych_100_dni_suhrn('Revúcka Lehota', null));
insert into v select 'suhrn: Trnavka s krajom', 't|f|Trnavský kraj|Okres Dunajská Streda',
  (select concat_ws('|', najdena, ma_data, kraj, okres) from public.prvych_100_dni_suhrn('Trnávka', 'Trnavský kraj'));
insert into v select 'suhrn: Trnavka druhy kraj', 'Okres Trebišov',
  (select okres from public.prvych_100_dni_suhrn('Trnávka', 'Košický kraj'));
insert into v select 'suhrn: neexistujuca obec', 'f|f',
  (select concat_ws('|', najdena, ma_data) from public.prvych_100_dni_suhrn('Neexistujuca Lehota', null));
insert into v select 'suhrn: prazdny nazov', 'false',
  (select najdena::text from public.prvych_100_dni_suhrn('', null));

-- obec s datami: ma_data=true a pocty sa pocitaju ako predtym
insert into public.contracts(id) values (90000001);
insert into public.opportunities(contract_id, authority_name, kraj, sector, effective_to, price_total)
  values (90000001, 'Obec Revúcka Lehota', 'Banskobystrický kraj', 'UPRATOVANIE', current_date + 100, 12345);
insert into v select 'suhrn: obec s datami', 't|t|1|12345|Okres Revúca',
  (select concat_ws('|', najdena, ma_data, pocet_konciacich, objem_konciacich, okres)
     from public.prvych_100_dni_suhrn('Revúcka Lehota', null));
insert into v select 'hladaj: obec z dat a z registra sa nezdvoji', '1',
  (select count(*)::text from public.hladaj_obec('Revúcka Lehota'));

-- tabulka je zamknuta pre anon aj authenticated
insert into v select 'obce_register: anon nema grant', 'false',
  has_table_privilege('anon', 'public.obce_register', 'select')::text;
insert into v select 'obce_register: authenticated nema grant', 'false',
  has_table_privilege('authenticated', 'public.obce_register', 'select')::text;

select case when ocakavane = skutocne then 'OK   ' else 'CHYBA' end || ' ' || nazov
       || case when ocakavane = skutocne then '' else '  (ocakavane=' || ocakavane || ', skutocne=' || coalesce(skutocne,'NULL') || ')' end
  from v;
select case when count(*) filter (where ocakavane is distinct from skutocne) = 0
            then 'VSETKO OK (' || count(*) || ' kontrol)' else 'NIEKTORE KONTROLY ZLYHALI' end from v;
