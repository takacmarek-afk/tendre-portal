-- Test migracie 82 (admin_prepni_plan). Spustat na lokalnej DB so schemou
-- a migraciami (rovnako ako ostatne tests/*.sql). Ocakavane:
--   zakaznik -> NIE_ADMIN, zly plan -> ZLY_PLAN, anon -> permission denied,
--   admin prepina len svoju firmu, plany bez konca obdobia, trial +14 dni,
--   kazde prepnutie je v events.
\set ON_ERROR_STOP off
\pset format unaligned
\pset fieldsep ' | '
insert into auth.users(id,email) values
  ('a0000000-0000-0000-0000-000000000001','takac.marek@gmail.com'),
  ('b0000000-0000-0000-0000-000000000002','zakaznik@firma.sk');
insert into public.organizations(id,nazov) values
  ('aaaaaaaa-0000-0000-0000-000000000001','LoveHome'),
  ('bbbbbbbb-0000-0000-0000-000000000002','Zakaznik');
insert into public.memberships(user_id,org_id,rola) values
  ('a0000000-0000-0000-0000-000000000001','aaaaaaaa-0000-0000-0000-000000000001','owner'),
  ('b0000000-0000-0000-0000-000000000002','bbbbbbbb-0000-0000-0000-000000000002','owner');
insert into public.subscriptions(org_id,plan,stav,obdobie_konci) values
  ('aaaaaaaa-0000-0000-0000-000000000001','start','aktivne', now()+interval '700 days'),
  ('bbbbbbbb-0000-0000-0000-000000000002','start','aktivne', now()+interval '20 days');
grant select on auth.users to authenticated;
set role authenticated;
select set_config('request.jwt.claim.sub','b0000000-0000-0000-0000-000000000002',false);
select 'zakaznik' as kto, public.admin_prepni_plan('admin');            -- NIE_ADMIN
select set_config('request.jwt.claim.sub','a0000000-0000-0000-0000-000000000001',false);
select 'admin growth', public.admin_prepni_plan('growth');
select 'admin zly', public.admin_prepni_plan('xyz');                     -- ZLY_PLAN
select 'admin trial', public.admin_prepni_plan('trial');
select 'admin poradca', public.admin_prepni_plan('poradca');
select 'admin start', public.admin_prepni_plan('start');
reset role;
select o.nazov, s.plan, s.stav, s.obdobie_konci is null as bez_konca
  from public.subscriptions s join public.organizations o on o.id = s.org_id
 where o.nazov in ('LoveHome','Zakaznik') order by 1;
-- ocakavane: LoveHome | start | aktivne | t ;  Zakaznik | start | aktivne | f
select count(*) as prepnuti from public.events where typ = 'admin_prepnutie_planu';   -- 4
set role anon;
select public.admin_prepni_plan('admin');                                -- permission denied
reset role;
