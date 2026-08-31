-- =============================================================================
--  TENDRE PORTAL — databázová schéma
--  Vloz cele do Supabase: lava lista -> SQL Editor -> New query -> Run
--  Spustit sa da opakovane, nic nepokazi (pouziva IF NOT EXISTS / OR REPLACE).
-- =============================================================================

create extension if not exists pgcrypto;

-- =============================================================================
--  1. ZAKAZNICI
-- =============================================================================

-- Firma, ktora u nas ma ucet
create table if not exists public.organizations (
    id         uuid primary key default gen_random_uuid(),
    nazov      text not null,
    ico        text unique,
    dic        text,
    adresa     text,
    created_at timestamptz not null default now()
);

-- Vazba pouzivatel <-> firma. Jedna firma moze mat viac ludi.
create table if not exists public.memberships (
    user_id    uuid not null references auth.users(id) on delete cascade,
    org_id     uuid not null references public.organizations(id) on delete cascade,
    rola       text not null default 'member' check (rola in ('owner', 'member')),
    created_at timestamptz not null default now(),
    primary key (user_id, org_id)
);

create index if not exists ix_memberships_org on public.memberships(org_id);

-- Predplatne. Kazda firma ma prave jeden zaznam.
create table if not exists public.subscriptions (
    org_id                 uuid primary key references public.organizations(id) on delete cascade,
    stav                   text not null default 'trial'
                             check (stav in ('trial', 'aktivne', 'po_splatnosti', 'zrusene')),
    trial_konci            timestamptz not null default (now() + interval '30 days'),
    stripe_customer_id     text,
    stripe_subscription_id text,
    obdobie_konci          timestamptz,
    plan                   text,
    updated_at             timestamptz not null default now()
);

-- Co firma sleduje. Toto je jadro personalizacie.
create table if not exists public.watchlists (
    id                uuid primary key default gen_random_uuid(),
    org_id            uuid not null references public.organizations(id) on delete cascade,
    nazov             text not null,
    okresy            text[] not null default '{}',
    sektory           text[] not null default '{}',
    min_hodnota       numeric not null default 5000,
    digest_frekvencia text not null default 'denne'
                        check (digest_frekvencia in ('denne', 'tyzdenne', 'ziadny')),
    aktivny           boolean not null default true,
    created_at        timestamptz not null default now()
);

create index if not exists ix_watchlists_org on public.watchlists(org_id);

-- =============================================================================
--  2. ZDIELANE DATA Z PIPELINE
--  Rovnake pre vsetkych zakaznikov. Zapisuje sem len pipeline cez service_role.
-- =============================================================================

create table if not exists public.contracts (
    id                  bigint primary key,          -- ID zo zdroja (CRZ)
    contract_identifier text,
    authority_name      text,
    authority_cin       text,
    authority_address   text,
    supplier_name       text,
    supplier_cin        text,
    subject             text,
    subject_description text,
    signed_on           date,
    effective_from      date,
    effective_to        date,
    effective_note      text,
    price               numeric,
    price_total         numeric,
    status_id           integer,
    type_id             integer,
    published_at        timestamptz,
    procurement_url     text,
    department          text,
    sector              text,
    class_score         integer,
    src_updated_at      timestamptz,
    updated_at          timestamptz not null default now()
);

create index if not exists ix_contracts_sector      on public.contracts(sector);
create index if not exists ix_contracts_effto       on public.contracts(effective_to);
create index if not exists ix_contracts_auth_sector on public.contracts(authority_cin, sector);

-- Prilezitosti: predpocitane pipeline po kazdom behu.
-- Zamerne to nie je pohlad (view) — prepocet je drahy a staci raz denne.
create table if not exists public.opportunities (
    contract_id            bigint primary key references public.contracts(id) on delete cascade,
    sector                 text,
    cpv                    text,
    authority_name         text,
    authority_cin          text,
    department             text,
    subject                text,
    subject_description    text,
    effective_to           date,
    dni_do_konca           integer,
    odhad_vyhlasenia       date,
    price_total            numeric,
    supplier_name          text,
    top_dodavatel          text,
    podiel_top_dodavatela  numeric,
    historicky_pocet       integer,
    pocet_dodavatelov      integer,
    riziko                 text,
    skore                  integer,
    okres_kod              text,          -- doplni sa neskor, na filtrovanie podla regionu
    refreshed_at           timestamptz not null default now()
);

create index if not exists ix_opp_skore  on public.opportunities(skore desc);
create index if not exists ix_opp_sector on public.opportunities(sector);
create index if not exists ix_opp_okres  on public.opportunities(okres_kod);
create index if not exists ix_opp_effto  on public.opportunities(effective_to);

-- Stav pipeline (checkpoint synchronizacie a podobne)
create table if not exists public.pipeline_meta (
    key        text primary key,
    value      text,
    updated_at timestamptz not null default now()
);

-- =============================================================================
--  3. AUDIT
-- =============================================================================

create table if not exists public.events (
    id         bigserial primary key,
    org_id     uuid references public.organizations(id) on delete set null,
    user_id    uuid references auth.users(id) on delete set null,
    typ        text not null,
    detail     jsonb,
    created_at timestamptz not null default now()
);

create index if not exists ix_events_org on public.events(org_id, created_at desc);

-- =============================================================================
--  4. POMOCNE FUNKCIE PRE ZABEZPECENIE
-- =============================================================================

-- Vrati ID firiem, do ktorych prihlaseny pouzivatel patri.
create or replace function public.moje_org_ids()
returns setof uuid
language sql
stable
security definer
set search_path = public
as $$
    select org_id from public.memberships where user_id = auth.uid();
$$;

-- Ma pouzivatel narok vidiet data? Plati pocas trialu aj pri aktivnom predplatnom.
-- Toto je jedine miesto, kde sa rozhoduje o pristupe. Nikdy to neries vo frontende.
create or replace function public.ma_aktivny_pristup()
returns boolean
language sql
stable
security definer
set search_path = public
as $$
    select exists (
        select 1
        from public.memberships m
        join public.subscriptions s on s.org_id = m.org_id
        where m.user_id = auth.uid()
          and (s.stav = 'aktivne'
               or (s.stav = 'trial' and s.trial_konci > now()))
    );
$$;

-- Zalozenie firmy pri registracii. Vytvori organizaciu, clenstvo aj trial naraz.
create or replace function public.zaloz_organizaciu(p_nazov text, p_ico text default null)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
    v_org_id uuid;
begin
    if auth.uid() is null then
        raise exception 'Nie si prihlaseny.';
    end if;

    if exists (select 1 from public.memberships where user_id = auth.uid()) then
        raise exception 'Tento pouzivatel uz patri do firmy.';
    end if;

    insert into public.organizations (nazov, ico)
    values (p_nazov, nullif(trim(p_ico), ''))
    returning id into v_org_id;

    insert into public.memberships (user_id, org_id, rola)
    values (auth.uid(), v_org_id, 'owner');

    insert into public.subscriptions (org_id) values (v_org_id);

    insert into public.events (org_id, user_id, typ, detail)
    values (v_org_id, auth.uid(), 'org_vytvorena', jsonb_build_object('nazov', p_nazov));

    return v_org_id;
end;
$$;

-- =============================================================================
--  5. ROW LEVEL SECURITY
--  Bez tohto by kazdy prihlaseny videl data vsetkych firiem.
-- =============================================================================

alter table public.organizations  enable row level security;
alter table public.memberships    enable row level security;
alter table public.subscriptions  enable row level security;
alter table public.watchlists     enable row level security;
alter table public.contracts      enable row level security;
alter table public.opportunities  enable row level security;
alter table public.pipeline_meta  enable row level security;
alter table public.events         enable row level security;

-- --- vlastna firma -----------------------------------------------------------
drop policy if exists org_select on public.organizations;
create policy org_select on public.organizations
    for select to authenticated
    using (id in (select public.moje_org_ids()));

drop policy if exists org_update on public.organizations;
create policy org_update on public.organizations
    for update to authenticated
    using (id in (select public.moje_org_ids()))
    with check (id in (select public.moje_org_ids()));

-- --- clenstva ----------------------------------------------------------------
drop policy if exists mem_select on public.memberships;
create policy mem_select on public.memberships
    for select to authenticated
    using (user_id = auth.uid() or org_id in (select public.moje_org_ids()));

-- --- predplatne (citanie ano, zapis len cez Stripe webhook = service_role) ---
drop policy if exists sub_select on public.subscriptions;
create policy sub_select on public.subscriptions
    for select to authenticated
    using (org_id in (select public.moje_org_ids()));

-- --- watchlisty: plna sprava vlastnych ---------------------------------------
drop policy if exists wl_all on public.watchlists;
create policy wl_all on public.watchlists
    for all to authenticated
    using (org_id in (select public.moje_org_ids()))
    with check (org_id in (select public.moje_org_ids()));

-- --- verejne data: len pre platnych pouzivatelov ------------------------------
drop policy if exists contracts_select on public.contracts;
create policy contracts_select on public.contracts
    for select to authenticated
    using (public.ma_aktivny_pristup());

drop policy if exists opp_select on public.opportunities;
create policy opp_select on public.opportunities
    for select to authenticated
    using (public.ma_aktivny_pristup());

-- --- audit: len citanie vlastnych --------------------------------------------
drop policy if exists events_select on public.events;
create policy events_select on public.events
    for select to authenticated
    using (org_id in (select public.moje_org_ids()));

-- pipeline_meta: ziadna politika = nikto okrem service_role sa tam nedostane.
-- To je zamer.

-- =============================================================================
--  HOTOVO
-- =============================================================================
select 'Schema vytvorena. Tabuliek: '
       || (select count(*) from information_schema.tables
           where table_schema = 'public' and table_type = 'BASE TABLE')::text as vysledok;
