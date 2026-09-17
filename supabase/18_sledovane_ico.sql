-- =============================================================================
--  SLEDOVANIE KONKURENCIE PODLA ICO
--  Vloz do Supabase: SQL Editor -> New query -> Run. Spustit sa da opakovane.
--  Spustaj PO 08_zadarmo.sql (potrebuje ma_pro()).
-- =============================================================================
--
--  CO TO JE
--  Firma si oznaci ICO konkurenta (alebo obchodneho partnera), ktore chce
--  sledovat. V UI potom vidi jeho aktualny profil z uz existujucej tabulky
--  `dodavatelia` (objem zmluv, pocet uradov, posledna zmluva) bez toho, aby
--  ho musela kazdy tyzden rucne hladat v zalozke Dodavatelia.
--
--  PRECO ZVLAST TABULKA A NIE STLPEC VO `watchlists`
--  Watchlist je definicia FILTRA (kraj/sektor/cena) na prilezitosti — jeden
--  riadok moze byt viacero kriterii naraz. Sledovanie konkretnej firmy je iny
--  typ objektu (jedno konkretne ICO, nie rozsah) a firma ich moze mat viac
--  sucasne. Zmiesat oboje do jednej tabulky by neskor sposobilo, ze stlpce
--  davaju zmysel len pre jeden z dvoch pripadov pouzitia.
--
--  PRECO JE VYTVORENIE VIAZANE NA ma_pro()
--  Profil dodavatela (objem, uradov, posledna zmluva) je uz dnes Pro-only
--  udaj (viz 06_plany.sql, dodavatelia_select). Sledovanie firmy bez pristupu
--  k jej profilu by bolo prazdnym zaznamom bez hodnoty — cita sa teda
--  ako Pro funkcia od zaciatku, aj ked pocas otvoreneho obdobia ma_pro()
--  vracia true pre kazdeho (viz 08_zadarmo.sql).
-- =============================================================================

create table if not exists public.sledovane_ico (
    id         uuid primary key default gen_random_uuid(),
    org_id     uuid not null references public.organizations(id) on delete cascade,
    ico        text not null,
    -- Nazov v case pridania. Cisty UI komfort (aby sa zoznam sledovanych
    -- dal vykreslit aj skor, nez dobehne join na `dodavatelia`) — pri
    -- zobrazeni sa vzdy prednostne pouzije aktualny nazov z `dodavatelia`.
    nazov      text,
    created_at timestamptz not null default now(),
    unique (org_id, ico)
);

create index if not exists ix_sledovane_ico_org on public.sledovane_ico(org_id);

alter table public.sledovane_ico enable row level security;

-- Citanie vlastnych sledovanych firiem nie je viazane na ma_pro(): ked firme
-- vyprsi Pro, nestrati zoznam toho, koho sledovala, len prestane vidiet
-- obohatene udaje o nich (tie su uz chranene RLS na `dodavatelia`).
drop policy if exists sledovane_ico_select on public.sledovane_ico;
create policy sledovane_ico_select on public.sledovane_ico
    for select to authenticated
    using (org_id in (select public.moje_org_ids()));

drop policy if exists sledovane_ico_insert on public.sledovane_ico;
create policy sledovane_ico_insert on public.sledovane_ico
    for insert to authenticated
    with check (org_id in (select public.moje_org_ids()) and public.ma_pro());

drop policy if exists sledovane_ico_delete on public.sledovane_ico;
create policy sledovane_ico_delete on public.sledovane_ico
    for delete to authenticated
    using (org_id in (select public.moje_org_ids()));

select 'Sledovanie ICO pripravene.' as vysledok;
