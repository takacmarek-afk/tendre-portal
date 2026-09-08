-- =============================================================================
--  REVIZIA: stlpcova diera v Pro, historizacia, zatvrdenie funkcii
--  Vloz do Supabase: SQL Editor -> New query -> Run. Spustit sa da opakovane.
--  Spustaj PO 06_plany.sql.
-- =============================================================================

-- ── 1. STLPCOVA DIERA V PRO VRSTVE ───────────────────────────────────────
--
--  RLS v Postgrese je RIADKOVA, nie stlpcova. Benchmark bol v `opportunities`
--  ako stlpce median_mesacna, odchylka_pct a vzoriek. Zakaznik na plane Start
--  ma pravo citat `opportunities` — takze si Pro udaje vytiahol obycajnym
--  ?select=*. Gating na urovni tabuliek to nechytil.
--
--  Riesenie: benchmark ma vlastnu tabulku s vlastnou politikou.

drop index if exists ix_opp_median;
alter table public.opportunities drop column if exists mesacna_cena;
alter table public.opportunities drop column if exists median_mesacna;
alter table public.opportunities drop column if exists odchylka_pct;
alter table public.opportunities drop column if exists vzoriek;
alter table public.opportunities drop column if exists navysenie_pct;

create table if not exists public.ceny_prilezitosti (
    contract_id        bigint primary key,
    porovnavacia_cena  numeric,
    zaklad             text,        -- 'mesiac' alebo 'zmluva'
    median_cena        numeric,
    odchylka_pct       numeric,
    vzoriek            integer,
    q1                 numeric,
    q3                 numeric,
    last_seen_at       date
);

alter table public.ceny_prilezitosti enable row level security;

drop policy if exists ceny_pril_select on public.ceny_prilezitosti;
create policy ceny_pril_select on public.ceny_prilezitosti
    for select to authenticated
    using (public.ma_pro());


-- ── 2. NOVE STLPCE V PRILEZITOSTIACH ─────────────────────────────────────
-- Karta "kto to ma teraz" nahradza detektor koncentracie, ktory oznacil
-- 8 zaznamov z 864. Tieto udaje maju stopercentne pokrytie.
alter table public.opportunities add column if not exists dodavatel_od            date;
alter table public.opportunities add column if not exists dodavatel_zmluv_celkom  integer;
alter table public.opportunities add column if not exists cena_neuvedena          boolean default false;


-- ── 3. HISTORIZACIA ──────────────────────────────────────────────────────
--
--  Bez `first_seen_at` sa neda poslat upozornenie "nove od vcera", spravit
--  spatny test predikcie ani zmerat vlastnu presnost. Klzave okno, ktore sa
--  cele prepisuje, historiu nema — a spatny test je jediny marketingovy
--  argument, ktory sa neda rozporovat.
alter table public.opportunities add column if not exists first_seen_at date;
alter table public.opportunities add column if not exists last_seen_at  date;
alter table public.subsidies     add column if not exists first_seen_at date;
alter table public.subsidies     add column if not exists last_seen_at  date;
alter table public.dodavatelia   add column if not exists last_seen_at  date;
alter table public.ceny_sektor   add column if not exists last_seen_at  date;

create index if not exists ix_opp_first_seen on public.opportunities(first_seen_at desc);
create index if not exists ix_sub_first_seen on public.subsidies(first_seen_at desc);


-- ── 4. UNIKATNE KLUCE PRE UPSERT ─────────────────────────────────────────
--
--  Povodne sa odvodene tabulky plnili cez DELETE + INSERT. To cez REST nie
--  je transakcia — medzi volaniami je okno, v ktorom je tabulka prazdna
--  a aplikacia vyzera rozbito. Upsert to okno rusi, ale potrebuje unikatny
--  kluc, na ktory sa da konfliktovat.
do $$
begin
    if not exists (select 1 from pg_constraint where conname = 'opportunities_contract_id_key') then
        alter table public.opportunities add constraint opportunities_contract_id_key unique (contract_id);
    end if;
    if not exists (select 1 from pg_constraint where conname = 'subsidies_contract_id_key') then
        alter table public.subsidies add constraint subsidies_contract_id_key unique (contract_id);
    end if;
end $$;


-- ── 5. CENY_SEKTOR: NOVA PODOBA ──────────────────────────────────────────
-- Jediny median bez rozptylu vyzera ako presna hodnota, ktorou sa da nacenit
-- ponuka. Kvartily hovoria, ake siroke je realne pasmo.
alter table public.ceny_sektor add column if not exists median_cena numeric;
alter table public.ceny_sektor add column if not exists q1          numeric;
alter table public.ceny_sektor add column if not exists q3          numeric;
alter table public.ceny_sektor add column if not exists zaklad      text;
alter table public.ceny_sektor drop column if exists median_mesacna;


-- ── 6. DODAVATELIA BEZ NAVYSENI ──────────────────────────────────────────
--
--  `price_total` NIE JE v praxi "suma vratane dodatkov". Merania na
--  44 566 nedotacnych zmluvach: 23 374 ma price_total = price, 34 ma
--  price_total vyssie. Funkcia sa rusi aj so stlpcami.
alter table public.dodavatelia drop column if exists zmluv_s_navysenim;
alter table public.dodavatelia drop column if exists podiel_zmluv_s_navysenim;
alter table public.dodavatelia drop column if exists priemerne_navysenie_pct;
drop index if exists ix_dod_navys;


-- ── 7. ZATVRDENIE SECURITY DEFINER FUNKCII ───────────────────────────────
--
--  Funkcie uz mali `set search_path = public`, co nie je klasicka zranitelnost
--  (ta vznika pri NEPRIPNUTOM search_path). Prazdny search_path s plne
--  kvalifikovanymi nazvami je vsak striktne bezpecnejsi: aj keby niekto
--  dokazal vytvorit objekt v schéme public, funkcia ho nepouzije.
alter function public.moje_org_ids()        set search_path = '';
alter function public.ma_aktivny_pristup()  set search_path = '';
alter function public.ma_pro()              set search_path = '';

-- ma_pro pouziva nekvalifikovane nazvy, s prazdnym search_path by spadla.
create or replace function public.ma_pro()
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
    select public.ma_aktivny_pristup()
       and exists (
             select 1
               from public.subscriptions s
               join public.memberships m on m.org_id = s.org_id
              where m.user_id = auth.uid()
                and s.plan in ('trial', 'pro')
           );
$$;

grant execute on function public.ma_pro() to authenticated;


-- ── 8. KONTROLA: MA KAZDA TABULKA V PUBLIC ZAPNUTE RLS? ──────────────────
--
--  V Supabase je nova tabulka bez `enable row level security` okamzite
--  verejne citatelna cez anon kluc. Tento dopyt musi vratit NULA riadkov.
--  Spustaj ho po kazdej zmene schemy.
select tablename as tabulka_bez_rls
  from pg_tables
 where schemaname = 'public'
   and rowsecurity = false;


select 'Revizia hotova. Ak vyssie nie je ziadny riadok "tabulka_bez_rls", RLS je vsade zapnuta.' as vysledok;


-- =============================================================================
--  DOPLNOK: SPOLAHLIVOST BENCHMARKU
--  Namerane rozptyly medzikvartiloveho rozpetia v sektoroch:
--    ZELEN_ZIMNA_UDRZBA 161x, ELEKTROINSTALACIE 111x, OSTRAHA 84x,
--    STAVEBNE_PRACE 21x, UPRATOVANIE 7x, STRAVOVANIE 6x, TLAC 4x
--  Tam, kde stredna polovica zmluv siaha cez dva rady velkosti, median
--  nie je pouzitelna porovnavacia kotva. Priznak to hovori nahlas.
-- =============================================================================

alter table public.ceny_prilezitosti add column if not exists rozptyl    numeric;
alter table public.ceny_prilezitosti add column if not exists spolahlivy boolean;
alter table public.ceny_sektor       add column if not exists rozptyl    numeric;
alter table public.ceny_sektor       add column if not exists spolahlivy boolean;

select 'Doplnok hotovy: rozptyl a spolahlivy pridane.' as vysledok2;
