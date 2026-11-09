-- =============================================================================
--  93 - NAVRH "MOJHO VYBERU" Z HISTORIE ZMLUV FIRMY (9. 11. 2026)
--  Vloz do Supabase: SQL Editor -> New query -> Run. Spustit sa da opakovane.
--  Predpoklad: migracie 51 (nastavenia_pouzivatela) a 78 uz bezali.
-- =============================================================================
--
--  Problem: novi pouzivatelia si po registracii nenastavili vyber (kraje +
--  sektory), takze nikdy nevideli zmluvy, ktore ich tykaju. Firma vsak IČO
--  zadala pri registracii a jej zmluvy v CRZ mame.
--
--  navrh_vyberu() vrati pre prihlaseneho pouzivatela navrh:
--    { zmluv, sektory: [najviac 2], kraje: [najviac 2] }
--  - sektory: najcastejsie sektory zmluv, kde je firma dodavatelom (5 rokov),
--  - kraje: kraje uradov z tych zmluv; kraj uradu berieme z opportunities
--    (pipeline ho urcuje z adresy, regiony.py). Kde kraj nevieme, nehadame.
--  Ziadne sumy, nazvy ani ine udaje zmluv sa nevracaju. RLS sa NEMENI.
-- =============================================================================

create or replace function public.navrh_vyberu()
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
    with ica as (
        select distinct o.ico
          from public.memberships m
          join public.organizations o on o.id = m.org_id
         where m.user_id = auth.uid()
           and o.ico is not null and o.ico <> ''
    ),
    moje as (
        select c.id, c.sector, c.authority_cin
          from public.contracts c
          join ica i on c.supplier_cin in (i.ico, ltrim(i.ico, '0'))
         where coalesce(c.signed_on, c.effective_from) >= current_date - 1826
    ),
    kraj_uradu as (
        select distinct on (op.authority_cin) op.authority_cin, op.kraj
          from public.opportunities op
         where op.kraj is not null
           and op.authority_cin in (select authority_cin from moje)
         order by op.authority_cin, op.refreshed_at desc
    ),
    sektory as (
        select sector, count(*) n
          from moje
         where sector is not null and sector <> ''
         group by sector
         order by n desc, sector
         limit 2
    ),
    kraje as (
        select k.kraj, count(*) n
          from moje m
          join kraj_uradu k on k.authority_cin = m.authority_cin
         group by k.kraj
         order by n desc, k.kraj
         limit 2
    )
    select jsonb_build_object(
        'zmluv',   (select count(*) from moje),
        'sektory', coalesce((select jsonb_agg(sector order by n desc, sector) from sektory), '[]'::jsonb),
        'kraje',   coalesce((select jsonb_agg(kraj order by n desc, kraj) from kraje), '[]'::jsonb)
    );
$$;

revoke all on function public.navrh_vyberu() from public, anon;
grant execute on function public.navrh_vyberu() to authenticated;
