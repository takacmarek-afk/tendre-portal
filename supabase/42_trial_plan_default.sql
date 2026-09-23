-- =============================================================================
--  OPRAVA: subscriptions.plan nemá default, čerstvé trial organizácie
--  dostávajú plan=NULL namiesto plan='trial' — testovacie obdobie "nefunguje"
--  presne v tomto zmysle.
--  Vloz do Supabase: SQL Editor -> New query -> Run. Spustit sa da opakovane.
-- =============================================================================
--
--  NALEZ (zivy audit 22.9.2026, uz raz zaznamenany v predoslej vlne ako
--  "caka na Marekovo rozhodnutie" — teraz vyriesene v ramci "oprav vsetko")
--  schema.sql definuje `plan text` BEZ defaultu. 06_plany.sql sa neskor
--  pokusil pridat `not null default 'trial'` cez
--  `add column if not exists plan text not null default 'trial'` — ale
--  stlpec uz existoval (z schema.sql), takze `if not exists` tento prikaz
--  TICHO PRESKOCIL. Default sa teda nikdy naozaj nenastavil (overene naživo:
--  `information_schema.columns` ukazuje column_default = NULL, is_nullable
--  = YES, aj po 06_plany.sql). zaloz_organizaciu() (03_trial.sql) pri
--  zalozeni noveho trialu vklada riadok do subscriptions bez `plan` stlpca
--  vobec — novy trial teda dostane plan=NULL.
--
--  PRECO JE TO PROBLEM
--  Vsade v kode (ma_pro(), viz 06/07/31_oprava, aj komentare typu "skuska
--  (trial) dava Pro uroven") je zamerom, ze POCAS TRIALU vidi zakaznik
--  Growth-uroven funkcie (sledovanie, CRM, denny digest, sanca na vyhru,
--  trhovy podiel) — presny dovod, preco 'trial' je v zozname planov pre
--  ma_pro(). S plan=NULL sa ale ziadna z tychto podmienok nezhoduje: kym
--  je_zadarmo() vracia true je to mrtve (vsetci vidia vsetko), ale v
--  momente prepnutia by kazdy NOVY trial pouzivatel dostal len zakladny
--  (Start-ekvivalentny) pristup bez Growth funkcii — presny opak toho, co
--  ma trial ukazat, aby presvedcil zakaznika platit za Growth.
--
--  OPRAVA (dve casti, zamerne obe, nie len jedna)
--  1. Stlpec: spravny prikaz (alter column, nie add column if not exists)
--     nastavi default aj not null. Existujuce plan=NULL riadky (ak nejake
--     su) sa najprv zalohuju rovnakou logikou, aku uz raz pouzil 06_plany.sql
--     (trial -> 'trial', inak -> 'start').
--  2. Funkcia: zaloz_organizaciu() (presna kopia tela z 03_trial.sql, zmeneny
--     LEN jeden insert do subscriptions) explicitne zapisuje plan='trial'
--     pri vytvoreni — nespolieha sa uz len na stlpcovy default (rovnaky
--     princip explicitnosti ako zvysok tohto projektu).
-- =============================================================================

update public.subscriptions
   set plan = case when stav = 'trial' then 'trial' else 'start' end
 where plan is null or plan = '';

alter table public.subscriptions alter column plan set default 'trial';
alter table public.subscriptions alter column plan set not null;

create or replace function public.zaloz_organizaciu(p_nazov text, p_ico text)
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

    -- OPRAVA 22.9.2026: plan='trial' teraz explicitne (viz komentar na
    -- zaciatku suboru) — predtym tu chybal cely stlpec, spoliehalo sa
    -- (nespravne) na stlpcovy default, ktory nikdy naozaj nebol nastaveny.
    insert into public.subscriptions (org_id, trial_konci, plan)
    values (v_org_id, now() + interval '3 days', 'trial');

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

select column_name, column_default, is_nullable
  from information_schema.columns
 where table_schema = 'public' and table_name = 'subscriptions' and column_name = 'plan';

select 'subscriptions.plan ma odteraz naozaj default ''trial'' + not null, a '
       'zaloz_organizaciu() ho aj explicitne zapisuje. Novy trial teraz '
       'dostane Growth-uroven funkcie pocas skusobnych 3 dni, presne ako '
       'bolo zamyslane.' as vysledok;
