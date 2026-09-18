-- =============================================================================
--  OPRAVA: sanca_na_vyhru nema refreshed_at (Pipeline CRZ #50 zlyhal)
--  Vloz do Supabase: SQL Editor -> New query -> Run. Spustit sa da opakovane.
-- =============================================================================
--
--  CO SA STALO
--  `24_sanca_na_vyhru.sql` vytvoril tabulku `sanca_na_vyhru` bez stlpca
--  `refreshed_at` — na rozdiel od vsetkych ostatnych tabuliek, ktore
--  `pipeline/store.py::_nahrad_tabulku()` prepisuje (tam_sektor,
--  trhovy_podiel, ceny_prilezitosti, ...), tento ho nedostal. Kazdy beh
--  `_nahrad_tabulku()` ale VZDY nastavi `refreshed_at` na kazdom riadku a
--  potom nim maze stare riadky — bez stlpca REST API odmietne cely upsert.
--  Ostatok pipeline (stiahnutie, zmluvy, prilezitosti, dotacie,
--  dodavatelia, benchmark) v behu #50 dobehol v poriadku — spadol len
--  tento posledny krok, cim padom sa "sanca na vyhru" (Growth funkcia,
--  #13) od 17.9.2026 vobec neprepocitava.
--
--  Po tejto oprave sposobi dalsi beh (scheduled alebo rucny
--  workflow_dispatch) uspesny zapis.
-- =============================================================================

alter table public.sanca_na_vyhru
    add column if not exists refreshed_at timestamptz not null default now();

select 'sanca_na_vyhru ma refreshed_at: ' ||
       exists(select 1 from information_schema.columns
               where table_schema='public' and table_name='sanca_na_vyhru'
                 and column_name='refreshed_at') as vysledok;
