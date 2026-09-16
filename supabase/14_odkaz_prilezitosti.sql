-- ════════════════════════════════════════════════════════════════════════
--  ODKAZ NA ZMLUVU V CRZ PRI PRILEZITOSTIACH
--
--  Externy audit 16. 9. 2026, nalez F-06:
--    "V celej aplikacii su dva odkazy: na zdroje.html a mailto.
--     Nula odkazov do CRZ."
--
--  A ma pravdu dvakrat. Raz kvoli dovere: cela nasa pozicia je "nic si
--  nevymyslame, kazdy udaj sa da overit v zdroji" — a overit sa nedal,
--  zakaznik musel ist rucne hladat na crz.gov.sk.
--
--  Druhy raz kvoli licencii. V zdroje.html mame NAPISANE:
--    "Povodny nezmeneny text je vzdy dostupny v Centralnom registri
--     zmluv pod odkazom pri kazdom zazname."
--  Tym sme deklarovali plnenie bodov 4.2, 4.3 a 4.9 podmienok
--  Slovensko.Digital sposobom, ktory v produkte nebol. Bez odkazu je
--  zdroje.html nepravda, nie nedokoncena funkcia.
--
--  Tabulky `subsidies` a `obce_ziadatelia` stlpec `odkaz` uz maju
--  (02_dotacie.sql a 13_ziadatelia.sql). Chybal len pri prilezitostiach.
--
--  Spusti v SQL editore Supabase. Bezpecne spustit aj opakovane.
-- ════════════════════════════════════════════════════════════════════════

alter table public.opportunities
    add column if not exists odkaz text;

-- Doplnenie do existujucich riadkov, aby odkaz fungoval hned a nemuselo
-- sa cakat na najblizsi beh pipeline. Vzor URL je ten isty, aky pouziva
-- pipeline pri dotaciach (subsidies.py) aj pri ziadateloch (ziadatelia.py).
update public.opportunities
   set odkaz = 'https://www.crz.gov.sk/zmluva/' || contract_id::text || '/'
 where odkaz is null
   and contract_id is not null;

select 'prilezitosti bez odkazu (MA BYT 0): '
       || count(*) filter (where odkaz is null)::text
       || '  z celkovo ' || count(*)::text as vysledok
  from public.opportunities;
