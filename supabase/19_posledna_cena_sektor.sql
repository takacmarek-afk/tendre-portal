-- =============================================================================
--  POSLEDNA SKUTOCNA CENA V SEKTORE
--  Vloz do Supabase: SQL Editor -> New query -> Run. Spustit sa da opakovane.
--  Spustaj PO 05_analytika.sql.
-- =============================================================================
--
--  CO TO JE
--  `ceny_sektor` uz obsahovala median a kvartily, ale medzi 17.9.2026 a touto
--  migraciou sa nikde v produkte nezobrazovala vobec — tabulka existovala,
--  pipeline ju kazdy den plnila, ale ziadna stranka sa jej nepytala. Tato
--  migracia dopna dva stlpce (analytics.medianySektora, funkcia
--  _posledna_skutocna_cena): konkretnu cenu a datum NAJNOVSEJ zmluvy v tom
--  istom sektore, ktora prezila rovnaky orez extremov ako median. Cielom je
--  dat zakaznikovi popri abstraktnom pasme aj jedno konkretne, overitelne
--  cislo: "naposledy sa v tomto sektore sutazilo o X EUR, dna Y".
-- =============================================================================

alter table public.ceny_sektor add column if not exists posledna_cena        numeric;
alter table public.ceny_sektor add column if not exists posledna_cena_datum  date;

select 'ceny_sektor: pridane posledna_cena a posledna_cena_datum.' as vysledok;
