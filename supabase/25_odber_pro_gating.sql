-- =============================================================================
--  DENNY DIGEST A WEBHOOK = GROWTH (platena vyhoda)
--  Vloz do Supabase: SQL Editor -> New query -> Run. Spustit sa da opakovane.
--  Spustaj PO 08_zadarmo.sql, 20_frekvencia_odberu.sql, 21_webhook_odberu.sql.
-- =============================================================================
--
--  CO TO JE
--  Rozhodnutie 17.9.2026 (audit + rozhovor s Marekom): denny e-mail a
--  Slack/Teams webhook (na rozdiel od tyzdenneho e-mailu, ktory zostava
--  sucastou aj Start planu) su vyhoda Growth planu. Doteraz to v databaze
--  nebolo nijak vynutene — hocikto si mohol v nastaveniach zapnut oboje
--  zadarmo.
--
--  DVE POLOVICE, LEBO JEDNA NESTACI
--  1) RLS `with check` nizsie zabrani NOVEMU zapisu frekvencia='denne'
--     alebo webhook_url bez Pro — ale iba pre klienta, ktory pise cez
--     anon/authenticated kluc (app.html). Je "dormant" v otvorenom
--     obdobi rovnako ako kazde ine public.ma_pro() gate (viz 08_zadarmo.sql)
--     — kym je_zadarmo() vracia true, ma_pro() je tiez vzdy true, teda
--     nikoho to este neobmedzuje.
--  2) `pipeline/posli_email.py` bezi pod SERVICE ROLE klucom, ktory RLS
--     obchadza uplne. Existujuci (stary) riadok s frekvencia='denne' by
--     teda RLS gate nizsie vobec nezastavil — pipeline by ho ticho poslal
--     dalej, aj ked uz organizacia nema Pro. Preto pridavame aj
--     `public.ma_pro_pre_org(uuid)`: rovnaka logika ako `ma_pro()`, ale
--     bez zavislosti na auth.uid() (ten je pod service_role prazdny) —
--     berie org_id ako parameter, aby ju vedel zavolat aj pipeline.
-- =============================================================================

-- ── 1. ma_pro_pre_org: rovnaka logika ako ma_pro(), pre pouzitie mimo
--       auth kontextu (service_role v pipeline nema auth.uid()) ──────────
create or replace function public.ma_pro_pre_org(p_org_id uuid)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
    select public.je_zadarmo()
        or (
            p_org_id is not null
            and exists (
                select 1
                  from public.subscriptions s
                 where s.org_id = p_org_id
                   and (s.stav = 'aktivne'
                        or (s.stav = 'trial' and s.trial_konci > now()))
                   and s.plan in ('trial', 'pro')
            )
        );
$$;

comment on function public.ma_pro_pre_org(uuid) is
    'Ako public.ma_pro(), ale pre volajuceho bez auth.uid() (service_role '
    'v pipeline/posli_email.py) — org_id sa odovzdava priamo.';

grant execute on function public.ma_pro_pre_org(uuid) to authenticated, service_role;

-- ── 2. RLS: frekvencia='denne' a webhook_url vyzaduju Pro ───────────────
--       (dormant, kym je_zadarmo() vracia true — presne ako inde)
drop policy if exists odber_insert on public.odber;
create policy odber_insert on public.odber
    for insert to authenticated
    with check (
        user_id = auth.uid()
        and (frekvencia is distinct from 'denne' or public.ma_pro())
        and (webhook_url is null or public.ma_pro())
    );

drop policy if exists odber_update on public.odber;
create policy odber_update on public.odber
    for update to authenticated
    using (user_id = auth.uid())
    with check (
        user_id = auth.uid()
        and (frekvencia is distinct from 'denne' or public.ma_pro())
        and (webhook_url is null or public.ma_pro())
    );

-- ── 3. KONTROLA ──────────────────────────────────────────────────────────
select proname, prosecdef
  from pg_proc
 where proname = 'ma_pro_pre_org' and pronamespace = 'public'::regnamespace;

select polname, pg_get_expr(polwithcheck, polrelid) as with_check
  from pg_policy
 where polrelid = 'public.odber'::regclass;

select 'Denny digest a webhook su teraz Growth-only (RLS + ma_pro_pre_org '
       'pre pipeline). Dormant, kym je_zadarmo() vracia true.' as vysledok;
