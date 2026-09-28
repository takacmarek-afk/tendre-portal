-- =============================================================================
--  52 — DOPYTY OD OBCÍ V PLATENEJ APPKE (audit 27. 9. 2026, P2.2)
--  Marekovo rozhodnutie (predtendrom-plan-obce-marketplace.md,
--  claude/predtendrom-audit-2026-09-27-stav.md): detail dopytov obcí
--  v app.html vidia Growth, Team a nový plán Poradca (cena 59 €/mesiac,
--  590 €/rok — v public/plany.js a v cenove_plany, doplnené migráciou 50).
--
--  Toto je ČISTO PRÍDAVOK k 34_obce_marketplace.sql — nemení žiadnu
--  existujúcu tabuľku, funkciu ani politiku, len PRIDÁVA:
--   1. novú funkciu ma_dopyty_pristup() (rovnaký vzor ako ma_pro()/ma_team())
--   2. jednu ďalšiu podmienku (OR) do existujúcej politiky dopyty_select,
--      aby otvorené dopyty videli aj platiaci Growth/Team/Poradca
--      zákazníci appky, nielen tí, čo si na trh.html založili bezplatný
--      profil poradcu (je_poradca()) — obe cesty platia súčasne.
--  Odpovedanie (reaguj_na_dopyt) sa nemení a naďalej vyžaduje profil
--  poradcu — appka na to len odkazuje na trh.html (zámerne, aby appka
--  neduplikovala už hotový a otestovaný flow založenia profilu a reakcie).
--  Spustiť sa dá opakovane.
-- =============================================================================

create or replace function public.ma_dopyty_pristup()
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
                   and s.plan in ('growth', 'team', 'poradca', 'admin')
            ));
$$;

grant execute on function public.ma_dopyty_pristup() to authenticated;

drop policy if exists dopyty_select on public.dopyty;
create policy dopyty_select on public.dopyty
    for select to authenticated
    using (
        obec_id = public.moj_obec_id()
        or (stav = 'otvoreny' and public.je_poradca())
        or (stav = 'otvoreny' and public.ma_dopyty_pristup())
    );

select 'ma_dopyty_pristup=' ||
       (select exists (select 1 from pg_proc p join pg_namespace n on n.oid = p.pronamespace
                         where n.nspname = 'public' and p.proname = 'ma_dopyty_pristup'))::text
    || ' | policies_dopyty=' ||
       (select count(*) from pg_policies where schemaname = 'public' and tablename = 'dopyty')::text
    as vysledok;
