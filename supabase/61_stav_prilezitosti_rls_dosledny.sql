-- =============================================================================
--  61 — moj_stav_prilezitosti: RLS politika dosledne vynucuje updated_by
--  Vloz do Supabase: SQL Editor -> New query -> Run. Spustit sa da opakovane.
-- =============================================================================
--
--  NAJDENA NEZROVNALOST (komplexny audit 29.9.2026, subagent "SQL/RLS
--  security"): komentar pri tabulke (32_stav_prilezitosti.sql) hovori
--  "Upsert cez RPC, nie priamy insert z klienta - ... updated_by/
--  updated_at sa vzdy nastavia servrom, nie tym, co posle prehliadac."
--  Politika stav_pril_all vsak bola "for all using/with check (org_id in
--  moje_org_ids() and ma_pro())" - nič nebranilo priamemu volaniu
--  PostgREST (obidenim RPC nastav_stav_prilezitosti) a nastaveniu
--  updated_by na hocijake uuid v ramci tej istej organizacie (napr. na
--  kolegu). Nizka zavaznost - len v ramci vlastnej organizacie, ziadny
--  unik cudzich dat - ale politika nerobila presne to, co komentar sluboval.
--
--  OPRAVA: with check doplneny o "updated_by = auth.uid()". RPC
--  nastav_stav_prilezitosti() je SECURITY DEFINER a bezi ako vlastnik
--  funkcie (obchadza RLS), takze tato zmena sa jej vobec netyka - opravuje
--  len priamy klientsky insert/update, ktory RLS politika doteraz
--  nespravne dovolovala.
-- =============================================================================

drop policy if exists stav_pril_all on public.moj_stav_prilezitosti;
create policy stav_pril_all on public.moj_stav_prilezitosti
    for all to authenticated
    using (org_id in (select public.moje_org_ids()) and public.ma_pro())
    with check (
        org_id in (select public.moje_org_ids())
        and public.ma_pro()
        and updated_by = auth.uid()
    );

select 'moj_stav_prilezitosti: RLS politika teraz vynucuje updated_by = auth.uid().' as vysledok;
