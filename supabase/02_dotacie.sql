-- =============================================================================
--  DOTACIE — predzvest tendra
--  Vloz do Supabase: SQL Editor -> New query -> Run
--  Spustit sa da opakovane.
--
--  Ked obec dostane nenavratny financny prispevok na rekonstrukciu skoly,
--  musi na tu rekonstrukciu vyhlasit verejne obstaravanie. Vidime to teda
--  o pol roka az rok a pol skor, nez sa tender objavi vo vestniku.
-- =============================================================================

create table if not exists public.subsidies (
    contract_id    bigint primary key references public.contracts(id) on delete cascade,
    prijimatel     text,          -- obec, mesto, skola (v CRZ je v poli dodavatela!)
    prijimatel_ico text,
    poskytovatel   text,          -- ministerstvo, agentura
    ucel           text,
    suma           numeric,
    podpisane      date,
    ucinne_od      date,
    sektor_odhad   text,          -- na aku pracu to je, na parovanie s klientom
    okno_od        date,          -- odhad, odkedy moze tender prist
    okno_do        date,          -- dokedy ma zmysel cakat
    odkaz          text,
    refreshed_at   timestamptz not null default now()
);

create index if not exists ix_subsidies_okno   on public.subsidies(okno_od);
create index if not exists ix_subsidies_sektor on public.subsidies(sektor_odhad);
create index if not exists ix_subsidies_suma   on public.subsidies(suma desc);

alter table public.subsidies enable row level security;

-- Rovnaky rezim ako pri prilezitostiach: verejne data statu, ale len pre
-- pouzivatelov s platnym trialom alebo predplatnym.
drop policy if exists subsidies_select on public.subsidies;
create policy subsidies_select on public.subsidies
    for select to authenticated
    using (public.ma_aktivny_pristup());

select 'Tabulka subsidies pripravena.' as vysledok;
