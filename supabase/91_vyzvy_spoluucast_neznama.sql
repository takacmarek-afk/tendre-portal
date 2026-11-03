-- =============================================================================
--  Migracia 91: spoluucast vyzvy moze byt neznama (3. 11. 2026)
--  Pri automatickom overeni zo zverejnenych podkladov nie vzdy zistime mieru
--  spolufinancovania. Radsej null ("overte vo vyzve") nez odhad, ktory by sa
--  v e-maile starostovi tvaril ako fakt. Karta aj e-mail null zobrazia ako
--  "spoluúčasť podľa výzvy" a kalkulacku skryju.
--  Bezpecne spustit opakovane.
-- =============================================================================

alter table public.vyzvy_karty alter column spoluucast_pct drop not null;

select 'Migracia 91 hotova: spoluucast_pct moze byt null.' as vysledok;
