-- =============================================================================
--  P3.2 C (zadanie: claude/predtendrom-p3-cesta-pre-starostov-zadanie.md,
--  sekcia "Malé obce bez úradníkov") — tlačidlo "Zavolajte mi".
--
--  "Pre mnohých starších starostov je telefón prirodzenejší ako formulár."
--  Ide o odľahčenú alternatívu k formuláru na servis.html (ten je dlhší:
--  obec/kraj/IČO/e-mail/popis) pre niekoho, kto teraz nemôže zdvihnúť
--  telefón, ale chce, aby mu Marek zavolal späť — meno, obec, telefón,
--  najlepší čas. Rovnaký "insert-only" RLS vzor ako servisne_dopyty
--  (38_servisny_segment.sql) a odber_obce (11_obce_a_email.sql): anon
--  smie vložiť, čítať smie len service_role (Marek cez Supabase Studio) —
--  inak by hociktoré prezradilo, ktoré obce si pýtajú pomoc.
-- =============================================================================

create table if not exists public.spatne_volania (
    id           bigserial primary key,
    meno         text not null,
    obec         text not null,
    telefon      text not null,
    najlepsi_cas text,
    vybavene     boolean not null default false,
    created_at   timestamptz not null default now()
);

alter table public.spatne_volania enable row level security;

drop policy if exists spatne_volania_insert on public.spatne_volania;
create policy spatne_volania_insert on public.spatne_volania
    for insert to anon, authenticated with check (true);

-- Ziadna select politika ZAMERNE — citanie vyhradne cez service_role.

comment on table public.spatne_volania is
    'Ziadosti "Zavolajte mi" z /starosta.html (P3.2 C). Anon smie len INSERT, '
    'citanie je zakazane (ziadna select politika) — spracovanie rucne cez service_role.';

-- =============================================================================
--  P3.2 C, druha cast tej istej sekcie — suhlas so zverejnenim servisneho
--  dopytu ako verejny dopyt na Trhu dopytov ("zo ziadosti o pomoc sa so
--  suhlasom obce automaticky stane dopyt na trhu").
--
--  DOLEZITA POZNAMKA (nie je to este cela funkcia, len zber suhlasu):
--  servisne_dopyty su anonymne (ziadny prihlaseny ucet), zatial co dopyty
--  na trhu (verejne viditelne poradcom) su viazane na obce_ucty.owner =
--  auth.uid() — kazdy riadok v dopyty ma vlastnika. Automaticke vytvorenie
--  verejneho dopytu zo servisneho by preto znamenalo bud (a) vytvorit
--  obce_ucty "bez vlastnika", co by narusilo RLS vzor pouzivany vsade v
--  34_obce_marketplace.sql a 37_marketplace_kontakt.sql, alebo (b) najprv
--  obec previest cez registraciu. Toto je bezpecnostne/architektonicke
--  rozhodnutie, ktore som nechcel urobit tichoo bez Marekovho vedomia —
--  preto v tejto vlne pribuda LEN stlpec so suhlasom (checkbox vo
--  formulari), automaticke zverejnenie prichadza az v dalsej vlne, po tom,
--  ako sa dohodneme na presnom mechanizme.
-- =============================================================================

alter table public.servisne_dopyty
    add column if not exists suhlas_zverejnit boolean not null default false;

comment on column public.servisne_dopyty.suhlas_zverejnit is
    'Obec suhlasila, ze ziadost sa moze (po schvaleni) zverejnit ako dopyt '
    'na Trhu dopytov. Mechanizmus samotneho zverejnenia zatial nie je '
    'automaticky — cakame na rozhodnutie o obce_ucty bez vlastnika (P3.2 C).';

select 'Spatne volania a suhlas so zverejnenim servisneho dopytu pripravene.' as vysledok;
