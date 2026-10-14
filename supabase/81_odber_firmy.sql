-- =============================================================================
--  81 - ODBER TYZDENNEHO PREHLADU PRE FIRMY (marketingovy motor, cast 1; 14.10.2026)
--  Vloz do Supabase: SQL Editor -> New query -> Run. Spustit sa da opakovane.
--
--  Navstevnik uvodnej stranky si pod ukazkou 3 zmluv vyziada tyzdenny prehlad
--  konciacich zmluv pre svoj odbor a kraj. Prihlasenie ide LEN cez Edge Function
--  verejny-formular (typ "odber_firmy": Turnstile + limit na IP), suhlas sa
--  potvrdzuje odkazom v e-maile (double opt-in). Po potvrdeni posiela
--  GitHub Action (pipeline/posli_odber_firmy.py) 4 e-maily za 3 tyzdne a potom
--  tyzdenny prehlad (najviac 26 tyzdnov). Odhlasenie jednym kliknutim; riadok
--  s odhlasenim zostava ako zoznam odhlasenych (nikdy znova neoslovit).
--
--  Tabulka je zatvorena: anon ani prihlaseny pouzivatel nemaju ziadne pravo.
--  Funkcie pre klienta (potvrd_odber_firmy, odhlas_odber_firmy) vracaju len
--  ok/nie a nikdy e-mail ani ine udaje.
-- =============================================================================

create table if not exists public.odber_firmy (
    id                    bigserial primary key,
    email                 text not null,
    sektor                text,
    kraj                  text,
    token                 uuid not null default gen_random_uuid(),
    potvrdeny             boolean not null default false,
    potvrdeny_at          timestamptz,
    suhlas_verzia         text not null default '2026-10-14',
    zdroj                 text,
    potvrdzovaci_email_at timestamptz,
    potvrdzovaci_pokusy   integer not null default 0,
    krok                  integer not null default 0,      -- kolko e-mailov prehladu uz odislo
    dalsi_email_at        timestamptz,
    posledny_email_at     timestamptz,
    odhlaseny_at          timestamptz,
    created_at            timestamptz not null default now(),
    constraint odber_firmy_dlzky check (
        char_length(email) <= 254
        and (sektor is null or char_length(sektor) <= 40)
        and (kraj   is null or char_length(kraj)   <= 80)
        and (zdroj  is null or char_length(zdroj)  <= 80)
    )
);

create unique index if not exists ux_odber_firmy_email on public.odber_firmy (lower(email));
create unique index if not exists ux_odber_firmy_token on public.odber_firmy (token);
create index if not exists ix_odber_firmy_dalsi
    on public.odber_firmy (dalsi_email_at) where potvrdeny and odhlaseny_at is null;

alter table public.odber_firmy enable row level security;
revoke all on table public.odber_firmy from anon, authenticated;
revoke all on sequence public.odber_firmy_id_seq from anon, authenticated;

comment on table public.odber_firmy is
    'Tyzdenny prehlad konciacich zmluv pre firmy (double opt-in). Len cez Edge Function a service_role; odhlaseni zostavaju ako zoznam "neoslovovat".';


-- 1) Prihlasenie (len service_role). Odpoved je VZDY rovnaka, nezistuje sa,
--    ci adresa uz v zozname je. Kto sa odhlasil a prihlasi sa znova, dava novy
--    suhlas: riadok sa resetuje a potvrdzuje sa odznova.
create or replace function public.prihlas_odber_firmy(
    p_email text, p_sektor text, p_kraj text, p_zdroj text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_email text := lower(trim(coalesce(p_email, '')));
begin
    if char_length(v_email) not between 5 and 254
       or v_email !~ '^[^@\s,;<>"]+@[^@\s,;<>"]+\.[A-Za-z]{2,}$' then
        return jsonb_build_object('ok', false, 'kod', 'EMAIL_NEPLATNY');
    end if;
    if coalesce(p_sektor, '') !~ '^[A-Z_]{3,40}$' then
        return jsonb_build_object('ok', false, 'kod', 'SEKTOR_NEPLATNY');
    end if;
    if char_length(coalesce(p_kraj, '')) > 80 or char_length(coalesce(p_zdroj, '')) > 80 then
        return jsonb_build_object('ok', false, 'kod', 'UDAJE_DLHE');
    end if;

    insert into public.odber_firmy (email, sektor, kraj, zdroj)
    values (v_email, p_sektor, nullif(trim(p_kraj), ''), nullif(trim(p_zdroj), ''))
    on conflict (lower(email)) do update
       set sektor = excluded.sektor,
           kraj = excluded.kraj,
           zdroj = excluded.zdroj,
           token = gen_random_uuid(),
           potvrdeny = false,
           potvrdeny_at = null,
           potvrdzovaci_email_at = null,
           potvrdzovaci_pokusy = 0,
           krok = 0,
           dalsi_email_at = null,
           posledny_email_at = null,
           odhlaseny_at = null,
           created_at = now()
     where public.odber_firmy.odhlaseny_at is not null;

    return jsonb_build_object('ok', true);
end;
$$;
revoke all on function public.prihlas_odber_firmy(text, text, text, text) from public, anon, authenticated;
grant execute on function public.prihlas_odber_firmy(text, text, text, text) to service_role;


-- 2) Zabratie potvrdzovacich e-mailov (rovnaky vzor ako zaber_potvrdenie_odberu):
--    najviac 3 pokusy, nie casteje nez raz za 10 minut, len do 3 dni od prihlasenia.
create or replace function public.zaber_potvrdenie_firmy(p_email text default null)
returns table (id bigint, email text, token uuid, sektor text, kraj text)
language plpgsql
security definer
set search_path = ''
as $$
begin
    return query
    update public.odber_firmy o
       set potvrdzovaci_email_at = now(),
           potvrdzovaci_pokusy   = o.potvrdzovaci_pokusy + 1
     where o.potvrdeny = false
       and o.odhlaseny_at is null
       and o.potvrdzovaci_pokusy < 3
       and o.created_at > now() - interval '3 days'
       and (o.potvrdzovaci_email_at is null
            or o.potvrdzovaci_email_at < now() - interval '10 minutes')
       and (p_email is null or lower(o.email) = lower(trim(p_email)))
    returning o.id, o.email, o.token, o.sektor, o.kraj;
end;
$$;
revoke all on function public.zaber_potvrdenie_firmy(text) from public, anon, authenticated;
grant execute on function public.zaber_potvrdenie_firmy(text) to service_role;

create or replace function public.vrat_potvrdenie_firmy(p_id bigint)
returns void
language sql
security definer
set search_path = ''
as $$
    update public.odber_firmy
       set potvrdzovaci_email_at = null,
           potvrdzovaci_pokusy   = greatest(potvrdzovaci_pokusy - 1, 0)
     where id = p_id and potvrdeny = false;
$$;
revoke all on function public.vrat_potvrdenie_firmy(bigint) from public, anon, authenticated;
grant execute on function public.vrat_potvrdenie_firmy(bigint) to service_role;


-- 3) Potvrdenie a odhlasenie odkazom z e-mailu (anon). Token je UUID v4.
--    Potvrdenie plati len do 7 dni od prihlasenia (potom treba novy suhlas).
--    Odhlasenie nikdy nemaze riadok: ostava ako zoznam odhlasenych.
create or replace function public.potvrd_odber_firmy(p_token uuid)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_n int;
begin
    update public.odber_firmy
       set potvrdeny = true,
           potvrdeny_at = coalesce(potvrdeny_at, now()),
           dalsi_email_at = case when potvrdeny then dalsi_email_at else now() end
     where token = p_token
       and odhlaseny_at is null
       and (potvrdeny or created_at > now() - interval '7 days');
    get diagnostics v_n = row_count;
    return v_n > 0;
end;
$$;
revoke all on function public.potvrd_odber_firmy(uuid) from public;
grant execute on function public.potvrd_odber_firmy(uuid) to anon, authenticated;

create or replace function public.odhlas_odber_firmy(p_token uuid)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_n int;
begin
    update public.odber_firmy
       set odhlaseny_at = coalesce(odhlaseny_at, now()),
           dalsi_email_at = null
     where token = p_token;
    get diagnostics v_n = row_count;
    return v_n > 0;
end;
$$;
revoke all on function public.odhlas_odber_firmy(uuid) from public;
grant execute on function public.odhlas_odber_firmy(uuid) to anon, authenticated;


-- 4) Vyber e-mailov na odoslanie (len service_role). Riadky sa zabera na 2 hodiny
--    (dalsi_email_at sa posunie), takze dva behy naraz nikomu nepoplu e-mail
--    dvakrat; ak odoslanie zlyha, riadok sa skusi znova po 2 hodinach.
create or replace function public.odber_firmy_na_odoslanie(p_max integer default 40, p_zaber boolean default true)
returns table (id bigint, email text, token uuid, sektor text, kraj text, krok integer)
language plpgsql
security definer
set search_path = ''
as $$
begin
    -- p_zaber = false (nasucho): len vypise, koho by sa tyka, nic nezabera ani nemeni
    if not coalesce(p_zaber, true) then
        return query
        select o.id, o.email, o.token, o.sektor, o.kraj, o.krok
          from public.odber_firmy o
         where o.potvrdeny and o.odhlaseny_at is null and o.dalsi_email_at is not null
           and o.dalsi_email_at <= now() and o.krok < 30
         order by o.dalsi_email_at
         limit greatest(least(coalesce(p_max, 40), 200), 1);
        return;
    end if;
    return query
    with c as (
        select o.id
          from public.odber_firmy o
         where o.potvrdeny
           and o.odhlaseny_at is null
           and o.dalsi_email_at is not null
           and o.dalsi_email_at <= now()
           and o.krok < 30
         order by o.dalsi_email_at
         limit greatest(least(coalesce(p_max, 40), 200), 1)
           for update skip locked
    )
    update public.odber_firmy o
       set dalsi_email_at = now() + interval '2 hours'
      from c
     where o.id = c.id
    returning o.id, o.email, o.token, o.sektor, o.kraj, o.krok;
end;
$$;
revoke all on function public.odber_firmy_na_odoslanie(integer, boolean) from public, anon, authenticated;
grant execute on function public.odber_firmy_na_odoslanie(integer, boolean) to service_role;

-- Po uspesnom odoslani: krok + termin dalsieho e-mailu
--   po 1. e-maile za 4 dni (2. e-mail = den 4), po 2. za 6 dni (den 10),
--   po 3. za 11 dni (den 21), potom raz za 7 dni; po 30. e-maile koniec.
create or replace function public.odber_firmy_oznac(p_id bigint, p_krok integer)
returns void
language sql
security definer
set search_path = ''
as $$
    update public.odber_firmy
       set krok = p_krok,
           posledny_email_at = now(),
           dalsi_email_at = case
               when p_krok >= 30 then null
               when p_krok = 1 then now() + interval '4 days'
               when p_krok = 2 then now() + interval '6 days'
               when p_krok = 3 then now() + interval '11 days'
               else now() + interval '7 days'
           end
     where id = p_id and odhlaseny_at is null;
$$;
revoke all on function public.odber_firmy_oznac(bigint, integer) from public, anon, authenticated;
grant execute on function public.odber_firmy_oznac(bigint, integer) to service_role;


-- 5) Tri zmluvy pre e-mail. p_posun striedavo posuva vyber (kazdy tyzden ine tri
--    zmluvy z toho isteho vyberu). Rovnake pravidla ako ukazka_koncich_zmluv (migr. 80).
create or replace function public.odber_firmy_zmluvy(p_sektor text, p_kraj text default null, p_posun integer default 0)
returns jsonb
language sql
stable
security definer
set search_path = public
as $$
with kandidati as (
    select o.contract_id, o.authority_name, o.subject, o.effective_to, o.price_total, o.odkaz,
           row_number() over (order by o.skore desc nulls last, o.effective_to) as rn
      from public.opportunities o
     where o.sector = p_sektor
       and o.sector <> 'DOTACIE_NFP'
       and (p_kraj is null or o.kraj = p_kraj)
       and o.effective_to between current_date + 30 and current_date + 365
       and o.authority_name is not null
       and o.subject is not null
),
pocet as (select count(*)::int as n from kandidati),
okno as (
    select case when n <= 3 then 0
                else (greatest(coalesce(p_posun, 0), 0) * 3) % (((n + 2) / 3) * 3) end as od
      from pocet
)
select jsonb_build_object(
    'celkom', (select n from pocet),
    'zoznam', coalesce((
        select jsonb_agg(jsonb_build_object(
                   'urad', k.authority_name,
                   'predmet', left(replace(k.subject, E'\n', ' '), 140),
                   'koniec', k.effective_to,
                   'cena', k.price_total,
                   'odkaz', coalesce(k.odkaz, 'https://www.crz.gov.sk/zmluva/' || k.contract_id || '/'))
               order by k.rn)
          from kandidati k, okno w
         where k.rn > w.od and k.rn <= w.od + 3), '[]'::jsonb)
);
$$;
revoke all on function public.odber_firmy_zmluvy(text, text, integer) from public, anon, authenticated;
grant execute on function public.odber_firmy_zmluvy(text, text, integer) to service_role;


-- 6) Upratovanie (volat z retencia_udajov): nepotvrdene po 3 dnoch preč; po skonceni
--    prehladov (30 e-mailov) alebo po 14 mesiacoch bez e-mailu preč. Odhlaseni ostavaju.
create or replace function public.odber_firmy_upratanie()
returns integer
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_n int;
begin
    delete from public.odber_firmy
     where odhlaseny_at is null
       and ((potvrdeny = false and created_at < now() - interval '3 days')
         or (potvrdeny and krok >= 30 and posledny_email_at < now() - interval '12 months')
         or (potvrdeny and coalesce(posledny_email_at, potvrdeny_at) < now() - interval '14 months'));
    get diagnostics v_n = row_count;
    return v_n;
end;
$$;
revoke all on function public.odber_firmy_upratanie() from public, anon, authenticated;
grant execute on function public.odber_firmy_upratanie() to service_role;

select 'Migracia 81 hotova: odber_firmy (len cez Edge Function a service_role).' as vysledok;
