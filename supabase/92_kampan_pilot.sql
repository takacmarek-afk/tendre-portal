-- =============================================================================
--  Migracia 92: vygenerovane e-maily pilotnej kampane (3. 11. 2026)
--  generuj-kampan.ts --do-db sem ulozi hotove e-maily namiesto CSV na disku
--  (bezi v GitHub Actions; repo aj logy su verejne, preto kontakty nikdy
--  nejdu do logu ani do artefaktu). Export do CSV robi admin cez SQL.
--  Len service_role / SQL editor: RLS zapnute, ziadne pravidla.
-- =============================================================================

create table if not exists public.kampan_pilot (
    mesiac       date not null,
    ico          text not null,
    email_obce   text not null,
    predmet      text not null,
    telo_text    text not null,
    variant      text not null check (variant in ('A', 'B')),
    vytvorene_at timestamptz not null default now(),
    primary key (mesiac, ico)
);
alter table public.kampan_pilot enable row level security;
revoke all on public.kampan_pilot from anon, authenticated;

select 'Migracia 92 hotova: kampan_pilot.' as vysledok;
