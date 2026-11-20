-- Migracia 105 (20. 11. 2026): kontrola IČO neukazuje „Váš trh“ firmam, ktorych
-- hlavna cinnost je mimo sledovanych odborov. Len nova verzia _trh_firmy
-- (rovnaka ako v 99, plus podmienka 40 % v CTE sektor). Da sa spustit opakovane.

create or replace function public._trh_firmy(p_cin text)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
    with nuts(kraj, kod) as (values
        ('Bratislavský kraj', 'SK010'), ('Trnavský kraj', 'SK021'), ('Trenčiansky kraj', 'SK022'),
        ('Nitriansky kraj', 'SK023'), ('Žilinský kraj', 'SK031'), ('Banskobystrický kraj', 'SK032'),
        ('Prešovský kraj', 'SK041'), ('Košický kraj', 'SK042')),
    moje as (
        select c.authority_cin, c.sector
          from public.contracts c
         where c.supplier_cin = p_cin
           and coalesce(c.signed_on, c.effective_from) >= current_date - 1826
    ),
    sektor0 as (
        select coalesce(
            (select d.hlavny_sektor from public.dodavatelia d
              where d.supplier_cin in (p_cin, lpad(p_cin, 8, '0')) and d.hlavny_sektor is not null
              limit 1),
            (select m.sector from moje m where m.sector is not null and m.sector <> 'DOTACIE_NFP'
              group by m.sector order by count(*) desc, m.sector limit 1)) as s
    ),
    -- Audit 20. 11. 2026: velka firma mimo nasich odborov (napr. telekom s 19
    -- zmluvami v 8 odboroch) dostala „Váš trh: stavebné práce“. Odbor ukazeme len
    -- vtedy, ked tvori aspon 40 % jej zmluv za 5 rokov (alebo ked ich za 5 rokov
    -- nemame a odbor je z historie v tabulke dodavatelia).
    sektor as (
        select case
            when (select count(*) from moje m where m.sector is not null and m.sector <> 'DOTACIE_NFP') = 0
                then (select s from sektor0)
            when (select count(*) from moje m where m.sector = (select s from sektor0)) * 10
                 >= (select count(*) from moje m where m.sector is not null and m.sector <> 'DOTACIE_NFP') * 4
                then (select s from sektor0)
            else null end as s
    ),
    kraje as (
        select distinct op.kraj
          from public.opportunities op
         where op.kraj is not null
           and op.authority_cin in (select authority_cin from moje)
    ),
    kody as (
        select n.kod from nuts n
         where n.kraj in (select kraj from kraje) or not exists (select 1 from kraje)
    ),
    opp as (
        select op.price_total
          from public.opportunities op
          join public.contracts c on c.id = op.contract_id
         where op.sector = (select s from sektor)
           and (op.kraj in (select kraj from kraje) or not exists (select 1 from kraje))
           and op.effective_to between current_date and current_date + 365
           and c.supplier_cin <> p_cin
    ),
    vys as (
        select v.pocet_ponuk
          from public.uvo_vysledky v
         where v.sektor = (select s from sektor)
           and v.podpisane >= current_date - 730
           and v.pocet_ponuk is not null
           and left(coalesce(v.nuts, ''), 5) in (select kod from kody)
    ),
    itms as (
        select i.predpokladana_hodnota
          from public.itms_vo i
         where i.stav = 'Pripravované'
           and i.vyhlasene_zistene_at is null
           and i.sektor = (select s from sektor)
           and (i.kraj in (select kraj from kraje) or not exists (select 1 from kraje))
           and i.itms_updated_at >= now() - interval '24 months'
    ),
    otv as (
        select 1
          from public.uvo_vyzvy z
         where z.typ = 'sutaz'
           and z.sektor = (select s from sektor)
           and z.lehota_ponuk >= now()
           and left(coalesce(z.nuts, ''), 5) in (select kod from kody)
    )
    select case when (select s from sektor) is null then null else jsonb_build_object(
        'sektor',              (select s from sektor),
        'kraje',               coalesce((select jsonb_agg(kraj order by kraj) from kraje), '[]'::jsonb),
        'prilezitosti_12m',    (select count(*) from opp),
        'prilezitosti_objem',  (select sum(price_total) filter (where price_total > 0) from opp),
        'vysledkov_24m',       (select count(*) from vys),
        'jedna_ponuka_24m',    (select count(*) filter (where pocet_ponuk = 1) from vys),
        'otvorene_sutaze',     (select count(*) from otv),
        'eurofondy_pripravovane', (select count(*) from itms),
        'eurofondy_objem',     (select sum(predpokladana_hodnota) filter (where predpokladana_hodnota > 0) from itms)
    ) end;
$$;

revoke all on function public._trh_firmy(text) from public, anon, authenticated;

select 'Migracia 105 hotova: _trh_firmy len pri podiele odboru aspon 40 %.' as vysledok;
