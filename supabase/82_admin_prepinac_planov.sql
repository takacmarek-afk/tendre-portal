-- =============================================================================
--  82 — ADMIN: PREPINAC PLANOV (22. 10. 2026)
--
--  Marek (je_admin() = pevny e-mail takac.marek@gmail.com, 27_navstevnost.sql)
--  si v appke vie prepnut plan VLASTNEJ firmy na trial / Start / Growth /
--  Team / Poradca / Admin a vidiet appku presne tak, ako ju vidi zakaznik
--  s tym planom. Prepina sa skutocny riadok v subscriptions, takze o pristupe
--  dalej rozhoduje ta ista RLS ako u zakaznikov (ziadna klientska simulacia).
--
--  Bezpecnost:
--   - funkciu smie volat len je_admin(); ina ucty dostanu NIE_ADMIN,
--   - meni len firmy, v ktorych je admin vlastnik alebo admin (nie cudzie),
--   - zaplatene plany sa nastavia bez konca obdobia (obdobie_konci = null),
--     preto nepride pripomienka obnovy (pripomienky_obnovy() ich preskoci),
--   - kazde prepnutie sa zapise do events (typ 'admin_prepnutie_planu').
--  Prepinac v appke funguje na kazdom plane, aj na Start a Poradca, lebo
--  overuje e-mail, nie plan.
--
--  Idempotentne.
-- =============================================================================

create or replace function public.admin_prepni_plan(p_plan text)
returns jsonb
language plpgsql
volatile
security definer
set search_path = ''
as $$
declare
    v_uid    uuid := auth.uid();
    v_pocet  int  := 0;
    r        record;
begin
    if not public.je_admin() then
        raise exception 'NIE_ADMIN: prepinac planov je len pre spravcu PredTendrom.sk.'
            using errcode = '42501';
    end if;

    if p_plan is null or p_plan not in ('trial', 'start', 'growth', 'team', 'poradca', 'admin') then
        raise exception 'ZLY_PLAN: %', coalesce(p_plan, 'null')
            using errcode = '22023';
    end if;

    for r in
        select s.org_id, s.plan as stary_plan, s.stav as stary_stav
          from public.subscriptions s
          join public.memberships m on m.org_id = s.org_id
         where m.user_id = v_uid
           and m.rola in ('owner', 'admin')
           for update of s
    loop
        if p_plan = 'trial' then
            update public.subscriptions
               set plan = 'trial',
                   stav = 'trial',
                   trial_konci = now() + interval '14 days',
                   obdobie_konci = null,
                   updated_at = now()
             where org_id = r.org_id;
        else
            update public.subscriptions
               set plan = p_plan,
                   stav = 'aktivne',
                   obdobie_konci = null,
                   updated_at = now()
             where org_id = r.org_id;
        end if;

        insert into public.events (org_id, user_id, typ, detail)
        values (r.org_id, v_uid, 'admin_prepnutie_planu',
                jsonb_build_object('z', r.stary_plan, 'z_stav', r.stary_stav, 'na', p_plan));

        v_pocet := v_pocet + 1;
    end loop;

    if v_pocet = 0 then
        raise exception 'BEZ_FIRMY: admin nie je vlastnikom ziadnej firmy.'
            using errcode = 'P0002';
    end if;

    return jsonb_build_object('ok', true, 'plan', p_plan, 'firmy', v_pocet);
end;
$$;

revoke all on function public.admin_prepni_plan(text) from public, anon;
grant execute on function public.admin_prepni_plan(text) to authenticated;

select 'Migracia 82 hotova: admin_prepni_plan() pre je_admin().' as vysledok;
