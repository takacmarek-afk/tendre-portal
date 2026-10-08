-- =============================================================================
--  75 - OPRAVY ZO ZAVERECNEHO AUDITU (vlna 89, 8. 10. 2026)
--  Vloz do Supabase: SQL Editor -> New query -> Run. Spustit sa da opakovane.
-- =============================================================================
--
--  1) start_skryte_pocty(): zostala pomala (volala start_kraj_ok()/start_sektor_ok()
--     pre kazdy riadok, odmerane 4,7 s pre Start pouzivatela). Migracia 72
--     opravila len politiky. Teraz sa vyber nacita raz do poli. Vysledok je
--     rovnaky (overene testom tests/test_audit_89.sql).
--  2) navstevy: strop jedneho riadku bol az ~3,5 kB a 20 000 riadkov za hodinu
--     = ~70 MB/hod. cez verejny anon kluc. Zuzene dlzky, strop 5 000/hod.,
--     a z referreru sa pred ulozenim odstrani query a fragment (mohli byt
--     v nom tokeny z odkazov).
--  3) odber: org_id si klient nastavoval sam (aj na cudziu organizaciu).
--     Teraz musi byt NULL alebo organizacia, ktorej je clenom.
--  4) prvych_100_dni_suhrn(): nazov dlhsi ako 80 znakov sa ignoruje (bez stropu
--     sa dal verejne volat s megabajtovym retazcom).
--  5) spracuj_platbu_stripe(): platba za Start/Growth uz neprepise plan Team,
--     Poradca ani admin (pripomienka obnovy posiela odkaz na platbu aj im);
--     ak organizacia nema riadok predplatneho, funkcia zlyha nahlas namiesto
--     ticheho "AKTIVOVANE" bez aktivacie.
--  Ostatne nalezy auditu (Start obchadza limit cez contracts, dopyty cez
--  poradcu zadarmo, zmena planu pri platbe) su obchodne rozhodnutia - pozri
--  claude/predtendrom-audit-2026-10-08-zaverecny.md v projekte.
-- =============================================================================

-- 1) -----------------------------------------------------------------------
create or replace function public.start_skryte_pocty()
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
    k text[];
    s text[];
    p bigint;
    d bigint;
begin
    if not public.je_start_obmedzeny() then
        return jsonb_build_object('start', false, 'prilezitosti', 0, 'dotacie', 0);
    end if;

    select n.kraje[1:2], n.sektory[1:2] into k, s
      from public.nastavenia_pouzivatela n
     where n.user_id = auth.uid();
    k := coalesce(k, '{}');
    s := coalesce(s, '{}');

    -- Rovnake pravidlo ako start_kraj_ok() + start_sektor_ok(): riadok je
    -- viditelny, len ked kraj AJ sektor patria do vyberu (dotacie: aj sektor NULL).
    select count(*) into p
      from public.opportunities o
     where (o.effective_to is null or o.effective_to >= current_date)
       and not (coalesce(o.kraj = any (k), false) and coalesce(o.sector = any (s), false));

    select count(*) into d
      from public.subsidies x
     where not (coalesce(x.kraj = any (k), false)
                and (x.sektor_odhad is null or coalesce(x.sektor_odhad = any (s), false)));

    return jsonb_build_object('start', true, 'prilezitosti', p, 'dotacie', d);
end;
$$;

revoke all on function public.start_skryte_pocty() from public, anon;
grant execute on function public.start_skryte_pocty() to authenticated;

-- 2) -----------------------------------------------------------------------
alter table public.navstevy drop constraint if exists navstevy_dlzky;
alter table public.navstevy add constraint navstevy_dlzky check (
    char_length(cesta) <= 300
    and (referrer     is null or char_length(referrer)     <= 300)
    and (session_id   is null or char_length(session_id)   <= 80)
    and (utm_source   is null or char_length(utm_source)   <= 100)
    and (utm_medium   is null or char_length(utm_medium)   <= 100)
    and (utm_campaign is null or char_length(utm_campaign) <= 150)
) not valid;

drop trigger if exists trg_strop_navstevy on public.navstevy;
create trigger trg_strop_navstevy before insert on public.navstevy
    for each row execute function public._strop_vkladov(5000);

create or replace function public._navstevy_orez_referrer()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
    if new.referrer is not null then
        new.referrer := split_part(split_part(new.referrer, '?', 1), '#', 1);
    end if;
    return new;
end;
$$;

drop trigger if exists trg_navstevy_referrer on public.navstevy;
create trigger trg_navstevy_referrer before insert on public.navstevy
    for each row execute function public._navstevy_orez_referrer();

-- 3) -----------------------------------------------------------------------
drop policy if exists odber_insert on public.odber;
create policy odber_insert on public.odber
    for insert to authenticated
    with check (
        user_id = auth.uid()
        and (email is null or lower(email) = lower(coalesce(auth.jwt() ->> 'email', '')))
        and (frekvencia is distinct from 'denne' or public.ma_pro())
        and (webhook_url is null or public.ma_pro())
        and (public.ma_pro() or (sektor is not null and kraj is not null))
        and (org_id is null or org_id in (select public.moje_org_ids()))
    );

drop policy if exists odber_update on public.odber;
create policy odber_update on public.odber
    for update to authenticated
    using (user_id = auth.uid())
    with check (
        user_id = auth.uid()
        and (email is null or lower(email) = lower(coalesce(auth.jwt() ->> 'email', '')))
        and (frekvencia is distinct from 'denne' or public.ma_pro())
        and (webhook_url is null or public.ma_pro())
        and (public.ma_pro() or (sektor is not null and kraj is not null))
        and (org_id is null or org_id in (select public.moje_org_ids()))
    );

-- 4) -----------------------------------------------------------------------
create or replace function public.prvych_100_dni_suhrn(p_nazov text, p_kraj text default null)
returns table(
    najdena             boolean,
    ma_data             boolean,
    kraj                text,
    okres               text,
    pocet_konciacich    integer,
    objem_konciacich    numeric,
    pocet_dotacii_bezi  integer,
    objem_dotacii_bezi  numeric
)
language sql
stable
security definer
set search_path = ''
as $$
    with n as (
        select case when char_length(coalesce(p_nazov, '')) <= 80
                    then lower(trim(coalesce(p_nazov, ''))) else '' end as core,
               case when char_length(coalesce(p_kraj, '')) <= 80
                    then nullif(trim(coalesce(p_kraj, '')), '') else null end as kraj_filter
    ),
    op as (
        select o.kraj, o.price_total, o.effective_to
          from public.opportunities o, n
         where n.core <> ''
           and public._je_obec_nazov(o.authority_name)
           and lower(public._obec_core_nazov(o.authority_name)) = n.core
           and (n.kraj_filter is null or lower(o.kraj) = lower(n.kraj_filter))
    ),
    su as (
        select s.kraj, s.suma, s.okno_do, s.vyplatene
          from public.subsidies s, n
         where n.core <> ''
           and public._je_obec_nazov(s.prijimatel)
           and lower(public._obec_core_nazov(s.prijimatel)) = n.core
           and (n.kraj_filter is null or lower(s.kraj) = lower(n.kraj_filter))
    ),
    reg as (
        select r.kraj, r.okres
          from public.obce_register r, n
         where n.core <> ''
           and lower(r.nazov) = n.core
           and (n.kraj_filter is null or lower(r.kraj) = lower(n.kraj_filter))
         order by r.kraj, r.okres
         limit 1
    ),
    zm as (
        select count(*)::int as pocet, coalesce(sum(price_total), 0) as objem
          from op
         where effective_to between current_date and (current_date + interval '365 days')
    ),
    dt as (
        select count(*)::int as pocet, coalesce(sum(suma), 0) as objem
          from su
         where (okno_do is null or okno_do >= current_date)
           and not coalesce(vyplatene, false)
    )
    select
        (exists(select 1 from op) or exists(select 1 from su) or exists(select 1 from reg)) as najdena,
        (exists(select 1 from op) or exists(select 1 from su)) as ma_data,
        coalesce((select kraj from op where kraj is not null limit 1),
                 (select kraj from su where kraj is not null limit 1),
                 (select kraj from reg),
                 (select kraj_filter from n)) as kraj,
        (select okres from reg) as okres,
        zm.pocet, zm.objem,
        dt.pocet, dt.objem
    from zm, dt;
$$;

grant execute on function public.prvych_100_dni_suhrn(text, text) to anon, authenticated;

-- 5) -----------------------------------------------------------------------
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
    v_riadkov  integer;
begin
    select * into v_platba from public.platby where reference = p_reference for update;

    if v_platba is null then
        return jsonb_build_object('ok', false, 'kod', 'NEZNAMA_REFERENCIA');
    end if;

    if v_platba.stav <> 'vytvorena' then
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

    -- Plany Team, Poradca a admin sa platbou za Start/Growth neprepisu (obdobie
    -- sa predlzi, plan ostava) - pripomienka obnovy posiela odkaz na platbu
    -- aj tymto zakaznikom a bez toho by sa potichu znizili.
    update public.subscriptions
       set stav = 'aktivne',
           plan = case when plan in ('team', 'poradca', 'admin') then plan else v_platba.plan end,
           obdobie_konci = greatest(coalesce(obdobie_konci, now()), now()) + v_interval,
           updated_at = now()
     where org_id = v_platba.org_id;
    get diagnostics v_riadkov = row_count;

    if v_riadkov = 0 then
        -- Zlyhanie nahlas: webhook dostane 5xx, Stripe opakuje a zaplatena platba
        -- neostane bez aktivacie. (Cela transakcia sa vracia spat.)
        raise exception 'Organizacia % nema riadok predplatneho, platba % sa nedala aktivovat.',
            v_platba.org_id, p_reference;
    end if;

    insert into public.events (org_id, typ, detail)
    values (v_platba.org_id, 'platba_prijata',
            jsonb_build_object('reference', p_reference, 'plan', v_platba.plan,
                                'obdobie', v_platba.obdobie, 'suma', v_platba.suma));

    return jsonb_build_object('ok', true, 'kod', 'AKTIVOVANE');
end;
$$;

revoke all on function public.spracuj_platbu_stripe(uuid, text, text) from public, authenticated, anon;
grant execute on function public.spracuj_platbu_stripe(uuid, text, text) to service_role;

select 'Migracia 75 hotova: opravy z auditu 8. 10. 2026.' as vysledok;
