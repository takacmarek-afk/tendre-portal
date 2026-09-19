-- =============================================================================
--  OPRAVA: ma_pro() a ma_pro_pre_org() nepoznali plany 'growth'/'team'/'admin'
--  Vloz do Supabase: SQL Editor -> New query -> Run. Spustit sa da opakovane.
-- =============================================================================
--
--  NALEZ (18.9.2026, jedenasta vlna)
--  29_platby.sql rozsiril subscriptions_plan_check o 'growth'/'team'/'admin',
--  ale ma_pro() (08_zadarmo.sql) aj ma_pro_pre_org() (25_odber_pro_gating.sql)
--  stale kontroluju len `plan in ('trial', 'pro')`. Kym je_zadarmo() vracia
--  true, chyba je uplne mrtva (ma_pro() = je_zadarmo() OR ...) — nikto si ju
--  nevsimol, lebo kazdy ma teraz vsetko odomknute bez ohladu na plan.
--
--  Ale v momente, ked sa je_zadarmo() prepne na false, by kazdy skutocny
--  platiaci zakaznik na Growth alebo Team (vyssie urovne nez Pro) prisiel
--  o pristup k profilom dodavatelov, cenovemu benchmarku, sanci na vyhru aj
--  k dennemu digestu/webhooku — presne tie funkcie, za ktore plati. Pro je
--  najnizsia platena uroven, Growth a Team ju musia obsahovat tiez.
--
--  OPRAVA: pridat 'growth', 'team', 'admin' do oboch funkcii. Ziadna zmena
--  spravania pocas otvoreneho obdobia (je_zadarmo() vyhrava OR-om aj tak).
-- =============================================================================

create or replace function public.ma_pro()
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
    select public.je_zadarmo()
        or (public.ma_aktivny_pristup()
            and exists (
                select 1
                  from public.subscriptions s
                  join public.memberships m on m.org_id = s.org_id
                 where m.user_id = auth.uid()
                   and s.plan in ('trial', 'pro', 'growth', 'team', 'admin')
            ));
$$;

grant execute on function public.ma_pro() to authenticated;

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
                   and s.plan in ('trial', 'pro', 'growth', 'team', 'admin')
            )
        );
$$;

grant execute on function public.ma_pro_pre_org(uuid) to authenticated, service_role;

select 'ma_pro() a ma_pro_pre_org() opravene: growth/team/admin su odteraz Pro-uroven a vyssie.' as vysledok;
