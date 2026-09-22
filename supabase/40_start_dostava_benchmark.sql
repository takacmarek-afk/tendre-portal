-- =============================================================================
--  OPRAVA: Start plan nedostaval "Cenovy benchmark sektora", hoci ho cennik.html
--  vyslovne sluby uz na urovni Start.
--  Vloz do Supabase: SQL Editor -> New query -> Run. Spustit sa da opakovane.
-- =============================================================================
--
--  NALEZ (zivy audit 22.9.2026)
--  dodavatelia_select, ceny_sektor_select a ceny_pril_select (06_plany.sql,
--  07_revizia.sql) vsetky gatuju na ma_pro(), ktora po 31_oprava_ma_pro_planov.sql
--  pozna 'trial','pro','growth','team','admin' - ale NIE 'start'. cennik.html
--  pritom Start planu vyslovne slubuje "Cenovy benchmark sektora" a appka
--  (app.html, komentar "Dodavatelia su Pro...") cely obsah zalozky Dodavatelia
--  (vratane benchmarku) skryva pre kohokolvek okrem tychto planov. Kym
--  je_zadarmo() vracia true, chyba je mrtva (presne ako pri 31_oprava);
--  v momente prepnutia by kazdy platiaci Start zakaznik dostal prazdnu
--  zalozku namiesto toho, co si kupil.
--
--  OPRAVA: cenovy benchmark (ceny_sektor, ceny_prilezitosti) a zoznam/profil
--  dodavatelov (dodavatelia) prechadzaju z ma_pro() na ma_aktivny_pristup()
--  - teda "akykolvek aktivny plan alebo platny trial", presne to, co Start
--  uz je. Sledovanie firiem (sledovane_ico), CRM stav (moj_stav_prilezitosti),
--  denny digest/webhook (25_odber_pro_gating.sql), sanca na vyhru a trhovy
--  podiel (22/24) OSTAVAJU na ma_pro() bez zmeny - tie su v cenniku vyslovne
--  len v stlpci Growth a vyssie.
-- =============================================================================

drop policy if exists dodavatelia_select on public.dodavatelia;
create policy dodavatelia_select on public.dodavatelia
    for select to authenticated
    using (public.ma_aktivny_pristup());

drop policy if exists ceny_sektor_select on public.ceny_sektor;
create policy ceny_sektor_select on public.ceny_sektor
    for select to authenticated
    using (public.ma_aktivny_pristup());

drop policy if exists ceny_pril_select on public.ceny_prilezitosti;
create policy ceny_pril_select on public.ceny_prilezitosti
    for select to authenticated
    using (public.ma_aktivny_pristup());

select polname, pg_get_expr(polqual, polrelid) as using_expr
  from pg_policy
 where polrelid in (
     'public.dodavatelia'::regclass,
     'public.ceny_sektor'::regclass,
     'public.ceny_prilezitosti'::regclass
 );

select 'Cenovy benchmark a zoznam dodavatelov su odteraz Start+ (ma_aktivny_pristup()), '
       'presne ako cennik.html sluby. Sledovanie/CRM/denny digest/webhook/sanca/trhovy '
       'podiel ostavaju Growth+ (ma_pro(), nezmenene).' as vysledok;
