-- ════════════════════════════════════════════════════════════════════════
--  JEDNORAZOVE DOCISTENIE HTML ENTIT V `contracts`
--
--  Toto NIE JE migracia schemy, je to JEDNORAZOVA UPRAVA DAT. Spusti ju
--  Marek, nie pipeline.
--
--  PRECO je to potrebne: od 16. 9. 2026 ciste entity uz pri ukladani
--  (crz._text), takze nove a znovu stiahnute zmluvy su v poriadku. Ale
--  `contracts` sa NEPREPOCITAVA — plni sa len pri stahovani. Existujuce
--  zaznamy teda entity podrzia, kym CRZ tu konkretnu zmluvu neaktualizuje.
--
--  `opportunities` a `subsidies` sa prepocitavaju, takze tie sa vycistia
--  samy pri najblizsom behu. Toto je len o zdrojovej tabulke.
--
--  BEZPECNOST: menia sa len riadky, ktore entitu naozaj obsahuju, a menia
--  sa len tie tri textove polia. Ziadne mazanie, ziadna zmena schemy.
--  Spustit sa da opakovane — druhy raz uz nenajde nic.
--
--  POZOR na poradie zamien: `&amp;` MUSI byt POSLEDNE. Keby slo prve,
--  z `&amp;quot;` by vzniklo `&quot;` a dalsia zamena by z toho urobila
--  uvodzovku — teda by sa dvojito zakodovany retazec dekodoval o jedno
--  kolo viac, nez ma. To je ta ista pastca, aku ma `odkoduj_entity`
--  v Pythone riesenu opakovanym dekodovanim.
-- ════════════════════════════════════════════════════════════════════════

-- Kolko riadkov je zasiahnutych PRED upravou.
select 'PRED: riadkov s entitou v subject = '
       || count(*) filter (where subject ~ '&(quot|amp|lt|gt|nbsp|apos|#\d+);?')::text
       || ', v subject_description = '
       || count(*) filter (where subject_description ~ '&(quot|amp|lt|gt|nbsp|apos|#\d+);?')::text
       || ', v authority_name = '
       || count(*) filter (where authority_name ~ '&(quot|amp|lt|gt|nbsp|apos|#\d+);?')::text
       as stav
  from public.contracts;

-- ── Samotne docistenie ──────────────────────────────────────────────────
create or replace function public._odkoduj_entity(t text)
returns text language sql immutable as $$
    select case when t is null then null else
        replace(
        replace(
        replace(
        replace(
        replace(
        replace(
        replace(t, '&quot;',  '"'),
                   '&#39;',   ''''),
                   '&apos;',  ''''),
                   '&lt;',    '<'),
                   '&gt;',    '>'),
                   '&nbsp;',  ' '),
                   '&amp;',   '&')   -- MUSI byt posledne, viz hlavicka
    end
$$;

update public.contracts
   set subject             = public._odkoduj_entity(subject),
       subject_description = public._odkoduj_entity(subject_description),
       authority_name      = public._odkoduj_entity(authority_name),
       supplier_name       = public._odkoduj_entity(supplier_name)
 where subject             ~ '&(quot|amp|lt|gt|nbsp|apos|#\d+);?'
    or subject_description ~ '&(quot|amp|lt|gt|nbsp|apos|#\d+);?'
    or authority_name      ~ '&(quot|amp|lt|gt|nbsp|apos|#\d+);?'
    or supplier_name       ~ '&(quot|amp|lt|gt|nbsp|apos|#\d+);?';

-- Druhe kolo na dvojite zakodovanie (`&amp;quot;` -> `&quot;` -> `"`).
update public.contracts
   set subject             = public._odkoduj_entity(subject),
       subject_description = public._odkoduj_entity(subject_description),
       authority_name      = public._odkoduj_entity(authority_name),
       supplier_name       = public._odkoduj_entity(supplier_name)
 where subject             ~ '&(quot|amp|lt|gt|nbsp|apos|#\d+);?'
    or subject_description ~ '&(quot|amp|lt|gt|nbsp|apos|#\d+);?'
    or authority_name      ~ '&(quot|amp|lt|gt|nbsp|apos|#\d+);?'
    or supplier_name       ~ '&(quot|amp|lt|gt|nbsp|apos|#\d+);?';

drop function if exists public._odkoduj_entity(text);

-- Kontrola PO uprave. Ma vyjst same nuly.
select 'PO: subject = '
       || count(*) filter (where subject ~ '&(quot|amp|lt|gt|nbsp|apos|#\d+);?')::text
       || ', subject_description = '
       || count(*) filter (where subject_description ~ '&(quot|amp|lt|gt|nbsp|apos|#\d+);?')::text
       || ', authority_name = '
       || count(*) filter (where authority_name ~ '&(quot|amp|lt|gt|nbsp|apos|#\d+);?')::text
       || ', supplier_name = '
       || count(*) filter (where supplier_name ~ '&(quot|amp|lt|gt|nbsp|apos|#\d+);?')::text
       || '   (MAJU BYT SAME NULY)'
       as stav
  from public.contracts;
