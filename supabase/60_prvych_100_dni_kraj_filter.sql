-- =============================================================================
--  60 — prvych_100_dni_suhrn: pridany p_kraj filter (oprava zlucenia rovnako
--  pomenovanych obci z roznych krajov)
--  Vloz do Supabase: SQL Editor -> New query -> Run. Spustit sa da opakovane.
-- =============================================================================
--
--  NAJDENA CHYBA (komplexny audit 29.9.2026, subagent "frontend-backend
--  consistency"): public/prvych-100-dni.html cita ?kraj= z URL (aj ho
--  dostava z kliknutia na konkretny vysledok hladania, hladaj_obec vracia
--  kraj pre kazdeho kandidata), ale nikdy ho neposiela do RPC —
--  prvych_100_dni_suhrn(p_nazov) parovala VYLUCNE podla mena, bez ohladu
--  na kraj. Na Slovensku existuje viacero obci s rovnakym nazvom v roznych
--  krajoch (napr. viacero obci "Nova Ves") — bez kraj filtra sa ich udaje
--  SCITAVALI DOHROMADY namiesto zobrazenia jednej konkretnej obce. Chyba
--  bola horsia, nez "moze zobrazit zlu obec" — realne miesala data
--  viacerych raznych obci do jedneho souctu, bez akehokolvek varovania.
--
--  Postihnute oba pouzitia: (1) klik na konkretny vysledok hladania na
--  /prvych-100-dni.html (hladaj_obec uz kraj vracia, len sa nepouzival),
--  (2) hlbky odkaz z kampanovych emailov (?nazov=X&kraj=Y, pipeline/
--  kampan_obce.py::obec_odkaz — bod, kvoli ktoremu bol kraj parameter
--  vobec pridany do URL, no bez tejto opravy sa v skutocnosti nikdy
--  nepouzil).
--
--  OPRAVA: p_kraj text default null pridany k prvych_100_dni_suhrn. Ked je
--  vyplneny (netriviálny po trim), filtruje presne na tento kraj (case-
--  insensitive). Ked je prazdny/null, sprava sa presne ako doteraz
--  (spatna kompatibilita pre existujuce volania bez kraja).
--
--  DROP FUNCTION explicitne PRED CREATE OR REPLACE — poucenie z migracie 55
--  (zaznamenane v audit docu): pridanie noveho parametra meni signaturu
--  funkcie v Postgrese, CREATE OR REPLACE by preto vytvoril DRUHU,
--  subeznu verziu namiesto nahradenia povodnej. Explicitny DROP tomu
--  predchadza.
-- =============================================================================

drop function if exists public.prvych_100_dni_suhrn(text);

create or replace function public.prvych_100_dni_suhrn(p_nazov text, p_kraj text default null)
returns table(
    najdena             boolean,
    kraj                text,
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
    zm as (
        select count(*)::int as pocet, coalesce(sum(o.price_total), 0) as objem
          from public.opportunities o, n
         where n.core <> ''
           and public._je_obec_nazov(o.authority_name)
           and lower(public._obec_core_nazov(o.authority_name)) = n.core
           and (n.kraj_filter is null or lower(o.kraj) = lower(n.kraj_filter))
           and o.effective_to between current_date and (current_date + interval '365 days')
    ),
    dt as (
        select count(*)::int as pocet, coalesce(sum(s.suma), 0) as objem
          from public.subsidies s, n
         where n.core <> ''
           and public._je_obec_nazov(s.prijimatel)
           and lower(public._obec_core_nazov(s.prijimatel)) = n.core
           and (n.kraj_filter is null or lower(s.kraj) = lower(n.kraj_filter))
           and (s.okno_do is null or s.okno_do >= current_date)
    ),
    kr as (
        select coalesce(
            (select o.kraj from public.opportunities o, n
              where n.core <> '' and public._je_obec_nazov(o.authority_name)
                and lower(public._obec_core_nazov(o.authority_name)) = n.core
                and (n.kraj_filter is null or lower(o.kraj) = lower(n.kraj_filter))
                and o.kraj is not null
              limit 1),
            (select s.kraj from public.subsidies s, n
              where n.core <> '' and public._je_obec_nazov(s.prijimatel)
                and lower(public._obec_core_nazov(s.prijimatel)) = n.core
                and (n.kraj_filter is null or lower(s.kraj) = lower(n.kraj_filter))
                and s.kraj is not null
              limit 1),
            (select n.kraj_filter from n)
        ) as kraj
    )
    select
        (select n.core from n) <> ''
          and (
            exists(select 1 from public.opportunities o, n
                    where n.core <> '' and public._je_obec_nazov(o.authority_name)
                      and lower(public._obec_core_nazov(o.authority_name)) = n.core
                      and (n.kraj_filter is null or lower(o.kraj) = lower(n.kraj_filter)))
            or exists(select 1 from public.subsidies s, n
                    where n.core <> '' and public._je_obec_nazov(s.prijimatel)
                      and lower(public._obec_core_nazov(s.prijimatel)) = n.core
                      and (n.kraj_filter is null or lower(s.kraj) = lower(n.kraj_filter)))
          ) as najdena,
        kr.kraj,
        zm.pocet, zm.objem,
        dt.pocet, dt.objem
    from kr, zm, dt;
$$;

grant execute on function public.prvych_100_dni_suhrn(text, text) to anon, authenticated;

select 'prvych_100_dni_suhrn: p_kraj filter pridany (opravene zlucenie rovnako pomenovanych obci).' as vysledok;
