-- =============================================================================
--  98 - PRIPRAVOVANE OBSTARAVANIA Z EUROFONDOV V REPORTE A V APPKE (10. 11. 2026)
--  Vloz do Supabase: SQL Editor -> New query -> Run. Spustit sa da opakovane.
--  Predpoklad: migracie 95 a 97.
-- =============================================================================
--  1) _trh_firmy: aj pocet a hodnota pripravovanych obstaravani z eurofondov
--     (itms_vo, stav Pripravované, aktualizovane za 24 mesiacov) v odbore
--     a krajoch firmy. Verejna /kontrola ukaze len pocet a sumu.
--  2) itms_pripravovane(sektory, kraje): zoznam pre appku. Growth+ a skuska
--     (ma_pro) vidia polozky, ostatni len pocet a sumu.
-- =============================================================================

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
    sektor as (
        select coalesce(
            (select d.hlavny_sektor from public.dodavatelia d
              where d.supplier_cin in (p_cin, lpad(p_cin, 8, '0')) and d.hlavny_sektor is not null
              limit 1),
            (select m.sector from moje m where m.sector is not null and m.sector <> 'DOTACIE_NFP'
              group by m.sector order by count(*) desc, m.sector limit 1)) as s
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

create or replace function public.itms_pripravovane(p_sektory text[] default null, p_kraje text[] default null)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
    with z as (
        select i.id, i.kod, i.nazov, i.obstaravatel_nazov, i.obstaravatel_ico, i.obstaravatel_obec,
               i.kraj, i.sektor, i.predpokladana_hodnota, i.itms_updated_at
          from public.itms_vo i
         where i.stav = 'Pripravované'
           and i.itms_updated_at >= now() - interval '24 months'
           and (p_sektory is null or cardinality(p_sektory) = 0 or i.sektor = any (p_sektory))
           and (p_kraje is null or cardinality(p_kraje) = 0 or i.kraj = any (p_kraje))
    )
    select jsonb_build_object(
        'pocet',     (select count(*) from z),
        'objem',     (select sum(predpokladana_hodnota) filter (where predpokladana_hodnota > 0) from z),
        'zamknute',  not coalesce(public.ma_pro(), false),
        'polozky',   case when coalesce(public.ma_pro(), false) then coalesce((
            select jsonb_agg(to_jsonb(t) order by t.predpokladana_hodnota desc nulls last)
              from (select * from z order by predpokladana_hodnota desc nulls last limit 300) t), '[]'::jsonb)
            else '[]'::jsonb end)
    where auth.uid() is not null;
$$;

revoke all on function public.itms_pripravovane(text[], text[]) from public, anon;
grant execute on function public.itms_pripravovane(text[], text[]) to authenticated;

select 'Migracia 98 hotova: eurofondy v _trh_firmy a itms_pripravovane().' as vysledok;
