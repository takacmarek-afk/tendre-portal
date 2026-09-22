-- =============================================================================
--  PLATBY: prechod z TrustPay/finby na Stripe
--  Vloz do Supabase: SQL Editor -> New query -> Run. Spustit sa da opakovane.
--  Spustaj PO 29_platby.sql.
--
--  DOVOD
--  finby ma pri nizkom objeme transakcii (PredTendrom.sk dnes: radovo
--  desiatky rocne) minimalny mesacny poplatok 12 EUR (= 144 EUR/rok pevne,
--  bez ohladu na skutocnu aktivitu — Cennik poplatkov, sekcia C). To je
--  viac, nez cele naklady na Stripe pri rovnakom objeme (ziadny mesacny ani
--  zriadovaci poplatok, len 1,5 % + 0,25 EUR za EU kartovu platbu — Stripe
--  je navyse potvrdene dostupny pre firmu so sidlom na Slovensku,
--  samoobsluzna registracia bez cakania na KYC support tiket, na rozdiel
--  od finby, kde bol ucet mesiace zaseknuty v Test mode). Marek potvrdil
--  (22.9.2026, po priamom porovnani poplatkov): usetrit peniaze je v tomto
--  pripade podstatnejsie nez zachovat uz raz sfunkcnenu finby integraciu —
--  finby sa teda UPLNE NAHRADZA, nie len doplna paralelne.
--
--  `platby` / `zaloz_platbu()` / `doplnit_platbu()` (29_platby.sql) zostavaju
--  bezo zmeny — uz boli navrhnute branovo-agnosticky (suma sa pocita v
--  cenove_plany, Edge Function ju len cita; `reference` je nahodne UUID
--  nezavisle od konkretnej brany). Meni sa len:
--    1. stlpec `trustpay_status` -> generickejsi `gateway_status`,
--    2. spracovacia funkcia — teraz overuje vysledok Stripe Checkout
--       Session (volana z noveho webhooku stripe-webhook) namiesto
--       finby notifikacie.
-- =============================================================================

alter table public.platby rename column trustpay_status to gateway_status;

drop function if exists public.spracuj_platbu_trustpay(uuid, text, text);

create or replace function public.spracuj_platbu_stripe(
    p_reference uuid, p_stav text, p_gateway_status text
) returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_platba   public.platby;
    v_interval interval;
begin
    select * into v_platba from public.platby where reference = p_reference for update;

    if v_platba is null then
        return jsonb_build_object('ok', false, 'kod', 'NEZNAMA_REFERENCIA');
    end if;

    if v_platba.stav <> 'vytvorena' then
        -- uz spracovane (Stripe vie poslat notifikaciu viackrat) - hlas
        -- uspech, nerob nic (rovnaka idempotencia ako predtym pri finby).
        return jsonb_build_object('ok', true, 'kod', 'UZ_SPRACOVANE');
    end if;

    update public.platby
       set stav = p_stav, gateway_status = p_gateway_status, spracovane_at = now()
     where reference = p_reference;

    if p_stav <> 'zaplatena' then
        insert into public.events (org_id, typ, detail)
        values (v_platba.org_id, 'platba_zamietnuta',
                jsonb_build_object('reference', p_reference, 'gateway_status', p_gateway_status));
        return jsonb_build_object('ok', true, 'kod', 'ZAMIETNUTA');
    end if;

    v_interval := case v_platba.obdobie when 'rok' then interval '365 days' else interval '31 days' end;

    update public.subscriptions
       set stav = 'aktivne',
           plan = v_platba.plan,
           obdobie_konci = greatest(coalesce(obdobie_konci, now()), now()) + v_interval,
           updated_at = now()
     where org_id = v_platba.org_id;

    insert into public.events (org_id, typ, detail)
    values (v_platba.org_id, 'platba_prijata',
            jsonb_build_object('reference', p_reference, 'plan', v_platba.plan,
                                'obdobie', v_platba.obdobie, 'suma', v_platba.suma));

    return jsonb_build_object('ok', true, 'kod', 'AKTIVOVANE');
end;
$$;

revoke all on function public.spracuj_platbu_stripe(uuid, text, text) from public, authenticated, anon;
grant execute on function public.spracuj_platbu_stripe(uuid, text, text) to service_role;


-- ── Kontrola ────────────────────────────────────────────────────────────
select column_name from information_schema.columns
 where table_schema = 'public' and table_name = 'platby' and column_name = 'gateway_status';

select routine_name from information_schema.routines
 where routine_schema = 'public' and routine_name in ('spracuj_platbu_stripe', 'spracuj_platbu_trustpay');

select 'Platby prepnute na Stripe: gateway_status stlpec, spracuj_platbu_stripe funkcia '
       '(spracuj_platbu_trustpay by uz nemala byt vyssie v zozname).' as vysledok;
