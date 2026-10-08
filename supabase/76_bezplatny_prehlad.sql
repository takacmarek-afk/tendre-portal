-- =============================================================================
--  76 - BEZPLATNY PREHLAD PO SKUSKE (vlna 92, 8. 10. 2026)
--  Vloz do Supabase: SQL Editor -> New query -> Run. Spustit sa da opakovane.
--  Predpoklad: migracie 68, 72, 74 a 75 uz bezali.
-- =============================================================================
--
--  Po skonceni skusky alebo zaplateneho obdobia sa pristup k datam zatvara
--  (RLS sa NEMENI). Tato migracia pridava len dve uzke cesty von:
--
--  1) bezplatny_prehlad()  - pre prihlaseneho pouzivatela BEZ aktivneho
--     pristupu: pocty a 3 ukazky pre 1 kraj + 1 sektor z jeho "Moj vyber".
--     Ukazky su bez sumy a bez mena dodavatela; sumy sa neposielaju vobec
--     (nie je to len rozmazanie v prehliadaci).
--  2) bezplatne_emaily() / oznac_bezplatny_email() - pre service_role:
--     kto ma dostat tyzdenny e-mail (len vlastnici/admini, najviac 8 tyzdnov
--     po skonceni, najviac raz za 6 dni).
-- =============================================================================

alter table public.subscriptions
    add column if not exists bezplatny_email_at timestamptz,
    -- Odhlasenie z tyzdenneho e-mailu (odpoved "Stop"; zatial nastavuje Marek
    -- v SQL: update public.subscriptions set bezplatny_email_stop = true where org_id = '...').
    add column if not exists bezplatny_email_stop boolean not null default false;

-- Spolocny vypocet obsahu (pre appku aj e-mail). Nikdy nie pre klienta.
create or replace function public._bezplatny_obsah(p_kraj text, p_sektor text)
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
    v_nastavene boolean := p_kraj is not null and p_sektor is not null;
    v_zmluvy    bigint;
    v_dotacie   bigint;
    v_dalsie    bigint;
    v_ukazky    jsonb;
begin
    select count(*) into v_zmluvy
      from public.opportunities o
     where o.effective_to between current_date and current_date + 365
       and (not v_nastavene or (o.kraj = p_kraj and o.sector = p_sektor));

    select count(*) into v_dotacie
      from public.subsidies s
     where not coalesce(s.vyplatene, false)
       and (s.okno_do is null or s.okno_do >= current_date)
       and (not v_nastavene
            or (s.kraj = p_kraj and (s.sektor_odhad is null or s.sektor_odhad = p_sektor)));

    if v_nastavene then
        select count(*) into v_dalsie
          from public.opportunities o
         where o.effective_to between current_date and current_date + 365
           and o.kraj = p_kraj
           and o.sector is distinct from p_sektor;

        select coalesce(jsonb_agg(jsonb_build_object(
                   'obstaravatel', left(coalesce(x.authority_name, ''), 120),
                   'predmet',      left(coalesce(x.subject, ''), 140),
                   'koniec',       to_char(x.effective_to, 'YYYY-MM')
               ) order by x.effective_to), '[]'::jsonb)
          into v_ukazky
          from (select o.authority_name, o.subject, o.effective_to
                  from public.opportunities o
                 where o.effective_to between current_date and current_date + 365
                   and o.kraj = p_kraj and o.sector = p_sektor
                 order by o.effective_to, o.contract_id
                 limit 3) x;
    else
        v_dalsie := 0;
        v_ukazky := '[]'::jsonb;
    end if;

    return jsonb_build_object(
        'nastavene',     v_nastavene,
        'kraj',          p_kraj,
        'sektor',        p_sektor,
        'pocet_zmluv',   v_zmluvy,
        'pocet_dotacii', v_dotacie,
        'dalsie_v_kraji', v_dalsie,
        'ukazky',        v_ukazky
    );
end;
$$;

revoke all on function public._bezplatny_obsah(text, text) from public, anon, authenticated;

-- 1) Pre prihlaseneho pouzivatela ---------------------------------------------
create or replace function public.bezplatny_prehlad()
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
    v_kraj   text;
    v_sektor text;
begin
    if auth.uid() is null then
        return jsonb_build_object('bezplatny', false);
    end if;
    -- Kto ma plny pristup (skuska, zaplateny plan, Poradca ma svoj vlastny),
    -- bezplatny prehlad nepotrebuje.
    if public.ma_aktivny_pristup() then
        return jsonb_build_object('bezplatny', false);
    end if;
    -- Len ten, kto uz kedy mal organizaciu s predplatnym (skusku/plan).
    if not exists (select 1
                     from public.memberships m
                     join public.subscriptions s on s.org_id = m.org_id
                    where m.user_id = auth.uid()) then
        return jsonb_build_object('bezplatny', false);
    end if;

    select n.kraje[1], n.sektory[1] into v_kraj, v_sektor
      from public.nastavenia_pouzivatela n
     where n.user_id = auth.uid();

    return jsonb_build_object('bezplatny', true)
           || public._bezplatny_obsah(v_kraj, v_sektor);
end;
$$;

revoke all on function public.bezplatny_prehlad() from public, anon;
grant execute on function public.bezplatny_prehlad() to authenticated;

-- 2) Pre tyzdenny e-mail (service_role) ---------------------------------------
-- Koniec pristupu = neskorsi z trial_konci a obdobie_konci. E-mail ide len
-- vlastnikovi/adminovi organizacie, ktora uz nema aktivny pristup, najviac
-- 56 dni po jeho konci a najviac raz za 6 dni. Poradca sa vynecha (ma vlastny
-- pristup k dopytom).
create or replace function public.bezplatne_emaily()
returns table (org_id uuid, email text, obsah jsonb)
language sql
stable
security definer
set search_path = ''
as $$
    select s.org_id, u.email::text,
           public._bezplatny_obsah(n.kraje[1], n.sektory[1])
      from public.subscriptions s
      join public.memberships m on m.org_id = s.org_id and m.rola in ('owner', 'admin')
      join auth.users u on u.id = m.user_id
      left join public.nastavenia_pouzivatela n on n.user_id = m.user_id
     where coalesce(s.plan, '') <> 'poradca'
       and not public._predplatne_aktivne(s.stav, s.trial_konci, s.obdobie_konci)
       and greatest(s.trial_konci, coalesce(s.obdobie_konci, s.trial_konci))
               between now() - interval '56 days' and now()
       and (s.bezplatny_email_at is null or s.bezplatny_email_at < now() - interval '6 days')
       and not s.bezplatny_email_stop
       and u.email is not null;
$$;

create or replace function public.oznac_bezplatny_email(p_org_id uuid)
returns void
language sql
security definer
set search_path = ''
as $$
    update public.subscriptions set bezplatny_email_at = now() where org_id = p_org_id;
$$;

revoke all on function public.bezplatne_emaily() from public, anon, authenticated;
revoke all on function public.oznac_bezplatny_email(uuid) from public, anon, authenticated;
grant execute on function public.bezplatne_emaily() to service_role;
grant execute on function public.oznac_bezplatny_email(uuid) to service_role;

select 'Migracia 76 hotova: bezplatny prehlad po skuske a tyzdenny e-mail.' as vysledok;
