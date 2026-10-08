-- =============================================================================
--  78 - OBRANA VLASTNYCH ZMLUV (vlna 94, 8. 10. 2026)
--  Vloz do Supabase: SQL Editor -> New query -> Run. Spustit sa da opakovane.
--  Predpoklad: migracie 31 (ma_pro), 47 (uvo_*), 64 a 77 uz bezali.
-- =============================================================================
--
--  Pre firmu s planom Growth+ (alebo skuskou) a jej ICO z registracie
--  (organizations.ico): zmluvy, v ktorych je dodavatelom a ktore konci do
--  12 mesiacov, spolu s
--   - odhadom vyhlasenia tendra (opportunities.odhad_vyhlasenia),
--   - poctom ponuk v poslednej sutazi toho isteho uradu v tom istom sektore
--     (uvo_vysledky.pocet_ponuk),
--   - informaciou, ci ten isty urad v tom istom sektore prave vyhlasil sutaz
--     (uvo_vyzvy; je to odhad "mozno nastupca", nie istota).
--
--  1) obrana_moje_zmluvy()  - pre prihlaseneho s Growth+ (appka, dlazdica Dnes)
--  2) obrana_nove_vyzvy()   - pre service_role (e-mail "urad vyhlasil sutaz")
--  3) oznac_obrana_alerty() - dedup (jedna dvojica zmluva + vyzva = jeden e-mail)
--  RLS sa NEMENI.
-- =============================================================================

create table if not exists public.obrana_alerty_odoslane (
    org_id      uuid   not null references public.organizations(id) on delete cascade,
    contract_id bigint not null,
    vyzva_id    bigint not null,
    odoslane_at timestamptz not null default now(),
    primary key (org_id, contract_id, vyzva_id)
);

alter table public.obrana_alerty_odoslane enable row level security;
revoke all on public.obrana_alerty_odoslane from public, anon, authenticated;

-- Spolocny zaklad: zmluvy jedneho ICO. Nikdy nie pre klienta.
create or replace function public._obrana_zmluvy(p_ico text)
returns table (
    contract_id            bigint,
    authority_name         text,
    subject                text,
    effective_to           date,
    price_total            numeric,
    sektor                 text,
    odhad_vyhlasenia       date,
    pocet_ponuk_naposledy  integer,
    vyzva_id               bigint,
    vyzva_nazov            text,
    vyzva_lehota           timestamptz,
    vyzva_url              text
)
language sql
stable
security definer
set search_path = ''
as $$
    select c.id,
           left(coalesce(c.authority_name, ''), 160),
           left(coalesce(c.subject, ''), 200),
           c.effective_to,
           coalesce(c.price_total, c.price),
           coalesce(o.sector, c.sector),
           o.odhad_vyhlasenia,
           v.pocet_ponuk,
           y.id,
           left(y.nazov, 200),
           y.lehota_ponuk,
           y.url
      from public.contracts c
      left join public.opportunities o on o.contract_id = c.id
      left join lateral (
            select r.pocet_ponuk
              from public.uvo_vysledky r
             where r.obstaravatel_ico = c.authority_cin
               and r.sektor = coalesce(o.sector, c.sector)
               and r.pocet_ponuk is not null
             order by r.podpisane desc nulls last, r.id desc
             limit 1) v on true
      left join lateral (
            select z.id, z.nazov, z.lehota_ponuk, z.url
              from public.uvo_vyzvy z
             where z.typ = 'sutaz'
               and z.obstaravatel_ico = c.authority_cin
               and z.sektor = coalesce(o.sector, c.sector)
               and (z.lehota_ponuk >= now() or z.publikovane >= current_date - 60)
             order by z.publikovane desc nulls last, z.id desc
             limit 1) y on true
     where p_ico is not null and p_ico <> ''
       and c.supplier_cin = p_ico
       and c.effective_to between current_date and current_date + 365
     order by c.effective_to, c.id;
$$;

revoke all on function public._obrana_zmluvy(text) from public, anon, authenticated;

-- 1) Pre prihlaseneho pouzivatela ---------------------------------------------
create or replace function public.obrana_moje_zmluvy()
returns table (
    contract_id            bigint,
    authority_name         text,
    subject                text,
    effective_to           date,
    price_total            numeric,
    sektor                 text,
    odhad_vyhlasenia       date,
    pocet_ponuk_naposledy  integer,
    vyzva_id               bigint,
    vyzva_nazov            text,
    vyzva_lehota           timestamptz,
    vyzva_url              text
)
language sql
stable
security definer
set search_path = ''
as $$
    select z.*
      from (select distinct o.ico
              from public.memberships m
              join public.organizations o on o.id = m.org_id
             where m.user_id = auth.uid() and o.ico is not null) i
     cross join lateral public._obrana_zmluvy(i.ico) z
     where public.ma_pro()
     order by z.effective_to, z.contract_id
     limit 50;
$$;

revoke all on function public.obrana_moje_zmluvy() from public, anon;
grant execute on function public.obrana_moje_zmluvy() to authenticated;

-- 2) Pre e-mail (service_role) --------------------------------------------------
create or replace function public.obrana_nove_vyzvy()
returns table (
    org_id                 uuid,
    email                  text,
    contract_id            bigint,
    authority_name         text,
    subject                text,
    effective_to           date,
    price_total            numeric,
    sektor                 text,
    odhad_vyhlasenia       date,
    pocet_ponuk_naposledy  integer,
    vyzva_id               bigint,
    vyzva_nazov            text,
    vyzva_lehota           timestamptz,
    vyzva_url              text
)
language sql
stable
security definer
set search_path = ''
as $$
    select g.id, u.email::text,
           z.contract_id, z.authority_name, z.subject, z.effective_to, z.price_total,
           z.sektor, z.odhad_vyhlasenia, z.pocet_ponuk_naposledy,
           z.vyzva_id, z.vyzva_nazov, z.vyzva_lehota, z.vyzva_url
      from public.organizations g
      join public.memberships m on m.org_id = g.id and m.rola in ('owner', 'admin')
      join auth.users u on u.id = m.user_id
     cross join lateral public._obrana_zmluvy(g.ico) z
     where g.ico is not null
       and z.vyzva_id is not null
       and u.email is not null
       and public.ma_pro_pre_org(g.id)
       and not exists (select 1
                         from public.obrana_alerty_odoslane a
                        where a.org_id = g.id
                          and a.contract_id = z.contract_id
                          and a.vyzva_id = z.vyzva_id)
     order by g.id, u.email, z.effective_to, z.contract_id;
$$;

create or replace function public.oznac_obrana_alerty(p_org_id uuid, p_contract_ids bigint[], p_vyzva_ids bigint[])
returns void
language sql
security definer
set search_path = ''
as $$
    insert into public.obrana_alerty_odoslane (org_id, contract_id, vyzva_id)
    select p_org_id, t.cid, t.vid
      from unnest(p_contract_ids, p_vyzva_ids) as t(cid, vid)
    on conflict (org_id, contract_id, vyzva_id) do nothing;
$$;

revoke all on function public.obrana_nove_vyzvy() from public, anon, authenticated;
revoke all on function public.oznac_obrana_alerty(uuid, bigint[], bigint[]) from public, anon, authenticated;
grant execute on function public.obrana_nove_vyzvy() to service_role;
grant execute on function public.oznac_obrana_alerty(uuid, bigint[], bigint[]) to service_role;

select 'Migracia 78 hotova: obrana vlastnych zmluv (zmluvy, ktorym sa blizi tender).' as vysledok;
