-- =============================================================================
--  74 - VYPLATENE DOTACIE (vlna 88, 8. 10. 2026)
--  Vloz do Supabase: SQL Editor -> New query -> Run. Spustit sa da opakovane.
-- =============================================================================
--
--  PROBLEM: Podohospodarska platobna agentura (PPA) vyplaca dotaciu AZ PO
--  zrealizovani projektu. Ak je dotacia v zozname vyplatenych, obec uz
--  postavila, co mala, a verejne obstaravanie je za nou. Zakaznikovi sme ju
--  ale ukazovali ako prilezitost "tender este pride".
--
--  RIESENIE: dva nove stlpce v `subsidies`:
--    vyplatene     boolean  - true = nasli sme vyplatu v zozname PPA
--    vyplatene_fy  text     - financny rok vyplaty (napr. FY2025)
--  Naplna ich pipeline (pipeline/ppa_vyplatene.py) pri dalsom behu "Pipeline CRZ".
--  Aplikacia ich predvolene skryva (filter "Skryt uz vyplatene"), uvodne cisla,
--  alerty a kampan ich nepocitaju. Riadky sa NEMAZU - zakaznik si ich vie zobrazit.
--
--  DOLEZITE: tuto migraciu treba pustit PRED nasadenim noveho kodu a PRED
--  dalsim behom pipeline. Inak by upsert do `subsidies` zlyhal na neznamom stlpci
--  a aplikacia by pytala neexistujuci stlpec.
--
--  Navyse sa prepisuje prvych_100_dni_suhrn(): "dotacie, ktore bezia" uz
--  nezahrnuju vyplatene.
-- =============================================================================

alter table public.subsidies
    add column if not exists vyplatene    boolean not null default false,
    add column if not exists vyplatene_fy text;

create index if not exists subsidies_vyplatene_idx on public.subsidies (vyplatene);

create or replace function public.prvych_100_dni_suhrn(p_nazov text, p_kraj text default null)
returns table(
    najdena             boolean,
    ma_data             boolean,
    kraj                text,
    okres               text,
    pocet_konciacich    integer,
    objem_konciacich    numeric,
    pocet_dotacii_bezi  integer,
    objem_dotacii_bezi  numeric
)
language sql
stable
security definer
set search_path = ''
as $$
    with n as (
        select lower(trim(coalesce(p_nazov, ''))) as core,
               nullif(trim(coalesce(p_kraj, '')), '') as kraj_filter
    ),
    op as (
        select o.kraj, o.price_total, o.effective_to
          from public.opportunities o, n
         where n.core <> ''
           and public._je_obec_nazov(o.authority_name)
           and lower(public._obec_core_nazov(o.authority_name)) = n.core
           and (n.kraj_filter is null or lower(o.kraj) = lower(n.kraj_filter))
    ),
    su as (
        select s.kraj, s.suma, s.okno_do, s.vyplatene
          from public.subsidies s, n
         where n.core <> ''
           and public._je_obec_nazov(s.prijimatel)
           and lower(public._obec_core_nazov(s.prijimatel)) = n.core
           and (n.kraj_filter is null or lower(s.kraj) = lower(n.kraj_filter))
    ),
    reg as (
        select r.kraj, r.okres
          from public.obce_register r, n
         where n.core <> ''
           and lower(r.nazov) = n.core
           and (n.kraj_filter is null or lower(r.kraj) = lower(n.kraj_filter))
         order by r.kraj, r.okres
         limit 1
    ),
    zm as (
        select count(*)::int as pocet, coalesce(sum(price_total), 0) as objem
          from op
         where effective_to between current_date and (current_date + interval '365 days')
    ),
    dt as (
        select count(*)::int as pocet, coalesce(sum(suma), 0) as objem
          from su
         where (okno_do is null or okno_do >= current_date)
           and not coalesce(vyplatene, false)
    )
    select
        (exists(select 1 from op) or exists(select 1 from su) or exists(select 1 from reg)) as najdena,
        (exists(select 1 from op) or exists(select 1 from su)) as ma_data,
        coalesce((select kraj from op where kraj is not null limit 1),
                 (select kraj from su where kraj is not null limit 1),
                 (select kraj from reg),
                 (select kraj_filter from n)) as kraj,
        (select okres from reg) as okres,
        zm.pocet, zm.objem,
        dt.pocet, dt.objem
    from zm, dt;
$$;

grant execute on function public.prvych_100_dni_suhrn(text, text) to anon, authenticated;

select 'Migracia 74 hotova: stlpce vyplatene a vyplatene_fy. Teraz nasadte kod a spustite "Pipeline CRZ".' as vysledok;
