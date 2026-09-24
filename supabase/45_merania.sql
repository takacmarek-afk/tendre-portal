-- =============================================================================
--  45 — MERANIA: zdroj návštevy (UTM), udalosti bez cookies, rebríček
--  konverzie a miera súhlasu s cookies.
--  Vlož do Supabase: SQL Editor -> New query -> Run. Spustiť sa dá opakovane.
--
--  PREČO: Google Analytics vidí naplno len tých, čo klikli "Prijať".
--  Obchodné čísla (koľko ľudí prišlo, klikli, zaregistrovali sa, aktivovali
--  odber, zaplatili) preto berieme z vlastnej databázy — bez cookies, bez
--  identifikátora návštevníka (session_id je len náhodné ID v sessionStorage
--  jednej karty, rovnako ako v 30_navstevnost_unique.sql). GA4 ostáva na to,
--  ODKIAĽ ľudia prišli a čo robili, u tých, čo súhlasili.
--
--  PORADIE NASADENIA: túto migráciu treba spustiť SKÔR, než sa nasadí nový
--  JS (vlna 33) — tracking snippet posiela nové stĺpce utm_*, a keby v tabuľke
--  ešte neboli, PostgREST by insert odmietol a pageview by sa stratil.
-- =============================================================================

-- ─── 1. UTM zdroj pri návšteve ───────────────────────────────────────────
alter table public.navstevy add column if not exists utm_source   text;
alter table public.navstevy add column if not exists utm_medium   text;
alter table public.navstevy add column if not exists utm_campaign text;

-- Obmedzenie dĺžky, aby anonymný insert nemohol zapísať ľubovoľne dlhý text.
alter table public.navstevy drop constraint if exists navstevy_utm_dlzka;
alter table public.navstevy add constraint navstevy_utm_dlzka check (
    coalesce(length(utm_source), 0)   <= 100 and
    coalesce(length(utm_medium), 0)   <= 100 and
    coalesce(length(utm_campaign), 0) <= 150
);


-- ─── 2. Udalosti bez cookies ─────────────────────────────────────────────
create table if not exists public.udalosti (
    id           bigserial primary key,
    nazov        text not null,
    cesta        text,
    session_id   text,
    utm_source   text,
    utm_medium   text,
    utm_campaign text,
    created_at   timestamptz not null default now()
);

alter table public.udalosti drop constraint if exists udalosti_nazov_povolene;
alter table public.udalosti add constraint udalosti_nazov_povolene check (nazov in (
    'klik_vyskusat',                -- klik na odkaz/tlačidlo vedúce na prihlásenie
    'odoslany_prihlasovaci_email',  -- prihlasenie.html: magic link úspešne odoslaný
    'begin_checkout',               -- app.html: klik na Zaplatiť (spustenie Stripe)
    'purchase',                     -- platba-vysledok.html so stav=uspech
    'suhlas_prijaty',               -- cookie banner: Prijať
    'suhlas_odmietnuty'             -- cookie banner: Iba nevyhnutné
));

alter table public.udalosti drop constraint if exists udalosti_dlzka;
alter table public.udalosti add constraint udalosti_dlzka check (
    coalesce(length(cesta), 0)        <= 300 and
    coalesce(length(session_id), 0)   <= 80  and
    coalesce(length(utm_source), 0)   <= 100 and
    coalesce(length(utm_medium), 0)   <= 100 and
    coalesce(length(utm_campaign), 0) <= 150
);

create index if not exists ix_udalosti_created_at on public.udalosti(created_at);
create index if not exists ix_udalosti_nazov      on public.udalosti(nazov);

alter table public.udalosti enable row level security;

-- Rovnaký vzor ako navstevy: anon smie len pridať riadok, čítať nikto priamo.
drop policy if exists udalosti_insert on public.udalosti;
create policy udalosti_insert on public.udalosti
    for insert to anon, authenticated with check (true);

comment on table public.udalosti is
    'Udalosti bez cookies (kliky, odoslany prihlasovaci e-mail, zaciatok '
    'platby, platba, volba v cookie banneri). Anon smie len INSERT, citanie '
    'len cez merania_*() funkcie pre admina.';


-- ─── 3. Zdroje návštev (UTM, inak doména referrera) — len admin ──────────
-- Počíta sa podľa PRVEJ stránky každej návštevy (session), aby jedna návšteva
-- prekliknutá cez viac stránok nepadla aj do "predtendrom.sk" (interný
-- referrer ďalších stránok) a aby sa nepočítala dvakrát.
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
  )
  select
    coalesce(
      nullif(v.utm_source, ''),
      nullif(substring(v.referrer from '^https?://(?:www\.)?([^/:]+)'), ''),
      '(priamo / bez odkazu)'
    ) as zdroj,
    coalesce(nullif(v.utm_medium, ''), '—') as medium,
    coalesce(nullif(v.utm_campaign, ''), '—') as kampan,
    count(*) as navstev
  from prve v
  where public.je_admin()
  group by 1, 2, 3
  order by navstev desc
  limit 30;
$$;


-- ─── 4. Rebríček konverzie — len admin ───────────────────────────────────
-- Každý krok zo "svojho" zdroja pravdy: návštevy a kliky z navstevy/udalosti
-- (bez cookies), registrácie z auth.users, aktivácie z odber, platby z platby.
-- Admin (je_admin e-mail) sa do registrácií nepočíta.
create or replace function public.merania_rebricek(p_dni int default 30)
returns table(krok text, poradie int, pocet bigint, suma numeric)
language sql
security definer
set search_path = public, auth
stable
as $$
  with od as (select now() - (greatest(p_dni, 1) || ' days')::interval as t)
  select * from (
    select 'Návštevy (unikátne)'::text, 1,
           count(distinct coalesce(n.session_id, n.id::text)), null::numeric
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
      from public.odber o, od where o.created_at >= od.t and o.chce_email
    union all
    select 'Spustená platba', 6, count(*), sum(p.suma)
      from public.platby p, od where p.created_at >= od.t
    union all
    select 'Zaplatené', 7, count(*), sum(p.suma)
      from public.platby p, od where p.created_at >= od.t and p.stav = 'zaplatena'
  ) x(krok, poradie, pocet, suma)
  where public.je_admin()
  order by poradie;
$$;


-- ─── 5. Miera súhlasu s cookies — len admin ──────────────────────────────
create or replace function public.merania_suhlas(p_dni int default 30)
returns table(volba text, pocet bigint)
language sql
security definer
set search_path = public
stable
as $$
  select case u.nazov when 'suhlas_prijaty' then 'Prijať' else 'Iba nevyhnutné' end,
         count(distinct coalesce(u.session_id, u.id::text))
  from public.udalosti u
  where public.je_admin()
    and u.nazov in ('suhlas_prijaty', 'suhlas_odmietnuty')
    and u.created_at >= now() - (greatest(p_dni, 1) || ' days')::interval
  group by 1
  order by 2 desc;
$$;

revoke all on function public.merania_zdroje(int)   from public;
revoke all on function public.merania_rebricek(int) from public;
revoke all on function public.merania_suhlas(int)   from public;
grant execute on function public.merania_zdroje(int)   to authenticated;
grant execute on function public.merania_rebricek(int) to authenticated;
grant execute on function public.merania_suhlas(int)   to authenticated;

-- Supabase dáva funkciám v schéme public execute aj priamo roli anon (default
-- privileges), takže "revoke ... from public" nestačí. Dáta by aj tak nevrátili
-- (je_admin() je pre anon false), ale anon ich nemá čo volať vôbec.
revoke all on function public.merania_zdroje(int)   from anon;
revoke all on function public.merania_rebricek(int) from anon;
revoke all on function public.merania_suhlas(int)   from anon;
