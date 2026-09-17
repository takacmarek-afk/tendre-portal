-- =============================================================================
--  FREKVENCIA ODBERU: denne alebo tyzdenne
--  Vloz do Supabase: SQL Editor -> New query -> Run. Spustit sa da opakovane.
--  Spustaj PO 08_zadarmo.sql (mení tabuľku `odber`, ktorú založila ona).
-- =============================================================================
--
--  CO TO JE
--  `watchlists.digest_frekvencia` uz roky ma tento isty enum (denne/tyzdenne/
--  ziadny), ale `posli_email.py` watchlists vobec nepouziva — cita `odber`,
--  jednoduchsiu tabulku so zaujmom (sektor+kraj), ktoru zaklada 08_zadarmo.sql.
--  Tato migracia prida rovnaky vyber priamo do nej, aby ho bolo mozne naozaj
--  pouzit tam, kde sa realne posiela.
--
--  PRECO DEFAULT 'tyzdenne'
--  Existujuci odberatelia sa prihlasovali na "tyzdenny prehlad" (viz text
--  v app.html). Zmena spustania workflowu z tyzdennej na dennu frekvenciu
--  (aby denni odberatelia vobec mohli dostat denny mail) by im bez tohto
--  defaultu zacala posielat mail kazdy den namiesto raz do tyzdna — presne
--  ten tichy posun v sprave, ktoremu sa tento projekt inde vyhyba.
-- =============================================================================

alter table public.odber add column if not exists frekvencia text not null default 'tyzdenne';

alter table public.odber drop constraint if exists odber_frekvencia_check;
alter table public.odber add constraint odber_frekvencia_check
    check (frekvencia in ('denne', 'tyzdenne'));

select 'odber: pridany vyber frekvencie (denne/tyzdenne), default tyzdenne.' as vysledok;
