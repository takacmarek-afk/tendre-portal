-- =============================================================================
--  VLASTNE ICO PRE OSOBNU RELEVANCIU (#7)
--  Vloz do Supabase: SQL Editor -> New query -> Run. Spustit sa da opakovane.
--  Spustaj PO 08_zadarmo.sql (potrebuje tabulku odber).
-- =============================================================================
--
--  CO TO JE
--  Firma si dobrovolne ulozi VLASTNE ICO do svojho odberu. Appka ho pouzije
--  len na jedno: vyhladanie vlastneho profilu v uz existujucej tabulke
--  `dodavatelia` (hlavny_sektor, priemerna_zmluva_eur) a s jeho pomocou
--  dolozi poradie zoznamu prilezitosti — ziadna nova agregacia, ziadny novy
--  vypocet v pipeline. Bez tohto pola personalizacia jednoducho vynecha
--  zlozku "vlastna historia" a pouzije len sektor/kraj z odberu.
--
--  PRECO ZIADNY NOVY INDEX
--  Citanie je opacnym smerom, nez by index pomohol: appka pozna JEDNO ICO
--  (vlastne) a hlada ho v `dodavatelia` podla existujuceho primary key
--  (supplier_cin). Riadok v `odber` sa nikdy nefiltruje podla moje_ico.
-- =============================================================================

alter table public.odber add column if not exists moje_ico text;

select 'moje_ico pripravene na public.odber.' as vysledok;
