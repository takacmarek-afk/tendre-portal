-- =============================================================================
--  46 — OPRAVA MERANÍ (nadväzuje na 45_merania.sql)
--  Vlož do Supabase: SQL Editor -> New query -> Run. Spustiť sa dá opakovane.
--
--  1. Rebríček: všetky kroky rovnaké časové okno, ktoré začína najskôr pri
--     spustení meraní (vlna 33, 24. 9. 2026). Predtým boli kliky a e-maily
--     merané len od nasadenia, ale registrácie a platby za 30 dní, a z toho
--     vychádzali percentá nad 100 %.
--  2. Rebríček: platby a odbery zakladateľa (jeho organizácie) sa nerátajú —
--     boli to testovacie platby, ktoré skresľovali tržby.
--  3. Zdroje: facebook.com / m.facebook.com / l.facebook.com a pod. sú jeden
--     zdroj "facebook" (rovnaký názov ako utm_source v našich odkazoch); UTM zdroj bez ohľadu na veľké písmená; interný odkaz ako prvá
--     stránka návštevy (nová karta otvorená z webu) je pomenovaný.
-- =============================================================================

-- Začiatok meraní udalostí (nasadenie vlny 33). Staršie obdobie by miešalo
-- kroky, ktoré sa vtedy ešte nezaznamenávali.
create or replace function public.merania_zaciatok()
returns timestamptz
language sql
immutable
as $$ select timestamptz '2026-09-24 20:30:00+00' $$;


-- ─── Rebríček ────────────────────────────────────────────────────────────
-- Mení sa návratový typ (pribudol stĺpec od), preto drop + create.
drop function if exists public.merania_rebricek(int);

create function public.merania_rebricek(p_dni int default 30)
returns table(krok text, poradie int, pocet bigint, suma numeric, od timestamptz)
language sql
security definer
set search_path = public, auth
stable
as $$
  with od as (
    select greatest(now() - (greatest(p_dni, 1) || ' days')::interval,
                    public.merania_zaciatok()) as t
  ),
  admin_org as (
    select m.org_id
    from public.memberships m
    join auth.users u on u.id = m.user_id
    where u.email = 'takac.marek@gmail.com'
  )
  select x.krok, x.poradie, x.pocet, x.suma, (select t from od)
  from (
    select 'Návštevy (unikátne)'::text as krok, 1 as poradie,
           count(distinct coalesce(n.session_id, n.id::text)) as pocet, null::numeric as suma
      from public.navstevy n, od where n.created_at >= od.t
    union all
    select 'Klik na Vyskúšať / Prihlásiť', 2,
           count(distinct coalesce(u.session_id, u.id::text)), null
      from public.udalosti u, od where u.nazov = 'klik_vyskusat' and u.created_at >= od.t
    union all
    select 'Odoslaný prihlasovací e-mail', 3,
           count(distinct coalesce(u.session_id, u.id::text)), null
      from public.udalosti u, od where u.nazov = 'odoslany_prihlasovaci_email' and u.created_at >= od.t
    union all
    select 'Nové registrácie (účty)', 4, count(*), null
      from auth.users au, od
     where au.created_at >= od.t and au.email is distinct from 'takac.marek@gmail.com'
    union all
    select 'Zapnutý e-mailový odber', 5, count(*), null
      from public.odber o, od
     where o.created_at >= od.t and o.chce_email
       and o.user_id not in (select id from auth.users where email = 'takac.marek@gmail.com')
    union all
    select 'Spustená platba', 6, count(*), sum(p.suma)
      from public.platby p, od
     where p.created_at >= od.t
       and (p.org_id is null or p.org_id not in (select org_id from admin_org))
    union all
    select 'Zaplatené', 7, count(*), sum(p.suma)
      from public.platby p, od
     where p.created_at >= od.t and p.stav = 'zaplatena'
       and (p.org_id is null or p.org_id not in (select org_id from admin_org))
  ) x
  where public.je_admin()
  order by x.poradie;
$$;


-- ─── Zdroje ──────────────────────────────────────────────────────────────
create or replace function public.merania_zdroje(p_dni int default 30)
returns table(zdroj text, medium text, kampan text, navstev bigint)
language sql
security definer
set search_path = public
stable
as $$
  with prve as (
    select distinct on (coalesce(n.session_id, n.id::text))
           n.referrer, n.utm_source, n.utm_medium, n.utm_campaign
    from public.navstevy n
    where n.created_at >= now() - (greatest(p_dni, 1) || ' days')::interval
    order by coalesce(n.session_id, n.id::text), n.created_at
  ),
  s_hostom as (
    select v.*,
           -- host bez www. / m. / l. / lm. / mobile. (facebook, instagram…)
           regexp_replace(
             lower(substring(v.referrer from '^https?://([^/:?#]+)')),
             '^(www|m|l|lm|mobile)\.', ''
           ) as host
    from prve v
  )
  select
    case
      when nullif(v.utm_source, '') is not null then lower(v.utm_source)
      when v.host is null or v.host = '' then '(priamo / bez odkazu)'
      when v.host = 'predtendrom.sk' then '(interný odkaz — nová karta)'
      when v.host ~ '(^|\.)google\.' then 'google'
      when v.host in ('facebook.com', 'fb.com', 'fb.me') then 'facebook'
      when v.host = 'instagram.com' then 'instagram'
      when v.host in ('linkedin.com', 'lnkd.in') then 'linkedin'
      else v.host
    end as zdroj,
    coalesce(nullif(lower(v.utm_medium), ''), '—') as medium,
    coalesce(nullif(v.utm_campaign, ''), '—') as kampan,
    count(*) as navstev
  from s_hostom v
  where public.je_admin()
  group by 1, 2, 3
  order by navstev desc
  limit 30;
$$;


revoke all on function public.merania_rebricek(int) from public;
revoke all on function public.merania_rebricek(int) from anon;
grant execute on function public.merania_rebricek(int) to authenticated;
revoke all on function public.merania_zdroje(int)   from public;
revoke all on function public.merania_zdroje(int)   from anon;
grant execute on function public.merania_zdroje(int)   to authenticated;
revoke all on function public.merania_zaciatok()     from anon;
