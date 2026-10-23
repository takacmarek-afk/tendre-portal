\set ON_ERROR_STOP 1
\i supabase/84_oslovenie_firiem.sql
\i supabase/84_oslovenie_firiem.sql
insert into public.oslovenie_firiem_kontakty (ico, nazov, email, stav) values ('36034762','DUG s.r.o.','info@dug.sk','ok');
-- anon nevidi nic a nevie zapisat
set role anon;
do $$ begin perform 1 from public.oslovenie_firiem_kontakty; raise exception 'anon vidi tabulku'; exception when insufficient_privilege then raise notice 'OK anon bez pristupu'; end $$;
select public.oslovenie_firiem_odhlas('zly') ->> 'ok' as zly_token;
select public.oslovenie_firiem_odhlas('00000000-0000-0000-0000-000000000000') ->> 'ok' as neznamy;
reset role;
select token::text as t from public.oslovenie_firiem_kontakty \gset
set role anon;
select public.oslovenie_firiem_odhlas(:'t') as odhlas;
reset role;
select odhlasene_at is not null as odhlasena from public.oslovenie_firiem_kontakty;
-- prihlaseny ne-admin nevidi riadky
set role authenticated;
select count(*) as vidi_neadmin from public.oslovenie_firiem_kontakty;
reset role;
insert into public.oslovenie_firiem_odoslane (ico,krok,email) values ('36034762',1,'info@dug.sk');
do $$ begin insert into public.oslovenie_firiem_odoslane (ico,krok,email) values ('36034762',1,'info@dug.sk'); raise exception 'duplicita presla'; exception when unique_violation then raise notice 'OK unique ico+krok'; end $$;
