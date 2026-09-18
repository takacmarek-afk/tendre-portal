-- =============================================================================
--  PLATBY: TrustPay/finby integracia
--  Vloz do Supabase: SQL Editor -> New query -> Run. Spustit sa da opakovane.
--  Spustaj PO 08_zadarmo.sql (a teda aj po 06_plany.sql).
-- =============================================================================
--
--  DOVOD A TVAR RIESENIA
--  Ceny na cenniku su tri urovne: Start (34 EUR/mes), Growth (89 EUR/mes),
--  Team (kontakt mailom, nie samoobsluzny checkout - zostava tak). Suma sa
--  NIKDY neberie od klienta (fronend by mohol poslat hocico) - pocita sa
--  tu, v `cenove_plany`, a Edge Function ju len precita.
--
--  Kazdy pokus o platbu ma vlastny nahodny, neuhadnutelny `reference`
--  (UUID), ktory je zaroven MerchantReference pre finby. Notifikacia sa
--  teda paruje spat na presne tento riadok - nie na org_id priamo - takze
--  ani odchytenie/zopakovanie starej notifikacie nedokaze zmenit cudziu
--  organizaciu. Spracovanie je idempotentne (`stav` sa kontroluje pred
--  zapisom), takze opakovana notifikacia (finby vie poslat viackrat) sa
--  aplikuje len raz.
--
--  PLAN 'admin' uz existoval (04_admin.sql), ale povodny check v
--  06_plany.sql ho nedovolil - ak by niekto 04_admin.sql spustil znova
--  PO 06_plany.sql, spadol by na constraint violation. Opravene tu.
-- =============================================================================

-- ── 1. Cenove plany (jeden zdroj pravdy pre sumy) ────────────────────────
create table if not exists public.cenove_plany (
    plan        text not null,
    obdobie     text not null check (obdobie in ('mesiac', 'rok')),
    suma        numeric(10,2) not null,
    mena        text not null default 'EUR',
    primary key (plan, obdobie)
);

insert into public.cenove_plany (plan, obdobie, suma) values
    ('start',  'mesiac', 34.00),
    ('start',  'rok',    340.00),
    ('growth', 'mesiac', 89.00),
    ('growth', 'rok',    890.00)
on conflict (plan, obdobie) do update set suma = excluded.suma;

alter table public.cenove_plany enable row level security;

drop policy if exists cenove_plany_select on public.cenove_plany;
create policy cenove_plany_select on public.cenove_plany
    for select to authenticated
    using (true);
-- Zapis len cez migraciu/service_role - ziadna insert/update politika.


-- ── 2. Oprava plan-check (doplnene 'growth', 'team', 'admin') ────────────
alter table public.subscriptions drop constraint if exists subscriptions_plan_check;
alter table public.subscriptions add constraint subscriptions_plan_check
    check (plan in ('trial', 'start', 'growth', 'team', 'pro', 'admin'));
-- 'pro' zostava kvoli spatnej kompatibilite (ma_pro() ho stale pouziva
-- pre trial/otvorene obdobie), noveho platiaceho uz nedostane priradene.


-- ── 3. Zaznam kazdeho pokusu o platbu ─────────────────────────────────────
create table if not exists public.platby (
    reference          uuid primary key default gen_random_uuid(),
    org_id             uuid not null references public.organizations(id) on delete cascade,
    plan               text not null check (plan in ('start', 'growth')),
    obdobie            text not null check (obdobie in ('mesiac', 'rok')),
    suma               numeric(10,2) not null,
    mena               text not null default 'EUR',
    stav               text not null default 'vytvorena'
                         check (stav in ('vytvorena', 'zaplatena', 'zamietnuta')),
    payment_request_id text,
    gateway_url        text,
    trustpay_status    text,
    created_at         timestamptz not null default now(),
    spracovane_at      timestamptz
);

create index if not exists ix_platby_org on public.platby(org_id);

alter table public.platby enable row level security;

drop policy if exists platby_select on public.platby;
create policy platby_select on public.platby
    for select to authenticated
    using (org_id in (select org_id from public.memberships where user_id = auth.uid()));
-- Ziadna insert/update politika pre klienta - vsetok zapis ide cez
-- SECURITY DEFINER funkcie nizsie (volane z Edge Functions so service_role).


-- ── 4. Zalozenie pokusu o platbu (vola trustpay-initiate) ────────────────
-- Vracia cely riadok, aby Edge Function nemusela robit dalsi dopyt.
create or replace function public.zaloz_platbu(p_plan text, p_obdobie text)
returns public.platby
language plpgsql
security definer
set search_path = public
as $$
declare
    v_org_id uuid;
    v_cena   public.cenove_plany;
    v_riadok public.platby;
begin
    if auth.uid() is null then
        raise exception 'NEPRIHLASENY';
    end if;

    select org_id into v_org_id
    from public.memberships
    where user_id = auth.uid() and rola in ('owner', 'admin')
    limit 1;

    if v_org_id is null then
        raise exception 'BEZ_OPRAVNENIA';
    end if;

    select * into v_cena
    from public.cenove_plany
    where plan = p_plan and obdobie = p_obdobie;

    if v_cena is null then
        raise exception 'NEZNAMY_PLAN';
    end if;

    insert into public.platby (org_id, plan, obdobie, suma, mena)
    values (v_org_id, p_plan, p_obdobie, v_cena.suma, v_cena.mena)
    returning * into v_riadok;

    return v_riadok;
end;
$$;

grant execute on function public.zaloz_platbu(text, text) to authenticated;
-- Ziadny grant pre anon - platit vie len prihlaseny clen firmy.


-- ── 5. Doplnenie GatewayUrl/PaymentRequestId po volani finby API ─────────
-- Vola trustpay-initiate service_role kluc, hned po tom, co dostane
-- odpoved od finby. Bez tejto funkcie by service_role musel mat priamy
-- UPDATE pristup - takto zostava aj on obmedzeny na presne tento ucel.
create or replace function public.doplnit_platbu(
    p_reference uuid, p_payment_request_id text, p_gateway_url text
) returns void
language sql
security definer
set search_path = public
as $$
    update public.platby
       set payment_request_id = p_payment_request_id,
           gateway_url = p_gateway_url
     where reference = p_reference
       and stav = 'vytvorena';
$$;

revoke all on function public.doplnit_platbu(uuid, text, text) from public, authenticated, anon;
grant execute on function public.doplnit_platbu(uuid, text, text) to service_role;


-- ── 6. Spracovanie notifikacie (vola trustpay-notify PO overeni podpisu) ──
-- Idempotentne: ak uz raz stav != 'vytvorena', nic sa nemeni. Predlzenie
-- obdobia je `greatest()` od existujuceho konca, nie od `now()` - platba
-- pred koncom predchadzajuceho obdobia teda predlzi, nie skráti.
create or replace function public.spracuj_platbu_trustpay(
    p_reference uuid, p_stav text, p_trustpay_status text
) returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_platba  public.platby;
    v_interval interval;
begin
    select * into v_platba from public.platby where reference = p_reference for update;

    if v_platba is null then
        return jsonb_build_object('ok', false, 'kod', 'NEZNAMA_REFERENCIA');
    end if;

    if v_platba.stav <> 'vytvorena' then
        -- uz spracovane (opakovana notifikacia) - hlas uspech, nerob nic
        return jsonb_build_object('ok', true, 'kod', 'UZ_SPRACOVANE');
    end if;

    update public.platby
       set stav = p_stav, trustpay_status = p_trustpay_status, spracovane_at = now()
     where reference = p_reference;

    if p_stav <> 'zaplatena' then
        insert into public.events (org_id, typ, detail)
        values (v_platba.org_id, 'platba_zamietnuta',
                jsonb_build_object('reference', p_reference, 'trustpay_status', p_trustpay_status));
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

revoke all on function public.spracuj_platbu_trustpay(uuid, text, text) from public, authenticated, anon;
grant execute on function public.spracuj_platbu_trustpay(uuid, text, text) to service_role;


-- ── 7. Kontrola ────────────────────────────────────────────────────────
select tablename as tabulka_bez_rls
  from pg_tables
 where schemaname = 'public' and rowsecurity = false;

select 'Platby pripravene: cenove_plany, platby, zaloz/doplnit/spracuj_platbu. '
       'Ak vyssie nie je riadok tabulka_bez_rls, RLS je vsade zapnuta.' as vysledok;
