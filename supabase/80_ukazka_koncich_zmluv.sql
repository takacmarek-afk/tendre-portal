-- =============================================================================
--  80 — UKAZKA 3 KONCIACICH ZMLUV NA WEBE (audit 13.10.2026)
--  Vloz do Supabase: SQL Editor -> New query -> Run. Spustit sa da opakovane.
--
--  Navstevnik uvodnej stranky vyberie odbor a kraj a hned uvidi 3 realne
--  konciace zmluvy, bez registracie. Vola sa len cez Edge Function
--  verejny-formular (typ "ukazka_zmluv": Turnstile + limit na IP), anon ani
--  prihlaseny pouzivatel ju priamo volat nemoze (rovnaky vzor ako migracia 69).
--
--  Vracia najviac 3 zaznamy a pocet vsetkych vyhovujucich (haczik "a dalsich N").
--  Nevracia meno dodavatela, len urad, predmet, koniec zmluvy, cenu a odkaz do CRZ.
-- =============================================================================

create or replace function public.ukazka_koncich_zmluv(p_sektor text, p_kraj text default null)
returns jsonb
language sql
stable
security definer
set search_path = public
as $$
with kandidati as (
    select o.contract_id, o.authority_name, o.subject, o.effective_to, o.price_total, o.odkaz, o.skore
      from public.opportunities o
     where o.sector = p_sektor
       and o.sector <> 'DOTACIE_NFP'
       and (p_kraj is null or o.kraj = p_kraj)
       and o.effective_to between current_date + 30 and current_date + 365
       and o.authority_name is not null
       and o.subject is not null
),
top3 as (
    select * from kandidati order by skore desc nulls last, effective_to limit 3
)
select jsonb_build_object(
    'celkom', (select count(*) from kandidati),
    'zoznam', coalesce((
        select jsonb_agg(jsonb_build_object(
                   'urad', authority_name,
                   'predmet', left(replace(subject, E'\n', ' '), 140),
                   'koniec', effective_to,
                   'cena', price_total,
                   'odkaz', coalesce(odkaz, 'https://www.crz.gov.sk/zmluva/' || contract_id || '/'))
               order by skore desc nulls last, effective_to)
          from top3), '[]'::jsonb)
);
$$;

revoke all on function public.ukazka_koncich_zmluv(text, text) from public, anon, authenticated;
grant execute on function public.ukazka_koncich_zmluv(text, text) to service_role;

select 'Migracia 80 hotova: ukazka_koncich_zmluv (len cez Edge Function).' as vysledok;
