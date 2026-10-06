\set ON_ERROR_STOP off
\pset format unaligned
\pset fieldsep ' | '
create or replace function public.je_zadarmo() returns boolean language sql immutable as $$ select false $$;
insert into public.contracts(id) select g from generate_series(1,6) g;
insert into public.opportunities(contract_id, kraj, sector, effective_to) values
 (1,'Bratislavský kraj','UPRATOVANIE', current_date+100),
 (2,'Bratislavský kraj','OSTRAHA', current_date+100),
 (3,'Košický kraj','UPRATOVANIE', current_date+100),
 (4,'Nitriansky kraj','STRAVOVANIE', current_date+100);
insert into public.subsidies(contract_id, kraj, sektor_odhad) values (5,'Bratislavský kraj',null),(6,'Košický kraj','UPRATOVANIE');
insert into public.obce_ziadatelia(contract_id,obec,kraj) values (5,'X','Bratislavský kraj'),(6,'Y','Košický kraj');
do $$
declare p record; u uuid; o uuid; i int := 0;
begin
  for p in select * from (values
     ('start','aktivne', now()+interval '10 days', null::timestamptz),
     ('start','aktivne', now()+interval '10 days', now()-interval '1 day'),   -- zaplatene, obdobie vyprsalo
     ('start','aktivne', now()+interval '10 days', now()+interval '20 days'),
     ('growth','aktivne', now()+interval '10 days', null),
     ('poradca','aktivne', now()+interval '10 days', null),
     ('trial','trial', now()+interval '10 days', null),
     ('team','aktivne', now()+interval '10 days', now()-interval '1 hour')) v(plan,stav,tk,ok)
  loop
    i := i+1;
    u := ('c0000000-0000-0000-0000-00000000000'||i)::uuid;
    insert into auth.users(id,email) values (u, 'u'||i||'@t.sk');
    insert into public.organizations(id,nazov) values (gen_random_uuid(), 'Org '||i) returning id into o;
    insert into public.memberships(user_id,org_id,rola) values (u,o,'owner');
    insert into public.subscriptions(org_id,plan,stav,trial_konci,obdobie_konci) values (o,p.plan,p.stav,p.tk,p.ok);
    -- vyber: BA + UPRATOVANIE
    insert into public.nastavenia_pouzivatela(user_id,kraje,sektory) values (u, array['Bratislavský kraj'], array['UPRATOVANIE']);
  end loop;
end $$;
grant select on auth.users to authenticated;
set role authenticated;
select set_config('request.jwt.claim.sub','c0000000-0000-0000-0000-000000000001',false);
select '1' as u,
  (select plan||'/'||coalesce(to_char(obdobie_konci,'MM-DD'),'-') from public.subscriptions limit 1) as plan,
  public.ma_aktivny_pristup() as aktivny, public.ma_pro() as pro, public.je_start_obmedzeny() as start_lim,
  (select count(*) from public.opportunities) as opp, (select count(*) from public.subsidies) as dot, (select count(*) from public.obce_ziadatelia) as ziad,
  public.ma_dopyty_pristup() as dopyty, public.ma_pristup_k_dotaciam() as dotacie_pristup,
  public.start_skryte_pocty()::text as skryte;
select set_config('request.jwt.claim.sub','c0000000-0000-0000-0000-000000000002',false);
select '2' as u,
  (select plan||'/'||coalesce(to_char(obdobie_konci,'MM-DD'),'-') from public.subscriptions limit 1) as plan,
  public.ma_aktivny_pristup() as aktivny, public.ma_pro() as pro, public.je_start_obmedzeny() as start_lim,
  (select count(*) from public.opportunities) as opp, (select count(*) from public.subsidies) as dot, (select count(*) from public.obce_ziadatelia) as ziad,
  public.ma_dopyty_pristup() as dopyty, public.ma_pristup_k_dotaciam() as dotacie_pristup,
  public.start_skryte_pocty()::text as skryte;
select set_config('request.jwt.claim.sub','c0000000-0000-0000-0000-000000000003',false);
select '3' as u,
  (select plan||'/'||coalesce(to_char(obdobie_konci,'MM-DD'),'-') from public.subscriptions limit 1) as plan,
  public.ma_aktivny_pristup() as aktivny, public.ma_pro() as pro, public.je_start_obmedzeny() as start_lim,
  (select count(*) from public.opportunities) as opp, (select count(*) from public.subsidies) as dot, (select count(*) from public.obce_ziadatelia) as ziad,
  public.ma_dopyty_pristup() as dopyty, public.ma_pristup_k_dotaciam() as dotacie_pristup,
  public.start_skryte_pocty()::text as skryte;
select set_config('request.jwt.claim.sub','c0000000-0000-0000-0000-000000000004',false);
select '4' as u,
  (select plan||'/'||coalesce(to_char(obdobie_konci,'MM-DD'),'-') from public.subscriptions limit 1) as plan,
  public.ma_aktivny_pristup() as aktivny, public.ma_pro() as pro, public.je_start_obmedzeny() as start_lim,
  (select count(*) from public.opportunities) as opp, (select count(*) from public.subsidies) as dot, (select count(*) from public.obce_ziadatelia) as ziad,
  public.ma_dopyty_pristup() as dopyty, public.ma_pristup_k_dotaciam() as dotacie_pristup,
  public.start_skryte_pocty()::text as skryte;
select set_config('request.jwt.claim.sub','c0000000-0000-0000-0000-000000000005',false);
select '5' as u,
  (select plan||'/'||coalesce(to_char(obdobie_konci,'MM-DD'),'-') from public.subscriptions limit 1) as plan,
  public.ma_aktivny_pristup() as aktivny, public.ma_pro() as pro, public.je_start_obmedzeny() as start_lim,
  (select count(*) from public.opportunities) as opp, (select count(*) from public.subsidies) as dot, (select count(*) from public.obce_ziadatelia) as ziad,
  public.ma_dopyty_pristup() as dopyty, public.ma_pristup_k_dotaciam() as dotacie_pristup,
  public.start_skryte_pocty()::text as skryte;
select set_config('request.jwt.claim.sub','c0000000-0000-0000-0000-000000000006',false);
select '6' as u,
  (select plan||'/'||coalesce(to_char(obdobie_konci,'MM-DD'),'-') from public.subscriptions limit 1) as plan,
  public.ma_aktivny_pristup() as aktivny, public.ma_pro() as pro, public.je_start_obmedzeny() as start_lim,
  (select count(*) from public.opportunities) as opp, (select count(*) from public.subsidies) as dot, (select count(*) from public.obce_ziadatelia) as ziad,
  public.ma_dopyty_pristup() as dopyty, public.ma_pristup_k_dotaciam() as dotacie_pristup,
  public.start_skryte_pocty()::text as skryte;
select set_config('request.jwt.claim.sub','c0000000-0000-0000-0000-000000000007',false);
select '7' as u,
  (select plan||'/'||coalesce(to_char(obdobie_konci,'MM-DD'),'-') from public.subscriptions limit 1) as plan,
  public.ma_aktivny_pristup() as aktivny, public.ma_pro() as pro, public.je_start_obmedzeny() as start_lim,
  (select count(*) from public.opportunities) as opp, (select count(*) from public.subsidies) as dot, (select count(*) from public.obce_ziadatelia) as ziad,
  public.ma_dopyty_pristup() as dopyty, public.ma_pristup_k_dotaciam() as dotacie_pristup,
  public.start_skryte_pocty()::text as skryte;
-- limit 2+2 pre Start (user 1 = start bez konca)
select set_config('request.jwt.claim.sub','c0000000-0000-0000-0000-000000000001',false);
do $$ begin
  begin update public.nastavenia_pouzivatela set kraje = array['Bratislavský kraj','Košický kraj','Nitriansky kraj'] where user_id = auth.uid();
        raise notice 'FAIL start 3 kraje presli';
  exception when others then raise notice 'OK start 3 kraje zamietnute: %', left(sqlerrm,40); end;
  update public.nastavenia_pouzivatela set kraje = array['Bratislavský kraj','Košický kraj'], sektory = array['UPRATOVANIE','OSTRAHA'] where user_id = auth.uid();
  raise notice 'OK start 2+2 ulozene';
end $$;
select 'start 2+2 opp' as t, count(*) from public.opportunities;
-- Growth moze viac
select set_config('request.jwt.claim.sub','c0000000-0000-0000-0000-000000000004',false);
do $$ begin
  update public.nastavenia_pouzivatela set kraje = array['Bratislavský kraj','Košický kraj','Nitriansky kraj'] where user_id = auth.uid();
  raise notice 'OK growth 3 kraje ulozene';
end $$;
grant usage on schema auth to authenticated;
set role authenticated;
select set_config('request.jwt.claim.sub','c0000000-0000-0000-0000-000000000001',false);
do $$ begin
  begin update public.nastavenia_pouzivatela set kraje = array['Bratislavský kraj','Košický kraj','Nitriansky kraj'] where user_id = auth.uid();
        raise notice 'FAIL start 3 kraje presli';
  exception when others then raise notice 'OK start 3 kraje zamietnute: %', left(sqlerrm,50); end;
  begin update public.nastavenia_pouzivatela set sektory = array['UPRATOVANIE','OSTRAHA','STRAVOVANIE'] where user_id = auth.uid();
        raise notice 'FAIL start 3 sektory presli';
  exception when others then raise notice 'OK start 3 sektory zamietnute'; end;
  update public.nastavenia_pouzivatela set kraje = array['Bratislavský kraj','Košický kraj'], sektory = array['UPRATOVANIE','OSTRAHA'] where user_id = auth.uid();
  raise notice 'OK start 2+2 ulozene';
end $$;
select 'start 2+2 -> opp' as t, count(*) from public.opportunities;
select 'start 2+2 -> dot' as t, count(*) from public.subsidies;
select set_config('request.jwt.claim.sub','c0000000-0000-0000-0000-000000000004',false);
do $$ begin
  update public.nastavenia_pouzivatela set kraje = array['Bratislavský kraj','Košický kraj','Nitriansky kraj'] where user_id = auth.uid();
  raise notice 'OK growth 3 kraje ulozene';
end $$;
\pset format unaligned
\pset fieldsep ' | '
reset role;
update public.subscriptions set pripomienka_obnovy_za = null;
update public.subscriptions s set obdobie_konci = now() + interval '3 days' where plan='start' and obdobie_konci is not null and obdobie_konci > now();
select 'pripomienky (service_role)' t;
set role service_role;
select plan, email, to_char(obdobie_konci,'MM-DD') from public.pripomienky_obnovy();
select public.oznac_pripomienku_obnovy(org_id, obdobie_konci) from public.pripomienky_obnovy();
select 'po oznaceni' t, count(*) from public.pripomienky_obnovy();
reset role; set role authenticated;
select set_config('request.jwt.claim.sub','c0000000-0000-0000-0000-000000000004',false);
do $$ begin
  begin perform * from public.pripomienky_obnovy(); raise notice 'FAIL authenticated vidi pripomienky';
  exception when others then raise notice 'OK authenticated zamietnuty'; end;
end $$;
