-- =============================================================================
--  67 — OVEROVANIE UCTOV OBCI (vlna 82, 6. 10. 2026; audit A6)
--
--  PROBLEM: ucet obce si mohol zalozit ktokolvek pod akymkolvek nazvom a jeho
--  dopyty sa hned rozosielali poradcom (e-mail "Obec Senec prave vypisala
--  dopyt") a vsetci poradcovia ich videli.
--
--  RIESENIE (hybrid, rozhodnutie Mareka 6. 10. 2026):
--   * ucet obce je predvolene NEOVERENY (obce_ucty.overena = false),
--   * overi sa AUTOMATICKY, ked e-mail prihlaseneho uctu (potvrdeny kodom
--     z e-mailu) sedi s uradnym kontaktom obce z nasho zoznamu
--     kampan_obce_kontakty (stav 'ok') pre zadane ICO: bud presna zhoda adresy,
--     alebo rovnaka domena (ale NIE bezna schranka typu gmail/centrum),
--   * inak caka na RUCNE schvalenie: select public.schval_obec('<id>');
--   * dopyt neoverenej obce sa uklada (obec ho vidi), ale poradcom sa
--     nezobrazuje, nerozosiela a nemozu naň odpovedat, kym sa obec neoveri
--     (dopyty.overeny). Po schvaleni obce sa jej dopyty uvolnia a bezny
--     e-mailovy cron ich rozosle.
--
--  Idempotentne. V produkcii je v case migracie 0 uctov obci a 0 dopytov,
--  takze nie je co dopocitavat.
-- =============================================================================

-- ── 1) Stlpce ────────────────────────────────────────────────────────────────
alter table public.obce_ucty
    add column if not exists overena         boolean     not null default false,
    add column if not exists overena_at      timestamptz,
    add column if not exists overena_sposob  text;

alter table public.obce_ucty drop constraint if exists obce_ucty_overena_sposob;
alter table public.obce_ucty add constraint obce_ucty_overena_sposob
    check (overena_sposob is null or overena_sposob in ('auto_email', 'rucne'));

do $$
begin
    if not exists (select 1 from information_schema.columns
                    where table_schema = 'public' and table_name = 'dopyty'
                      and column_name = 'admin_upozorneny') then
        alter table public.dopyty
            add column overeny           boolean not null default false,
            add column admin_upozorneny  boolean not null default false;

        -- Existujuce dopyty (ak by nejake boli): overene podla obce; stare
        -- dopyty nema zmysel hlasit adminovi (spusta sa len pri prvom behu).
        update public.dopyty d
           set overeny = true
          from public.obce_ucty o
         where o.id = d.obec_id and o.overena;
        update public.dopyty set admin_upozorneny = true;
    end if;
end $$;

-- Klient nesmie menit overenie ani priznaky (uz nema update na dopyty z 65,
-- na obce_ucty ide update len cez RPC; poistka pre pripad stlpcoveho grantu).
revoke update (overena, overena_at, overena_sposob) on public.obce_ucty from anon, authenticated;
revoke update (overeny, admin_upozorneny) on public.dopyty from anon, authenticated;

-- ── 2) Pomocna funkcia: patri e-mail uctu k obci s tymto ICO? ───────────────
create or replace function public._email_patri_obci(p_email text, p_ico text)
returns boolean
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
    v_email text := lower(trim(coalesce(p_email, '')));
    v_ico   text := regexp_replace(coalesce(p_ico, ''), '\s', '', 'g');
    v_dom   text;
    v_volne text[] := array[
        'gmail.com','googlemail.com','outlook.com','hotmail.com','live.com','msn.com',
        'yahoo.com','icloud.com','me.com','proton.me','protonmail.com',
        'centrum.sk','centrum.cz','azet.sk','zoznam.sk','post.sk','atlas.sk','pobox.sk',
        'seznam.cz','email.cz','orangemail.sk','stonline.sk','chello.sk','szm.sk','inmail.sk'
    ];
begin
    if v_email = '' or position('@' in v_email) = 0 or v_ico !~ '^[0-9]{6,8}$' then
        return false;
    end if;
    v_dom := split_part(v_email, '@', 2);

    return exists (
        select 1
          from public.kampan_obce_kontakty k
         where k.ico = v_ico
           and k.stav = 'ok'
           and (
                lower(trim(k.email)) = v_email
                or (v_dom <> '' and not (v_dom = any (v_volne))
                    and lower(split_part(trim(k.email), '@', 2)) = v_dom)
           )
    );
end;
$$;

revoke all on function public._email_patri_obci(text, text) from public, anon, authenticated;

-- ── 3) zaloz_obec_ucet: automaticke overenie podla e-mailu uctu ──────────────
create or replace function public.zaloz_obec_ucet(
    p_nazov         text,
    p_kraj          text default null,
    p_ico           text default null,
    p_kontakt_email text default null
)
returns uuid
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_id    uuid;
    v_mail  text;
    v_auto  boolean;
begin
    if auth.uid() is null then
        raise exception 'Nie si prihlaseny.';
    end if;
    if trim(coalesce(p_nazov, '')) = '' then
        raise exception 'Zadaj nazov obce.';
    end if;
    if exists (select 1 from public.obce_ucty where owner = auth.uid()) then
        raise exception 'Uz mas zalozeny obecny ucet.';
    end if;

    select u.email into v_mail from auth.users u where u.id = auth.uid();
    v_auto := public._email_patri_obci(v_mail, p_ico);

    insert into public.obce_ucty (owner, nazov, kraj, ico, kontakt_email,
                                  overena, overena_at, overena_sposob)
    values (auth.uid(), trim(p_nazov), nullif(trim(p_kraj), ''),
            nullif(trim(p_ico), ''), nullif(trim(p_kontakt_email), ''),
            v_auto, case when v_auto then now() end,
            case when v_auto then 'auto_email' end)
    returning id into v_id;

    return v_id;
end;
$$;

revoke all on function public.zaloz_obec_ucet(text, text, text, text) from public, anon;
grant execute on function public.zaloz_obec_ucet(text, text, text, text) to authenticated;

-- ── 4) vytvor_dopyt: dopyt dedi stav overenia obce ───────────────────────────
-- (telo = verzia z migracie 65 + len `overeny`)
create or replace function public.vytvor_dopyt(
    p_nazov       text,
    p_popis       text default null,
    p_typ         text default null,
    p_contract_id bigint default null,
    p_sablona     text default null,
    p_termin      text default null,
    p_rozpocet    text default null
)
returns uuid
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_obec_id uuid;
    v_obec    record;
    v_id      uuid;
    v_dnes    int;
begin
    v_obec_id := public.moj_obec_id();
    if v_obec_id is null then
        raise exception 'Nemas obecny ucet. Najprv si ho zaloz.';
    end if;
    select id, nazov, kraj, overena into v_obec from public.obce_ucty where id = v_obec_id;

    if trim(coalesce(p_nazov, '')) = '' then
        raise exception 'Zadaj, co potrebujes.';
    end if;
    if char_length(p_nazov) > 300 then
        raise exception 'Nazov dopytu je prilis dlhy (najviac 300 znakov).';
    end if;
    if char_length(coalesce(p_popis, '')) > 4000 then
        raise exception 'Popis dopytu je prilis dlhy (najviac 4000 znakov).';
    end if;
    if char_length(coalesce(p_sablona, '')) > 200
       or char_length(coalesce(p_termin, '')) > 200
       or char_length(coalesce(p_rozpocet, '')) > 200 then
        raise exception 'Niektore pole dopytu je prilis dlhe.';
    end if;
    if p_typ is not null and p_typ not in ('zmluva', 'dotacia', 'ine') then
        raise exception 'Neznamy typ.';
    end if;

    select count(*) into v_dnes
      from public.dopyty
     where obec_id = v_obec.id
       and created_at > now() - interval '24 hours';
    if v_dnes >= 10 then
        raise exception 'Dnes ste zadali uz 10 dopytov. Skuste to prosim zajtra, alebo nam napiste na info@predtendrom.sk.'
            using errcode = '54000';
    end if;

    insert into public.dopyty (obec_id, obec_nazov, kraj, typ, contract_id, nazov, popis,
                                sablona, termin, rozpocet, overeny, admin_upozorneny)
    values (v_obec.id, v_obec.nazov, v_obec.kraj, p_typ, p_contract_id,
            trim(p_nazov), nullif(trim(p_popis), ''),
            nullif(trim(p_sablona), ''), nullif(trim(p_termin), ''), nullif(trim(p_rozpocet), ''),
            coalesce(v_obec.overena, false), coalesce(v_obec.overena, false))
    returning id into v_id;

    return v_id;
end;
$$;

revoke all on function public.vytvor_dopyt(text, text, text, bigint, text, text, text) from public, anon;
grant execute on function public.vytvor_dopyt(text, text, text, bigint, text, text, text) to authenticated;

-- ── 5) Poradcovia vidia a odpovedaju len na dopyty overenych obci ────────────
drop policy if exists dopyty_select on public.dopyty;
create policy dopyty_select on public.dopyty
    for select to authenticated
    using (
        obec_id = public.moj_obec_id()
        or (stav = 'otvoreny' and overeny and public.je_poradca())
        or (stav = 'otvoreny' and overeny and public.ma_dopyty_pristup())
    );

-- reaguj_na_dopyt: telo z migracie 63 + podmienka `overeny`
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
      where id = p_dopyt_id and stav = 'otvoreny' and overeny
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

revoke all on function public.reaguj_na_dopyt(uuid, text) from public, anon;
grant execute on function public.reaguj_na_dopyt(uuid, text) to authenticated;

-- ── 6) Rucne schvalenie (len administrator) ──────────────────────────────────
create or replace function public.schval_obec(p_obec_id uuid)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_n int;
begin
    perform public.vyzaduj_admina();

    update public.obce_ucty
       set overena = true, overena_at = now(), overena_sposob = 'rucne'
     where id = p_obec_id and not overena;
    get diagnostics v_n = row_count;

    update public.dopyty
       set overeny = true
     where obec_id = p_obec_id and not overeny;

    return jsonb_build_object('ok', true, 'schvalena', v_n > 0);
end;
$$;

revoke all on function public.schval_obec(uuid) from public, anon;
grant execute on function public.schval_obec(uuid) to authenticated;

-- Zoznam obci cakajucich na schvalenie (len administrator).
create or replace function public.cakajuce_obce()
returns table (id uuid, nazov text, ico text, kraj text, kontakt_email text,
               prihlasovaci_email text, vytvorena timestamptz, otvorene_dopyty bigint)
language plpgsql
stable
security definer
set search_path = ''
as $$
begin
    perform public.vyzaduj_admina();
    return query
        select o.id, o.nazov, o.ico, o.kraj, o.kontakt_email, u.email::text, o.created_at,
               (select count(*) from public.dopyty d where d.obec_id = o.id and d.stav = 'otvoreny')
          from public.obce_ucty o
          left join auth.users u on u.id = o.owner
         where not o.overena
         order by o.created_at;
end;
$$;

revoke all on function public.cakajuce_obce() from public, anon;
grant execute on function public.cakajuce_obce() to authenticated;

select 'Migracia 67 hotova: obce su overovane (auto podla e-mailu / rucne schvalenie).' as vysledok;
