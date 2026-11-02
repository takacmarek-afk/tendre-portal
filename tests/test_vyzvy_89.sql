-- Test migracie 89 (vyzvy pre obce). Kazdy riadok vypisu: "nazov|t".
\set ON_ERROR_STOP on
\pset format unaligned
\pset tuples_only on

insert into public.obce_register(kod, nazov, kraj, okres, ico, pocet_obyvatelov, nro, mrk)
values ('SK0328599999', 'Testovo', 'Banskobystrický kraj', 'Okres Revúca', '00999999', 812, true, false)
on conflict (kod) do nothing;

-- vzor JSON sa da vlozit 1:1
\set vzor `cat supabase/vzory/vyzva_karta_vzor.json`
insert into public.vyzvy_karty select * from jsonb_populate_record(null::public.vyzvy_karty,
    (:'vzor'::jsonb) || jsonb_build_object('vytvorene_at', now(), 'upravene_at', now()));

select 'vzor vlozeny, neovereny', overene_at is null from public.vyzvy_karty where kod = 'VZOR-EF-ZD-2027';
select 'neoverena karta sa nezobrazi', public.karta_vyzvy('VZOR-EF-ZD-2027', null) is null;

update public.vyzvy_karty set overil = 'marek', overene_at = now() where kod = 'VZOR-EF-ZD-2027';
select 'overenie ulozene', overene_at is not null from public.vyzvy_karty where kod = 'VZOR-EF-ZD-2027';
select 'karta bez tokenu: obec null', (public.karta_vyzvy('VZOR-EF-ZD-2027', null) -> 'obec') = 'null'::jsonb
    or public.karta_vyzvy('VZOR-EF-ZD-2027', null) -> 'obec' is null;
select 'karta bez interneho poľa overil', not (public.karta_vyzvy('VZOR-EF-ZD-2027', null) -> 'vyzva') ? 'overil';

select 'karta s tokenom: obec', (public.karta_vyzvy('VZOR-EF-ZD-2027',
    (select karta_token from public.obce_register where kod='SK0328599999')) -> 'obec' ->> 'nazov') = 'Testovo';

select 'semafor zly token', (public.uloz_semafor(gen_random_uuid(), 'VZOR-EF-ZD-2027', '{"q1":"ano"}') ->> 'kod') = 'NEZNAMY_TOKEN';
select 'semafor zly kluc', (public.uloz_semafor((select karta_token from public.obce_register where kod='SK0328599999'),
    'VZOR-EF-ZD-2027', '{"q8":"ano"}') ->> 'kod') = 'ZLY_FORMAT';
select 'semafor zla hodnota', (public.uloz_semafor((select karta_token from public.obce_register where kod='SK0328599999'),
    'VZOR-EF-ZD-2027', '{"q1":"<script>"}') ->> 'kod') = 'ZLY_FORMAT';
select 'semafor ulozeny', (public.uloz_semafor((select karta_token from public.obce_register where kod='SK0328599999'),
    'VZOR-EF-ZD-2027', '{"q1":"ano","q2":"nie","q3":"neviem"}') ->> 'kod') = 'ULOZENE';
select 'semafor prepisany', (public.uloz_semafor((select karta_token from public.obce_register where kod='SK0328599999'),
    'VZOR-EF-ZD-2027', '{"q1":"nie"}') ->> 'ok')::boolean;
select 'semafor ma novu hodnotu', (select odpovede ->> 'q1' from public.vyzvy_semafor where kod_obce='SK0328599999') = 'nie';
select 'karta vrati odpovede', (public.karta_vyzvy('VZOR-EF-ZD-2027',
    (select karta_token from public.obce_register where kod='SK0328599999')) -> 'odpovede' ->> 'q1') = 'nie';

-- zmena obsahu zrusi overenie
update public.vyzvy_karty set nfp_max = 500000 where kod = 'VZOR-EF-ZD-2027';
select 'zmena zrusi overenie', overene_at is null and overil is null from public.vyzvy_karty where kod = 'VZOR-EF-ZD-2027';

-- kontroly integrity
do $$ begin
  begin insert into public.vyzvy_karty(kod,nazov,poskytovatel,zdroj_url,typ_ziadatela,spoluucast_pct,dph_opravnena,financovanie,overil)
        values ('X1','x','x','https://x.sk','{obec}',5,'ano','refundacia','marek');
        raise exception 'overil bez overene_at presiel';
  exception when check_violation then null; end;
  begin insert into public.vyzvy_karty(kod,nazov,poskytovatel,zdroj_url,typ_ziadatela,spoluucast_pct,dph_opravnena,financovanie,obyv_min,obyv_max)
        values ('X2','x','x','https://x.sk','{obec}',5,'ano','refundacia',5000,100);
        raise exception 'obyv_min > obyv_max presiel';
  exception when check_violation then null; end;
  begin insert into public.vyzvy_karty(kod,nazov,poskytovatel,zdroj_url,typ_ziadatela,spoluucast_pct,dph_opravnena,financovanie)
        values ('X3','x','x','http://x.sk','{obec}',5,'ano','refundacia');
        raise exception 'http presiel';
  exception when check_violation then null; end;
end $$;
select 'integrita', true;

select 'anon nesmie citat tabulku', not has_table_privilege('anon','public.vyzvy_karty','select');
select 'anon smie kartu', has_function_privilege('anon','public.karta_vyzvy(text,uuid)','execute');
select 'anon nesmie signaly', not has_function_privilege('anon','public.vyzvy_signaly_obci()','execute');
select 'signaly obce', (select count(*) from public.vyzvy_signaly_obci() where kod='SK0328599999') = 1;
