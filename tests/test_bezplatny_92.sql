-- Test migracie 76 (bezplatny prehlad po skuske, vlna 92). Pusti sa po 72, 74, 75, 76:
--   su postgres -c "psql -q -d <db> -f tests/test_bezplatny_92.sql"
\set ON_ERROR_STOP on
\pset format unaligned
\pset tuples_only on
create or replace function public.je_zadarmo() returns boolean language sql immutable as $$ select false $$;
insert into public.contracts(id) select g from generate_series(1,60) g on conflict do nothing;
delete from public.opportunities where contract_id between 1 and 60;
delete from public.subsidies where contract_id between 1 and 60;
insert into public.opportunities(contract_id, kraj, sector, authority_name, subject, effective_to, price_total, supplier_name) values
 (1,'KrajA','UPRATOVANIE','Urad 1','Predmet 1', current_date+10, 111111,'Dodavatel X'),
 (2,'KrajA','UPRATOVANIE','Urad 2','Predmet 2', current_date+20, 222222,'Dodavatel Y'),
 (3,'KrajA','UPRATOVANIE','Urad 3','Predmet 3', current_date+30, 333333,'Dodavatel Z'),
 (4,'KrajA','UPRATOVANIE','Urad 4','Predmet 4', current_date+40, 444444,'Dodavatel W'),
 (5,'KrajA','OSTRAHA',    'Urad 5','Predmet 5', current_date+50, 5,'D'),
 (6,'KrajB','UPRATOVANIE','Urad 6','Predmet 6', current_date+60, 6,'D'),
 (7,'KrajA','UPRATOVANIE','Urad 7','Uz skoncila', current_date-5, 7,'D'),
 (8,'KrajA','UPRATOVANIE','Urad 8','Daleko', current_date+500, 8,'D');
insert into public.subsidies(contract_id, kraj, sektor_odhad, vyplatene, okno_do) values
 (11,'KrajA','UPRATOVANIE', false, current_date+100),
 (12,'KrajA',null,          false, null),
 (13,'KrajA','OSTRAHA',     false, current_date+100),
 (14,'KrajA','UPRATOVANIE', true,  current_date+100),
 (15,'KrajA','UPRATOVANIE', false, current_date-1),
 (16,'KrajB','UPRATOVANIE', false, current_date+100);
do $$
declare r record; u uuid; o uuid; i int := 0;
begin
  for r in select * from (values
     -- plan, stav, trial_konci, obdobie_konci, ma_nastavenia
     ('growth','trial',  now()-interval '3 days',  null::timestamptz,           true),   -- 1 skuska skoncila pred 3 dnami
     ('growth','aktivne',now()-interval '30 days', now()+interval '20 days',    true),   -- 2 plni pristup
     ('growth','trial',  now()-interval '3 days',  null,                        false),  -- 3 skoncena, bez nastaveni
     ('poradca','trial', now()-interval '3 days',  null,                        true),   -- 4 poradca
     ('growth','trial',  now()-interval '100 days',null,                        true),   -- 5 stara skuska (>56 dni)
     ('start','aktivne', now()-interval '90 days', now()-interval '2 days',      true),   -- 6 zaplatene skoncilo
     ('growth','trial',  now()-interval '3 days',  null,                        true)    -- 7 skoncena, e-mail nedavno poslany
  ) v(plan,stav,tk,ok,nast)
  loop
    i := i+1;
    u := ('d0000000-0000-0000-0000-00000000000'||i)::uuid;
    insert into auth.users(id,email) values (u, 'b'||i||'@t.sk') on conflict do nothing;
    insert into public.organizations(id,nazov) values (gen_random_uuid(), 'BOrg '||i) returning id into o;
    insert into public.memberships(user_id,org_id,rola) values (u,o,'owner');
    insert into public.subscriptions(org_id,plan,stav,trial_konci,obdobie_konci,bezplatny_email_at)
       values (o,r.plan,r.stav,r.tk,r.ok, case when i=7 then now()-interval '2 days' else null end);
    if r.nast then
      insert into public.nastavenia_pouzivatela(user_id,kraje,sektory) values (u, array['KrajA','KrajB'], array['UPRATOVANIE','OSTRAHA']) on conflict do nothing;
    end if;
  end loop;
  -- 8: pouzivatel bez organizacie
  insert into auth.users(id,email) values ('d0000000-0000-0000-0000-000000000008','b8@t.sk') on conflict do nothing;
end $$;
create temp table v(nazov text, ocakavane text, skutocne text);
grant all on v to authenticated, anon;
set role authenticated;

select set_config('request.jwt.claim.sub','d0000000-0000-0000-0000-000000000001',false) \gset
create temp table p1 as select public.bezplatny_prehlad() r;
insert into v select 'skoncena skuska: bezplatny', 'true', (select r->>'bezplatny' from p1);
insert into v select 'pocet zmluv v KrajA+UPRATOVANIE (4, bez skoncenej a dalekej)', '4', (select r->>'pocet_zmluv' from p1);
insert into v select 'pocet dotacii (11, 12; nie vyplatena/prosla/ina/ina oblast)', '2', (select r->>'pocet_dotacii' from p1);
insert into v select 'dalsie v kraji (OSTRAHA 1)', '1', (select r->>'dalsie_v_kraji' from p1);
insert into v select 'ukazky: 3, najblizsie', '3|Predmet 1', (select jsonb_array_length(r->'ukazky') || '|' || (r->'ukazky'->0->>'predmet') from p1);
insert into v select 'ukazky bez sumy a dodavatela', 'f|f|f', (select concat_ws('|', r::text ~* 'price|suma', r::text ~ 'Dodavatel', r::text ~ '111111') from p1);

select set_config('request.jwt.claim.sub','d0000000-0000-0000-0000-000000000002',false) \gset
insert into v select 'aktivny plan: bezplatny false', 'false', (select (public.bezplatny_prehlad())->>'bezplatny');
select set_config('request.jwt.claim.sub','d0000000-0000-0000-0000-000000000003',false) \gset
insert into v select 'bez nastaveni: nastavene false, ukazky 0', 'false|0', (select concat_ws('|', r->>'nastavene', jsonb_array_length(r->'ukazky')) from (select public.bezplatny_prehlad() r) x);
select set_config('request.jwt.claim.sub','d0000000-0000-0000-0000-000000000008',false) \gset
insert into v select 'bez organizacie: bezplatny false', 'false', (select (public.bezplatny_prehlad())->>'bezplatny');
select set_config('request.jwt.claim.sub','',false) \gset
insert into v select 'bez prihlasenia: bezplatny false', 'false', (select (public.bezplatny_prehlad())->>'bezplatny');
-- cudzie funkcie nesmie klient volat
do $$ begin perform public.bezplatne_emaily(); insert into v values ('klient vola bezplatne_emaily','zakazane','povolene'); exception when insufficient_privilege then insert into v values ('klient vola bezplatne_emaily','zakazane','zakazane'); end $$;
do $$ begin perform public._bezplatny_obsah('KrajA','UPRATOVANIE'); insert into v values ('klient vola _bezplatny_obsah','zakazane','povolene'); exception when insufficient_privilege then insert into v values ('klient vola _bezplatny_obsah','zakazane','zakazane'); end $$;
set role anon;
do $$ begin perform public.bezplatny_prehlad(); insert into v values ('anon vola bezplatny_prehlad','zakazane','povolene'); exception when insufficient_privilege then insert into v values ('anon vola bezplatny_prehlad','zakazane','zakazane'); end $$;
reset role;

-- e-mail: len 1 (skoncena pred 3 dnami), 3 (skoncena, bez nastaveni) a 6 (zaplatene skoncilo pred 2 dnami); nie 2,4,5,7
insert into v select 'e-maily: komu', 'b1@t.sk,b3@t.sk,b6@t.sk',
  (select string_agg(email, ',' order by email) from public.bezplatne_emaily() where email like 'b_@t.sk');
insert into v select 'e-mail b3: nenastavene', 'false', (select (obsah->>'nastavene') from public.bezplatne_emaily() where email='b3@t.sk');
select public.oznac_bezplatny_email(m.org_id) from public.memberships m where m.user_id='d0000000-0000-0000-0000-000000000001';
insert into v select 'po oznaceni b1 uz nie', 'b3@t.sk,b6@t.sk',
  (select string_agg(email, ',' order by email) from public.bezplatne_emaily() where email like 'b_@t.sk');

update public.subscriptions set bezplatny_email_stop = true where org_id = (select org_id from public.memberships where user_id='d0000000-0000-0000-0000-000000000003');
insert into v select 'odhlaseny b3 uz nie', 'b6@t.sk',
  (select string_agg(email, ',' order by email) from public.bezplatne_emaily() where email like 'b_@t.sk');

select case when ocakavane = skutocne then 'OK   ' else 'CHYBA' end || ' ' || nazov || case when ocakavane = skutocne then '' else '  [ocakavane=' || ocakavane || ' skutocne=' || coalesce(skutocne,'NULL') || ']' end from v;
select 'CELKOM CHYB: ' || count(*) from v where ocakavane is distinct from skutocne;
