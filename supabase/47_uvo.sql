-- =============================================================================
--  47 — VESTNÍK ÚVO: výsledky súťaží (kto vyhral, za koľko, na ako dlho)
--  a vyhlásené súťaže. Plní pipeline/uvo.py (.github/workflows/uvo.yml).
--  Vlož do Supabase: SQL Editor -> New query -> Run. Spustiť sa dá opakovane.
--
--  ZDROJ: Národný katalóg otvorených dát (data.slovensko.sk), vydavateľ ÚVO,
--  každé číslo Vestníka je samostatný JSON dataset s eForms formulármi.
--  Prieskum: Projects doc predtendrom-uvo-vestnik-prieskum-2026-09-25.md.
--
--  ČÍTANIE: rovnako ako opportunities — prihlásený s aktívnym prístupom
--  (ma_aktivny_pristup). Zapisuje len pipeline cez service_role.
-- =============================================================================

-- ─── Spracované čísla Vestníka (checkpoint + štatistika) ─────────────────
create table if not exists public.uvo_vestniky (
    vestnik          text primary key,          -- "193/2026"
    rok              int  not null,
    cislo            int  not null,
    publikovany      date,
    dataset_id       text,
    oznameni         int,                       -- položiek v čísle
    vysledkov        int,                       -- uložených riadkov do uvo_vysledky
    vyziev           int,                       -- uložených riadkov do uvo_vyzvy
    preskocenych     int,                       -- XML / nečitateľné položky
    spracovany_at    timestamptz not null default now()
);

-- ─── Výsledky: jeden riadok = jedna časť (lot) × jeden víťaz ─────────────
create table if not exists public.uvo_vysledky (
    id                   bigserial primary key,
    oznamenie_id         bigint not null,       -- ID formulára vo Vestníku
    vestnik              text   not null,
    typ_oznamenia        text,                  -- "Oznámenie o výsledku … (D24)"
    zakazka_id           bigint,                -- ID zákazky na uvo.gov.sk
    obstaravatel_ico     text,
    obstaravatel_nazov   text,
    nuts                 text,                  -- miesto plnenia, napr. SK022
    nazov                text,                  -- názov zákazky (postupu)
    cast_id              text not null default '',   -- LOT-0001
    cast_nazov           text,
    cpv                  text,
    sektor               text,                  -- naše sektory (config.SEKTORY) alebo null
    druh                 text,                  -- works / supplies / services
    vitaz_ico            text not null default '',
    vitaz_nazov          text,
    hodnota              numeric,               -- cena víťaznej ponuky
    mena                 text,
    predpokladana_hodnota numeric,
    pocet_ponuk          int,
    podpisane            date,                  -- BT-145
    trvanie_mesiace      numeric,               -- BT-36 prepočítané na mesiace
    koniec               date,                  -- BT-537, inak podpisane + trvanie
    koniec_odhad         boolean not null default false,  -- true = dopočítaný
    zmluva_cislo         text,
    crz_url              text,
    url                  text,
    publikovane          date,
    created_at           timestamptz not null default now(),
    unique (oznamenie_id, cast_id, vitaz_ico)
);

create index if not exists ix_uvo_vys_obst   on public.uvo_vysledky(obstaravatel_ico);
create index if not exists ix_uvo_vys_vitaz  on public.uvo_vysledky(vitaz_ico);
create index if not exists ix_uvo_vys_sektor on public.uvo_vysledky(sektor);
create index if not exists ix_uvo_vys_koniec on public.uvo_vysledky(koniec);
create index if not exists ix_uvo_vys_pub    on public.uvo_vysledky(publikovane desc);

-- ─── Vyhlásené súťaže a predbežné oznámenia: riadok = časť (lot) ─────────
create table if not exists public.uvo_vyzvy (
    id                   bigserial primary key,
    oznamenie_id         bigint not null,
    vestnik              text   not null,
    typ                  text   not null,       -- 'sutaz' | 'predbezne'
    typ_oznamenia        text,
    zakazka_id           bigint,
    obstaravatel_ico     text,
    obstaravatel_nazov   text,
    nuts                 text,
    nazov                text,
    cast_id              text not null default '',
    cast_nazov           text,
    cpv                  text,
    sektor               text,
    druh                 text,
    predpokladana_hodnota numeric,
    mena                 text,
    lehota_ponuk         timestamptz,           -- BT-131
    trvanie_mesiace      numeric,
    url                  text,
    publikovane          date,
    created_at           timestamptz not null default now(),
    unique (oznamenie_id, cast_id)
);

create index if not exists ix_uvo_vyz_sektor on public.uvo_vyzvy(sektor);
create index if not exists ix_uvo_vyz_lehota on public.uvo_vyzvy(lehota_ponuk);
create index if not exists ix_uvo_vyz_pub    on public.uvo_vyzvy(publikovane desc);
create index if not exists ix_uvo_vyz_obst   on public.uvo_vyzvy(obstaravatel_ico);

-- ─── RLS ─────────────────────────────────────────────────────────────────
alter table public.uvo_vestniky enable row level security;
alter table public.uvo_vysledky enable row level security;
alter table public.uvo_vyzvy    enable row level security;

drop policy if exists uvo_vysledky_select on public.uvo_vysledky;
create policy uvo_vysledky_select on public.uvo_vysledky
    for select to authenticated
    using (public.ma_aktivny_pristup());

drop policy if exists uvo_vyzvy_select on public.uvo_vyzvy;
create policy uvo_vyzvy_select on public.uvo_vyzvy
    for select to authenticated
    using (public.ma_aktivny_pristup());

-- uvo_vestniky je interná evidencia pipeline, bez select politiky
-- (service_role RLS obchádza).

select 'uvo_vestniky, uvo_vysledky, uvo_vyzvy pripravené.' as vysledok;
