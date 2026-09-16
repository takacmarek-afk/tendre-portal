-- ════════════════════════════════════════════════════════════════════════
--  PRIZNAK VYMENENYCH STRAN PRI DOTACIACH
--
--  Odmerane 16. 9. 2026: 11 z 3 276 dotacnych zmluv (0,4 %) ma v CRZ
--  poskytovatela v poli dodavatela a obec v poli objednavatela — teda
--  presne naopak nez zvysok. Na stranke to vypadalo takto:
--
--      PRIJIMATEL: Ministerstvo financií SR
--      poskytovatel: Obec Mestečko
--
--  Skoda nebola len v poradi stlpcov. Kraj sa odvodzuje z nazvu
--  prijimatela, takze tych 11 riadkov dostalo kraj a mesto SIDLA
--  POSKYTOVATELA: styri Bratislavu, sest Kosice. Dotacia pre Obec
--  Ludovitova (Nitriansky kraj) sa teda zobrazovala ako bratislavska.
--
--  Pipeline ich teraz OTACA a tento stlpec si pamata, ze sa tak stalo —
--  aby to bolo vidiet v UI aj v exporte a aby sa na to nezabudlo.
--
--  Spusti v SQL editore Supabase. Bezpecne spustit aj opakovane.
-- ════════════════════════════════════════════════════════════════════════

alter table public.subsidies
    add column if not exists strany_vymenene boolean not null default false;

comment on column public.subsidies.strany_vymenene is
    'TRUE = v CRZ boli strany zamenene a pipeline ich otocila. Priznak drzime, aby sa dalo overit, ktore riadky sme upravili.';

select 'subsidies.strany_vymenene doplneny. Naplni ich najblizsi beh.' as vysledok;
