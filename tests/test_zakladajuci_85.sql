\set ON_ERROR_STOP 1
-- Spustenie: psql -d <skusobna db s migraciami 1-84> -f tests/test_zakladajuci_85.sql (z korena repozitara)
\i supabase/85_zakladajuci_kod.sql
\i supabase/85_zakladajuci_kod.sql
-- pripravime 31 firiem s vlastnikom
insert into auth.users (id, email) select ('00000000-0000-0000-0000-'||lpad(i::text,12,'0'))::uuid, 'u'||i||'@x.sk' from generate_series(1,32) i on conflict do nothing;
insert into public.organizations (id, nazov) select ('10000000-0000-0000-0000-'||lpad(i::text,12,'0'))::uuid, 'Firma '||i from generate_series(1,32) i on conflict do nothing;
insert into public.memberships (user_id, org_id, rola) select ('00000000-0000-0000-0000-'||lpad(i::text,12,'0'))::uuid, ('10000000-0000-0000-0000-'||lpad(i::text,12,'0'))::uuid, 'owner' from generate_series(1,32) i on conflict do nothing;
create or replace function pg_temp.ako(i int) returns void language sql as $$ select set_config('request.jwt.claim.sub', '00000000-0000-0000-0000-'||lpad(i::text,12,'0'), false), set_config('request.jwt.claims', json_build_object('sub','00000000-0000-0000-0000-'||lpad(i::text,12,'0'))::text, false) $$;
select pg_temp.ako(1);
set role authenticated;
select 'bez kodu growth rok' as t, suma from public.zaloz_platbu('growth','rok');
select 'kod start rok' as t, suma, zlava_kod from public.zaloz_platbu('start','rok','zakladatel ');
do $$ begin perform public.zaloz_platbu('start','mesiac','ZAKLADATEL'); raise exception 'mesacne preslo'; exception when others then if sqlerrm <> 'KOD_LEN_ROCNE' then raise; end if; raise notice 'OK len rocne'; end $$;
do $$ begin perform public.zaloz_platbu('start','rok','ZLAVA50'); raise exception 'zly kod presiel'; exception when others then if sqlerrm <> 'NEPLATNY_KOD' then raise; end if; raise notice 'OK neplatny kod'; end $$;
select 'volne pred' as t, public.zakladajuce_miesta();
reset role;
-- 30 firiem zaplatilo s kodom
insert into public.platby (org_id, plan, obdobie, suma, zlava_kod, stav, spracovane_at)
  select ('10000000-0000-0000-0000-'||lpad(i::text,12,'0'))::uuid, 'start','rok',240,'ZAKLADATEL','zaplatena', now() - interval '1 day' from generate_series(2,31) i;
set role anon;
select 'volne po' as t, public.zakladajuce_miesta();
reset role;
select pg_temp.ako(32);
set role authenticated;
do $$ begin perform public.zaloz_platbu('start','rok','ZAKLADATEL'); raise exception '31. firma presla'; exception when others then if sqlerrm <> 'KOD_VYCERPANY' then raise; end if; raise notice 'OK vycerpane'; end $$;
reset role;
select pg_temp.ako(2);
set role authenticated;
select 'obnova firmy 2' as t, suma from public.zaloz_platbu('growth','rok','ZAKLADATEL');
reset role;
update public.platby set spracovane_at = now() - interval '25 months' where org_id = '10000000-0000-0000-0000-000000000003';
select pg_temp.ako(3);
set role authenticated;
do $$ begin perform public.zaloz_platbu('start','rok','ZAKLADATEL'); raise exception 'po 2 rokoch preslo'; exception when others then if sqlerrm <> 'KOD_SKONCIL' then raise; end if; raise notice 'OK po 2 rokoch koniec'; end $$;
do $$ begin perform 1 from public.zakladajuce_ceny; raise exception 'vidi ceny'; exception when insufficient_privilege then raise notice 'OK tabulka cien zatvorena'; end $$;
reset role;
select 'stara 2-arg verzia' as t, count(*) from pg_proc where proname='zaloz_platbu';
