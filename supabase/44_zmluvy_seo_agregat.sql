-- =============================================================================
--  ZMLUVY_SEO_AGREGAT — verejny agregat konciacich zmluv per sektor+kraj,
--  zaklad pre programovo generovane SEO podstranky /konciace-zmluvy/[sektor]/[kraj]
--  Vloz do Supabase: SQL Editor -> New query -> Run. Spustit sa da opakovane.
-- =============================================================================
--
--  CO TO JE
--  Vyvojarske zadanie 23.9.2026 ("Marketing", "Programmatic SEO"): rozsirenie
--  uz funkcneho vzoru z 33_kraj_prehlad.sql (dotacie pre obce) na druhu
--  vrstvu produktu — konciace zmluvy z `opportunities`. Rovnaky rezim:
--  AGREGAT, nie riadkove data. `opportunities` sama je authenticated-only
--  (schema.sql, opp_select) — tato tabulka existuje presne preto, aby sa
--  z nej dal verejne ukazat SUHRN a par NAJMENEJ CITLIVYCH riadkov, bez
--  odhalenia toho, co je jadro platenej hodnoty.
--
--  HRANICA (potvrdena vyhodnotenim v marketingovej strategii, sekcia 7):
--  `teaser` smie obsahovat NAJVIAC 3 skutocne riadky, VZDY LEN polia
--  authority_name / price_total / mesiac_konca (nie presny den). NIKDY
--  supplier_name, top_dodavatel, podiel_top_dodavatela, historicky_pocet,
--  pocet_dodavatelov ani odkaz — presne tieto polia su jadro platenej
--  konkurencnej hodnoty (Growth/Team plan) a do tejto tabulky sa NESMU
--  nikdy zapisat, ani do teaseru.
--
--  Narozdiel od kraj_prehlad (ktory dnes obnovuje len jednorazovy INSERT
--  v migracii, bez pipeline refresh kroku — zname obmedzenie) tuto tabulku
--  napĺňa a obnovuje priamo `pipeline/generuj_zmluvy_podstranky.py` pri
--  kazdom behu (service_role, cita `opportunities` priamo) — nie je
--  potrebny samostatny "refresh krok" navyse.
-- =============================================================================

create table if not exists public.zmluvy_seo_agregat (
    sector            text not null,
    kraj              text not null,
    pocet             integer not null default 0,
    objem_eur         numeric,
    najblizsi_koniec  date,
    -- Najviac 3 objekty: {"authority_name": "...", "price_total": 12345, "mesiac_konca": "2026-12"}.
    -- ZIADNE ine polia. Kontrolovane vyhradne v generuj_zmluvy_podstranky.py.
    teaser            jsonb not null default '[]'::jsonb,
    last_seen_at      date,
    refreshed_at      timestamptz not null default now(),
    primary key (sector, kraj)
);

alter table public.zmluvy_seo_agregat enable row level security;

drop policy if exists zmluvy_seo_agregat_select on public.zmluvy_seo_agregat;
create policy zmluvy_seo_agregat_select on public.zmluvy_seo_agregat
    for select to anon, authenticated using (true);

comment on table public.zmluvy_seo_agregat is
    'Verejny agregat konciacich zmluv per sektor+kraj (pocet, objem, najblizsi koniec, '
    'najviac 3 teaser riadky s authority_name/price_total/mesiac_konca). Zaklad pre '
    'SEO podstranky /konciace-zmluvy/[sektor]/[kraj]. NIKDY neobsahuje supplier_name/ '
    'top_dodavatel/podiel_top_dodavatela ani ine riadkove pole z opportunities — to je '
    'jadro platenej hodnoty. Napĺňa pipeline/generuj_zmluvy_podstranky.py.';

-- Tabulka zamerne ostava prazdna, kym prvy krat nepobezi
-- pipeline/generuj_zmluvy_podstranky.py (workflow_dispatch, rucne spustenie
-- Marekom) — ziadny jednorazovy INSERT tu, na rozdiel od 33_kraj_prehlad.sql,
-- presne preto, aby prve data vznikli tou istou cestou ako vsetky dalsie.
select 'zmluvy_seo_agregat vytvorena.' as vysledok;
