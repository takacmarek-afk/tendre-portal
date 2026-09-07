-- =============================================================================
--  PLANY: Start a Pro
--  Vloz do Supabase: SQL Editor -> New query -> Run. Spustit sa da opakovane.
--  Spustaj PO 05_analytika.sql.
-- =============================================================================
--
--  ROZHODNUTIE, PRECO SA ZAMYKA TOTO A NIE FILTRE
--
--  Filtre na kraj a sektor su sposob, ako zakaznik NAJDE svoju zakazku. Keby
--  boli za peniaze, zakladna verzia by bola zoznam 900 zakaziek z celeho
--  Slovenska, v ktorom stavbar z Presova nenajde nic — a nezaplati, pretoze
--  produkt mu nic neukazal. Filtre preto zostavaju kazdemu platicovi.
--
--  Za peniaze ide to, co zakaznik NEVIE zistit sam ani za pol dna prace:
--    - profily dodavatelov: kto pre stat robi najviac, u kolkych uradov,
--      a ako casto si po podpise priplaca dodatkami
--    - cenovy benchmark: medianna mesacna cena v sektore
--  Prve odpoveda na "kde mam prilezitost", druhe na "proti komu idem a za kolko".
--
--  Skusobne tri dni davaju Pro. Kto benchmark nikdy nevidel, nezaplati za neho.
-- =============================================================================

alter table public.subscriptions
    add column if not exists plan text not null default 'trial';

-- Existujuce zaznamy: trial ma Pro, aktivne bez planu davame na start.
update public.subscriptions
   set plan = case when stav = 'trial' then 'trial' else 'start' end
 where plan is null or plan = '';

alter table public.subscriptions drop constraint if exists subscriptions_plan_check;
alter table public.subscriptions add constraint subscriptions_plan_check
    check (plan in ('trial', 'start', 'pro'));


-- ── Ma prihlaseny pouzivatel Pro? ────────────────────────────────────────
-- Stavia na existujucej ma_aktivny_pristup(): bez aktivneho pristupu nie je
-- Pro ani ten, kto ho ma zaplateny. Trial je Pro zamerne.
create or replace function public.ma_pro()
returns boolean
language sql
stable
security definer
set search_path = public
as $$
    select public.ma_aktivny_pristup()
       and exists (
             select 1
               from public.subscriptions s
               join public.memberships m on m.org_id = s.org_id
              where m.user_id = auth.uid()
                and s.plan in ('trial', 'pro')
           );
$$;

grant execute on function public.ma_pro() to authenticated;


-- ── Pro-only tabulky ─────────────────────────────────────────────────────
drop policy if exists dodavatelia_select on public.dodavatelia;
create policy dodavatelia_select on public.dodavatelia
    for select to authenticated
    using (public.ma_pro());

drop policy if exists ceny_sektor_select on public.ceny_sektor;
create policy ceny_sektor_select on public.ceny_sektor
    for select to authenticated
    using (public.ma_pro());


-- ── Aby si plan videl aj prehliadac ──────────────────────────────────────
-- Politika na subscriptions uz existuje zo schema.sql; plan je novy stlpec
-- v tej istej tabulke, takze sa cita rovnako. Nic dalsie netreba.

select 'Plany pripravene. Trial = Pro. dodavatelia a ceny_sektor su Pro-only.' as vysledok;
