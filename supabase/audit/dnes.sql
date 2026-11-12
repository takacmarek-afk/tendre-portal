-- Dnesny lievik (12. 11. 2026). LEN CITANIE. Len suhrnne pocty, ziadne e-maily ani mena (logy su verejne).
set session characteristics as transaction read only;
\pset footer off
\echo '== A. Odoslane e-maily dnes (oslovenie firiem, osobne, onboarding, obce)'
select 'oslovenie_firiem' t, krok::text, stav, count(*) from public.oslovenie_firiem_odoslane
 where odoslane_at::date = current_date group by 2,3
union all select 'onboarding', null, null, count(*) from public.onboarding_odoslane where (to_jsonb(onboarding_odoslane)->>'odoslane_at')::date = current_date
union all select 'kampan_obce', null, stav, count(*) from public.kampan_obce_odoslane where odoslane_at::date = current_date group by 3;

\echo '== B. Navstevy dnes podla zdroja (utm) a stranky'
select coalesce(utm_source,'-') src, coalesce(utm_campaign,'-') kampan, split_part(cesta,'?',1) stranka,
       count(*) zaznamov, count(distinct session_id) unikatnych
from public.navstevy where created_at >= current_date
group by 1,2,3 order by 4 desc limit 40;

\echo '== C. Navstevy z e-mailov za 3 dni (unikatne podla dna)'
select created_at::date d, coalesce(utm_campaign,'-') kampan, count(distinct session_id) unikatnych
from public.navstevy where created_at > now() - interval '3 days' and utm_source = 'email'
group by 1,2 order by 1,2;

\echo '== D. Udalosti dnes (events + udalosti)'
select 'events' z, (to_jsonb(e)->>'typ') typ, count(*) from public.events e
 where (to_jsonb(e)->>'created_at')::timestamptz >= current_date group by 2
union all
select 'udalosti', nazov, count(*) from public.udalosti where created_at >= current_date group by 2
order by 1,3 desc;

\echo '== E. Nove ucty a organizacie (dnes / 3 dni)'
select 'auth_users_dnes' t, count(*) from auth.users where created_at >= current_date
union all select 'auth_users_3dni', count(*) from auth.users where created_at > now()-interval '3 days'
union all select 'prihlasenia_dnes', count(*) from auth.users where last_sign_in_at >= current_date
union all select 'organizations_dnes', count(*) from public.organizations where (to_jsonb(organizations)->>'created_at')::timestamptz >= current_date;

\echo '== F. Pilot pozvanky'
select count(*) vsetky, count(*) filter (where (to_jsonb(p)->>'prijate_at') is not null) prijate,
       max((to_jsonb(p)->>'vytvorene_at')) posledna
from public.pilot_pozvanky p;

\echo '== G. Odpovede na oslovenie (posledne 3 dni)'
select (to_jsonb(o)->>'typ') typ, count(*) from public.oslovenie_odpovede o
 where (to_jsonb(o)->>'created_at')::timestamptz > now()-interval '3 days' group by 1;
