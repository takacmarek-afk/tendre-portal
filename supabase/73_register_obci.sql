-- =============================================================================
--  73 - REGISTER OBCI (vlna 86, 8. 10. 2026): hladanie najde KAZDU obec
--  Vloz do Supabase: SQL Editor -> New query -> Run. Spustit sa da opakovane.
-- =============================================================================
--
--  PROBLEM (zisteny 8. 10. 2026 pri skusani obci Trnavka a Revucka Lehota):
--  hladaj_obec() hladala len v obciach, ktore uz maju riadok v `opportunities`
--  (zmluva konciaca do 12 mesiacov) alebo v `subsidies` (dotacia nad 20 000 EUR).
--  Mala obec bez takeho riadku sa teda nenasla vobec a navstevnik dostal
--  "nic sme nenasli" - hoci obec existuje.
--
--  RIESENIE:
--   1) Tabulka `obce_register` (kod, nazov, kraj, okres) so VSETKYMI obcami SR
--      (zdroj: register Statistickeho uradu, pipeline/data/register_obce_raw.json).
--      Naplni ju workflow "Register obci" (pipeline/obce_register.py) - po tejto
--      migracii ho treba raz spustit.
--   2) hladaj_obec() hlada v registri aj v dotoch; presna zhoda a zhoda od
--      zaciatku nazvu su na zozname prve.
--   3) prvych_100_dni_suhrn() vracia navyse `ma_data` (je v dotoch nejaky riadok)
--      a `okres`. `najdena` je true aj pre obec, ktora je len v registri; stranka
--      vtedy ukaze vysvetlenie namiesto "nic sme nenasli".
--  Tabulka je zamknuta (RLS bez pravidiel, bez grantov) - cita ju len
--  SECURITY DEFINER funkcia. Rovnaky vzor ako ostatne verejne vyhladavanie.
-- =============================================================================

create table if not exists public.obce_register (
    kod           text primary key,
    nazov         text not null,
    kraj          text not null,
    okres         text,
    aktualizovane timestamptz not null default now()
);

alter table public.obce_register enable row level security;
revoke all on public.obce_register from public, anon, authenticated;

create index if not exists obce_register_nazov_idx on public.obce_register (lower(nazov));

-- -- Vyhladavanie: register + obce z dat ---
create or replace function public.hladaj_obec(p_hladanie text)
returns table(nazov text, kraj text)
language sql
stable
security definer
set search_path = ''
as $$
    with q as (
        select extensions.unaccent(trim(coalesce(p_hladanie, ''))) as t
    ),
    zdroj as (
        select r.nazov as n, r.kraj
          from public.obce_register r, q
         where q.t <> '' and char_length(q.t) <= 80
           and extensions.unaccent(r.nazov) ilike '%' || q.t || '%'
        union all
        select public._obec_core_nazov(o.authority_name), o.kraj
          from public.opportunities o, q
         where q.t <> '' and char_length(q.t) <= 80
           and public._je_obec_nazov(o.authority_name)
           and extensions.unaccent(o.authority_name) ilike '%' || q.t || '%'
        union all
        select public._obec_core_nazov(s.prijimatel), s.kraj
          from public.subsidies s, q
         where q.t <> '' and char_length(q.t) <= 80
           and public._je_obec_nazov(s.prijimatel)
           and extensions.unaccent(s.prijimatel) ilike '%' || q.t || '%'
    ),
    jedinecne as (
        select distinct on (lower(n), kraj) n, kraj
          from zdroj
         where n is not null and trim(n) <> ''
         order by lower(n), kraj nulls last
    )
    select j.n as nazov, j.kraj
      from jedinecne j, q
     order by case when lower(extensions.unaccent(j.n)) = lower(q.t) then 0
                   when lower(extensions.unaccent(j.n)) like lower(q.t) || '%' then 1
                   else 2 end,
              lower(j.n), j.kraj nulls last
     limit 25;
$$;

grant execute on function public.hladaj_obec(text) to anon, authenticated;

-- -- Suhrn: pribudli ma_data a okres (zmena stlpcov = najprv DROP) ---
drop function if exists public.prvych_100_dni_suhrn(text, text);

create or replace function public.prvych_100_dni_suhrn(p_nazov text, p_kraj text default null)
returns table(
    najdena             boolean,
    ma_data             boolean,
    kraj                text,
    okres               text,
    pocet_konciacich    integer,
    objem_konciacich    numeric,
    pocet_dotacii_bezi  integer,
    objem_dotacii_bezi  numeric
)
language sql
stable
security definer
set search_path = ''
as $$
    with n as (
        select lower(trim(coalesce(p_nazov, ''))) as core,
               nullif(trim(coalesce(p_kraj, '')), '') as kraj_filter
    ),
    op as (
        select o.kraj, o.price_total, o.effective_to
          from public.opportunities o, n
         where n.core <> ''
           and public._je_obec_nazov(o.authority_name)
           and lower(public._obec_core_nazov(o.authority_name)) = n.core
           and (n.kraj_filter is null or lower(o.kraj) = lower(n.kraj_filter))
    ),
    su as (
        select s.kraj, s.suma, s.okno_do
          from public.subsidies s, n
         where n.core <> ''
           and public._je_obec_nazov(s.prijimatel)
           and lower(public._obec_core_nazov(s.prijimatel)) = n.core
           and (n.kraj_filter is null or lower(s.kraj) = lower(n.kraj_filter))
    ),
    reg as (
        select r.kraj, r.okres
          from public.obce_register r, n
         where n.core <> ''
           and lower(r.nazov) = n.core
           and (n.kraj_filter is null or lower(r.kraj) = lower(n.kraj_filter))
         order by r.kraj, r.okres
         limit 1
    ),
    zm as (
        select count(*)::int as pocet, coalesce(sum(price_total), 0) as objem
          from op
         where effective_to between current_date and (current_date + interval '365 days')
    ),
    dt as (
        select count(*)::int as pocet, coalesce(sum(suma), 0) as objem
          from su
         where okno_do is null or okno_do >= current_date
    )
    select
        (exists(select 1 from op) or exists(select 1 from su) or exists(select 1 from reg)) as najdena,
        (exists(select 1 from op) or exists(select 1 from su)) as ma_data,
        coalesce((select kraj from op where kraj is not null limit 1),
                 (select kraj from su where kraj is not null limit 1),
                 (select kraj from reg),
                 (select kraj_filter from n)) as kraj,
        (select okres from reg) as okres,
        zm.pocet, zm.objem,
        dt.pocet, dt.objem
    from zm, dt;
$$;

grant execute on function public.prvych_100_dni_suhrn(text, text) to anon, authenticated;

select 'Migracia 73 hotova: tabulka obce_register + hladanie v registri. Teraz spustite workflow "Register obci".' as vysledok;
