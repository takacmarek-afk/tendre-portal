-- =============================================================================
--  KRAJ_PREHLAD — verejny agregat dotacii per kraj, zaklad pre SEO podstranky
--  Vloz do Supabase: SQL Editor -> New query -> Run. Spustit sa da opakovane.
-- =============================================================================
--
--  CO TO JE
--  Audit 18.9. ("Marketing", "Prioritizacia"): /obce.html ma vysoky
--  long-tail SEO potencial ("dotacie pre obce [kraj]"), ale dnes je to
--  jedna staticka stranka. Tato tabulka je verejny (anon-citatelny) zaklad
--  pre programovo generovane podstranky per kraj — rovnaky rezim ako
--  `ucely_dotacii`/`aktivne_programy`/`sprostredkovatelia` (11_obce_a_email.sql,
--  12_ucely.sql): AGREGATY, nie riadkove data. Riadkove dotacie s oknom
--  ostavaju dodavatelskym obsahom za prihlasenim, presne ako inde v projekte.
--
--  `subsidies` sama o sebe je authenticated-only (02_dotacie.sql) — tato
--  tabulka existuje presne preto, aby sa z nej dal verejne ukazat SUHRN
--  bez toho, aby sa odhalili jednotlive zmluvy.
-- =============================================================================

create table if not exists public.kraj_prehlad (
    kraj           text primary key,
    obci           integer,
    dotacii        integer,
    objem_eur      numeric,
    median_suma    numeric,
    top_ucely      text,        -- traja najcastejsi ucely v kraji, oddelene bodkou
    top_poskytovatelia text,    -- traja najcastejsi poskytovatelia v kraji
    posledna       date,
    last_seen_at   date,
    refreshed_at   timestamptz not null default now()
);

alter table public.kraj_prehlad enable row level security;

drop policy if exists kraj_prehlad_select on public.kraj_prehlad;
create policy kraj_prehlad_select on public.kraj_prehlad
    for select to anon, authenticated using (true);

comment on table public.kraj_prehlad is
    'Verejny agregat dotacii per kraj (obci, dotacii, objem, top ucely/poskytovatelia). '
    'Zaklad pre programovo generovane SEO podstranky /obce/kraj-*.html. '
    'Riadkove dotacie NEODHALUJE — presny rezim ako ucely_dotacii.';

-- ── Prve naplnenie (18.9.2026, jedenasta vlna) ───────────────────────────
-- Buduce behy pipeline (pipeline/main.py, po zavedeni refresh kroku) toto
-- prepisu cerstvymi datami. Tento INSERT je len naplnenie na start, nie
-- jednorazovy hack — pouziva rovnaku logiku, aku bude mat pipeline funkcia.
with zaklad as (
    select
        s.kraj,
        count(distinct s.prijimatel_ico) filter (where s.prijimatel_ico is not null) as obci,
        count(*) as dotacii,
        sum(s.suma) as objem_eur,
        percentile_cont(0.5) within group (order by s.suma) as median_suma,
        max(s.podpisane) as posledna
    from public.subsidies s
    where s.kraj is not null and trim(s.kraj) <> ''
    group by s.kraj
),
top_ucely_kraj as (
    select kraj, string_agg(ucel_top, '. ' order by pocet desc) as top_ucely
    from (
        select kraj,
               coalesce(nullif(trim(ucel), ''), 'neurčený účel') as ucel_top,
               count(*) as pocet,
               row_number() over (partition by kraj order by count(*) desc) as poradie
        from public.subsidies
        where kraj is not null and trim(kraj) <> ''
        group by kraj, ucel_top
    ) r
    where poradie <= 3
    group by kraj
),
top_posk_kraj as (
    select kraj, string_agg(posk_top, '. ' order by pocet desc) as top_poskytovatelia
    from (
        select kraj,
               coalesce(nullif(trim(poskytovatel), ''), 'neznámy poskytovateľ') as posk_top,
               count(*) as pocet,
               row_number() over (partition by kraj order by count(*) desc) as poradie
        from public.subsidies
        where kraj is not null and trim(kraj) <> ''
        group by kraj, posk_top
    ) r
    where poradie <= 3
    group by kraj
)
insert into public.kraj_prehlad (kraj, obci, dotacii, objem_eur, median_suma, top_ucely, top_poskytovatelia, posledna, last_seen_at)
select
    z.kraj, z.obci, z.dotacii, z.objem_eur, z.median_suma,
    tu.top_ucely, tp.top_poskytovatelia, z.posledna, current_date
from zaklad z
left join top_ucely_kraj tu on tu.kraj = z.kraj
left join top_posk_kraj  tp on tp.kraj = z.kraj
on conflict (kraj) do update
    set obci = excluded.obci,
        dotacii = excluded.dotacii,
        objem_eur = excluded.objem_eur,
        median_suma = excluded.median_suma,
        top_ucely = excluded.top_ucely,
        top_poskytovatelia = excluded.top_poskytovatelia,
        posledna = excluded.posledna,
        last_seen_at = excluded.last_seen_at,
        refreshed_at = now();

select kraj, obci, dotacii, objem_eur, median_suma, top_ucely, top_poskytovatelia from public.kraj_prehlad order by dotacii desc;
