-- =============================================================================
--  TAM (VELKOST TRHU) A TRHOVY PODIEL PODLA SEKTORA
--  Vloz do Supabase: SQL Editor -> New query -> Run. Spustit sa da opakovane.
--  Spustaj PO 06_plany.sql (potrebuje ma_pro()).
-- =============================================================================
--
--  CO TO JE
--  Dve nove agregacie nad uz stiahnutymi zmluvami (ziadny novy datovy
--  zdroj), obe za posledych 12 mesiacov (pipeline/analytics.py: DNI_TAM):
--
--  `tam_sektor` — kolko sa v danom sektore rocne realne minie (sucet cien
--  zmluv so znamou cenou). Ramcove dohody (cena 0 v CRZ) sa do suctu
--  nepocitaju, takze `objem_eur` je vzdy DOLNA hranica — `spolahlivy=false`
--  znamena, ze viac ako polovica zmluv v sektore nema uvedenu cenu a odhad
--  je preto vyrazne podhodnoteny.
--
--  `trhovy_podiel` — TOP 5 dodavatelov v kazdom sektore podla objemu za to
--  iste obdobie, s podielom na objeme sektora. Rovnaky GDPR filter ako
--  `dodavatelia` (len pravnicke osoby).
-- =============================================================================

create table if not exists public.tam_sektor (
    sector               text primary key,
    objem_eur            numeric,
    pocet_s_cenou        integer,
    pocet_bez_ceny       integer,
    podiel_bez_ceny_pct  numeric,
    spolahlivy           boolean,
    last_seen_at         date,
    refreshed_at         timestamptz not null default now()
);

alter table public.tam_sektor enable row level security;

drop policy if exists tam_sektor_select on public.tam_sektor;
create policy tam_sektor_select on public.tam_sektor
    for select to authenticated
    using (public.ma_pro());


create table if not exists public.trhovy_podiel (
    sector               text not null,
    supplier_cin         text not null,
    dodavatel            text,
    zmluv                integer,
    objem_eur            numeric,
    podiel_sektora_pct   numeric,
    poradie              integer,
    last_seen_at         date,
    refreshed_at         timestamptz not null default now(),
    primary key (sector, supplier_cin)
);

create index if not exists ix_trhovy_podiel_sektor on public.trhovy_podiel(sector, poradie);

alter table public.trhovy_podiel enable row level security;

drop policy if exists trhovy_podiel_select on public.trhovy_podiel;
create policy trhovy_podiel_select on public.trhovy_podiel
    for select to authenticated
    using (public.ma_pro());

select 'TAM a trhovy podiel pripravene (Pro-only, rovnako ako dodavatelia a ceny_sektor).' as vysledok;
