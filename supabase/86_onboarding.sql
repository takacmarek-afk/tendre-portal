-- =============================================================================
--  86 - UVITACIE E-MAILY PO REGISTRACII (plan predaja, sekcia 6; 23. 10. 2026)
--  Vloz do Supabase: SQL Editor -> New query -> Run. Spustit sa da opakovane.
-- =============================================================================
--
--  Pat e-mailov (den 0, 1, 3, 7 a 2 dni pred koncom skusky), kazdy s jednym
--  navodom a jednym krokom. Posiela pipeline/posli_onboarding.py cez Resend
--  (pouzivatel sa sam zaregistroval). Len pouzivatelia zaregistrovani PO
--  spusteni tejto migracie (rozhodnutie Mareka 23. 10. 2026).
--
--  onboarding_kandidati() vrati pre kazdeho noveho pouzivatela vsetko, co
--  skript potrebuje na rozhodnutie a text. Rozhoduje Python (testovatelne).
--  Odhlasenie: odkaz s tokenom -> /odhlasenie-tipov -> onboarding_odhlas().
-- =============================================================================

create table if not exists public.onboarding_nastavenie (
    id            boolean primary key default true check (id),
    spustene_od   timestamptz not null default now()
);
insert into public.onboarding_nastavenie (id) values (true) on conflict (id) do nothing;

create table if not exists public.onboarding_pouzivatelia (
    user_id       uuid primary key references auth.users(id) on delete cascade,
    token         uuid not null default gen_random_uuid() unique,
    zaradeny_at   timestamptz not null default now(),
    odhlasene_at  timestamptz
);

create table if not exists public.onboarding_odoslane (
    id            bigserial primary key,
    user_id       uuid not null references auth.users(id) on delete cascade,
    krok          smallint not null check (krok in (0, 1, 3, 7, 12)),
    stav          text not null default 'odoslane' check (stav in ('odoslane', 'vynechane')),
    odoslane_at   timestamptz not null default now(),
    unique (user_id, krok)
);

alter table public.onboarding_nastavenie   enable row level security;
alter table public.onboarding_pouzivatelia enable row level security;
alter table public.onboarding_odoslane     enable row level security;
revoke all on table public.onboarding_nastavenie   from anon, authenticated;
revoke all on table public.onboarding_pouzivatelia from anon, authenticated;
revoke all on table public.onboarding_odoslane     from anon, authenticated;
revoke all on sequence public.onboarding_odoslane_id_seq from anon, authenticated;

-- Kandidati: novi pouzivatelia (od spustenia), ktori sa neodhlasili. Funkcia
-- najprv zaradi novych (token na odhlasenie), potom vrati ich stav.
create or replace function public.onboarding_kandidati()
returns table (
    user_id         uuid,
    email           text,
    token           uuid,
    registrovany_at timestamptz,
    org_id          uuid,
    plan            text,
    stav            text,
    trial_konci     timestamptz,
    zaplatene       boolean,
    kraj            text,
    sektor          text,
    ma_vyber        boolean,
    pocet_zmluv     bigint,
    najblizsia      jsonb,
    ma_sledovanie   boolean,
    odoslane        smallint[]
)
language plpgsql
security definer
set search_path = ''
as $$
#variable_conflict use_column
declare
    v_od timestamptz;
begin
    select n.spustene_od into v_od from public.onboarding_nastavenie n;

    insert into public.onboarding_pouzivatelia (user_id)
    select u.id
      from auth.users u
     where u.created_at >= v_od
       and u.email is not null
       and lower(u.email) not like '%@predtendrom.sk'
       and lower(u.email) <> 'takac.marek@gmail.com'
    on conflict on constraint onboarding_pouzivatelia_pkey do nothing;

    return query
    with ja as (
        select p.user_id, p.token, u.email::text as email, u.created_at
          from public.onboarding_pouzivatelia p
          join auth.users u on u.id = p.user_id
         where p.odhlasene_at is null
           and u.created_at > now() - interval '30 days'
    ),
    clen as (
        select distinct on (m.user_id) m.user_id, m.org_id
          from public.memberships m
         where m.user_id in (select ja.user_id from ja)
         order by m.user_id, m.created_at
    )
    select ja.user_id, ja.email, ja.token, ja.created_at,
           c.org_id, s.plan, s.stav, s.trial_konci,
           (s.org_id is not null and coalesce(s.plan, 'trial') not in ('trial')
            and public._predplatne_aktivne(s.stav, s.trial_konci, s.obdobie_konci)),
           n.kraje[1], n.sektory[1],
           (coalesce(cardinality(n.kraje), 0) > 0 and coalesce(cardinality(n.sektory), 0) > 0),
           (select count(*) from public.opportunities o
             where o.effective_to between current_date and current_date + 365
               and o.kraj = any(n.kraje) and o.sector = any(n.sektory)),
           (select jsonb_build_object(
                       'urad',    left(coalesce(o.authority_name, ''), 120),
                       'predmet', left(coalesce(o.subject, ''), 140),
                       'koniec',  o.effective_to)
              from public.opportunities o
             where o.effective_to between current_date + 30 and current_date + 365
               and o.kraj = any(n.kraje) and o.sector = any(n.sektory)
             order by o.effective_to, o.contract_id
             limit 1),
           exists (select 1 from public.moj_stav_prilezitosti x where x.org_id = c.org_id),
           coalesce((select array_agg(d.krok order by d.krok)
                       from public.onboarding_odoslane d where d.user_id = ja.user_id),
                    '{}'::smallint[])
      from ja
      left join clen c on c.user_id = ja.user_id
      left join public.subscriptions s on s.org_id = c.org_id
      left join public.nastavenia_pouzivatela n on n.user_id = ja.user_id;
end;
$$;

create or replace function public.onboarding_oznac(p_user_id uuid, p_krok smallint, p_stav text default 'odoslane')
returns void
language sql
security definer
set search_path = ''
as $$
    insert into public.onboarding_odoslane (user_id, krok, stav)
    values (p_user_id, p_krok, p_stav)
    on conflict (user_id, krok) do nothing;
$$;

revoke all on function public.onboarding_kandidati() from public, anon, authenticated;
revoke all on function public.onboarding_oznac(uuid, smallint, text) from public, anon, authenticated;
grant execute on function public.onboarding_kandidati() to service_role;
grant execute on function public.onboarding_oznac(uuid, smallint, text) to service_role;

-- Odhlasenie (vola /odhlasenie-tipov po kliknuti na tlacidlo, aj bez prihlasenia)
create or replace function public.onboarding_odhlas(p_token text)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_id uuid;
begin
    if p_token is null or p_token !~ '^[0-9a-fA-F-]{36}$' then
        return jsonb_build_object('ok', false);
    end if;
    update public.onboarding_pouzivatelia
       set odhlasene_at = coalesce(odhlasene_at, now())
     where token = p_token::uuid
    returning user_id into v_id;
    return jsonb_build_object('ok', v_id is not null);
end;
$$;

revoke all on function public.onboarding_odhlas(text) from public;
grant execute on function public.onboarding_odhlas(text) to anon, authenticated;

select 'Migracia 86 hotova: uvitacie e-maily od ' || to_char((select spustene_od from public.onboarding_nastavenie), 'DD. MM. YYYY HH24:MI') || '.' as vysledok;
