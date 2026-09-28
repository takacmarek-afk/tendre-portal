-- =============================================================================
--  53 — "PRVÝCH 100 DNÍ" — verejný súhrn pre jednu konkrétnu obec (P3.2 A)
--  Vloz do Supabase: SQL Editor -> New query -> Run. Spustit sa da opakovane.
-- =============================================================================
--
--  CO TO JE
--  Zadanie P3 ("cesta pre starostov", claude/predtendrom-p3-cesta-pre-
--  starostov-zadanie.md, persóna A — nový starosta): stránka, kde si
--  starosta bez prihlásenia vyhľadá VLASTNÚ obec a uvidí súhrn toho, čo
--  "zdedil" — koľko zmlúv sa v najbližších 12 mesiacoch končí, koľko
--  dotácií ešte beží, a koľko firiem doteraz obci písalo žiadosti.
--
--  ROZSAH (Marekovo rozhodnutie 28.9.2026, "čo odporúčaš?" — moja voľba):
--  LEN SÚHRN (počty a súčty), NIKDY jednotlivé riadky. Presne rovnaký
--  princíp ako `kraj_prehlad`/`zmluvy_seo_agregat` (33_kraj_prehlad.sql,
--  44_zmluvy_seo_agregat.sql) — podrobný riadkový zoznam (predmet zmluvy,
--  presná suma, presný dátum, meno dodávateľa) ostáva vyhradený pre
--  platiacich zákazníkov appky (Growth/Team). Tu sa NESMIE nikdy pridať
--  stĺpec s menom firmy, predmetom zmluvy ani presným dátumom jednotlivej
--  zmluvy/dotácie.
--
--  "Doterajší poradcovia" (tretia časť zo zadania P3.2 A) tu ZÁMERNE nie
--  je — presná logika (kto je/nie je poradca, ručné vylúčenia IČO, zlúčenie
--  duplicít) žije v pipeline/obce.py::sprostredkovatelia() a je príliš
--  krehká na to, aby sa bezpečne duplikovala priamo v SQL naživo. Kým
--  nevznikne per-obec agregát z pipeline (rovnaký vzor ako
--  zmluvy_seo_agregat), stránka to ukazuje ako "pripravujeme" — čestne,
--  nie vymyslené číslo.
--
--  PRECO RPC, NIE NOVA TABULKA
--  Narozdiel od kraj_prehlad/zmluvy_seo_agregat (ktore su vopred
--  prepocitane pipeline behom) tu ide o vyhladavanie JEDNEJ konkretnej
--  obce na požiadanie — stačí live SQL nad uz existujucimi `opportunities`
--  a `subsidies` (obe su inak authenticated-only), cez SECURITY DEFINER
--  funkcie, ktore vracaju VYHRADNE agregovane cisla, nikdy riadky.
-- =============================================================================

-- Odstráni "Obec "/"Mesto "/"Mestská časť " zo začiatku názvu, aby sa dalo
-- hľadať a porovnávať bez ohľadu na to, či to používateľ napíše alebo nie.
-- Rovnaký vzor prefixu ako _JE_OBEC v pipeline/obce.py.
create or replace function public._obec_core_nazov(p text)
returns text
language sql
immutable
set search_path = ''
as $$
    select trim(regexp_replace(
        coalesce(p, ''),
        '^\s*(Obec|Mesto|Mestsk[aá]\s*[cč]as[tť])\s+',
        '', 'i'
    ));
$$;

-- Presne rovnaká podmienka ako _JE_OBEC v pipeline/obce.py — názov MUSÍ
-- začínať "Obec"/"Mesto"/"Mestská časť", inak to nie je obec ako
-- obstarávateľ/prijímateľ, ale niečo iné (škola, združenie, meno fyzickej
-- osoby v zle vyplnenom riadku CRZ a pod.).
--
-- Zistené naživo pri testovaní (28.9.2026): bez tejto podmienky hľadanie
-- "Nová" vrátilo aj "Anna Michalinová" (zhoda podreťazca priezviska!),
-- "Cirkevné gymnázium..." a podobné nezmysly — _obec_core_nazov totiž
-- predponu len VOLITEĽNE odstráni, nevyžaduje ju. Táto funkcia to opravuje.
create or replace function public._je_obec_nazov(p text)
returns boolean
language sql
immutable
set search_path = ''
as $$
    select coalesce(p, '') ~* '^\s*(Obec|Mesto|Mestsk[aá]\s*[cč]as[tť])\s+';
$$;

-- Vyhľadávanie: používateľ napíše časť názvu, dostane zoznam kandidátov
-- (názov bez predpony + kraj), z ktorých si vyberie presne tú svoju obec.
-- Vracia LEN názvy a kraje — žiadne finančné údaje.
create or replace function public.hladaj_obec(p_hladanie text)
returns table(nazov text, kraj text)
language sql
stable
security definer
set search_path = ''
as $$
    select distinct on (lower(n)) n as nazov, kraj
    from (
        select public._obec_core_nazov(authority_name) as n, kraj
          from public.opportunities
         where trim(coalesce(p_hladanie, '')) <> ''
           and public._je_obec_nazov(authority_name)
           and authority_name ilike '%' || trim(p_hladanie) || '%'
        union all
        select public._obec_core_nazov(prijimatel) as n, kraj
          from public.subsidies
         where trim(coalesce(p_hladanie, '')) <> ''
           and public._je_obec_nazov(prijimatel)
           and prijimatel ilike '%' || trim(p_hladanie) || '%'
    ) s
    where n is not null and trim(n) <> ''
    order by lower(n), kraj nulls last
    limit 15;
$$;

grant execute on function public._obec_core_nazov(text) to anon, authenticated;
grant execute on function public._je_obec_nazov(text) to anon, authenticated;
grant execute on function public.hladaj_obec(text) to anon, authenticated;

-- Súhrn pre presne jednu obec (p_nazov = "nazov" tak, ako ho vrátilo
-- hladaj_obec — teda bez predpony "Obec"/"Mesto"). LEN počty a súčty.
create or replace function public.prvych_100_dni_suhrn(p_nazov text)
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
        select lower(trim(coalesce(p_nazov, ''))) as core
    ),
    zm as (
        select count(*)::int as pocet, coalesce(sum(o.price_total), 0) as objem
          from public.opportunities o, n
         where n.core <> ''
           and public._je_obec_nazov(o.authority_name)
           and lower(public._obec_core_nazov(o.authority_name)) = n.core
           and o.effective_to between current_date and (current_date + interval '365 days')
    ),
    dt as (
        select count(*)::int as pocet, coalesce(sum(s.suma), 0) as objem
          from public.subsidies s, n
         where n.core <> ''
           and public._je_obec_nazov(s.prijimatel)
           and lower(public._obec_core_nazov(s.prijimatel)) = n.core
           and (s.okno_do is null or s.okno_do >= current_date)
    ),
    kr as (
        select coalesce(
            (select o.kraj from public.opportunities o, n
              where n.core <> '' and public._je_obec_nazov(o.authority_name)
                and lower(public._obec_core_nazov(o.authority_name)) = n.core
                and o.kraj is not null
              limit 1),
            (select s.kraj from public.subsidies s, n
              where n.core <> '' and public._je_obec_nazov(s.prijimatel)
                and lower(public._obec_core_nazov(s.prijimatel)) = n.core
                and s.kraj is not null
              limit 1)
        ) as kraj
    )
    select
        (select n.core from n) <> ''
          and (
            exists(select 1 from public.opportunities o, n
                    where n.core <> '' and public._je_obec_nazov(o.authority_name)
                      and lower(public._obec_core_nazov(o.authority_name)) = n.core)
            or exists(select 1 from public.subsidies s, n
                    where n.core <> '' and public._je_obec_nazov(s.prijimatel)
                      and lower(public._obec_core_nazov(s.prijimatel)) = n.core)
          ) as najdena,
        kr.kraj,
        zm.pocet, zm.objem,
        dt.pocet, dt.objem
    from kr, zm, dt;
$$;

grant execute on function public.prvych_100_dni_suhrn(text) to anon, authenticated;

select 'hladaj_obec + prvych_100_dni_suhrn pripravene.' as vysledok;
