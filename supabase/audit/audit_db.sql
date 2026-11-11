-- Finalny audit 11. 11. 2026. LEN CITANIE (spusta sa s default_transaction_read_only).
-- Vypisuje len nazvy objektov a suhrnne pocty, ziadne e-maily ani mena (logy su verejne).
set session characteristics as transaction read only;
\pset footer off
\echo '== 1. Tabulky v public bez RLS'
select c.relname from pg_class c join pg_namespace n on n.oid=c.relnamespace
where n.nspname='public' and c.relkind in ('r','p') and not c.relrowsecurity order by 1;

\echo '== 2. Politiky pre anon/public s podmienkou true (SELECT/ALL)'
select tablename, policyname, cmd, roles::text from pg_policies
where schemaname='public' and (roles && array['anon','public']::name[])
  and cmd in ('SELECT','ALL') and coalesce(qual,'') in ('true','(true)') order by 1;

\echo '== 3. Politiky pre anon/public na zapis'
select tablename, policyname, cmd, roles::text, left(coalesce(with_check,qual,''),80) podmienka from pg_policies
where schemaname='public' and (roles && array['anon','public']::name[]) and cmd in ('INSERT','UPDATE','DELETE','ALL') order by 1;

\echo '== 4. Pohlady v public citatelne pre anon bez security_invoker'
select c.relname from pg_class c join pg_namespace n on n.oid=c.relnamespace
where n.nspname='public' and c.relkind in ('v','m') and has_table_privilege('anon', c.oid, 'SELECT')
  and not coalesce(c.reloptions::text ilike '%security_invoker=true%', false) order by 1;

\echo '== 5. SECURITY DEFINER funkcie bez pevneho search_path'
select p.proname from pg_proc p join pg_namespace n on n.oid=p.pronamespace
where n.nspname='public' and p.prosecdef
  and not exists (select 1 from unnest(coalesce(p.proconfig,'{}')) x where x like 'search_path=%') order by 1;

\echo '== 6. Storage buckety'
select id, public from storage.buckets order by 1;

\echo '== 7. Pouzivatelia (auth)'
select count(*) spolu,
       count(*) filter (where email_confirmed_at is not null) potvrdeni,
       count(*) filter (where created_at > now()-interval '30 days') novi_30d,
       count(*) filter (where created_at > now()-interval '7 days') novi_7d,
       count(*) filter (where last_sign_in_at > now()-interval '7 days') aktivni_7d,
       count(*) filter (where last_sign_in_at > now()-interval '30 days') aktivni_30d
from auth.users;

\echo '== 8. Predplatne podla stavu a planu'
select stav, coalesce(plan,'-') plan, count(*),
       count(*) filter (where stav='trial' and trial_konci > now()) trial_bezi
from public.subscriptions group by 1,2 order by 1,2;

\echo '== 9. Platby (TrustPay tabulka)'
select stav, count(*), sum(suma) from public.platby group by 1;

\echo '== 10. Organizacie a clenstva'
select (select count(*) from public.organizations) org, (select count(*) from public.memberships) clenstva;

\echo '== 11. Odbery a oslovenia'
select 'odber_firmy' t, count(*) from public.odber_firmy
union all select 'odber_obce', count(*) from public.odber_obce
union all select 'odber', count(*) from public.odber
union all select 'oslovenie_odoslane', count(*) from public.oslovenie_firiem_odoslane where stav='odoslane'
union all select 'oslovenie_chyba', count(*) from public.oslovenie_firiem_odoslane where stav='chyba'
union all select 'oslovenie_odpovedali', count(*) from public.oslovenie_firiem_kontakty where stav='odpovedal'
union all select 'oslovenie_vylucene', count(*) from public.oslovenie_firiem_kontakty where stav='vylucene'
union all select 'oslovenie_ok_cakaju', count(*) from public.oslovenie_firiem_kontakty k where stav='ok'
      and not exists (select 1 from public.oslovenie_firiem_odoslane o where o.ico=k.ico)
union all select 'kampan_obce_odoslane', count(*) from public.kampan_obce_odoslane
union all select 'onboarding_odoslane', count(*) from public.onboarding_odoslane
union all select 'servisne_dopyty', count(*) from public.servisne_dopyty
union all select 'dopyty', count(*) from public.dopyty;

\echo '== 12. Oslovenie podla kroku a tyzdna'
select date_trunc('week', odoslane_at)::date tyzden, krok, count(*) from public.oslovenie_firiem_odoslane
where stav='odoslane' group by 1,2 order by 1,2;

\echo '== 13. Navstevy za 30 dni podla stranky (top 25)'
select cesta, count(*) from public.navstevy where created_at > now()-interval '30 days'
group by 1 order by 2 desc limit 25;

\echo '== 14. Referreri za 30 dni (top 15, len domena)'
select coalesce(substring(referrer from '^https?://([^/]+)'),'(priamo)') dom, count(*) from public.navstevy
where created_at > now()-interval '30 days' group by 1 order by 2 desc limit 15;

\echo '== 15. Navstevy denne 14 dni'
select created_at::date d, count(*) from public.navstevy where created_at > now()-interval '14 days' group by 1 order by 1;

\echo '== 16. Udalosti (events) za 30 dni podla typu'
select * from (select (to_jsonb(e) ->> 'typ') typ, count(*) from public.events e
  where (to_jsonb(e)->>'created_at')::timestamptz > now()-interval '30 days' group by 1 order by 2 desc limit 25) x;

\echo '== 17. Velkost databazy a najvacsie tabulky'
select pg_size_pretty(pg_database_size(current_database())) db;
select relname, pg_size_pretty(pg_total_relation_size(c.oid)) from pg_class c join pg_namespace n on n.oid=c.relnamespace
where n.nspname='public' and relkind='r' order by pg_total_relation_size(c.oid) desc limit 10;

\echo '== 18. Cerstvost zdrojov'
select 'contracts' z, max(published_at)::text from public.contracts
union all select 'uvo_vestniky', max(publikovany)::text from public.uvo_vestniky
union all select 'uvo_vyzvy', max(created_at)::text from public.uvo_vyzvy
union all select 'itms_sync', max(koniec)::text from public.itms_sync_log
union all select 'subsidies', max(podpisane)::text from public.subsidies;

\echo '== 19. Lehoty vo vyzvach: otvorene vs. po lehote'
select count(*) filter (where (to_jsonb(v)->>'lehota')::date >= current_date) otvorene,
       count(*) filter (where (to_jsonb(v)->>'lehota')::date < current_date) po_lehote,
       count(*) filter (where to_jsonb(v)->>'lehota' is null) bez_lehoty
from public.uvo_vyzvy v;
