-- 104: Pilot — pozvanka na plan zadarmo na urcity cas (11. 11. 2026).
-- Marek posle firme osobny e-mail s odkazom predtendrom.sk/pilot?t=<token>.
-- Klik zapne plan (Growth) na 90 dni bez karty a bez automatickej obnovy.
-- 7 dni pred koncom pride bezna pripomienka (pripomienky_obnovy), potom sa
-- pristup zatvori a firma si moze predplatne kupit (zakladajuca cena).

create table if not exists public.pilot_pozvanky (
    token         uuid primary key default gen_random_uuid(),
    org_id        uuid not null references public.organizations(id) on delete cascade,
    plan          text not null default 'growth' check (plan in ('start', 'growth')),
    dni           int  not null default 90 check (dni between 7 and 180),
    platna_do     timestamptz not null default now() + interval '30 days',
    vytvorena_at  timestamptz not null default now(),
    prijata_at    timestamptz,
    koniec        timestamptz
);
alter table public.pilot_pozvanky enable row level security;
revoke all on public.pilot_pozvanky from public, anon, authenticated;

-- Vytvori pozvanku pre firmu podla ICO (len service_role, pouziva posli_osobny_email.py).
create or replace function public.vytvor_pilot(p_ico text, p_dni int default 90, p_plan text default 'growth')
returns uuid
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_org uuid;
    v_token uuid;
begin
    select id into v_org from public.organizations
     where ltrim(ico, '0') = ltrim(coalesce(p_ico, ''), '0') limit 1;
    if v_org is null then
        raise exception 'Firma s ICO % nema ucet.', p_ico;
    end if;
    -- jedna platna neprijata pozvanka na firmu: ak uz je, vrati ju
    select token into v_token from public.pilot_pozvanky
     where org_id = v_org and prijata_at is null and platna_do > now()
     order by vytvorena_at desc limit 1;
    if v_token is null then
        insert into public.pilot_pozvanky (org_id, plan, dni)
        values (v_org, coalesce(p_plan, 'growth'), coalesce(p_dni, 90))
        returning token into v_token;
    end if;
    return v_token;
end;
$$;
revoke all on function public.vytvor_pilot(text, int, text) from public, anon, authenticated;
grant execute on function public.vytvor_pilot(text, int, text) to service_role;

-- Prijatie pozvanky (verejne, chrani ho tajny token). Nikdy neznizi platny plan.
create or replace function public.prijmi_pilot(p_token uuid)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    r  public.pilot_pozvanky%rowtype;
    s  public.subscriptions%rowtype;
    v_nazov  text;
    v_koniec timestamptz;
    v_ma     boolean;
begin
    select * into r from public.pilot_pozvanky where token = p_token for update;
    if not found then
        return jsonb_build_object('ok', false, 'chyba', 'nezname');
    end if;
    select nazov into v_nazov from public.organizations where id = r.org_id;
    if r.prijata_at is not null then
        return jsonb_build_object('ok', true, 'uz_prijata', true, 'firma', v_nazov,
                                  'plan', r.plan, 'koniec', r.koniec);
    end if;
    if r.platna_do < now() then
        return jsonb_build_object('ok', false, 'chyba', 'expirovana');
    end if;

    select * into s from public.subscriptions where org_id = r.org_id for update;
    v_ma := found;
    if v_ma and s.stav = 'aktivne' and s.plan in ('growth', 'team', 'admin')
       and (s.obdobie_konci is null or s.obdobie_konci >= now() + make_interval(days => r.dni)) then
        v_koniec := s.obdobie_konci;          -- uz ma rovnaky alebo lepsi plan dlhsie
    else
        v_koniec := greatest(now(), case when v_ma and s.stav = 'aktivne' and s.plan = r.plan
                                         then coalesce(s.obdobie_konci, now()) else now() end)
                    + make_interval(days => r.dni);
        if v_ma then
            update public.subscriptions
               set plan = r.plan, stav = 'aktivne', obdobie_konci = v_koniec,
                   auto_obnova = false, updated_at = now()
             where org_id = r.org_id;
        else
            insert into public.subscriptions (org_id, stav, plan, trial_konci, obdobie_konci)
            values (r.org_id, 'aktivne', r.plan, now(), v_koniec);
        end if;
    end if;

    update public.pilot_pozvanky set prijata_at = now(), koniec = v_koniec where token = p_token;
    insert into public.events (org_id, user_id, typ, detail)
    values (r.org_id, auth.uid(), 'pilot_prijaty',
            jsonb_build_object('plan', r.plan, 'dni', r.dni, 'koniec', v_koniec));
    return jsonb_build_object('ok', true, 'uz_prijata', false, 'firma', v_nazov,
                              'plan', r.plan, 'koniec', v_koniec);
end;
$$;
revoke all on function public.prijmi_pilot(uuid) from public;
grant execute on function public.prijmi_pilot(uuid) to anon, authenticated;

-- Prehlad pre spravu (Marek / Claude): kto pozvanku prijal.
create or replace function public.pilot_prehlad()
returns table (firma text, ico text, plan text, vytvorena_at timestamptz, prijata_at timestamptz, koniec timestamptz)
language sql
stable
security definer
set search_path = ''
as $$
    select o.nazov, o.ico, p.plan, p.vytvorena_at, p.prijata_at, p.koniec
      from public.pilot_pozvanky p join public.organizations o on o.id = p.org_id
     order by p.vytvorena_at desc;
$$;
revoke all on function public.pilot_prehlad() from public, anon, authenticated;
grant execute on function public.pilot_prehlad() to service_role;

select 'Migracia 104 hotova: pilot_pozvanky, vytvor_pilot(), prijmi_pilot().' as vysledok;
