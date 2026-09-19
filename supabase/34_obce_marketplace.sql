-- =============================================================================
--  OBOJSMERNY TRH /obce.html: obecne ucty, profily poradcov, dopyt/ponuka
--  Vloz do Supabase: SQL Editor -> New query -> Run. Spustit sa da opakovane.
-- =============================================================================
--
--  CO TO RIESI
--  Strategicka polozka z auditu 18.9. ("Premenit /obce.html na obojsmerny
--  produkt s uctami pre obce a poradcov", vysoky dopad / vysoka namaha).
--  Plny kontext a rozhodnutia su v projektovom dokumente
--  claude/predtendrom-plan-obce-marketplace.md. Tri povodne blokujuce
--  otazky Marek rozhodol priamo v komentaroch k tomu dokumentu (19.9.2026):
--
--   (a) OVERENIE IDENTITY OBCE: ziadne. Obec sa self-deklaruje (nazov, kraj,
--       ICO, kontaktny e-mail) bez formalnej kontroly — rovnaka zasada ako
--       inde v produkte smerom k obciam (bez trenia, bez byrokracie).
--   (b) BURZA, NIE KATALOG: obec vypise konkretny dopyt, poradcovia sa
--       hlasia priamo nan (rovnaky princip ako existujuci
--       moj_stav_prilezitosti — pipeline stav pri prilezitosti, len teraz
--       z pohladu obce a smerom von, nie interne pre dodavatela).
--   (c) CENNIK PRE PORADCOV: zaklad zadarmo (nizka bariera vstupu je
--       nutna na cold-start), plati sa len za zvyraznenie/pretlacenie na
--       vrch — pole `zvyraznenie_do` nizsie je pripravene miesto pre tento
--       mechanizmus, samotne napojenie na platby (TrustPay, vid 29_platby.sql)
--       je samostatny nasledujuci krok, nie sucast tejto migracie.
--
--  PRECO SAMOSTATNE TABULKY, NIE ROZSIRENIE organizations/memberships
--  Obec nie je firma-dodavatel a nema plany/ma_pro() v tom istom zmysle —
--  zdielat organizations by znamenalo riziko, ze niektora existujuca
--  podmienka (ma_pro(), moje_org_ids()) tichoNU predpoklada "organizacia =
--  firma" a nieco sa prelomi pre platiacich zakaznikov. Cistejsie oddelenie:
--  chyba v obecnom module sa nemoze dotknut dodavatelskej casti.
--
--  MVP ROZSAH (zamerne): jeden ucet = jeden owner (auth.uid()), bez
--  viacerych ludi na jednu obec/poradcu (na rozdiel od memberships, kde to
--  firma ma). Da sa rozsirit neskor rovnakym vzorom ako Team pozvanky
--  (26_team_pozvanky.sql), ak bude treba.
-- =============================================================================

-- =============================================================================
--  1. TABULKY
-- =============================================================================

create table if not exists public.obce_ucty (
    id             uuid primary key default gen_random_uuid(),
    owner          uuid not null unique references auth.users(id) on delete cascade,
    nazov          text not null,
    kraj           text,
    ico            text,
    kontakt_email  text,
    created_at     timestamptz not null default now()
);

create table if not exists public.poradcovia_profily (
    id                uuid primary key default gen_random_uuid(),
    owner             uuid not null unique references auth.users(id) on delete cascade,
    nazov             text not null,
    kontakt_email     text not null,
    kontakt_telefon   text,
    popis             text,
    kraje_posobenia   text[] not null default '{}',
    -- Pay-to-promote miesto (rozhodnutie c vyssie): NULL alebo minulost =
    -- bezny bezplatny profil, buducnost = zvyraznene/pretlacene na vrch.
    -- Samotne nastavovanie cez platbu je dalsi krok, nie sucast tejto migracie.
    zvyraznenie_do    timestamptz,
    aktivny           boolean not null default true,
    created_at        timestamptz not null default now()
);

create table if not exists public.dopyty (
    id           uuid primary key default gen_random_uuid(),
    obec_id      uuid not null references public.obce_ucty(id) on delete cascade,
    -- Denormalizovane z obce_ucty, aby poradcovia mohli filtrovat/zobrazit
    -- bez potreby sirsej SELECT politiky na obce_ucty samotnu.
    obec_nazov   text not null,
    kraj         text,
    typ          text check (typ in ('zmluva', 'dotacia', 'ine')),
    -- Volitelny odkaz na konkretnu prilezitost z existujucich dat (ak obec
    -- prisla z konkretnej dotacie/programu), inak vseobecny dopyt.
    contract_id  bigint,
    nazov        text not null,
    popis        text,
    stav         text not null default 'otvoreny' check (stav in ('otvoreny', 'uzavrety')),
    created_at   timestamptz not null default now(),
    updated_at   timestamptz not null default now()
);

create index if not exists ix_dopyty_stav on public.dopyty(stav);
create index if not exists ix_dopyty_kraj on public.dopyty(kraj);
create index if not exists ix_dopyty_obec on public.dopyty(obec_id);

create table if not exists public.reakcie (
    id           uuid primary key default gen_random_uuid(),
    dopyt_id     uuid not null references public.dopyty(id) on delete cascade,
    poradca_id   uuid not null references public.poradcovia_profily(id) on delete cascade,
    sprava       text not null,
    created_at   timestamptz not null default now(),
    updated_at   timestamptz not null default now(),
    unique (dopyt_id, poradca_id)
);

create index if not exists ix_reakcie_dopyt on public.reakcie(dopyt_id);
create index if not exists ix_reakcie_poradca on public.reakcie(poradca_id);

-- =============================================================================
--  2. POMOCNE FUNKCIE (rovnaky vzor ako moje_org_ids()/ma_pro())
-- =============================================================================

create or replace function public.moj_obec_id()
returns uuid
language sql
stable
security definer
set search_path = ''
as $$
    select id from public.obce_ucty where owner = auth.uid();
$$;

create or replace function public.moj_poradca_id()
returns uuid
language sql
stable
security definer
set search_path = ''
as $$
    select id from public.poradcovia_profily where owner = auth.uid();
$$;

create or replace function public.je_poradca()
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
    select exists (select 1 from public.poradcovia_profily where owner = auth.uid());
$$;

-- =============================================================================
--  3. REGISTRACNE A AKCNE RPC (insert/update len cez servr, rovnaky dovod
--     ako pri nastav_stav_prilezitosti — server dopocitava vlastnicke ID,
--     klient si ho nemoze vymysliet)
-- =============================================================================

create or replace function public.zaloz_obec_ucet(
    p_nazov         text,
    p_kraj          text default null,
    p_ico           text default null,
    p_kontakt_email text default null
)
returns uuid
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_id uuid;
begin
    if auth.uid() is null then
        raise exception 'Nie si prihlaseny.';
    end if;
    if trim(coalesce(p_nazov, '')) = '' then
        raise exception 'Zadaj nazov obce.';
    end if;
    if exists (select 1 from public.obce_ucty where owner = auth.uid()) then
        raise exception 'Uz mas zalozeny obecny ucet.';
    end if;

    insert into public.obce_ucty (owner, nazov, kraj, ico, kontakt_email)
    values (auth.uid(), trim(p_nazov), nullif(trim(p_kraj), ''),
            nullif(trim(p_ico), ''), nullif(trim(p_kontakt_email), ''))
    returning id into v_id;

    return v_id;
end;
$$;

grant execute on function public.zaloz_obec_ucet(text, text, text, text) to authenticated;

create or replace function public.zaloz_poradcu_profil(
    p_nazov           text,
    p_kontakt_email   text,
    p_kontakt_telefon text default null,
    p_popis           text default null,
    p_kraje           text[] default '{}'
)
returns uuid
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_id uuid;
begin
    if auth.uid() is null then
        raise exception 'Nie si prihlaseny.';
    end if;
    if trim(coalesce(p_nazov, '')) = '' or trim(coalesce(p_kontakt_email, '')) = '' then
        raise exception 'Zadaj nazov a kontaktny e-mail.';
    end if;
    if exists (select 1 from public.poradcovia_profily where owner = auth.uid()) then
        raise exception 'Uz mas zalozeny profil poradcu.';
    end if;

    insert into public.poradcovia_profily
        (owner, nazov, kontakt_email, kontakt_telefon, popis, kraje_posobenia)
    values
        (auth.uid(), trim(p_nazov), trim(p_kontakt_email),
         nullif(trim(p_kontakt_telefon), ''), nullif(trim(p_popis), ''),
         coalesce(p_kraje, '{}'))
    returning id into v_id;

    return v_id;
end;
$$;

grant execute on function public.zaloz_poradcu_profil(text, text, text, text, text[]) to authenticated;

create or replace function public.vytvor_dopyt(
    p_nazov       text,
    p_popis       text default null,
    p_typ         text default null,
    p_contract_id bigint default null
)
returns uuid
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_obec_id  uuid;
    v_obec     record;
    v_id       uuid;
begin
    select id, nazov, kraj into v_obec
      from public.obce_ucty where owner = auth.uid();

    if v_obec.id is null then
        raise exception 'Nemas obecny ucet. Najprv si ho zaloz.';
    end if;
    if trim(coalesce(p_nazov, '')) = '' then
        raise exception 'Zadaj, co potrebujes.';
    end if;
    if p_typ is not null and p_typ not in ('zmluva', 'dotacia', 'ine') then
        raise exception 'Neznamy typ.';
    end if;

    insert into public.dopyty (obec_id, obec_nazov, kraj, typ, contract_id, nazov, popis)
    values (v_obec.id, v_obec.nazov, v_obec.kraj, p_typ, p_contract_id,
            trim(p_nazov), nullif(trim(p_popis), ''))
    returning id into v_id;

    return v_id;
end;
$$;

grant execute on function public.vytvor_dopyt(text, text, text, bigint) to authenticated;

create or replace function public.zatvor_dopyt(p_dopyt_id uuid)
returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
    update public.dopyty
       set stav = 'uzavrety', updated_at = now()
     where id = p_dopyt_id
       and obec_id = (select id from public.obce_ucty where owner = auth.uid());
end;
$$;

grant execute on function public.zatvor_dopyt(uuid) to authenticated;

create or replace function public.reaguj_na_dopyt(p_dopyt_id uuid, p_sprava text)
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_poradca_id uuid;
begin
    select id into v_poradca_id
      from public.poradcovia_profily where owner = auth.uid();

    if v_poradca_id is null then
        raise exception 'Nemas profil poradcu. Najprv si ho zaloz.';
    end if;
    if trim(coalesce(p_sprava, '')) = '' then
        raise exception 'Napis spravu.';
    end if;
    if not exists (select 1 from public.dopyty where id = p_dopyt_id and stav = 'otvoreny') then
        raise exception 'Tento dopyt uz nie je otvoreny.';
    end if;

    insert into public.reakcie (dopyt_id, poradca_id, sprava)
    values (p_dopyt_id, v_poradca_id, trim(p_sprava))
    on conflict (dopyt_id, poradca_id) do update
        set sprava = excluded.sprava, updated_at = now();
end;
$$;

grant execute on function public.reaguj_na_dopyt(uuid, text) to authenticated;

-- =============================================================================
--  4. ROW LEVEL SECURITY
-- =============================================================================

alter table public.obce_ucty          enable row level security;
alter table public.poradcovia_profily enable row level security;
alter table public.dopyty             enable row level security;
alter table public.reakcie            enable row level security;

-- --- obce_ucty: vidi a upravuje len vlastny ucet ------------------------------
drop policy if exists obce_ucty_select on public.obce_ucty;
create policy obce_ucty_select on public.obce_ucty
    for select to authenticated
    using (owner = auth.uid());

drop policy if exists obce_ucty_update on public.obce_ucty;
create policy obce_ucty_update on public.obce_ucty
    for update to authenticated
    using (owner = auth.uid())
    with check (owner = auth.uid());

-- (insert/delete zamerne bez politiky — zalozenie ide cez zaloz_obec_ucet(),
--  mazanie uctov nie je v MVP rozsahu.)

-- --- poradcovia_profily: vlastny profil plne, ostatni len aktivne profily ----
-- Dovod pre "authenticated" a nie "anon": burza (nie verejny katalog, viz
-- rozhodnutie b vyssie) — kto ma vidiet poradcov, sa prihlasi.
drop policy if exists poradcovia_select on public.poradcovia_profily;
create policy poradcovia_select on public.poradcovia_profily
    for select to authenticated
    using (owner = auth.uid() or aktivny = true);

drop policy if exists poradcovia_update on public.poradcovia_profily;
create policy poradcovia_update on public.poradcovia_profily
    for update to authenticated
    using (owner = auth.uid())
    with check (owner = auth.uid());

-- --- dopyty: vlastna obec plne, poradcovia len otvorene -----------------------
drop policy if exists dopyty_select on public.dopyty;
create policy dopyty_select on public.dopyty
    for select to authenticated
    using (
        obec_id = public.moj_obec_id()
        or (stav = 'otvoreny' and public.je_poradca())
    );

drop policy if exists dopyty_update on public.dopyty;
create policy dopyty_update on public.dopyty
    for update to authenticated
    using (obec_id = public.moj_obec_id())
    with check (obec_id = public.moj_obec_id());

-- (insert ide cez vytvor_dopyt(), nie priamy insert z klienta.)

-- --- reakcie: poradca vidi/pisze vlastne, obec vidi reakcie na svoje dopyty --
drop policy if exists reakcie_select on public.reakcie;
create policy reakcie_select on public.reakcie
    for select to authenticated
    using (
        poradca_id = public.moj_poradca_id()
        or dopyt_id in (select id from public.dopyty where obec_id = public.moj_obec_id())
    );

-- (insert/update ide cez reaguj_na_dopyt().)

select 'Obojsmerny trh pripraveny: obce_ucty, poradcovia_profily, dopyty, reakcie + RPC.' as vysledok;
