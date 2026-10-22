-- =============================================================================
--  83 - START: RYCHLE POCTY A UPLNE OBMEDZENIE (audit 22. 10. 2026)
--  Vloz do Supabase: SQL Editor -> New query -> Run. Spustit sa da opakovane.
-- =============================================================================
--
--  PROBLEM 1 (blocker auditu): na obrazovke Dnes padali pocty pre plan Start.
--  HEAD dotazy s `Prefer: count=exact` na `opportunities` vracali 503 a appka
--  ukazala "0 novych prilezitosti". Pre Start sa v pravidle stale vola pre
--  KAZDY riadok start_kraj_ok_r()/start_sektor_ok_r() a kazde volanie cita
--  nastavenia_pouzivatela. Pocet cez celu tabulku = tisicky vnorenych dotazov.
--
--  OPRAVA 1: vyber Startu sa nacita JEDNOU na dotaz (InitPlan) ako pole
--  a riadok sa porovna obycajnym `= any(pole)`. Vyznam pravidiel sa nemeni:
--    start_kraj_ok_r(k)         == k = any(prve 2 kraje)       (null kraj = nie)
--    start_sektor_ok_r(s,false) == s = any(prve 2 sektory)      (null = nie)
--    start_sektor_ok_r(s,true)  == s is null or s = any(...)
--  Bez riadku v nastavenia_pouzivatela je pole null -> nic (ako doteraz).
--
--  PROBLEM 2: Start cital cez API celu tabulku `contracts` (233 000 zmluv,
--  vsetky sektory), `dodavatelia` a `ceny_sektor` — limit 2 + 2 sa dal obist
--  jednym dotazom.
--
--  OPRAVA 2: pre Start aj tieto tabulky len v jeho 2 sektoroch
--  (`contracts.sector`, `dodavatelia.hlavny_sektor`, `ceny_sektor.sector`).
--  Kraj tieto tabulky nemaju, preto sa obmedzuje len sektor. Growth, Team,
--  skuska a admin bez zmeny.
-- =============================================================================

-- Vyber Startu ako pole, raz na dotaz. Pre ineho nez Start sa nepouzije
-- (vetva `not je_start_obmedzeny()` je pravdiva skor).
create or replace function public.start_kraje()
returns text[]
language sql
stable
security definer
set search_path = ''
as $$
    select (select n.kraje[1:2] from public.nastavenia_pouzivatela n where n.user_id = auth.uid());
$$;

create or replace function public.start_sektory()
returns text[]
language sql
stable
security definer
set search_path = ''
as $$
    select (select n.sektory[1:2] from public.nastavenia_pouzivatela n where n.user_id = auth.uid());
$$;

revoke all on function public.start_kraje() from public, anon;
revoke all on function public.start_sektory() from public, anon;
grant execute on function public.start_kraje() to authenticated;
grant execute on function public.start_sektory() to authenticated;

-- -- Pravidla s obmedzenim Startu: pole namiesto funkcie na riadok ---
alter policy opp_select on public.opportunities
    using ((select public.ma_aktivny_pristup())
           and ((select not public.je_start_obmedzeny())
                or (kraj = any ((select public.start_kraje())::text[])
                    and sector = any ((select public.start_sektory())::text[]))));

alter policy subsidies_select on public.subsidies
    using ((select public.ma_pristup_k_dotaciam())
           and ((select not public.je_start_obmedzeny())
                or (kraj = any ((select public.start_kraje())::text[])
                    and (sektor_odhad is null
                         or sektor_odhad = any ((select public.start_sektory())::text[])))));

alter policy ziadatelia_select on public.obce_ziadatelia
    using ((select public.ma_pristup_k_dotaciam())
           and ((select not public.je_start_obmedzeny())
                or kraj = any ((select public.start_kraje())::text[])));

alter policy uvo_vysledky_select on public.uvo_vysledky
    using ((select public.ma_aktivny_pristup())
           and ((select not public.je_start_obmedzeny())
                or sektor is null
                or sektor = any ((select public.start_sektory())::text[])));

alter policy uvo_vyzvy_select on public.uvo_vyzvy
    using ((select public.ma_aktivny_pristup())
           and ((select not public.je_start_obmedzeny())
                or sektor is null
                or sektor = any ((select public.start_sektory())::text[])));

-- -- Nove: Start aj v zmluvach, dodavateloch a cenach len vo svojich sektoroch ---
alter policy contracts_select on public.contracts
    using ((select public.ma_aktivny_pristup())
           and ((select not public.je_start_obmedzeny())
                or sector = any ((select public.start_sektory())::text[])));

alter policy dodavatelia_select on public.dodavatelia
    using ((select public.ma_aktivny_pristup())
           and ((select not public.je_start_obmedzeny())
                or hlavny_sektor = any ((select public.start_sektory())::text[])));

alter policy ceny_sektor_select on public.ceny_sektor
    using ((select public.ma_aktivny_pristup())
           and ((select not public.je_start_obmedzeny())
                or sector = any ((select public.start_sektory())::text[])));

select 'Migracia 83 hotova: Start ma rychle pocty a obmedzenie 2 + 2 aj v zmluvach, dodavateloch a cenach.' as vysledok;
