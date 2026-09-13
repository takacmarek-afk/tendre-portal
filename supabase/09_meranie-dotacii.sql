-- ════════════════════════════════════════════════════════════════════════
-- MERANIE DOTAČNEJ VRSTVY
-- Odpovedá na otázku: dotácia je nenávratná a spotrebuje sa. Je teda
-- dotačná vrstva jednorazová, alebo má stálu zásobu?
--
-- POZOR: Supabase v SQL editore zobrazí len výsledok POSLEDNÉHO príkazu.
-- Spúšťaj dotazy JEDEN PO DRUHOM a výsledok každého mi pošli.
--
-- HRANICE MERANIA — čítaj skôr, než budeš výsledky interpretovať:
--  1. BOOTSTRAP_SINCE = 2023-01-01. Databáza obsahuje zmluvy, ktoré boli
--     v zdroji zmenené od januára 2023. Zmluvy podpísané PRED rokom 2023
--     sú preto zastúpené len čiastočne. Všetky dotazy sú preto obmedzené
--     na signed_on >= 2023-01-01. Hlbšiu históriu z týchto dát nedostaneme.
--  2. Bežiaci kvartál je vždy nedokončený a CRZ zverejňuje s odstupom,
--     takže posledné dva riadky trendu budú podhodnotené. Neinterpretuj
--     ich ako pokles.
--  3. Filter samosprávy je hrubý — kopíruje _je_samosprava() z pipeline.
--     Zachytí obce, mestá, kraje, školy, nemocnice a domovy. Dotácie
--     firmám sú tu úmyselne vynechané: firma obstarávať nemusí.
-- ════════════════════════════════════════════════════════════════════════


-- ─── DOTAZ 1 ────────────────────────────────────────────────────────────
-- Prítok nových dotácií po kvartáloch.
-- Toto je hlavná otázka: prichádzajú nové dotácie stále, alebo prítok
-- vysychá? Ak je počet za kvartál stabilný, vrstva má zásobu bez ohľadu
-- na to, že jednotlivá dotácia sa neopakuje.
with d as (
  select
    c.id,
    c.signed_on,
    c.price_total as suma,
    c.supplier_name,
    coalesce(nullif(trim(c.supplier_cin), ''), lower(c.supplier_name)) as prijimatel_kluc
  from public.contracts c
  where c.sector = 'DOTACIE_NFP'
    and c.signed_on >= date '2023-01-01'
    and c.price_total >= 20000
    and c.supplier_name ~* '(obec |mesto |mestsk[aá] ?[cč]as[tť]|samospr[aá]vny kraj|vy[sš][sš][ií] [uú]zemn[yý] celok|z[aá]kladn[aá] [sš]kola|matersk[aá] [sš]kola|stredn[aá] [sš]kola|gymn[aá]zium|domov soci[aá]lnych|nemocnica|poliklinika)'
)
select
  extract(year from signed_on)::int || '-Q' || extract(quarter from signed_on)::int
    as kvartal,
  count(*)                                    as pocet_dotacii,
  count(distinct prijimatel_kluc)              as prijimatelov,
  round(sum(suma) / 1000000.0, 1)              as objem_mil_eur,
  round(avg(suma))                             as priemerna_dotacia_eur
from d
group by extract(year from signed_on), extract(quarter from signed_on)
order by extract(year from signed_on), extract(quarter from signed_on);


-- ─── DOTAZ 2 ────────────────────────────────────────────────────────────
-- Opakovanie na úrovni prijímateľa.
-- Ak väčšina obcí dostane za 3,7 roka jedinú dotáciu, prijímateľ nie je
-- opakujúci sa signál a sledovať treba dotáciu. Ak sa objem koncentruje
-- do obcí s viacerými dotáciami, prijímateľ je entita, ktorú má zmysel
-- sledovať dlhodobo — a firma, ktorá tam raz vyhrá, má výhodu nabudúce.
with d as (
  select
    c.price_total as suma,
    c.supplier_name,
    coalesce(nullif(trim(c.supplier_cin), ''), lower(c.supplier_name)) as prijimatel_kluc
  from public.contracts c
  where c.sector = 'DOTACIE_NFP'
    and c.signed_on >= date '2023-01-01'
    and c.price_total >= 20000
    and c.supplier_name ~* '(obec |mesto |mestsk[aá] ?[cč]as[tť]|samospr[aá]vny kraj|vy[sš][sš][ií] [uú]zemn[yý] celok|z[aá]kladn[aá] [sš]kola|matersk[aá] [sš]kola|stredn[aá] [sš]kola|gymn[aá]zium|domov soci[aá]lnych|nemocnica|poliklinika)'
),
poc as (
  select prijimatel_kluc, count(*) as dotacii, sum(suma) as objem
  from d group by prijimatel_kluc
),
b as (
  select
    objem,
    case when dotacii = 1 then 1 when dotacii = 2 then 2 when dotacii = 3 then 3
         when dotacii <= 6 then 4 else 5 end as poradie,
    case when dotacii = 1 then '1 dotácia'
         when dotacii = 2 then '2 dotácie'
         when dotacii = 3 then '3 dotácie'
         when dotacii <= 6 then '4 až 6 dotácií'
         else '7 a viac dotácií' end as skupina
  from poc
)
select
  b.skupina,
  count(*)                                                             as prijimatelov,
  round(100.0 * count(*) / (select count(*) from poc), 1)              as podiel_prijimatelov_pct,
  round(sum(b.objem) / 1000000.0, 1)                                   as objem_mil_eur,
  round(100.0 * sum(b.objem) / (select sum(objem) from poc), 1)        as podiel_objemu_pct
from b
group by b.poradie, b.skupina
order by b.poradie;


-- ─── DOTAZ 3 ────────────────────────────────────────────────────────────
-- Odstup medzi dvomi dotáciami toho istého prijímateľa.
-- Ak je medián okolo roka, obec s dotáciou je opakujúci sa zdroj práce
-- a stojí za to postaviť nad prijímateľom profil. Ak je to tri roky
-- a viac, na dĺžku predplatného to nestačí.
with d as (
  select
    c.signed_on,
    coalesce(nullif(trim(c.supplier_cin), ''), lower(c.supplier_name)) as prijimatel_kluc
  from public.contracts c
  where c.sector = 'DOTACIE_NFP'
    and c.signed_on >= date '2023-01-01'
    and c.price_total >= 20000
    and c.supplier_name ~* '(obec |mesto |mestsk[aá] ?[cč]as[tť]|samospr[aá]vny kraj|vy[sš][sš][ií] [uú]zemn[yý] celok|z[aá]kladn[aá] [sš]kola|matersk[aá] [sš]kola|stredn[aá] [sš]kola|gymn[aá]zium|domov soci[aá]lnych|nemocnica|poliklinika)'
),
s as (
  select
    signed_on,
    lag(signed_on) over (partition by prijimatel_kluc order by signed_on) as predchadzajuca
  from d
)
select
  count(*)                                                                as pocet_odstupov,
  round(percentile_cont(0.25) within group (order by (signed_on - predchadzajuca))) as p25_dni,
  round(percentile_cont(0.50) within group (order by (signed_on - predchadzajuca))) as median_dni,
  round(percentile_cont(0.75) within group (order by (signed_on - predchadzajuca))) as p75_dni
from s
where predchadzajuca is not null;


-- ─── DOTAZ 4 ────────────────────────────────────────────────────────────
-- Kto dotácie poskytuje.
-- Toto meria závislosť od jedného zdroja peňazí. Ak väčšinu objemu
-- rozdáva pár ministerstiev spravujúcich eurofondové programy, vrstva
-- kopíruje sedemročný cyklus EÚ a po skončení programu vysychá.
-- Ak je objem rozložený aj na národné fondy, prítok je stabilnejší.
with d as (
  select
    c.authority_name as poskytovatel,
    c.price_total    as suma
  from public.contracts c
  where c.sector = 'DOTACIE_NFP'
    and c.signed_on >= date '2023-01-01'
    and c.price_total >= 20000
    and c.supplier_name ~* '(obec |mesto |mestsk[aá] ?[cč]as[tť]|samospr[aá]vny kraj|vy[sš][sš][ií] [uú]zemn[yý] celok|z[aá]kladn[aá] [sš]kola|matersk[aá] [sš]kola|stredn[aá] [sš]kola|gymn[aá]zium|domov soci[aá]lnych|nemocnica|poliklinica|poliklinika)'
)
select
  poskytovatel,
  count(*)                                                        as dotacii,
  round(sum(suma) / 1000000.0, 1)                                 as objem_mil_eur,
  round(100.0 * sum(suma) / (select sum(suma) from d), 1)         as podiel_objemu_pct
from d
group by poskytovatel
order by sum(suma) desc
limit 15;


-- ─── DOTAZ 5 ────────────────────────────────────────────────────────────
-- Zásoba, ktorú portál práve teraz drží.
-- Dotaz 1 hovorí, či prítok pokračuje. Tento hovorí, na koľko mesiacov
-- dopredu máme čo zobrazovať. Ak posledný riadok padne do najbližších
-- dvoch kvartálov, zásoba sa vypredáva a nová nedobieha.
select
  extract(year from okno_od)::int || '-Q' || extract(quarter from okno_od)::int
    as okno_zacina,
  count(*)                        as dotacii,
  round(sum(suma) / 1000000.0, 1) as objem_mil_eur
from public.subsidies
group by extract(year from okno_od), extract(quarter from okno_od)
order by extract(year from okno_od), extract(quarter from okno_od);
