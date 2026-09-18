-- =============================================================================
--  NÁVŠTEVNOSŤ — unikátne návštevy + vylúčenie admina
--  Vlož do Supabase: SQL Editor -> New query -> Run. Spustiť sa dá opakovane.
--
--  Marek nahlásil dva problémy so štatistikami z 27_navstevnost.sql:
--  (1) jeho vlastné prekliknutie appky ako admin sa počítalo do čísel,
--  (2) jeden človek, čo si preklikol 3 stránky, sa počítal ako 3 "návštevy"
--      namiesto 1 — číslo teda vyzeralo vyššie, než koľko ľudí reálne prišlo.
--
--  Riešenie (2): pridaný voliteľný session_id — náhodné ID v sessionStorage
--  prehliadača (nie cookie, mizne so zatvorením karty), rovnaké pre všetky
--  stránky prezerané v jednej návšteve. Funkcie nižšie počítajú
--  count(distinct session_id) namiesto count(*) — to je "unikátna návšteva".
--  Riadky bez session_id (staré dáta pred touto migráciou, alebo zlyhanie
--  sessionStorage) sa počítajú každý zvlášť (fallback na pôvodné správanie).
--
--  Riešenie (1) je v public/*.html (tracking snippet) — pred POSTom overí
--  cez je_admin() RPC, či je v prehliadači prihlásený admin, a ak áno,
--  vôbec nič neposle. Táto migrácia len pridáva stĺpec, na ktorý sa ten
--  check nespolieha.
-- =============================================================================

alter table public.navstevy
    add column if not exists session_id text;

create index if not exists ix_navstevy_session_id on public.navstevy(session_id);


create or replace function public.navstevnost_stranky(p_dni int default 30)
returns table(cesta text, navstev bigint)
language sql
security definer
set search_path = public
stable
as $$
  select n.cesta, count(distinct coalesce(n.session_id, n.id::text)) as navstev
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
         count(distinct coalesce(n.session_id, n.id::text)) as navstev
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
  select date(n.created_at) as den,
         count(distinct coalesce(n.session_id, n.id::text)) as navstev
  from public.navstevy n
  where public.je_admin()
    and n.created_at >= now() - (greatest(p_dni, 1) || ' days')::interval
  group by 1
  order by 1 desc;
$$;

-- Funkcie už existujú s rovnakým menom/signatúrou (create or replace ich
-- len prepíše) — práva (revoke/grant) sú už nastavené z 27_navstevnost.sql
-- a create or replace ich nemení.

select 'Navstevnost: session_id stlpec pridany, funkcie prepocitane na unikatne navstevy. Stlpcov s session_id: ' ||
       (select count(*) from information_schema.columns
         where table_schema='public' and table_name='navstevy' and column_name='session_id') as vysledok;
