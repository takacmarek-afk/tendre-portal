-- =============================================================================
--  57 — P3.2 B: verejný cenový benchmark (medián) + mesačný e-mail o obci
--  Vloz do Supabase: SQL Editor -> New query -> Run. Spustit sa da opakovane.
-- =============================================================================
--
--  ROZHODNUTIA MAREKA (29.9.2026, cez klikatelne otazky v chate):
--
--  1) BENCHMARK BEZ "VASEJ VELKOSTI" — ziadny spolahlivy, strojovo
--     citatelny zdroj poctu obyvatelov obci sa nenasiel (rovnake zistenie
--     ako pri "Sused uz stavia", pipeline/alerty.py, 22.9.2026). Text preto
--     hovori len "Obce na Slovensku platia...", bez segmentacie podla
--     velkosti.
--
--  2) LEN MEDIAN ZADARMO, NIE CELY ROZSAH — ten isty cenovy benchmark
--     (pipeline/analytics.py -> tabulka ceny_sektor) je dnes platena
--     funkcia appky (plan Start a vyssie, 40_start_dostava_benchmark.sql).
--     Aby verejna stranka /starosta nedavala zadarmo presne to, za co
--     platia zakaznici appky, tato funkcia vracia LEN median_cena (+ pocet
--     vzoriek pre doveryhodnost), NIKDY q1/q3 (presny rozsah cien) ani
--     posledna_cena. Navyse vracia LEN sektory so spolahlivy = true —
--     tam, kde je rozptyl cien v sektore prilis velky (napr. OSTRAHA,
--     ZELEN_ZIMNA_UDRZBA), median by bol zavadzajuci, preto sa nevrati nic.
--
--  3) MESACNY E-MAIL LEN PRE OBCE S EXISTUJUCIM UCTOM (zatial) — nemame
--     samostatny zoznam oficialnych e-mailov vsetkych obci, len
--     obce_ucty.kontakt_email tych, ktore si uz zalozili ucet na trh.html.
-- =============================================================================

-- ── 1) Verejny cenovy median (bez presneho rozsahu) ─────────────────────────
-- SECURITY DEFINER cez rovnaky vzor ako hladaj_obec/prvych_100_dni_suhrn
-- (53_prvych_100_dni.sql) — anon nema priamy SELECT na ceny_sektor (ten
-- ostava Start+ platena funkcia appky, 06_plany.sql/40_start_dostava_
-- benchmark.sql), ale smie zavolat tuto funkciu, ktora z nej vytiahne
-- VYHRADNE median_cena, zaklad a pocet vzoriek pre presne jeden sektor —
-- a LEN ked je oznaceny ako spolahlivy.
create or replace function public.verejny_cenovy_median(p_sektor text)
returns table(
    sector      text,
    median_cena numeric,
    zaklad      text,
    vzoriek     integer
)
language sql
stable
security definer
set search_path = ''
as $$
    select sector, median_cena, zaklad, vzoriek
      from public.ceny_sektor
     where sector = p_sektor
       and spolahlivy = true;
$$;

grant execute on function public.verejny_cenovy_median(text) to anon, authenticated;

-- ── 2) Sledovanie mesacneho e-mailu pre obce_ucty ───────────────────────────
alter table public.obce_ucty
    add column if not exists posledny_mesacny_email timestamptz;

comment on column public.obce_ucty.posledny_mesacny_email is
    'Kedy naposledy dostala tato obec mesacny e-mail o novinkach (P3.2 B, '
    'pipeline/posli_obec_mesacny_email.py). NULL = este nikdy.';

select 'Verejny cenovy median + sledovanie mesacneho emailu pripravene.' as vysledok;
