-- =============================================================================
--  96 - SPRACOVANE ODPOVEDE NA STUDENE E-MAILY (10. 11. 2026)
--  Vloz do Supabase: SQL Editor -> New query -> Run. Spustit sa da opakovane.
--  Predpoklad: migracia 84 (oslovenie_firiem_*).
-- =============================================================================
--
--  pipeline/odpovede.py cita schranku marek@predtendrom.sk (IMAP) a kazdu
--  spravu spracuje najviac raz. Tu si pamata, ktoru (podla Message-ID).
--  typ: 'nie' (jasne odmietnutie, poslala sa zdvorila veta), 'auto' (automaticka
--  odpoved, nic), 'nedorucene' (vratena sprava, adresa vyradena), 'rucne'
--  (otazka/zaujem/nejasne - odpoveda Marek). Ziadny obsah e-mailu sa neuklada.
-- =============================================================================

create table if not exists public.oslovenie_odpovede (
    message_id     text primary key,
    ico            text,
    typ            text not null check (typ in ('nie', 'auto', 'nedorucene', 'rucne', 'ine')),
    odpoved_odoslana boolean not null default false,
    prijate_at     timestamptz,
    spracovane_at  timestamptz not null default now()
);

create index if not exists ix_oslovenie_odpovede_cas on public.oslovenie_odpovede(spracovane_at desc);

alter table public.oslovenie_odpovede enable row level security;
revoke all on public.oslovenie_odpovede from public, anon, authenticated;

select 'Migracia 96 hotova: oslovenie_odpovede.' as vysledok;
