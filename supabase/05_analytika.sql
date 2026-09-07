-- =============================================================================
--  ANALYTIKA — region, mesacna cena, navysenia, profily dodavatelov
--  Vloz do Supabase: SQL Editor -> New query -> Run. Spustit sa da opakovane.
-- =============================================================================

-- 1. Nove stlpce v prilezitostiach ----------------------------------------
alter table public.opportunities add column if not exists mesto              text;
alter table public.opportunities add column if not exists kraj               text;
alter table public.opportunities add column if not exists mesacna_cena       numeric;
alter table public.opportunities add column if not exists median_mesacna     numeric;
alter table public.opportunities add column if not exists odchylka_pct       numeric;
alter table public.opportunities add column if not exists vzoriek            integer;
alter table public.opportunities add column if not exists navysenie_pct      numeric;
alter table public.opportunities add column if not exists typicka_dlzka_dni  integer;

create index if not exists ix_opp_kraj  on public.opportunities(kraj);
create index if not exists ix_opp_mesto on public.opportunities(mesto);

-- To iste pri dotaciach — filter na kraj ma zmysel aj tam
alter table public.subsidies add column if not exists mesto text;
alter table public.subsidies add column if not exists kraj  text;

create index if not exists ix_subsidies_kraj on public.subsidies(kraj);


-- 2. Profily dodavatelov --------------------------------------------------
-- Kto najviac pracuje pre stat, za kolko, u kolkych uradov a ako casto
-- si po podpise priplaca dodatkami.
--
-- POZNAMKA K FORMULACII: vysoke navysenie NIE JE dokaz niceho nekaleho.
-- Legitimne dovody existuju. V UI sa to zobrazuje ako fakt s kontextom,
-- nikdy ako obvinenie.
create table if not exists public.dodavatelia (
    supplier_cin              text primary key,
    dodavatel                 text,
    hlavny_sektor             text,
    zmluv                     integer,
    objem_eur                 numeric,
    priemerna_zmluva_eur      numeric,
    uradov                    integer,
    sektorov                  integer,
    zmluv_s_navysenim         integer,
    podiel_zmluv_s_navysenim  numeric,
    priemerne_navysenie_pct   numeric,
    prva_zmluva               date,
    posledna_zmluva           date,
    refreshed_at              timestamptz not null default now()
);

create index if not exists ix_dod_objem   on public.dodavatelia(objem_eur desc);
create index if not exists ix_dod_sektor  on public.dodavatelia(hlavny_sektor);
create index if not exists ix_dod_navys   on public.dodavatelia(priemerne_navysenie_pct desc);

alter table public.dodavatelia enable row level security;

drop policy if exists dodavatelia_select on public.dodavatelia;
create policy dodavatelia_select on public.dodavatelia
    for select to authenticated
    using (public.ma_aktivny_pristup());


-- 3. Medianne mesacne ceny per sektor ------------------------------------
-- Male tabulky, ale drzime ich zvlast, aby sa dali zobrazit aj bez
-- konkretnej prilezitosti.
create table if not exists public.ceny_sektor (
    sector          text primary key,
    median_mesacna  numeric,
    vzoriek         integer,
    refreshed_at    timestamptz not null default now()
);

alter table public.ceny_sektor enable row level security;

drop policy if exists ceny_sektor_select on public.ceny_sektor;
create policy ceny_sektor_select on public.ceny_sektor
    for select to authenticated
    using (public.ma_aktivny_pristup());


select 'Analytika pripravena: stlpce doplnene, tabulky dodavatelia a ceny_sektor vytvorene.' as vysledok;
