-- =============================================================================
--  RUZ FINANCIE: financny kontext + NACE sektor v profile dodavatela
--  Vloz do Supabase: SQL Editor -> New query -> Run. Spustit sa da opakovane.
--  Spustaj PO 06_plany.sql (potrebuje moje_org_ids()/ma_aktivny_pristup()) a
--  PO 31_oprava_ma_pro_planov.sql (rovnaky vzor pre ma_team()).
-- =============================================================================
--
--  CO A PRECO (22. vlna, 21.9.2026)
--
--  Marek schvalil implementaciu financneho kontextu (obrat, vysledok
--  hospodarenia za poslednych par rokov) a NACE sektora vo verejnom
--  profile dodavatela, zdroj: Register uctovnych zavierok (registeruz.sk,
--  CC0, verejne API, overene naživo). Explicitne ako SUCAST NAJVYSSIEHO
--  BALIKA (Team), nie Growth+ ako doterajsie "dodavatelia"/cenovy
--  benchmark (06_plany.sql).
--
--  Surove RUZ data (obrat/zisk) NIE SU sami o sebe moat - finstat.sk ich
--  uz ukazuje. Hodnota je v kontexte s CRZ historiou, ktoru uz mame. Preto
--  su tieto tabulky oddelene od `dodavatelia` (ten patri dennemu CRZ
--  pipeline a jeho _nahrad_tabulku() maze vsetko mimo aktualneho behu -
--  keby sme RUZ stlpce pridali tam, kazdy CRZ beh by ich vynuloval, kym
--  sa nespusti aj RUZ obohacovaci skript). Vlastni ich VYHRADNE
--  pipeline/obohat_financie.py, samostatny skript so samostatnym
--  GitHub Actions behom (rovnaky vzor ako ceny_prilezitosti/sanca_na_vyhru
--  su oddelene od opportunities - viz 24_sanca_na_vyhru.sql).
--
--  DVE TABULKY, NIE JEDNA
--    ruz_zaklad    - jeden riadok na ICO: NACE, pravna forma, a najma
--                    `ma_zaznam` - ci RUZ o firme vobec nieco vie. Bez
--                    tohto priznaku by sme nevedeli odlisit "firmu sme
--                    este neobohatili" od "RUZ pre nu nema ziadne
--                    priznane zavierky" (viz prieskum registrov,
--                    21.9.2026: ~48-tisic firiem na Slovensku neodovzdava
--                    zavierky vobec alebo nepravidelne). Frontend na
--                    zaklade `ma_zaznam=false` zobrazi "Udaje nedostupne",
--                    NIE ticho nulu.
--    ruz_financie  - jeden riadok na (ICO, rok): obrat a vysledok
--                    hospodarenia z Vykazu ziskov a strat. Viacero rokov
--                    na ICO umoznuje trend v UI.
--
--  GATING: ma_team() nizsie je DOSLOVNA kopia vzoru ma_pro() z
--  31_oprava_ma_pro_planov.sql (vratane OR s je_zadarmo() - kym je
--  otvorene obdobie, vidi to kazdy, presne ako vsetky ostatne Pro/Growth
--  funkcie). Rozdiel je len v zozname planov: len 'team' a 'admin', nie
--  'trial'/'pro'/'growth' - skuska (trial) dava Pro uroven (06_plany.sql:
--  "Skusobne tri dni davaju Pro"), nie Team.
-- =============================================================================

create table if not exists public.ruz_zaklad (
    supplier_cin          text primary key references public.dodavatelia(supplier_cin) on delete cascade,
    ma_zaznam             boolean not null,
    nace_kod              text,
    nace_nazov            text,
    pravna_forma          text,
    velkost_organizacie   text,
    checked_at            timestamptz not null default now()
);

comment on table public.ruz_zaklad is
    'Zakladny RUZ stav za ICO (existencia zaznamu, NACE, velkost). '
    'Vlastni vyhradne pipeline/obohat_financie.py. ma_zaznam=false '
    'rozlisuje "RUZ o firme nic nevie" od "este sme neobohatili".';

create table if not exists public.ruz_financie (
    supplier_cin              text not null references public.dodavatelia(supplier_cin) on delete cascade,
    rok                        integer not null,
    obdobie_od                 date,
    obdobie_do                 date,
    datum_podania               date,
    obrat                      numeric,
    vysledok_hospodarenia      numeric,
    refreshed_at               timestamptz not null default now(),
    primary key (supplier_cin, rok)
);

comment on table public.ruz_financie is
    'Rocny financny suhrn z Vykazu ziskov a strat (RUZ). obrat = "Cisty '
    'obrat" alebo "Vynosy z hospodarskej cinnosti spolu" podla sablony, '
    'vysledok_hospodarenia = zisk/strata PO ZDANENI. NULL = RUZ ma zaznam '
    'za dany rok, ale sablonu/riadok sa nepodarilo spolahlivo dekodovat '
    '(neznama sablona) - nie 0.';

create index if not exists ruz_financie_supplier_cin_idx
    on public.ruz_financie (supplier_cin);


-- ── Ma prihlaseny pouzivatel Team? ───────────────────────────────────────
create or replace function public.ma_team()
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
    select public.je_zadarmo()
        or (public.ma_aktivny_pristup()
            and exists (
                select 1
                  from public.subscriptions s
                  join public.memberships m on m.org_id = s.org_id
                 where m.user_id = auth.uid()
                   and s.plan in ('team', 'admin')
            ));
$$;

grant execute on function public.ma_team() to authenticated;

comment on function public.ma_team() is
    'Team-only gate (financny kontext + NACE dodavatela). Rovnaky vzor '
    'ako ma_pro() (31_oprava_ma_pro_planov.sql), len uzsi zoznam planov - '
    'trial dava Pro uroven, nie Team, preto tu NIE JE.';


-- ── RLS ───────────────────────────────────────────────────────────────────
alter table public.ruz_zaklad   enable row level security;
alter table public.ruz_financie enable row level security;

drop policy if exists ruz_zaklad_select on public.ruz_zaklad;
create policy ruz_zaklad_select on public.ruz_zaklad
    for select to authenticated
    using (public.ma_team());

drop policy if exists ruz_financie_select on public.ruz_financie;
create policy ruz_financie_select on public.ruz_financie
    for select to authenticated
    using (public.ma_team());

-- Ziadne INSERT/UPDATE politiky: zapisuje vyhradne obohat_financie.py cez
-- service_role kluc, ktory RLS obchadza (rovnaky dovod ako v store.py).

select 'RUZ financie pripravene: ruz_zaklad, ruz_financie, ma_team() (Team-only).' as vysledok;
