-- =============================================================================
--  72 - RYCHLE POLITIKY (vlna 86, 8. 10. 2026): oprava pomaleho nacitania appky
--  Vloz do Supabase: SQL Editor -> New query -> Run. Spustit sa da opakovane.
-- =============================================================================
--
--  PROBLEM (zisteny 8. 10. 2026 na zivej appke, ucet Growth):
--  appka sa pri prvom nacitani zasekla na "Udaje sa nepodarilo nacitat",
--  v konzole 2x HTTP 500. Dotaz na `subsidies?select=*` trval 5 az 8 sekund
--  a Supabase ho po 8 s zrusil (statement timeout, kod 57014).
--
--  PRICINA (moja chyba z vlny 83, migracia 68): pravidla pristupu (RLS) na
--  `opportunities`, `subsidies`, `obce_ziadatelia`, `uvo_*` volali pre KAZDY
--  riadok funkcie ma_aktivny_pristup(), start_kraj_ok() a start_sektor_ok(),
--  a tie vo vnutri znova volaju dalsie funkcie a citaju subscriptions/
--  memberships. Pri 6 000 riadkoch ide o desattisice vnorenych kontrol.
--  Namerane lokalne na kopii databazy: 6 000 prilezitosti = 3,4 s,
--  3 500 dotacii = 2,6 s (v produkcii na mensom stroji viac).
--
--  OPRAVA: vyraz `(select funkcia())` sa v pravidle vyhodnoti JEDNOU na cely
--  dotaz (InitPlan), nie na kazdy riadok. Vyznam pravidiel sa NEMENI:
--    ma_aktivny_pristup() and start_kraj_ok(kraj) and start_sektor_ok(s)
--    ==  ma_aktivny_pristup() and (not je_start_obmedzeny()
--                                  or (kraj v mojich 2 krajoch and sektor v mojich 2 sektoroch))
--  Na pravidla sa nesiaha DROP-om, len ALTER POLICY ... USING, takze roly a
--  prikaz (SELECT) ostavaju. Funkcie start_*_ok ostavaju (vola ich aj iny kod).
--  Pre riadkovu vetvu pribudli _r varianty bez vnutornej kontroly obmedzenia.
-- =============================================================================

-- Riadkove varianty: vyhodnocuju sa LEN ked je pouzivatel na Starte (obmedzeny).
create or replace function public.start_kraj_ok_r(p_kraj text)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
    select exists (
        select 1
          from public.nastavenia_pouzivatela n
         where n.user_id = auth.uid()
           and p_kraj is not null
           and p_kraj = any (n.kraje[1:2])
    );
$$;

create or replace function public.start_sektor_ok_r(p_sektor text, p_null_ok boolean default false)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
    select exists (
        select 1
          from public.nastavenia_pouzivatela n
         where n.user_id = auth.uid()
           and ((p_sektor is null and p_null_ok)
                or p_sektor = any (n.sektory[1:2]))
    );
$$;

revoke all on function public.start_kraj_ok_r(text) from public, anon;
revoke all on function public.start_sektor_ok_r(text, boolean) from public, anon;
grant execute on function public.start_kraj_ok_r(text) to authenticated;
grant execute on function public.start_sektor_ok_r(text, boolean) to authenticated;

-- -- Pravidla bez riadkoveho obmedzenia: len InitPlan ---
alter policy contracts_select       on public.contracts          using ((select public.ma_aktivny_pristup()));
alter policy ceny_pril_select       on public.ceny_prilezitosti  using ((select public.ma_aktivny_pristup()));
alter policy ceny_sektor_select     on public.ceny_sektor        using ((select public.ma_aktivny_pristup()));
alter policy dodavatelia_select     on public.dodavatelia        using ((select public.ma_aktivny_pristup()));
alter policy ruz_financie_select    on public.ruz_financie       using ((select public.ma_team()));
alter policy ruz_zaklad_select      on public.ruz_zaklad         using ((select public.ma_team()));
alter policy sanca_na_vyhru_select  on public.sanca_na_vyhru     using ((select public.ma_pro()));
alter policy tam_sektor_select      on public.tam_sektor         using ((select public.ma_pro()));
alter policy trhovy_podiel_select   on public.trhovy_podiel      using ((select public.ma_pro()));

-- -- Pravidla s obmedzenim Startu (kraj / sektor) ---
alter policy opp_select on public.opportunities
    using ((select public.ma_aktivny_pristup())
           and ((select not public.je_start_obmedzeny())
                or (public.start_kraj_ok_r(kraj)
                    and public.start_sektor_ok_r(sector, false))));

alter policy subsidies_select on public.subsidies
    using ((select public.ma_pristup_k_dotaciam())
           and ((select not public.je_start_obmedzeny())
                or (public.start_kraj_ok_r(kraj)
                    and public.start_sektor_ok_r(sektor_odhad, true))));

alter policy ziadatelia_select on public.obce_ziadatelia
    using ((select public.ma_pristup_k_dotaciam())
           and ((select not public.je_start_obmedzeny())
                or public.start_kraj_ok_r(kraj)));

alter policy uvo_vysledky_select on public.uvo_vysledky
    using ((select public.ma_aktivny_pristup())
           and ((select not public.je_start_obmedzeny())
                or public.start_sektor_ok_r(sektor, true)));

alter policy uvo_vyzvy_select on public.uvo_vyzvy
    using ((select public.ma_aktivny_pristup())
           and ((select not public.je_start_obmedzeny())
                or public.start_sektor_ok_r(sektor, true)));

-- -- Dopyty: ta ista uprava, vyznam nezmeneny ---
alter policy dopyty_select on public.dopyty
    using ((obec_id = (select public.moj_obec_id()))
           or (stav = 'otvoreny' and overeny and (select public.je_poradca()))
           or (stav = 'otvoreny' and overeny and (select public.ma_dopyty_pristup())));

select 'Migracia 72 hotova: pravidla pristupu sa vyhodnocuju raz na dotaz, nie na riadok.' as vysledok;
