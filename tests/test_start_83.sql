-- Test migracie 83: Start vidi zmluvy, dodavatelov a ceny len vo svojich
-- 2 sektoroch; prilezitosti/dotacie ako doteraz; pocet cez celu tabulku je rychly.
--   su postgres -c "psql -q -d <db> -f tests/test_start_83.sql"
\set ON_ERROR_STOP on
\pset format unaligned
\pset tuples_only on
create or replace function public.je_zadarmo() returns boolean language sql immutable as $$ select false $$;
insert into public.contracts(id, sector) values (1,'UPRATOVANIE'),(2,'OSTRAHA'),(3,'IT_TECHNIKA'),(4,null),(5,'UPRATOVANIE');
insert into public.dodavatelia(supplier_cin, dodavatel, hlavny_sektor, refreshed_at) values
  ('1','A','UPRATOVANIE',now()),('2','B','IT_TECHNIKA',now()),('3','C',null,now());
insert into public.ceny_sektor(sector, refreshed_at) values ('UPRATOVANIE',now()),('OSTRAHA',now()),('IT_TECHNIKA',now());
-- 20 000 prilezitosti na meranie poctu
insert into public.contracts(id) select g from generate_series(1000, 20999) g;
insert into public.opportunities(contract_id, kraj, sector, effective_to)
  select g, (array['Bratislavský kraj','Košický kraj','Nitriansky kraj'])[1 + g % 3],
            (array['UPRATOVANIE','OSTRAHA','IT_TECHNIKA','STRAVOVANIE'])[1 + g % 4], current_date + 100
  from generate_series(1000, 20999) g;
do $$
declare p record; u uuid; o uuid; i int := 0;
begin
  for p in select * from (values ('growth'),('start'),('start')) v(plan) loop
    i := i + 1;
    u := ('d0000000-0000-0000-0000-00000000000'||i)::uuid;
    insert into auth.users(id,email) values (u, 'v'||i||'@t.sk');
    insert into public.organizations(id,nazov) values (gen_random_uuid(), 'Org '||i) returning id into o;
    insert into public.memberships(user_id,org_id,rola) values (u,o,'owner');
    insert into public.subscriptions(org_id,plan,stav,trial_konci,obdobie_konci)
      values (o,p.plan,'aktivne',now()+interval '10 days',now()+interval '20 days');
    if i <> 3 then   -- tretí (Start) nemá výber
      insert into public.nastavenia_pouzivatela(user_id,kraje,sektory)
        values (u, array['Bratislavský kraj','Košický kraj'], array['UPRATOVANIE','OSTRAHA']);
    end if;
  end loop;
end $$;
grant select on auth.users to authenticated;
set role authenticated;
create temp table v(meno text, ocak bigint, skut bigint);
select set_config('request.jwt.claim.sub','d0000000-0000-0000-0000-000000000001',false);
insert into v values ('growth: contracts', 20005, (select count(*) from public.contracts)),
                     ('growth: dodavatelia', 3, (select count(*) from public.dodavatelia)),
                     ('growth: ceny_sektor', 3, (select count(*) from public.ceny_sektor)),
                     ('growth: prilezitosti', 20000, (select count(*) from public.opportunities));
select set_config('request.jwt.claim.sub','d0000000-0000-0000-0000-000000000002',false);
insert into v values ('start: contracts len UPRATOVANIE/OSTRAHA', 3, (select count(*) from public.contracts)),
                     ('start: dodavatelia len vlastny sektor', 1, (select count(*) from public.dodavatelia)),
                     ('start: ceny_sektor len vlastne sektory', 2, (select count(*) from public.ceny_sektor)),
                     ('start: prilezitosti BA+KE x UPR+OST', (select count(*) from generate_series(1000,20999) g where g % 3 in (0,1) and g % 4 in (0,1)), (select count(*) from public.opportunities));
select set_config('request.jwt.claim.sub','d0000000-0000-0000-0000-000000000003',false);
insert into v values ('start bez vyberu: contracts', 0, (select count(*) from public.contracts)),
                     ('start bez vyberu: prilezitosti', 0, (select count(*) from public.opportunities));
select (case when ocak = skut then 'OK   ' else 'CHYBA' end) || ' ' || meno || ' (ocakavane ' || ocak || ', skutocne ' || skut || ')' from v;
-- rychlost poctu pre Start (predtym funkcia na kazdy riadok)
select set_config('request.jwt.claim.sub','d0000000-0000-0000-0000-000000000002',false);
do $$ declare t0 timestamptz := clock_timestamp(); n bigint; ms int;
begin
  select count(*) into n from public.opportunities;
  ms := extract(milliseconds from clock_timestamp() - t0)::int;
  raise notice '% start: pocet 20 000 prilezitosti za % ms', case when ms < 500 then 'OK   ' else 'CHYBA' end, ms;
end $$;
reset role;
