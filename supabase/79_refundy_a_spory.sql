-- =============================================================================
--  REFUNDY A SPORY: zaznam do tabulky events (audit 13.10.2026, polozka 12)
--  Vloz do Supabase: SQL Editor -> New query -> Run. Spustit sa da opakovane.
--  Spustaj PO 30_stripe_platby.sql.
--
--  PROBLEM
--  Webhook stripe-webhook spracuvaval len stav Checkout Session. Ak zakaznik
--  dostal spat peniaze (refund) alebo otvoril spor u banky (dispute), system
--  o tom nevedel: predplatne zostalo aktivne a nikto sa to nedozvedel.
--
--  RIESENIE (zamerne konzervativne)
--  1. platby.payment_intent: webhook ho ulozi pri uspesnej platbe, aby sa dal
--     refund/spor sparovat s nasou platbou (charge.* udalosti nenesu nasu
--     referenciu, len payment_intent).
--  2. spracuj_refund_stripe(): zapise do events typ 'platba_vratena' alebo
--     'platba_spor'. Predplatne SAMO NEVYPINA: ci sa pristup zrusi, rozhodnes
--     ty (ciastocny refund, sukromna dohoda, vyhrany spor...). Upozornenie
--     dostanes tak, ze si tieto zaznamy pozries (dotaz nizsie).
--
--  KONTROLA (spusti si raz tyzdenne, kym nie je e-mailove upozornenie):
--    select created_at, org_id, typ, detail from public.events
--     where typ in ('platba_vratena','platba_spor') order by created_at desc;
-- =============================================================================

alter table public.platby add column if not exists payment_intent text;
create index if not exists ix_platby_payment_intent on public.platby(payment_intent);

create or replace function public.zapis_payment_intent(p_reference uuid, p_payment_intent text)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
begin
    if p_payment_intent is null or p_payment_intent = '' then
        return jsonb_build_object('ok', false, 'kod', 'PRAZDNY_PAYMENT_INTENT');
    end if;
    update public.platby set payment_intent = p_payment_intent
     where reference = p_reference and payment_intent is null;
    return jsonb_build_object('ok', true);
end;
$$;

create or replace function public.spracuj_refund_stripe(
    p_payment_intent text, p_udalost text, p_suma numeric, p_plna boolean
) returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_platba public.platby;
    v_typ    text;
begin
    select * into v_platba from public.platby
     where payment_intent = p_payment_intent
     order by created_at desc limit 1;

    if v_platba is null then
        -- Platba, ktoru nepoznas (napr. testovacia alebo stara, pred touto
        -- migraciou). Potvrd prijatie, nech Stripe neopakuje dorucenie.
        return jsonb_build_object('ok', false, 'kod', 'NEZNAMA_PLATBA');
    end if;

    v_typ := case when p_udalost = 'charge.dispute.created' then 'platba_spor' else 'platba_vratena' end;

    -- Idempotencia: ta ista udalost pre tu istu platbu a sumu sa zapise raz.
    if exists (select 1 from public.events
                where org_id = v_platba.org_id and typ = v_typ
                  and detail->>'payment_intent' = p_payment_intent
                  and detail->>'udalost' = p_udalost
                  and (detail->>'suma')::numeric = p_suma) then
        return jsonb_build_object('ok', true, 'kod', 'UZ_ZAPISANE');
    end if;

    insert into public.events (org_id, typ, detail)
    values (v_platba.org_id, v_typ,
            jsonb_build_object('reference', v_platba.reference, 'plan', v_platba.plan,
                               'obdobie', v_platba.obdobie, 'suma_platby', v_platba.suma,
                               'suma', p_suma, 'plna', p_plna,
                               'udalost', p_udalost, 'payment_intent', p_payment_intent));

    return jsonb_build_object('ok', true, 'kod', 'ZAPISANE');
end;
$$;

revoke all on function public.zapis_payment_intent(uuid, text) from public, authenticated, anon;
grant execute on function public.zapis_payment_intent(uuid, text) to service_role;
revoke all on function public.spracuj_refund_stripe(text, text, numeric, boolean) from public, authenticated, anon;
grant execute on function public.spracuj_refund_stripe(text, text, numeric, boolean) to service_role;

select 'Refundy a spory: platby.payment_intent, zapis_payment_intent(), spracuj_refund_stripe()' as vysledok;
