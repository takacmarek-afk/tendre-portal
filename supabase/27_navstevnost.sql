-- =============================================================================
--  NÁVŠTEVNOSŤ — vlastná mini-analytika namiesto plateného Plausible
--  Vlož do Supabase: SQL Editor -> New query -> Run. Spustiť sa dá opakovane.
--
--  PREČO VLASTNÉ RIEŠENIE, NIE PLAUSIBLE: Marek už má hosting (Cloudflare
--  Pages) aj databázu (Supabase) aj e-mailový pipeline (Resend) — všetko,
--  čo táto vrstva potrebuje. Platený Plausible (9 $/mes.) by bol nový
--  mesačný náklad a self-hosted Plausible by vyžadoval nový server
--  (Docker, Postgres, ClickHouse), čo Cloudflare Pages (len statické
--  súbory) nevie spustiť. Táto tabuľka nezbiera nič, čo by Plausible
--  nezbieral tiež — žiadne cookies, žiadny identifikátor návštevníka,
--  len cesta + odkiaľ prišiel + kedy. Zostáva pravdivé tvrdenie v texte
--  o ochrane údajov ("žiadne analytické cookies").
-- =============================================================================

-- ─── 1. Tabuľka návštev ──────────────────────────────────────────────────
-- Zámerne BEZ session/visitor ID — nie je to sledovanie človeka naprieč
-- návštevami, len počítadlo "koľko + odkiaľ + kedy" na úrovni stránky.
create table if not exists public.navstevy (
    id         bigserial primary key,
    cesta      text not null,
    referrer   text,
    created_at timestamptz not null default now()
);

create index if not exists ix_navstevy_cesta      on public.navstevy(cesta);
create index if not exists ix_navstevy_created_at on public.navstevy(created_at);


-- ─── 2. Práva ────────────────────────────────────────────────────────────
alter table public.navstevy enable row level security;

-- Hocikto (aj neprihlásený návštevník) môže PRIDAŤ jeden riadok — presne
-- jeden fetch() z verejnej stránky pri načítaní. Nikto nesmie čítať priamo:
-- rovnaký vzor ako odber_obce (11_obce_a_email.sql) — bez toho by
-- ktokoľvek vedel dopytom zistiť presnú návštevnosť konkurencie.
drop policy if exists navstevy_insert on public.navstevy;
create policy navstevy_insert on public.navstevy
    for insert to anon, authenticated with check (true);

-- Žiadna select politika tu ZÁMERNE nie je. Čítanie ide výhradne cez
-- funkcie nižšie (len pre Mareka) alebo cez pipeline so service_role.

comment on table public.navstevy is
    'Vlastna mini-analytika navstevnosti (nahrada za Plausible). '
    'Anon smie len INSERT, citanie je zakazane okrem navstevnost_*() funkcii.';


-- ─── 3. Overenie admina ──────────────────────────────────────────────────
-- Instance-wide admin, nie organizacny 'owner' (to je iny koncept — vid
-- memberships.rola). Projekt ma jedineho zakladatela, takze porovnanie
-- s pevnym e-mailom je poctive riesenie, nie skratka — meniť sa bude len
-- vtedy, ked pribudne druhy clovek so spravcovskym pristupom.
create or replace function public.je_admin()
returns boolean
language sql
security definer
set search_path = public
stable
as $$
  select coalesce(
    (select email from auth.users where id = auth.uid()) = 'takac.marek@gmail.com',
    false
  );
$$;

revoke all on function public.je_admin() from public;
grant execute on function public.je_admin() to authenticated;


-- ─── 4. Čítanie — len pre admina ─────────────────────────────────────────
-- Tri pohľady namiesto jedného veľkého exportu: najviac navštevované
-- stránky, odkiaľ ľudia prichádzajú, a denný trend. To je presne to, čo
-- audit z 17.9.2026 označil za chýbajúce ("nulová analytika = slepá UX
-- iterácia") — nie kompletná Plausible-úroveň dashboardu, len základ.
create or replace function public.navstevnost_stranky(p_dni int default 30)
returns table(cesta text, navstev bigint)
language sql
security definer
set search_path = public
stable
as $$
  select n.cesta, count(*) as navstev
  from public.navstevy n
  where public.je_admin()
    and n.created_at >= now() - (greatest(p_dni, 1) || ' days')::interval
  group by n.cesta
  order by navstev desc
  limit 50;
$$;

create or replace function public.navstevnost_referreri(p_dni int default 30)
returns table(referrer text, navstev bigint)
language sql
security definer
set search_path = public
stable
as $$
  select coalesce(nullif(n.referrer, ''), '(priamo / bez odkazu)') as referrer,
         count(*) as navstev
  from public.navstevy n
  where public.je_admin()
    and n.created_at >= now() - (greatest(p_dni, 1) || ' days')::interval
  group by 1
  order by navstev desc
  limit 20;
$$;

create or replace function public.navstevnost_denne(p_dni int default 30)
returns table(den date, navstev bigint)
language sql
security definer
set search_path = public
stable
as $$
  select date(n.created_at) as den, count(*) as navstev
  from public.navstevy n
  where public.je_admin()
    and n.created_at >= now() - (greatest(p_dni, 1) || ' days')::interval
  group by 1
  order by 1 desc;
$$;

revoke all on function public.navstevnost_stranky(int)   from public;
revoke all on function public.navstevnost_referreri(int) from public;
revoke all on function public.navstevnost_denne(int)     from public;
grant execute on function public.navstevnost_stranky(int)   to authenticated;
grant execute on function public.navstevnost_referreri(int) to authenticated;
grant execute on function public.navstevnost_denne(int)     to authenticated;


-- ════════════════════════════════════════════════════════════════════════
--  KONTROLA
-- ════════════════════════════════════════════════════════════════════════
select 'Navstevnost pripravena: tabulka + ' ||
       (select count(*) from pg_proc where proname in
         ('je_admin', 'navstevnost_stranky', 'navstevnost_referreri', 'navstevnost_denne')
         and pronamespace = 'public'::regnamespace) ||
       ' funkcie.' as vysledok;
