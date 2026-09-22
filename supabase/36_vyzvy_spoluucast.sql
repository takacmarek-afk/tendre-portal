-- =============================================================================
--  VYZVY: pole pre financnu spoluucast (kratky, doslovny vytah zo zdroja)
--  Vloz do Supabase: SQL Editor -> New query -> Run. Spustit sa da opakovane.
--
--  CO TOTO RIESI
--  Marek chcel, aby obce pri otvorenych vyzvach videli aj zakladnu info o
--  financnej ucasti (spoluucast/spolufinancovanie) — s podmienkou "blbuvzdorne",
--  teda NIKDY vymyslene cislo. Zvazovali sme aj rucne udrziavanu tabulku
--  "typicka spoluucast pre hlavny program", ale to by bolo bud zbytocne vseobecne
--  (nepouzitelne), alebo riskantne konkretne (mohlo by sa minut ucinnosti a
--  nikto by to neopravil). Namiesto toho: pri kazdej jednotlivej vyzve pipeline
--  skusa v REALNOM texte zdroja (nazov+popis clanku) najst vetu o spoluucasti/
--  spolufinancovani (pipeline/vyzvy.py::_najdi_spoluucast, jednoduchy regex na
--  % v okoli tychto slov). Ked ju najde, ulozi presne tu vetu (doslovny vytah,
--  nie prepocitane cislo). Ked ju nenajde, pole zostava NULL a UI nic nezobrazi
--  — ziadne hadanie, ziadne "zvycajne okolo X %".
-- =============================================================================

alter table public.vyzvy add column if not exists spoluucast_text text;

select 'vyzvy.spoluucast_text pripravene.' as vysledok;
