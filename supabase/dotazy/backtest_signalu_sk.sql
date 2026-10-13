-- SK backtest signalu "konci zmluva v CRZ -> ten isty obstaravatel vyhlasi sutaz" (13.10.2026)
-- Len citanie. Spusti v Supabase SQL editore.
-- Signal: obstaravatel (authority_cin), ktoremu v rokoch 2025-07-01 az 2026-03-31 konci zmluva (effective_to).
-- Zhoda: v uvo_vyzvy (typ='sutaz') ten isty obstaravatel_ico vyhlasil sutaz v okne end-180 az end+183 dni.
-- Kontrola: obstaravatelia so zmluvou, ktora konci az po 2027-06-01; pseudo-datum konca nahodne v rovnakom rozsahu.
-- Obmedzenia: uvo_vyzvy zacina 2025-01-02 (len nadlimitne zakazky z Vestnika), z 1373 IČO vo vyzvach
--             sa ich v contracts nachadza len 400. Test je preto skor dolna hranica ako meranie.
-- Vysledok 13.10.2026: signal n=4326 zhoda 6,0 % (260); kontrola n=3315 zhoda 12,2 % (405);
--   po 61-dnovych oknach signal 3,4/3,5/3,7/3,5/3,4/3,7 % (ziadny pik pri konci zmluvy).
with sig as (
 select distinct authority_cin cin, effective_to e from public.contracts
 where effective_to between '2025-07-01' and '2026-03-31' and authority_cin is not null),
ctl as (
 select distinct authority_cin cin, ('2025-07-01'::date + (abs(hashtext(authority_cin||effective_to::text)) % 274)) e
 from public.contracts where effective_to between '2027-06-01' and '2035-12-31' and authority_cin is not null),
allp as (select 'signal' g,* from sig union all select 'control',* from ctl),
j as (select p.g,p.cin,p.e, v.publikovane - p.e as d from allp p
  left join public.uvo_vyzvy v on v.typ='sutaz' and v.obstaravatel_ico=p.cin and v.publikovane between p.e-180 and p.e+183)
select g, count(distinct (cin,e)) n,
 count(distinct (cin,e)) filter (where d is not null) hit,
 count(distinct (cin,e)) filter (where d between -180 and -120) b1,
 count(distinct (cin,e)) filter (where d between -119 and -59) b2,
 count(distinct (cin,e)) filter (where d between -58 and 2) b3,
 count(distinct (cin,e)) filter (where d between 3 and 63) b4,
 count(distinct (cin,e)) filter (where d between 64 and 124) b5,
 count(distinct (cin,e)) filter (where d between 125 and 183) b6
from j group by g order by g;
