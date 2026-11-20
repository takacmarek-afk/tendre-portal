-- =============================================================================
--  107 - DATA PRE VEREJNE SEO STRANKY OBSTARAVATELOV /obstaravatelia/<kraj>/<nazov-ico>
--  (oba portaly; ceska obdoba je hledam-zakazky 016 /zadavatele/)
--  Pre kazdy urad, obec, mesto a kraj: zmluvy z CRZ, ktore skoncia do 12
--  mesiacov (pocet, objem, 3 ukazky BEZ dodavatela) a pripravovane
--  obstaravania z eurofondov (ITMS, 3 ukazky). Vola len service_role
--  (pipeline/generuj_obstaravatelia_podstranky.py).
--  Bezpecne spustit opakovane.
-- =============================================================================

create or replace function public.seo_obstaravatelia()
returns table (ico text, nazov text, kraj text, konci12 bigint, objem12 numeric, ukazky jsonb,
               eurofondy_pocet bigint, eurofondy_objem numeric, eurofondy jsonb)
language sql stable security definer
set search_path = public
set statement_timeout = '120s'
as $$
    with k as (
        select lpad(ltrim(o.authority_cin, '0'), 8, '0') as ico, max(o.authority_name) as nazov, max(o.kraj) as kraj,
               count(*) as konci12, sum(o.price_total) filter (where o.price_total > 0) as objem12,
               (jsonb_agg(jsonb_build_object('predmet', o.subject, 'mesiac', to_char(o.effective_to, 'YYYY-MM'),
                                             'cena', case when o.price_total > 0 then o.price_total end)
                          order by o.price_total desc nulls last))::jsonb as vse
          from public.opportunities o
         where o.effective_to between current_date and current_date + 365
           and coalesce(ltrim(o.authority_cin, '0'), '') ~ '^[0-9]{1,8}$'
         group by 1
    ),
    e as (
        select lpad(ltrim(v.obstaravatel_ico, '0'), 8, '0') as ico, max(v.obstaravatel_nazov) as nazov, max(v.kraj) as kraj,
               count(*) as pocet, sum(v.predpokladana_hodnota) as objem,
               (jsonb_agg(jsonb_build_object('nazov', v.nazov, 'hodnota', v.predpokladana_hodnota)
                          order by v.predpokladana_hodnota desc nulls last))::jsonb as vse
          from public.itms_vo v
         where v.stav = 'Pripravované'
           and coalesce(ltrim(v.obstaravatel_ico, '0'), '') ~ '^[0-9]{1,8}$'
         group by 1
    ),
    v as (select ico from k union select ico from e)
    select v.ico, coalesce(k.nazov, e.nazov), coalesce(k.kraj, e.kraj),
           coalesce(k.konci12, 0), k.objem12,
           coalesce((select jsonb_agg(x) from jsonb_array_elements(k.vse) with ordinality t(x, i) where i <= 3), '[]'::jsonb),
           coalesce(e.pocet, 0), e.objem,
           coalesce((select jsonb_agg(x) from jsonb_array_elements(e.vse) with ordinality t(x, i) where i <= 3), '[]'::jsonb)
      from v
      left join k on k.ico = v.ico
      left join e on e.ico = v.ico;
$$;
revoke all on function public.seo_obstaravatelia() from public, anon, authenticated;
grant execute on function public.seo_obstaravatelia() to service_role;

select 'Migracia 107 hotova: seo_obstaravatelia().' as vysledok;
