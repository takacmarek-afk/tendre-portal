-- =============================================================================
--  62 — obec_poradcovia_agregat: doterajší poradcovia PO KONKRÉTNEJ OBCI
--  Vloz do Supabase: SQL Editor -> New query -> Run. Spustit sa da opakovane.
-- =============================================================================
--
--  Posledný bod z punch listu (audit 29.9.2026): /prvych-100-dni.html mal
--  na mieste "Doterajší poradcovia" len text "pripravujeme" — čaká na to
--  odkedy P3.2 A (vlna 50). Rovnaké fakty ako v existujúcej tabuľke
--  `sprostredkovatelia` (11_obce_a_email.sql), len INAK ZOSKUPENÉ: tam je
--  jeden riadok na FIRMU (agregát naprieč všetkými obcami), tu je jeden
--  riadok na dvojicu (OBEC, firma) — presne to, čo treba zobraziť pri
--  vyhľadaní jednej konkrétnej obce.
--
--  Plní pipeline/obce.py::doterajsi_poradcovia_po_obci() cez
--  pipeline/store.py::nahrad_obec_poradcovia() (rovnaký "nahraď, nikdy
--  nezmaž pri prázdnom výsledku" vzor ako ostatné tabuľky pre obce).
--
--  ZLOŽENÝ KĽÚČ (obec_core, kraj, kluc): rovnaký dôvod ako p_kraj filter
--  v migrácii 60 — tá istá obec ("Nová Ves") existuje vo viacerých krajoch
--  a nesmú sa zliať dokopy. kraj je NOT NULL DEFAULT '' (nie NULL), lebo
--  NULL v stĺpci primárneho kľúča Postgres nedovoľuje — pipeline posiela
--  prázdny reťazec, keď sa adresa obstarávateľa nedá rozobrať.
-- =============================================================================

create table if not exists public.obec_poradcovia_agregat (
    obec_core         text not null,
    kraj              text not null default '',
    kluc              text not null,   -- IČO, a keď chýba, názov (rovnaký vzor ako sprostredkovatelia.kluc)
    sprostredkovatel  text not null,
    supplier_cin      text,
    zmluv             integer,
    median_ceny       numeric,
    prva_zmluva       date,
    posledna_zmluva   date,
    last_seen_at      date,
    refreshed_at      timestamptz not null default now(),
    primary key (obec_core, kraj, kluc)
);

create index if not exists ix_obec_poradcovia_obec
    on public.obec_poradcovia_agregat (lower(obec_core), kraj);

alter table public.obec_poradcovia_agregat enable row level security;

-- Agregát z už verejných zmlúv (rovnaký princíp ako sprostredkovatelia) —
-- verejne čitateľný, aj pre neprihláseného starostu.
drop policy if exists obec_poradcovia_select on public.obec_poradcovia_agregat;
create policy obec_poradcovia_select on public.obec_poradcovia_agregat
    for select to anon, authenticated using (true);

grant select on public.obec_poradcovia_agregat to anon, authenticated;

-- RPC v rovnakom štýle ako prvych_100_dni_suhrn/hladaj_obec (p_nazov =
-- "core" názov bez predpony, presne ako vracia hladaj_obec; p_kraj
-- nepovinný filter). Vracia najviac 10 firiem, zoradené podľa počtu
-- zmlúv a najnovšej aktivity — žiadne skóre úspešnosti (rovnaký princíp
-- ako sprostredkovatelia, dôvod je v hlavičke pipeline/obce.py).
create or replace function public.doterajsi_poradcovia_obce(p_nazov text, p_kraj text default null)
returns table(
    sprostredkovatel text,
    zmluv            integer,
    median_ceny      numeric,
    posledna_zmluva  date
)
language sql
stable
security definer
set search_path = ''
as $$
    select a.sprostredkovatel, a.zmluv, a.median_ceny, a.posledna_zmluva
      from public.obec_poradcovia_agregat a
     where trim(coalesce(p_nazov, '')) <> ''
       and lower(a.obec_core) = lower(trim(p_nazov))
       and (
            nullif(trim(coalesce(p_kraj, '')), '') is null
            or lower(a.kraj) = lower(trim(p_kraj))
       )
     order by a.zmluv desc nulls last, a.posledna_zmluva desc nulls last
     limit 10;
$$;

grant execute on function public.doterajsi_poradcovia_obce(text, text) to anon, authenticated;

select 'obec_poradcovia_agregat: tabuľka, RLS a RPC doterajsi_poradcovia_obce vytvorené.' as vysledok;
