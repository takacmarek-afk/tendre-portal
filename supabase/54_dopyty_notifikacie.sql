-- =============================================================================
--  54 — STĹPCE PRE E-MAILOVÉ UPOZORNENIA PRI DOPYTOCH (zistenie 28.9.2026)
--  Vloz do Supabase: SQL Editor -> New query -> Run. Spustit sa da opakovane.
-- =============================================================================
--
--  CO TO RIESI
--  Marek nahlasil naziva 28.9.2026: vytvoril si testovaci dopyt za obec a
--  nedostal ziadny e-mail. Overenie v kode potvrdilo realnu dieru — ani
--  vytvor_dopyt() ani reaguj_na_dopyt() (34_obce_marketplace.sql) nemaju
--  ziadnu notifikaciu. Poradca sa o novom dopyte dozvie len ked si sam
--  otvori trh.html, obec sa o reakcii dozvie len ked si sama skontroluje
--  svoj dopyt. Zapisane v audit dokumente, teraz sa to dorieova.
--
--  PRECO STLPCE, NIE DB TRIGGER + pg_net
--  Priamy trigger, co by pri INSERTe rovno volal Resend cez pg_net, by bol
--  najrychlejsi (naozaj okamzity), ALE pg_net v tomto projekte este NIE JE
--  zapnute rozsirenie a zapnutie noveho rozsirenia v produkcnej databaze je
--  zmena, ktoru si vyzaduje samostatne explicitne schvalenie (rovnaky
--  bezpecnostny dovod, preco aj tato migracia bezi len s priamym suhlasom).
--  Miesto toho tieto dva nove stlpce len OZNACIA, ktore dopyty/reakcie este
--  neboli notifikovane — poslanie sameho e-mailu robi novy Python skript
--  (pipeline/posli_dopyt_email.py), rovnakym sposobom ako uz existujuci
--  tyzdenny/denny e-mail (posli_email.py), len castejsie naplanovany
--  (kazdych 15 minut, viz .github/workflows/dopyty-email.yml). Ziadne nove
--  tajomstvo, ziadne nove rozsirenie — len znovupouzitie uz schvalenej cesty
--  (Resend cez RESEND_API_KEY, uz v GitHub Secrets).
--
--  Dosledok: notifikacia nepride OKAMZITE, ale do ~15 minut. Pre burzu s
--  dnes 0 riadkami v dopyty/reakcie je to zanedbatelny rozdiel oproti tomu,
--  ze doteraz nechodilo nic vobec.
-- =============================================================================

alter table public.dopyty
    add column if not exists poradcovia_notifikovani boolean not null default false;

alter table public.reakcie
    add column if not exists obec_notifikovana boolean not null default false;

-- Existujuce riadky (vratane akychkolvek testovacich, ktore uz Marek/ja
-- upratali) oznacit ako "uz notifikovane", aby prvy beh skriptu neposlal
-- e-maily o starych/testovacich zaznamoch spred existencie tejto funkcie.
update public.dopyty  set poradcovia_notifikovani = true where poradcovia_notifikovani = false;
update public.reakcie set obec_notifikovana        = true where obec_notifikovana = false;

create index if not exists ix_dopyty_nenotifikovane
    on public.dopyty(poradcovia_notifikovani) where poradcovia_notifikovani = false;
create index if not exists ix_reakcie_nenotifikovane
    on public.reakcie(obec_notifikovana) where obec_notifikovana = false;

select 'Stlpce pre notifikacie pripravene, existujuce riadky oznacene ako uz notifikovane.' as vysledok;
