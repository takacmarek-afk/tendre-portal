-- ════════════════════════════════════════════════════════════════════════
--  NA ČO OBCE DOSTÁVAJÚ PENIAZE
--
--  Stránka pre obce hovorila len „Ministerstvo dopravy rozdelilo 39,5 M €".
--  Z pohľadu starostky je to nepoužiteľné — chýbalo tam to jedno slovo,
--  ktoré potrebuje: NA ČO. Bez toho nevie, či sa jej to vôbec týka.
--
--  Sú to ZÁMERNE agregáty, nie zoznam zákaziek. Riadkové dotácie
--  s otvoreným oknom sú obsah dodávateľskej časti portálu a verejne ich
--  nedávame. Starostke stačí vedieť, že na cesty dotácie existujú,
--  koľko bývajú a kto ich dáva.
--
--  Spusti v SQL editore Supabase. Je bezpečné spustiť to aj opakovane.
-- ════════════════════════════════════════════════════════════════════════

create table if not exists public.ucely_dotacii (
    ucel            text primary key,   -- kluc z ucely.UCELY
    popis           text not null,      -- to, co vidi starostka
    obci            integer,
    dotacii         integer,
    median_suma     numeric,
    najmensia       numeric,
    najvacsia       numeric,
    objem_eur       numeric,
    poskytovatelia  text,               -- traja najcastejsi, oddelene bodkou
    posledna        date,
    last_seen_at    date,
    refreshed_at    timestamptz not null default now()
);

create index if not exists ix_ucely_dotacii on public.ucely_dotacii(dotacii desc);

alter table public.ucely_dotacii enable row level security;

drop policy if exists ucely_select on public.ucely_dotacii;
create policy ucely_select on public.ucely_dotacii
    for select to anon, authenticated using (true);

comment on table public.ucely_dotacii is
    'Na co obce dostavaju peniaze. Agregaty, nie zoznam zakaziek.';

select 'ucely_dotacii: ' || count(*)::text || ' riadkov (naplni ich beh pipeline)'
    as vysledok from public.ucely_dotacii;
