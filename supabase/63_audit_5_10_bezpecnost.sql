-- =============================================================================
--  63 — AUDIT 5. 10. 2026: bezpečnosť verejných formulárov, členstvo vo firme,
--       limit reakcií, súkromie poradcov, double opt-in pre obce
--  Vlož do Supabase: SQL Editor -> New query -> Run. Spustiť sa dá opakovane.
-- =============================================================================
--
--  Čo táto migrácia rieši (čísla = audit 5. 10. 2026, projektový doc
--  "predtendrom-audit-2026-10-05-hlbkovy-pred-spustenim"):
--
--   K3 + V2  Verejné formuláre (servisne_dopyty, spatne_volania, odber_obce,
--            navstevy): anonym smie vložiť LEN stĺpce, ktoré formulár naozaj
--            posiela (stĺpcové granty), takže si nevie nastaviť schvaleny,
--            vybavene, token ani potvrdeny. Navyše limity dĺžky (CHECK) a
--            poistka proti záplave (max. riadkov za hodinu na tabuľku).
--   V1       odber_obce: double opt-in. Nový riadok je potvrdeny=false, kým
--            adresa nepotvrdí odkaz z e-mailu (token, RPC potvrd/odhlas).
--   K1       zaloz_organizaciu už NEPRIPÁJA nikoho do cudzej firmy len za
--            zadané IČO (vráti FIRMA_UZ_EXISTUJE). Kontrola kontrolnej číslice
--            IČO. org_update len pre vlastníka. Vlastník môže odobrať člena.
--   K4       reaguj_na_dopyt: najviac 5 poradcov na jeden dopyt.
--   V3       Kontakty poradcov vidí len ich vlastník a obec, ktorej poradca
--            odpovedal na dopyt (nie každý prihlásený používateľ).
--   V4       odber.email musí zodpovedať e-mailu prihláseného používateľa.
--   U10      hladaj_obec ignoruje diakritiku a nezlučuje rovnomenné obce
--            z rôznych krajov.
--
--  Všetko je spätne kompatibilné s doterajším frontendom okrem K1 (nový kód
--  FIRMA_UZ_EXISTUJE) — preto sa táto migrácia spúšťa PRED nasadením nového
--  frontendu a nový frontend s ňou počíta.
-- =============================================================================


-- ═════════════════════════════════════════════════════════════════════════
--  1) VEREJNÉ FORMULÁRE: stĺpcové granty (K3, V2)
-- ═════════════════════════════════════════════════════════════════════════
-- Predtým: `grant insert` na celú tabuľku (Supabase default) + politika
-- `with check (true)` => anonym vedel poslať aj schvaleny=true, vybavene=true,
-- potvrdeny=true, vlastný token. Teraz: insert len do vymenovaných stĺpcov.

revoke insert on public.servisne_dopyty from anon, authenticated;
grant insert (obec, ico, kraj, kontakt_email, kontakt_telefon, popis, suhlas_zverejnit)
    on public.servisne_dopyty to anon, authenticated;

revoke insert on public.spatne_volania from anon, authenticated;
grant insert (meno, obec, telefon, najlepsi_cas)
    on public.spatne_volania to anon, authenticated;

revoke insert on public.odber_obce from anon, authenticated;
grant insert (email, obec, ico, kraj, zdroj)
    on public.odber_obce to anon, authenticated;

-- navstevy a udalosti (45_merania.sql) tu zamerne NEMENIME stlpcove granty:
-- analytika posiela aj session_id a utm_*, a tabulky nemaju ziadny stlpec,
-- ktory by si anonym vedel nastavit na svoj prospech. Chraní ich len CHECK
-- dlzky (nizsie) a strop vkladov.

-- Sekvencie (bigserial) musia ostať použiteľné pre insert.
grant usage on sequence public.servisne_dopyty_id_seq to anon, authenticated;
grant usage on sequence public.spatne_volania_id_seq  to anon, authenticated;
grant usage on sequence public.odber_obce_id_seq      to anon, authenticated;


-- ═════════════════════════════════════════════════════════════════════════
--  2) LIMITY DĹŽKY (CHECK ... NOT VALID = neskúma existujúce riadky,
--     platí pre všetky nové zápisy)
-- ═════════════════════════════════════════════════════════════════════════

alter table public.servisne_dopyty drop constraint if exists servisne_dopyty_dlzky;
alter table public.servisne_dopyty add constraint servisne_dopyty_dlzky check (
    char_length(obec) between 1 and 200
    and char_length(popis) between 1 and 4000
    and char_length(kontakt_email) between 5 and 254
    and kontakt_email like '%_@_%._%'
    and (ico is null or char_length(ico) <= 20)
    and (kraj is null or char_length(kraj) <= 80)
    and (kontakt_telefon is null or char_length(kontakt_telefon) <= 40)
) not valid;

alter table public.spatne_volania drop constraint if exists spatne_volania_dlzky;
alter table public.spatne_volania add constraint spatne_volania_dlzky check (
    char_length(meno) between 1 and 120
    and char_length(obec) between 1 and 200
    and char_length(telefon) between 5 and 40
    and (najlepsi_cas is null or char_length(najlepsi_cas) <= 200)
) not valid;

alter table public.odber_obce drop constraint if exists odber_obce_dlzky;
alter table public.odber_obce add constraint odber_obce_dlzky check (
    char_length(email) between 5 and 254
    and email like '%_@_%._%'
    and (obec is null or char_length(obec) <= 200)
    and (ico is null or char_length(ico) <= 20)
    and (kraj is null or char_length(kraj) <= 80)
    and (zdroj is null or char_length(zdroj) <= 80)
) not valid;

alter table public.navstevy drop constraint if exists navstevy_dlzky;
alter table public.navstevy add constraint navstevy_dlzky check (
    char_length(cesta) <= 1000
    and (referrer is null or char_length(referrer) <= 2000)
) not valid;


-- ═════════════════════════════════════════════════════════════════════════
--  3) POISTKA PROTI ZÁPLAVE (globálny strop riadkov za hodinu)
-- ═════════════════════════════════════════════════════════════════════════
-- Nie je to náhrada za captchu, ale zabráni tomu, aby jeden skript zaplnil
-- kvótu databázy (výpadok pre všetkých). Stropy sú o rád vyššie než reálna
-- prevádzka. SECURITY DEFINER, lebo anon nemá právo SELECT na tieto tabuľky.

create or replace function public._strop_vkladov()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_strop int := tg_argv[0]::int;
    v_pocet int;
begin
    execute format(
        'select count(*) from %I.%I where created_at > now() - interval ''1 hour''',
        tg_table_schema, tg_table_name
    ) into v_pocet;

    if v_pocet >= v_strop then
        raise exception 'Prilis vela poziadaviek. Skuste to prosim neskor.'
            using errcode = '54000';
    end if;
    return new;
end;
$$;

create index if not exists ix_servisne_dopyty_created on public.servisne_dopyty(created_at);
create index if not exists ix_spatne_volania_created   on public.spatne_volania(created_at);
create index if not exists ix_odber_obce_created       on public.odber_obce(created_at);

drop trigger if exists trg_strop_servisne_dopyty on public.servisne_dopyty;
create trigger trg_strop_servisne_dopyty before insert on public.servisne_dopyty
    for each row execute function public._strop_vkladov(60);

drop trigger if exists trg_strop_spatne_volania on public.spatne_volania;
create trigger trg_strop_spatne_volania before insert on public.spatne_volania
    for each row execute function public._strop_vkladov(60);

drop trigger if exists trg_strop_odber_obce on public.odber_obce;
create trigger trg_strop_odber_obce before insert on public.odber_obce
    for each row execute function public._strop_vkladov(300);

drop trigger if exists trg_strop_navstevy on public.navstevy;
create trigger trg_strop_navstevy before insert on public.navstevy
    for each row execute function public._strop_vkladov(20000);


-- ═════════════════════════════════════════════════════════════════════════
--  4) DOUBLE OPT-IN PRE ODBER OBCÍ (V1)
-- ═════════════════════════════════════════════════════════════════════════
-- Existujúce riadky ostávajú potvrdeny=true (už boli v zozname, nič sa im
-- nemení). NOVÉ riadky sú potvrdeny=false, kým adresa neklikne na odkaz.

alter table public.odber_obce alter column potvrdeny set default false;

alter table public.odber_obce
    add column if not exists token uuid not null default gen_random_uuid();
alter table public.odber_obce
    add column if not exists potvrdzovaci_email_at timestamptz;

create unique index if not exists ux_odber_obce_token on public.odber_obce(token);

-- Potvrdenie / odhlásenie odkazom z e-mailu. Token je neuhádnuteľný (UUID v4),
-- funkcie nevracajú e-mail ani žiadne iné údaje — len ok/nie.
create or replace function public.potvrd_odber_obce(p_token uuid)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_n int;
begin
    update public.odber_obce set potvrdeny = true where token = p_token;
    get diagnostics v_n = row_count;
    return v_n > 0;
end;
$$;

create or replace function public.odhlas_odber_obce(p_token uuid)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_n int;
begin
    delete from public.odber_obce where token = p_token;
    get diagnostics v_n = row_count;
    return v_n > 0;
end;
$$;

grant execute on function public.potvrd_odber_obce(uuid)  to anon, authenticated;
grant execute on function public.odhlas_odber_obce(uuid)  to anon, authenticated;


-- ═════════════════════════════════════════════════════════════════════════
--  5) K1: ČLENSTVO VO FIRME
-- ═════════════════════════════════════════════════════════════════════════

-- 5a) Kontrola kontrolnej číslice slovenského IČO (modulo 11).
create or replace function public._ico_platne(p_ico text)
returns boolean
language plpgsql
immutable
set search_path = ''
as $$
declare
    v_s int := 0;
    v_r int;
    v_c int;
    i   int;
begin
    if p_ico is null or p_ico !~ '^\d{8}$' then
        return false;
    end if;
    for i in 1..7 loop
        v_s := v_s + substr(p_ico, i, 1)::int * (9 - i);
    end loop;
    v_r := v_s % 11;
    v_c := (11 - v_r) % 10;
    return v_c = substr(p_ico, 8, 1)::int;
end;
$$;

-- 5b) zaloz_organizaciu: ŽIADNE automatické pripojenie k cudzej firme.
--     Telo je totožné s verziou z 42_trial_plan_default.sql (+ 50: 14 dní),
--     zmenené sú len dve veci: kontrola IČO a vetva "firma už existuje".
--     Trial dĺžku preberáme z existujúcej funkcie nepriamo: 14 dní (vlna 50).
create or replace function public.zaloz_organizaciu(p_nazov text, p_ico text)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_ico    text;
    v_org_id uuid;
begin
    if auth.uid() is null then
        return jsonb_build_object('ok', false, 'kod', 'NEPRIHLASENY');
    end if;

    v_ico := regexp_replace(coalesce(p_ico, ''), '\D', '', 'g');
    -- "SK" predpona a medzery odstráni regexp vyššie; DIČ "20xxxxxxxx" nie je IČO.
    if length(v_ico) <> 8 or not public._ico_platne(v_ico) then
        return jsonb_build_object('ok', false, 'kod', 'ICO_NEPLATNE');
    end if;

    if char_length(coalesce(p_nazov, '')) > 200 then
        return jsonb_build_object('ok', false, 'kod', 'NAZOV_DLHY');
    end if;

    if exists (select 1 from public.memberships where user_id = auth.uid()) then
        return jsonb_build_object('ok', false, 'kod', 'UZ_V_FIRME');
    end if;

    -- Firma s týmto IČO už v systéme je. NIKOHO nepripájame automaticky:
    -- IČO je verejný údaj, takže kto ho napíše, by inak dostal prístup k dátam
    -- cudzej firmy. Pripojiť sa dá len pozvánkou od vlastníka (prijmi_pozvanku).
    if exists (select 1 from public.organizations o where o.ico = v_ico) then
        return jsonb_build_object('ok', false, 'kod', 'FIRMA_UZ_EXISTUJE');
    end if;

    -- Firma tu nie je, ale IČO už raz skúšku malo.
    if exists (select 1 from public.trial_history where ico = v_ico) then
        return jsonb_build_object('ok', false, 'kod', 'TRIAL_VYCERPANY');
    end if;

    insert into public.organizations (nazov, ico)
    values (nullif(trim(p_nazov), ''), v_ico)
    returning id into v_org_id;

    insert into public.memberships (user_id, org_id, rola)
    values (auth.uid(), v_org_id, 'owner');

    insert into public.subscriptions (org_id, trial_konci, plan)
    values (v_org_id, now() + interval '14 days', 'trial');

    insert into public.trial_history (ico, org_id)
    values (v_ico, v_org_id);

    insert into public.events (org_id, user_id, typ, detail)
    values (v_org_id, auth.uid(), 'org_vytvorena',
            jsonb_build_object('nazov', p_nazov, 'ico', v_ico));

    return jsonb_build_object('ok', true, 'kod', 'TRIAL_SPUSTENY', 'org_id', v_org_id);
end;
$$;

grant execute on function public.zaloz_organizaciu(text, text) to authenticated;

-- 5c) organizations.update len pre vlastníka firmy (predtým ktorýkoľvek člen).
drop policy if exists org_update on public.organizations;
create policy org_update on public.organizations
    for update to authenticated
    using (
        id in (select m.org_id from public.memberships m
                where m.user_id = auth.uid() and m.rola = 'owner')
    )
    with check (
        id in (select m.org_id from public.memberships m
                where m.user_id = auth.uid() and m.rola = 'owner')
    );

-- 5d) Odobratie člena z firmy (len vlastník, nie seba, nie iného vlastníka).
create or replace function public.odober_clena_firmy(p_user_id uuid)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_org_id uuid;
    v_rola   text;
begin
    select m.org_id into v_org_id
      from public.memberships m
     where m.user_id = auth.uid() and m.rola = 'owner';
    if v_org_id is null then
        return jsonb_build_object('ok', false, 'kod', 'LEN_VLASTNIK');
    end if;

    if p_user_id = auth.uid() then
        return jsonb_build_object('ok', false, 'kod', 'SEBA_NIE');
    end if;

    select m.rola into v_rola
      from public.memberships m
     where m.user_id = p_user_id and m.org_id = v_org_id;
    if v_rola is null then
        return jsonb_build_object('ok', false, 'kod', 'NIE_JE_CLEN');
    end if;
    if v_rola = 'owner' then
        return jsonb_build_object('ok', false, 'kod', 'VLASTNIKA_NIE');
    end if;

    delete from public.memberships where user_id = p_user_id and org_id = v_org_id;

    insert into public.events (org_id, user_id, typ, detail)
    values (v_org_id, auth.uid(), 'clen_odobrany',
            jsonb_build_object('user_id', p_user_id));

    return jsonb_build_object('ok', true, 'kod', 'ODOBRANY');
end;
$$;

grant execute on function public.odober_clena_firmy(uuid) to authenticated;


-- ═════════════════════════════════════════════════════════════════════════
--  6) K4: NAJVIAC 5 PORADCOV NA JEDEN DOPYT
-- ═════════════════════════════════════════════════════════════════════════
-- Verejný sľub obciam: "odpovedať môže najviac 5 firiem". Teraz ho systém
-- naozaj dodrží. Úprava vlastnej existujúcej reakcie ostáva vždy možná.
-- Zámok riadku dopytu serializuje súbežné reakcie (inak by dvaja poradcovia
-- naraz prekročili strop).

create or replace function public.reaguj_na_dopyt(p_dopyt_id uuid, p_sprava text)
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_poradca_id uuid;
    v_pocet      int;
begin
    select id into v_poradca_id
      from public.poradcovia_profily where owner = auth.uid();

    if v_poradca_id is null then
        raise exception 'Nemas profil poradcu. Najprv si ho zaloz.';
    end if;
    if trim(coalesce(p_sprava, '')) = '' then
        raise exception 'Napis spravu.';
    end if;
    if char_length(p_sprava) > 4000 then
        raise exception 'Sprava je prilis dlha.';
    end if;

    perform 1 from public.dopyty
      where id = p_dopyt_id and stav = 'otvoreny'
      for update;
    if not found then
        raise exception 'Tento dopyt uz nie je otvoreny.';
    end if;

    if not exists (select 1 from public.reakcie
                    where dopyt_id = p_dopyt_id and poradca_id = v_poradca_id) then
        select count(*) into v_pocet from public.reakcie where dopyt_id = p_dopyt_id;
        if v_pocet >= 5 then
            raise exception 'Na tento dopyt uz odpovedalo maximalny pocet poradcov (5).';
        end if;
    end if;

    insert into public.reakcie (dopyt_id, poradca_id, sprava)
    values (p_dopyt_id, v_poradca_id, trim(p_sprava))
    on conflict (dopyt_id, poradca_id) do update
        set sprava = excluded.sprava, updated_at = now();
end;
$$;

grant execute on function public.reaguj_na_dopyt(uuid, text) to authenticated;


-- ═════════════════════════════════════════════════════════════════════════
--  7) V3: KONTAKTY PORADCOV NEVIDÍ KAŽDÝ PRIHLÁSENÝ
-- ═════════════════════════════════════════════════════════════════════════
-- Vidí ich: vlastník profilu a obec, ktorej poradca odpovedal na dopyt.
-- (trh.html číta poradcovia_profily len tými dvoma spôsobmi.)

create or replace function public.poradcovia_mojich_dopytov()
returns setof uuid
language sql
stable
security definer
set search_path = ''
as $$
    select r.poradca_id
      from public.reakcie r
      join public.dopyty d on d.id = r.dopyt_id
     where d.obec_id = public.moj_obec_id();   -- vlastnik aj pozvani clenovia obce (58)
$$;

grant execute on function public.poradcovia_mojich_dopytov() to authenticated;

drop policy if exists poradcovia_select on public.poradcovia_profily;
create policy poradcovia_select on public.poradcovia_profily
    for select to authenticated
    using (
        owner = auth.uid()
        or id in (select public.poradcovia_mojich_dopytov())
    );


-- ═════════════════════════════════════════════════════════════════════════
--  8) V4: ODBER — E-MAIL MUSÍ PATRIŤ PRIHLÁSENÉMU POUŽÍVATEĽOVI
-- ═════════════════════════════════════════════════════════════════════════
-- Zachované sú pôvodné podmienky z 43_start_kraj_sektor_limit.sql, pridaná je
-- jediná: email je buď prázdny, alebo sa rovná e-mailu z prihlásenia.

drop policy if exists odber_insert on public.odber;
create policy odber_insert on public.odber
    for insert to authenticated
    with check (
        user_id = auth.uid()
        and (email is null or lower(email) = lower(coalesce(auth.jwt() ->> 'email', '')))
        and (frekvencia is distinct from 'denne' or public.ma_pro())
        and (webhook_url is null or public.ma_pro())
        and (public.ma_pro() or (sektor is not null and kraj is not null))
    );

drop policy if exists odber_update on public.odber;
create policy odber_update on public.odber
    for update to authenticated
    using (user_id = auth.uid())
    with check (
        user_id = auth.uid()
        and (email is null or lower(email) = lower(coalesce(auth.jwt() ->> 'email', '')))
        and (frekvencia is distinct from 'denne' or public.ma_pro())
        and (webhook_url is null or public.ma_pro())
        and (public.ma_pro() or (sektor is not null and kraj is not null))
    );


-- ═════════════════════════════════════════════════════════════════════════
--  9) U10: VYHĽADÁVANIE OBCÍ BEZ OHĽADU NA DIAKRITIKU
-- ═════════════════════════════════════════════════════════════════════════
create extension if not exists unaccent with schema extensions;

create or replace function public.hladaj_obec(p_hladanie text)
returns table(nazov text, kraj text)
language sql
stable
security definer
set search_path = ''
as $$
    select distinct on (lower(n), kraj) n as nazov, kraj
    from (
        select public._obec_core_nazov(authority_name) as n, kraj
          from public.opportunities
         where trim(coalesce(p_hladanie, '')) <> ''
           and char_length(p_hladanie) <= 80
           and public._je_obec_nazov(authority_name)
           and extensions.unaccent(authority_name)
               ilike '%' || extensions.unaccent(trim(p_hladanie)) || '%'
        union all
        select public._obec_core_nazov(prijimatel) as n, kraj
          from public.subsidies
         where trim(coalesce(p_hladanie, '')) <> ''
           and char_length(p_hladanie) <= 80
           and public._je_obec_nazov(prijimatel)
           and extensions.unaccent(prijimatel)
               ilike '%' || extensions.unaccent(trim(p_hladanie)) || '%'
    ) s
    where n is not null and trim(n) <> ''
    order by lower(n), kraj nulls last
    limit 25;
$$;

grant execute on function public.hladaj_obec(text) to anon, authenticated;


select 'Migracia 63 hotova: stlpcove granty, limity, double opt-in, K1 (bez auto-pripojenia), limit 5 reakcii, sukromie poradcov, odber e-mail, hladaj_obec bez diakritiky.' as vysledok;
