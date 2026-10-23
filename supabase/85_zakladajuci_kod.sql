-- =============================================================================
--  85 - KOD "ZAKLADATEL" PRI ROCNEJ PLATBE (plan predaja, sekcia 2; 23. 10. 2026)
--  Vloz do Supabase: SQL Editor -> New query -> Run. Spustit sa da opakovane.
-- =============================================================================
--
--  Zakladajuca ponuka z cennika (Start 240 €, Growth 590 € rocne, cena plati
--  2 roky, prvych 30 firiem) sa doteraz vybavovala e-mailom a fakturou.
--  Teraz si ju zakaznik uplatni sam: pri rocnej platbe v appke zada kod
--  ZAKLADATEL. Cenu urci VZDY databaza (nikdy klient ani Edge Function):
--    - len rocne obdobie a plany start/growth,
--    - najviac 30 ROZNYCH firiem so zaplatenou platbou s kodom,
--    - firma, ktora kod uz zaplatila, ho smie pouzit znova do 2 rokov od
--      prvej zaplatenej platby s kodom (obnova za rovnaku cenu) — aj ked je 30 plnych.
--  zaloz_platbu() dostava novy nepovinny parameter p_kod. Stara 2-argumentova
--  verzia sa zrusi, inak by PostgREST pri volani bez p_kod nevedel, ktoru
--  funkciu zavolat (PGRST203).
-- =============================================================================

create table if not exists public.zakladajuce_ceny (
    plan    text primary key check (plan in ('start', 'growth')),
    suma    numeric(10,2) not null,
    mena    text not null default 'EUR'
);
insert into public.zakladajuce_ceny (plan, suma) values ('start', 240.00), ('growth', 590.00)
on conflict (plan) do update set suma = excluded.suma;

alter table public.zakladajuce_ceny enable row level security;
revoke all on table public.zakladajuce_ceny from anon, authenticated;

alter table public.platby add column if not exists zlava_kod text;

drop function if exists public.zaloz_platbu(text, text);

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
        elsif v_prva < now() - interval '2 years' then
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

-- Pocet volnych zakladajucich miest pre cennik (verejne, len cislo)
create or replace function public.zakladajuce_miesta()
returns integer
language sql
stable
security definer
set search_path = ''
as $$
    select greatest(0, 30 - (select count(distinct org_id)::int from public.platby
                             where zlava_kod = 'ZAKLADATEL' and stav = 'zaplatena'));
$$;
revoke all on function public.zakladajuce_miesta() from public;
grant execute on function public.zakladajuce_miesta() to anon, authenticated;

select 'Migracia 85 hotova: kod ZAKLADATEL pri rocnej platbe (Start 240 €, Growth 590 €, prvych 30 firiem, 2 roky).' as vysledok;
