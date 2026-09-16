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


-- ════════════════════════════════════════════════════════════════════════
--  DOPLNENÉ 16. 9. 2026 — OPRAVA MAZANIA STARÝCH RIADKOV
--
--  Našiel som to až na produkcii. `_nahrad_tabulku` mazalo staré riadky
--  podmienkou `last_seen_at < dnes`. Lenže `last_seen_at` je DÁTUM, takže
--  pri dvoch behoch v ten istý deň majú staré riadky tiež dnešný dátum
--  a podmienka „starší než dnes" ich NEZMAŽE.
--
--  Prejavilo sa to takto: opravil som kód tak, aby sa zo stránky prestalo
--  zobrazovať meno fyzickej osoby ako poskytovateľa dotácií. Kód bol
--  správny, beh prešiel — a meno tam zostalo. Až do polnoci.
--
--  Pipeline teraz porovnáva `refreshed_at`, čo je timestamptz, takže dva
--  behy o tri minúty od seba sa už rozlíšia. Táto tabuľka bola jediná,
--  ktorá ten stĺpec nemala.
-- ════════════════════════════════════════════════════════════════════════

alter table public.ceny_prilezitosti
    add column if not exists refreshed_at timestamptz not null default now();

select 'ceny_prilezitosti ma refreshed_at: ' ||
       (select count(*)::text from information_schema.columns
        where table_schema='public' and table_name='ceny_prilezitosti'
          and column_name='refreshed_at') as vysledok;
