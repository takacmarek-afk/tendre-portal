-- =============================================================================
--  77 - UPOZORNENIE "KONKURENTOVI KONCI ZMLUVA" (vlna 93, 8. 10. 2026)
--  Vloz do Supabase: SQL Editor -> New query -> Run. Spustit sa da opakovane.
--  Predpoklad: migracie 18 (sledovane_ico), 31 (ma_pro_pre_org) a 68 uz bezali.
-- =============================================================================
--
--  Organizacia s planom Growth+ (alebo skuskou) si v appke sleduje firmy podla
--  ICO (tabulka sledovane_ico). Doteraz sa sledovanie nikde neozvalo e-mailom.
--  Tato migracia pridava:
--   - sledovane_alerty_odoslane: ktoru zmluvu uz sme ktorej organizacii poslali
--     (jedna zmluva = najviac jeden alert na organizaciu, navzdy),
--   - sledovane_konciace_alerty(): nove zmluvy sledovanych firiem (dodavatel =
--     sledovane ICO), ktorym koniec nastava v najblizsich N dnoch; len pre
--     vlastnikov/adminov organizacii s pristupom Growth+; len pre service_role,
--   - oznac_sledovane_alerty(): zapis o odoslani.
--  RLS sa NEMENI; tabulka s dedupom nema ziadnu politiku (vidi ju len service_role).
-- =============================================================================

create table if not exists public.sledovane_alerty_odoslane (
    org_id      uuid   not null references public.organizations(id) on delete cascade,
    contract_id bigint not null,
    ico         text   not null,
    odoslane_at timestamptz not null default now(),
    primary key (org_id, contract_id)
);

alter table public.sledovane_alerty_odoslane enable row level security;
revoke all on public.sledovane_alerty_odoslane from public, anon, authenticated;

create or replace function public.sledovane_konciace_alerty(p_dni integer default 180)
returns table (
    org_id          uuid,
    email           text,
    ico             text,
    nazov_firmy     text,
    contract_id     bigint,
    authority_name  text,
    subject         text,
    effective_to    date,
    price_total     numeric,
    kraj            text,
    odhad_vyhlasenia date
)
language sql
stable
security definer
set search_path = ''
as $$
    select s.org_id,
           u.email::text,
           s.ico,
           coalesce(d.dodavatel, s.nazov, c.supplier_name) as nazov_firmy,
           c.id,
           left(coalesce(c.authority_name, ''), 160),
           left(coalesce(c.subject, ''), 200),
           c.effective_to,
           coalesce(c.price_total, c.price),
           o.kraj,
           o.odhad_vyhlasenia
      from public.sledovane_ico s
      join public.contracts c on c.supplier_cin = s.ico
      join public.memberships m on m.org_id = s.org_id and m.rola in ('owner', 'admin')
      join auth.users u on u.id = m.user_id
      left join public.dodavatelia d on d.supplier_cin = s.ico
      left join public.opportunities o on o.contract_id = c.id
     where c.effective_to between current_date
                              and current_date + least(greatest(coalesce(p_dni, 180), 30), 365)
       and coalesce(c.price_total, c.price, 0) >= 5000
       and u.email is not null
       and public.ma_pro_pre_org(s.org_id)
       and not exists (select 1
                         from public.sledovane_alerty_odoslane a
                        where a.org_id = s.org_id and a.contract_id = c.id)
     order by s.org_id, u.email, c.effective_to, c.id;
$$;

create or replace function public.oznac_sledovane_alerty(p_org_id uuid, p_ico text[], p_contract_ids bigint[])
returns void
language sql
security definer
set search_path = ''
as $$
    insert into public.sledovane_alerty_odoslane (org_id, contract_id, ico)
    select p_org_id, t.cid, coalesce(t.ico, '')
      from unnest(p_contract_ids, p_ico) as t(cid, ico)
    on conflict (org_id, contract_id) do nothing;
$$;

revoke all on function public.sledovane_konciace_alerty(integer) from public, anon, authenticated;
revoke all on function public.oznac_sledovane_alerty(uuid, text[], bigint[]) from public, anon, authenticated;
grant execute on function public.sledovane_konciace_alerty(integer) to service_role;
grant execute on function public.oznac_sledovane_alerty(uuid, text[], bigint[]) to service_role;

select 'Migracia 77 hotova: upozornenie, ked sledovanej firme konci zmluva.' as vysledok;
