-- =============================================================================
--  100 - ZAKLADAJUCA CENA LEN PRVY ROK (10. 11. 2026, rozhodnutie Mareka)
--  Vloz do Supabase: SQL Editor -> New query -> Run. Spustit sa da opakovane.
-- =============================================================================
--  Doteraz: kod ZAKLADATEL plati 2 roky od prvej platby. Odteraz 1 rok.
--  Pri automatickom predplatnom (Stripe) je zakladajuca cena jednorazovy
--  kupon na prvu faktúru (stripe-checkout), obnova ide za beznu cenu.
--  Tu sa len skracuje lehota na opakovane pouzitie kodu (rucna platba).
--  Zatial nikto kod nezaplatil, nikoho sa zmena nedotkne.
-- =============================================================================

create or replace function public.zaloz_platbu(p_plan text, p_obdobie text, p_kod text default null)
returns public.platby
language plpgsql
security definer
set search_path = public
as $$
declare
    v_org_id  uuid;
    v_cena    public.cenove_plany;
    v_suma    numeric(10,2);
    v_mena    text;
    v_kod     text := upper(btrim(coalesce(p_kod, '')));
    v_prva    timestamptz;
    v_firiem  integer;
    v_riadok  public.platby;
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

    v_suma := v_cena.suma;
    v_mena := v_cena.mena;

    if v_kod <> '' then
        if v_kod <> 'ZAKLADATEL' then
            raise exception 'NEPLATNY_KOD';
        end if;
        if p_obdobie <> 'rok' or p_plan not in ('start', 'growth') then
            raise exception 'KOD_LEN_ROCNE';
        end if;

        -- serializuje sucasne pokusy o posledne miesto
        perform pg_advisory_xact_lock(hashtext('zakladajuci_kod'));

        select min(coalesce(spracovane_at, created_at)) into v_prva
        from public.platby
        where org_id = v_org_id and zlava_kod = 'ZAKLADATEL' and stav = 'zaplatena';

        if v_prva is null then
            select count(distinct org_id) into v_firiem
            from public.platby
            where zlava_kod = 'ZAKLADATEL' and stav = 'zaplatena';
            if v_firiem >= 30 then
                raise exception 'KOD_VYCERPANY';
            end if;
        elsif v_prva < now() - interval '1 year' then
            raise exception 'KOD_SKONCIL';
        end if;

        select z.suma, z.mena into v_suma, v_mena
        from public.zakladajuce_ceny z where z.plan = p_plan;
    end if;

    insert into public.platby (org_id, plan, obdobie, suma, mena, zlava_kod)
    values (v_org_id, p_plan, p_obdobie, v_suma, v_mena, nullif(v_kod, ''))
    returning * into v_riadok;

    return v_riadok;
end;
$$;

revoke all on function public.zaloz_platbu(text, text, text) from public, anon;
grant execute on function public.zaloz_platbu(text, text, text) to authenticated;

select 'Migracia 100 hotova: zakladajuca cena len prvy rok.' as vysledok;
