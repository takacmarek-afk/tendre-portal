-- =============================================================================
--  Migracia 87: automaticky obnovovane predplatne cez Stripe (audit 2. 11. 2026,
--  Top 5 bod 4). Doteraz bola kazda platba jednorazova a po skonceni obdobia
--  zakaznik musel zaplatit znova sam (pripomienka obnovy). Odteraz moze
--  stripe-checkout (pri STRIPE_PREDPLATNE=true) zalozit Stripe Subscription:
--
--    checkout.session.completed (mode=subscription)
--        -> spracuj_platbu_stripe()  (ako doteraz: aktivuje a predlzi)
--        -> prepoj_predplatne_stripe()  (ulozi subscription/customer id)
--    invoice.paid (billing_reason=subscription_cycle)
--        -> obnov_predplatne_stripe()  (novy riadok v platby + predlzenie)
--    customer.subscription.updated / deleted
--        -> nastav_obnovu_stripe()  (zrusenie obnovy, pristup do konca obdobia)
--
--  Vsetky funkcie su len pre service_role (Edge Function stripe-webhook).
--  Idempotencia: jedna faktura Stripe = najviac jeden riadok v platby
--  (unikatny index na stripe_invoice_id).
--  Bezpecne spustit opakovane.
-- =============================================================================

alter table public.platby add column if not exists stripe_invoice_id text;
create unique index if not exists platby_stripe_invoice_uq
    on public.platby (stripe_invoice_id) where stripe_invoice_id is not null;

alter table public.subscriptions add column if not exists auto_obnova boolean not null default false;
create index if not exists ix_subscriptions_stripe_sub on public.subscriptions (stripe_subscription_id);

-- 1) Po prvej platbe v rezime predplatneho ------------------------------------
create or replace function public.prepoj_predplatne_stripe(
    p_reference uuid, p_subscription_id text, p_customer_id text, p_invoice_id text
) returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_org uuid;
begin
    select org_id into v_org from public.platby where reference = p_reference;
    if v_org is null then
        return jsonb_build_object('ok', false, 'kod', 'NEZNAMA_REFERENCIA');
    end if;
    if p_subscription_id is null or p_subscription_id = '' then
        return jsonb_build_object('ok', false, 'kod', 'BEZ_PREDPLATNEHO');
    end if;

    update public.platby
       set stripe_invoice_id = coalesce(stripe_invoice_id, nullif(p_invoice_id, ''))
     where reference = p_reference
       and not exists (select 1 from public.platby x
                        where x.stripe_invoice_id = p_invoice_id and x.reference <> p_reference);

    update public.subscriptions
       set stripe_subscription_id = p_subscription_id,
           stripe_customer_id = coalesce(nullif(p_customer_id, ''), stripe_customer_id),
           auto_obnova = true,
           updated_at = now()
     where org_id = v_org;

    insert into public.events (org_id, typ, detail)
    values (v_org, 'predplatne_zalozene',
            jsonb_build_object('reference', p_reference, 'subscription', p_subscription_id));

    return jsonb_build_object('ok', true, 'kod', 'PREPOJENE');
end;
$$;

-- 2) Kazda dalsia (automaticka) platba ----------------------------------------
create or replace function public.obnov_predplatne_stripe(
    p_subscription_id text, p_invoice_id text, p_suma numeric, p_obdobie_do timestamptz
) returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_sub      public.subscriptions;
    v_posledna public.platby;
    v_interval interval;
begin
    if p_invoice_id is null or p_invoice_id = '' then
        return jsonb_build_object('ok', false, 'kod', 'BEZ_FAKTURY');
    end if;
    if exists (select 1 from public.platby where stripe_invoice_id = p_invoice_id) then
        return jsonb_build_object('ok', true, 'kod', 'UZ_SPRACOVANE');
    end if;

    select * into v_sub from public.subscriptions
     where stripe_subscription_id = p_subscription_id
     for update;
    if v_sub.org_id is null then
        -- Nepozname predplatne (napr. zalozene rucne v Dashboarde). Nie 5xx,
        -- inak by Stripe opakoval donekonecna; udalost sa zapise na kontrolu.
        insert into public.events (org_id, typ, detail)
        values (null, 'predplatne_nezname',
                jsonb_build_object('subscription', p_subscription_id, 'invoice', p_invoice_id, 'suma', p_suma));
        return jsonb_build_object('ok', false, 'kod', 'NEZNAME_PREDPLATNE');
    end if;

    select * into v_posledna from public.platby
     where org_id = v_sub.org_id and stav = 'zaplatena'
     order by created_at desc
     limit 1;

    v_interval := case coalesce(v_posledna.obdobie, 'mesiac')
                    when 'rok' then interval '365 days' else interval '31 days' end;

    insert into public.platby (org_id, plan, obdobie, suma, mena, stav, gateway_status,
                               spracovane_at, stripe_invoice_id, zlava_kod)
    values (v_sub.org_id, coalesce(v_posledna.plan, 'growth'), coalesce(v_posledna.obdobie, 'mesiac'),
            p_suma, coalesce(v_posledna.mena, 'EUR'), 'zaplatena', 'invoice.paid',
            now(), p_invoice_id, v_posledna.zlava_kod);

    -- Obdobie podla Stripe (koniec fakturovaneho obdobia); bez neho o jedno
    -- obdobie dalej. Nikdy sa neskracuje.
    update public.subscriptions
       set stav = 'aktivne',
           auto_obnova = true,
           obdobie_konci = greatest(coalesce(obdobie_konci, now()),
                                    coalesce(p_obdobie_do, greatest(coalesce(obdobie_konci, now()), now()) + v_interval)),
           updated_at = now()
     where org_id = v_sub.org_id;

    insert into public.events (org_id, typ, detail)
    values (v_sub.org_id, 'platba_obnova',
            jsonb_build_object('invoice', p_invoice_id, 'suma', p_suma, 'do', p_obdobie_do));

    return jsonb_build_object('ok', true, 'kod', 'OBNOVENE');
end;
$$;

-- 3) Zrusenie / obnovenie automatickej obnovy ----------------------------------
create or replace function public.nastav_obnovu_stripe(p_subscription_id text, p_auto boolean)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_org uuid;
begin
    update public.subscriptions
       set auto_obnova = p_auto, updated_at = now()
     where stripe_subscription_id = p_subscription_id
    returning org_id into v_org;

    if v_org is null then
        return jsonb_build_object('ok', false, 'kod', 'NEZNAME_PREDPLATNE');
    end if;
    insert into public.events (org_id, typ, detail)
    values (v_org, case when p_auto then 'predplatne_obnova_zapnuta' else 'predplatne_obnova_zrusena' end,
            jsonb_build_object('subscription', p_subscription_id));
    return jsonb_build_object('ok', true, 'kod', case when p_auto then 'ZAPNUTE' else 'ZRUSENE' end);
end;
$$;

-- 4) Customer id pre portal (Edge Function stripe-portal, pod JWT) -------------
-- Vrati Stripe customer id firmy prihlaseneho vlastnika/admina, inak null.
create or replace function public.moj_stripe_zakaznik()
returns text
language sql
stable
security definer
set search_path = public
as $$
    select s.stripe_customer_id
      from public.subscriptions s
      join public.memberships m on m.org_id = s.org_id
     where m.user_id = auth.uid() and m.rola in ('owner', 'admin')
     limit 1;
$$;

-- 5) Pripomienka obnovy pozna automaticku obnovu --------------------------------
-- Pri automatickej obnove sa mesacne predplatne nepripomina (obnovi sa samo);
-- rocne dostane upozornenie 7 dni vopred, ze sa obnovi a ako ho zrusit.
drop function if exists public.pripomienky_obnovy();
create function public.pripomienky_obnovy()
returns table (org_id uuid, email text, plan text, obdobie_konci timestamptz, auto_obnova boolean, obdobie text)
language sql
stable
security definer
set search_path = ''
as $$
    select s.org_id, u.email::text, s.plan, s.obdobie_konci, s.auto_obnova, p.obdobie
      from public.subscriptions s
      join public.memberships m on m.org_id = s.org_id and m.rola in ('owner', 'admin')
      join auth.users u on u.id = m.user_id
      left join lateral (select x.obdobie from public.platby x
                          where x.org_id = s.org_id and x.stav = 'zaplatena'
                          order by x.created_at desc limit 1) p on true
     where s.stav = 'aktivne'
       and s.plan in ('start', 'growth', 'team', 'poradca', 'pro')
       and s.obdobie_konci is not null
       and s.obdobie_konci > now()
       and s.obdobie_konci <= now() + interval '7 days'
       and s.pripomienka_obnovy_za is distinct from s.obdobie_konci
       and not (s.auto_obnova and coalesce(p.obdobie, 'mesiac') = 'mesiac')
       and u.email is not null;
$$;
revoke all on function public.pripomienky_obnovy() from public, anon, authenticated;
grant execute on function public.pripomienky_obnovy() to service_role;

revoke all on function public.prepoj_predplatne_stripe(uuid, text, text, text) from public, anon, authenticated;
revoke all on function public.obnov_predplatne_stripe(text, text, numeric, timestamptz) from public, anon, authenticated;
revoke all on function public.nastav_obnovu_stripe(text, boolean) from public, anon, authenticated;
grant execute on function public.prepoj_predplatne_stripe(uuid, text, text, text) to service_role;
grant execute on function public.obnov_predplatne_stripe(text, text, numeric, timestamptz) to service_role;
grant execute on function public.nastav_obnovu_stripe(text, boolean) to service_role;
revoke all on function public.moj_stripe_zakaznik() from public, anon;
grant execute on function public.moj_stripe_zakaznik() to authenticated;

select 'Migracia 87 hotova: automaticky obnovovane predplatne (Stripe).' as vysledok;
