-- =============================================================================
--  TRIAL: 3 dni, jeden na firmu (IČO) navždy
--  Vloz do Supabase: SQL Editor -> New query -> Run. Spustit sa da opakovane.
-- =============================================================================

-- 1. Trial sa skracuje z 30 na 3 dni --------------------------------------
alter table public.subscriptions
    alter column trial_konci set default (now() + interval '3 days');

-- 2. Historia trialov -----------------------------------------------------
-- Zamerne SAMOSTATNA tabulka, nie priznak v organizations. Keby sa firma
-- niekedy zmazala, zaznam o vycerpanom triale musi prezit — inak sa trial
-- da resetovat zmazanim a znovuzalozenim firmy.
create table if not exists public.trial_history (
    ico           text primary key,
    prvy_trial_od timestamptz not null default now(),
    org_id        uuid references public.organizations(id) on delete set null
);

alter table public.trial_history enable row level security;
-- Ziadna politika = cita a zapisuje len service_role a security definer
-- funkcie. Klient sa k tomu nedostane, a to je zamer.

-- Doplnenie historie pre firmy, ktore uz v systeme su
insert into public.trial_history (ico, prvy_trial_od, org_id)
select o.ico, o.created_at, o.id
from public.organizations o
where o.ico is not null
  and not exists (select 1 from public.trial_history t where t.ico = o.ico)
on conflict (ico) do nothing;

-- 3. Zakladanie firmy s kontrolou IČO -------------------------------------
-- Vracia jsonb, nie uuid, aby frontend vedel rozlisit dovod odmietnutia
-- a zobrazit spravnu spravu.
--
-- POZOR: `create or replace` nedokaze zmenit navratovy typ funkcie. Povodna
-- verzia vracala uuid, tato vracia jsonb — bez tohto DROP by Postgres
-- odmietol zmenu chybou 42P13.
drop function if exists public.zaloz_organizaciu(text, text);

create function public.zaloz_organizaciu(p_nazov text, p_ico text)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_ico    text;
    v_org_id uuid;
    v_nazov  text;
    v_stav   text;
    v_konci  timestamptz;
begin
    if auth.uid() is null then
        return jsonb_build_object('ok', false, 'kod', 'NEPRIHLASENY');
    end if;

    -- IČO normalizujeme na 8 cislic. "47 586 362", "SK47586362" aj
    -- "47586362" musia byt ta ista firma, inak je kontrola na nic.
    v_ico := regexp_replace(coalesce(p_ico, ''), '\D', '', 'g');
    if length(v_ico) <> 8 then
        return jsonb_build_object('ok', false, 'kod', 'ICO_NEPLATNE');
    end if;

    if exists (select 1 from public.memberships where user_id = auth.uid()) then
        return jsonb_build_object('ok', false, 'kod', 'UZ_V_FIRME');
    end if;

    select o.id, o.nazov into v_org_id, v_nazov
    from public.organizations o where o.ico = v_ico;

    -- ── Firma uz v systeme je ────────────────────────────────────────────
    if v_org_id is not null then
        select s.stav, s.trial_konci into v_stav, v_konci
        from public.subscriptions s where s.org_id = v_org_id;

        -- Plati alebo ma bezici trial -> nового kolegu pripojime.
        -- Toto je dolezite: inak by sme odmietli druheho cloveka z firmy,
        -- ktora nam prave plati.
        if v_stav = 'aktivne' or (v_stav = 'trial' and v_konci > now()) then
            insert into public.memberships (user_id, org_id, rola)
            values (auth.uid(), v_org_id, 'member');

            insert into public.events (org_id, user_id, typ, detail)
            values (v_org_id, auth.uid(), 'clen_pripojeny',
                    jsonb_build_object('ico', v_ico));

            return jsonb_build_object('ok', true, 'kod', 'PRIPOJENY',
                                      'org_id', v_org_id);
        end if;

        -- Trial vyprsal a nikto neplati.
        return jsonb_build_object('ok', false, 'kod', 'TRIAL_VYCERPANY');
    end if;

    -- ── Firma tu nie je, ale IČO uz raz trial malo ───────────────────────
    if exists (select 1 from public.trial_history where ico = v_ico) then
        return jsonb_build_object('ok', false, 'kod', 'TRIAL_VYCERPANY');
    end if;

    -- ── Nova firma, spustame 3-dnovy trial ───────────────────────────────
    insert into public.organizations (nazov, ico)
    values (nullif(trim(p_nazov), ''), v_ico)
    returning id into v_org_id;

    insert into public.memberships (user_id, org_id, rola)
    values (auth.uid(), v_org_id, 'owner');

    insert into public.subscriptions (org_id, trial_konci)
    values (v_org_id, now() + interval '3 days');

    insert into public.trial_history (ico, org_id)
    values (v_ico, v_org_id);

    insert into public.events (org_id, user_id, typ, detail)
    values (v_org_id, auth.uid(), 'org_vytvorena',
            jsonb_build_object('nazov', p_nazov, 'ico', v_ico));

    return jsonb_build_object('ok', true, 'kod', 'TRIAL_SPUSTENY',
                              'org_id', v_org_id,
                              'trial_konci', now() + interval '3 days');
end;
$$;

select 'Trial nastaveny na 3 dni, jeden na ICO.' as vysledok;
