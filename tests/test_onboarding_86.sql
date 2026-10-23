-- Test migracie 86 (uvitacie e-maily). Spustat na lokalnej DB so schemou
-- a migraciami (rovnako ako ostatne tests/*.sql). Ocakavane riadky su v komentaroch.
\set ON_ERROR_STOP off
\pset format unaligned
\pset fieldsep ' | '
update public.onboarding_nastavenie set spustene_od = now() - interval '1 hour';
insert into auth.users(id,email,created_at) values
  ('a0000000-0000-0000-0000-000000000001','takac.marek@gmail.com', now()),
  ('b0000000-0000-0000-0000-000000000002','novy@firma.sk', now()),
  ('c0000000-0000-0000-0000-000000000003','stary@firma.sk', now() - interval '5 days'),
  ('d0000000-0000-0000-0000-000000000004','demo@predtendrom.sk', now()),
  ('e0000000-0000-0000-0000-000000000005','bezfirmy@firma.sk', now());
insert into public.organizations(id,nazov) values
  ('bbbbbbbb-0000-0000-0000-000000000002','Nova s.r.o.');
insert into public.memberships(user_id,org_id,rola) values
  ('b0000000-0000-0000-0000-000000000002','bbbbbbbb-0000-0000-0000-000000000002','owner');
insert into public.subscriptions(org_id,plan,stav,trial_konci) values
  ('bbbbbbbb-0000-0000-0000-000000000002','trial','trial', now()+interval '14 days');
insert into public.nastavenia_pouzivatela(user_id,kraje,sektory) values
  ('b0000000-0000-0000-0000-000000000002','{"Bratislavský kraj"}','{UPRATOVANIE}');
insert into public.contracts(id) values (1),(2),(3),(4);
insert into public.opportunities(contract_id,kraj,sector,effective_to,authority_name,subject) values
  (1,'Bratislavský kraj','UPRATOVANIE', current_date + 10,  'Mesto A','Upratovanie A'),
  (2,'Bratislavský kraj','UPRATOVANIE', current_date + 60,  'Mesto B','Upratovanie B'),
  (3,'Bratislavský kraj','OSTRAHA',     current_date + 60,  'Mesto C','Ostraha C'),
  (4,'Bratislavský kraj','UPRATOVANIE', current_date + 500, 'Mesto D','Upratovanie D');

select email, ma_vyber, pocet_zmluv, najblizsia->>'urad', zaplatene, odoslane
  from public.onboarding_kandidati() order by email;
-- ocakavane: bezfirmy@firma.sk | f | 0 | (null) | f | {}
--            novy@firma.sk | t | 2 | Mesto B | f | {}
--   (Marek, demo@ a stary pred spustenim chybaju)

select public.onboarding_oznac('b0000000-0000-0000-0000-000000000002', 0::smallint);
select public.onboarding_oznac('b0000000-0000-0000-0000-000000000002', 0::smallint);  -- znova: nic
select email, odoslane from public.onboarding_kandidati() where email = 'novy@firma.sk';
-- ocakavane: novy@firma.sk | {0}

set role anon;
select public.onboarding_kandidati();                                   -- permission denied
select public.onboarding_odhlas('nie-token');                            -- {"ok": false}
reset role;
select set_config('t.tok', (select token::text from public.onboarding_pouzivatelia
                              where user_id = 'b0000000-0000-0000-0000-000000000002'), false);
set role anon;
select public.onboarding_odhlas(current_setting('t.tok'));               -- {"ok": true}
select count(*) from public.onboarding_pouzivatelia;                     -- permission denied
reset role;
select count(*) as po_odhlaseni from public.onboarding_kandidati() where email = 'novy@firma.sk';  -- 0
