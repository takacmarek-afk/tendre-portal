-- =============================================================================
--  SERVISNY SEGMENT: dopytovy formular pre "urobime to za vas" (servis.html)
--  Vloz do Supabase: SQL Editor -> New query -> Run. Spustit sa da opakovane.
--
--  CO TOTO RIESI
--  Z navrhu rozvoja portalu (doc "Predtendrom.sk — navrh rozvoja portalu",
--  sekcia "Vlastny servisny segment pre najmenej schopne obce"): najmensie
--  a najmenej solventne obce su segment, ktory si sukromny poradca ani dnes
--  neberie (marza prilis nizka voci administrativnej zataazi). Marek chcel
--  "postavit cele" — ale toto NIE JE len softver (realni ludia, zodpovednost
--  za vysledok, ina ekonomika nez SaaS predplatne), takze rozsah tejto vlny
--  je landing page + dopytovy formular (spracovanie dopytov zatial rucne,
--  Marek/tim), nie automatizovana sluzba.
--
--  PRECO SAMOSTATNA TABULKA S "INSERT-ONLY" RLS (vzor odber_obce,
--  11_obce_a_email.sql)
--  Formular vyplna nepirhlaseny navstevnik (rovnaka "bez trenia" filozofia
--  ako inde smerom k obciam) — insert musi byt mozny bez auth.uid(). Citanie
--  ale musi byt zakazane pre kohokolvek okrem service_role (Marek cez
--  Supabase Studio), inak by ktokolvek dopytom zistil, ktore obce si servis
--  ziadaju (citlive: priznanie vlastnej nedostatocnej kapacity).
-- =============================================================================

create table if not exists public.servisne_dopyty (
    id              bigserial primary key,
    obec            text not null,
    ico             text,
    kraj            text,
    kontakt_email   text not null,
    kontakt_telefon text,
    popis           text not null,
    vybavene        boolean not null default false,
    created_at      timestamptz not null default now()
);

alter table public.servisne_dopyty enable row level security;

drop policy if exists servisne_dopyty_insert on public.servisne_dopyty;
create policy servisne_dopyty_insert on public.servisne_dopyty
    for insert to anon, authenticated with check (true);

-- Ziadna select politika tu ZAMERNE nie je — rovnaky dovod ako pri
-- odber_obce. Citanie vyhradne cez service_role (Supabase Studio).

comment on table public.servisne_dopyty is
    'Dopyty na servisny segment ("urobime to za vas"). Anon smie len INSERT, '
    'citanie je zakazane (ziadna select politika) — spracovanie rucne cez service_role.';

select 'Servisny segment pripraveny: servisne_dopyty (' || count(*)::text || ' riadkov).' as vysledok
  from public.servisne_dopyty;
