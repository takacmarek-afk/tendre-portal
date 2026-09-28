-- =============================================================================
--  51 — OSOBNÉ NASTAVENIE PREHĽADU (audit 27. 9. 2026, P1.3)
--  Po prvom prihlásení si firma vyberie kraje, sektory a veľkosť zákaziek.
--  Appka to použije ako predvolený filter a radenie „relevantné pre mňa“.
--  Dá sa kedykoľvek zmeniť (tlačidlo „Moje nastavenie“). Spustiť sa dá
--  opakovane.
-- =============================================================================

create table if not exists public.nastavenia_pouzivatela (
    user_id      uuid primary key default auth.uid()
                 references auth.users(id) on delete cascade,
    kraje        text[] not null default '{}',     -- napr. {"Košický kraj"}
    sektory      text[] not null default '{}',     -- kľúče sektorov (UPRATOVANIE, …)
    velkost      text   not null default 'vsetko'
                 check (velkost in ('do50', 'do250', 'viac', 'vsetko')),
    upravene_at  timestamptz not null default now()
);

alter table public.nastavenia_pouzivatela enable row level security;

drop policy if exists nastavenia_select on public.nastavenia_pouzivatela;
create policy nastavenia_select on public.nastavenia_pouzivatela
    for select to authenticated using (user_id = auth.uid());

drop policy if exists nastavenia_insert on public.nastavenia_pouzivatela;
create policy nastavenia_insert on public.nastavenia_pouzivatela
    for insert to authenticated with check (user_id = auth.uid());

drop policy if exists nastavenia_update on public.nastavenia_pouzivatela;
create policy nastavenia_update on public.nastavenia_pouzivatela
    for update to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());

select 'tabulka=' || (select to_regclass('public.nastavenia_pouzivatela') is not null)::text
    || ' | rls=' || (select relrowsecurity from pg_class where oid = 'public.nastavenia_pouzivatela'::regclass)::text
    || ' | policies=' || (select count(*) from pg_policies
                            where schemaname = 'public' and tablename = 'nastavenia_pouzivatela')::text
    as vysledok;
