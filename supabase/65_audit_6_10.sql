-- =============================================================================
--  65 — AUDIT 6. 10. 2026 (vlna 81): opravy zo zistenia A1–A6, B1–B11
--  Idempotentne (da sa spustit viackrat). Nemeni ziadne existujuce data.
--
--  1) dopyty: obec uz nemoze UPDATE-om menit hocico (stav, obec_nazov,
--     poradcovia_notifikovani ...). Zatvorenie ide cez RPC zatvor_dopyt.
--  2) vytvor_dopyt: limity dlzok a denny strop na obec; stare preťaženia preč.
--  3) organizations: nikto z klienta nemeni ico/nazov priamo (obchadzalo by
--     kontrolu IČO a unikátnosť); zmeny idu cez RPC.
--  4) navstevy / udalosti: anonym smie zapisat len stlpce formulara (nie
--     created_at => nemoze obist hodinovy strop); strop aj pre udalosti.
--  5) odber_obce: RPC prihlas_odber_obce (konstantna odpoved, nepreraduje, ci
--     adresa v zozname je), atomicke zabratie potvrdenia s limitom pokusov
--     (zaber_potvrdenie_odberu), tabulka limitov na IP pre Edge Function.
--  6) odber (digest dodavatelov): odhlasovaci token + RPC, odstranenie odberu
--     odobraneho clena firmy.
--  7) stare preťažené funkcie (vytvor_dopyt/4 arg, uprav_kontakt_obce/1 arg).
--
--  POZOR: priame INSERT-y anonyma do odber_obce / servisne_dopyty /
--  spatne_volania sa ZATIAL NEODOBERAJU (stara verzia stranok ich este
--  pouziva). Odoberie ich az migracia 66, ked bude nasadena Edge Function
--  verejny-formular a nove stranky.
-- =============================================================================


-- ═════════════════════════════════════════════════════════════════════════
--  1) DOPYTY: ziadny priamy UPDATE z klienta
-- ═════════════════════════════════════════════════════════════════════════
-- Klient dopyty len cita (SELECT) a uzatvara cez RPC zatvor_dopyt
-- (SECURITY DEFINER, obec_id = moj_obec_id()). Predtym mohla obec cez REST
-- prepisat stav, obec_nazov, kraj aj poradcovia_notifikovani (= znovu
-- rozposlat dopyt vsetkym poradcom kazdych 15 minut).
drop policy if exists dopyty_update on public.dopyty;
revoke update on public.dopyty from anon, authenticated;
revoke insert on public.dopyty from anon, authenticated;   -- vklad ide len cez vytvor_dopyt


-- ═════════════════════════════════════════════════════════════════════════
--  2) vytvor_dopyt: limity
-- ═════════════════════════════════════════════════════════════════════════
alter table public.dopyty drop constraint if exists dopyty_dlzky;
alter table public.dopyty add constraint dopyty_dlzky check (
    char_length(nazov) <= 300
    and (popis     is null or char_length(popis)     <= 4000)
    and (sablona   is null or char_length(sablona)   <= 200)
    and (termin    is null or char_length(termin)    <= 200)
    and (rozpocet  is null or char_length(rozpocet)  <= 200)
    and (obec_nazov is null or char_length(obec_nazov) <= 200)
) not valid;

-- Stare preťaženie (4 argumenty) zmizne: zostane jediná verzia funkcie.
drop function if exists public.vytvor_dopyt(text, text, text, bigint);
drop function if exists public.uprav_kontakt_obce(text);

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
    select id, nazov, kraj into v_obec from public.obce_ucty where id = v_obec_id;

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

    -- Poradcovia dostavaju e-mail za kazdy dopyt. Denny strop chrani ich
    -- schranky aj nas pred zneuzitim ucta obce (max. 10 dopytov za 24 hodin).
    select count(*) into v_dnes
      from public.dopyty
     where obec_id = v_obec.id
       and created_at > now() - interval '24 hours';
    if v_dnes >= 10 then
        raise exception 'Dnes ste zadali uz 10 dopytov. Skuste to prosim zajtra, alebo nam napiste na info@predtendrom.sk.'
            using errcode = '54000';
    end if;

    insert into public.dopyty (obec_id, obec_nazov, kraj, typ, contract_id, nazov, popis,
                                sablona, termin, rozpocet)
    values (v_obec.id, v_obec.nazov, v_obec.kraj, p_typ, p_contract_id,
            trim(p_nazov), nullif(trim(p_popis), ''),
            nullif(trim(p_sablona), ''), nullif(trim(p_termin), ''), nullif(trim(p_rozpocet), ''))
    returning id into v_id;

    return v_id;
end;
$$;

revoke all on function public.vytvor_dopyt(text, text, text, bigint, text, text, text) from public, anon;
grant execute on function public.vytvor_dopyt(text, text, text, bigint, text, text, text) to authenticated;


-- ═════════════════════════════════════════════════════════════════════════
--  3) ORGANIZATIONS: ziadny priamy UPDATE z klienta
-- ═════════════════════════════════════════════════════════════════════════
-- Policy org_update pustala vlastnika zmenit "ico" bez kontroly kontrolnej
-- cislice a obist unikatnost/overenie firmy. Klient organizations nikdy
-- neupravuje (zaklada ich RPC zaloz_organizaciu), preto UPDATE zrusime.
drop policy if exists org_update on public.organizations;
revoke update on public.organizations from anon, authenticated;
revoke insert on public.organizations from anon, authenticated;
revoke delete on public.organizations from anon, authenticated;


-- ═════════════════════════════════════════════════════════════════════════
--  4) NAVSTEVY / UDALOSTI: stlpcove granty + strop + dlzky
-- ═════════════════════════════════════════════════════════════════════════
-- Anonym doteraz mohol nastavit aj created_at (napr. rok 2000), cim by obisiel
-- hodinovy strop (trigger pocita riadky mladsie ako hodina) a skreslil
-- statistiky. Povolime len stlpce, ktore posiela analytika.
revoke insert on public.navstevy from anon, authenticated;
grant insert (cesta, referrer, session_id, utm_source, utm_medium, utm_campaign)
    on public.navstevy to anon, authenticated;

revoke insert on public.udalosti from anon, authenticated;
grant insert (nazov, cesta, session_id, utm_source, utm_medium, utm_campaign)
    on public.udalosti to anon, authenticated;

grant usage on sequence public.navstevy_id_seq  to anon, authenticated;
grant usage on sequence public.udalosti_id_seq  to anon, authenticated;

alter table public.navstevy drop constraint if exists navstevy_dlzky;
alter table public.navstevy add constraint navstevy_dlzky check (
    char_length(cesta) <= 1000
    and (referrer     is null or char_length(referrer)     <= 2000)
    and (session_id   is null or char_length(session_id)   <= 80)
    and (utm_source   is null or char_length(utm_source)   <= 100)
    and (utm_medium   is null or char_length(utm_medium)   <= 100)
    and (utm_campaign is null or char_length(utm_campaign) <= 150)
) not valid;

create index if not exists ix_udalosti_created on public.udalosti(created_at);
drop trigger if exists trg_strop_udalosti on public.udalosti;
create trigger trg_strop_udalosti before insert on public.udalosti
    for each row execute function public._strop_vkladov(20000);


-- ═════════════════════════════════════════════════════════════════════════
--  5) ODBER_OBCE: RPC, atomicke zabratie potvrdenia, limity na IP
-- ═════════════════════════════════════════════════════════════════════════
alter table public.odber_obce
    add column if not exists potvrdzovaci_pokusy int not null default 0;

-- 5a) Limity na IP pre Edge Function. IP sa uklada len ako SHA-256 odtlacok
--     so soľou (soľ drzi Edge Function v tajnom nastaveni), nikdy v cistom tvare.
create table if not exists public.verejny_formular_pokusy (
    id         bigserial primary key,
    ip_hash    text not null check (char_length(ip_hash) <= 128),
    typ        text not null check (char_length(typ) <= 40),
    created_at timestamptz not null default now()
);
create index if not exists ix_vfp_hash_cas on public.verejny_formular_pokusy(ip_hash, typ, created_at);
create index if not exists ix_vfp_cas      on public.verejny_formular_pokusy(created_at);
alter table public.verejny_formular_pokusy enable row level security;
revoke all on public.verejny_formular_pokusy from public, anon, authenticated;
revoke all on sequence public.verejny_formular_pokusy_id_seq from public, anon, authenticated;

-- Zapise pokus a vrati true, ak je este v limite (p_max pokusov za p_minut minut).
create or replace function public.verejny_formular_strop(
    p_ip_hash text, p_typ text, p_max int, p_minut int
)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_n int;
begin
    if p_ip_hash is null or p_typ is null or p_max < 1 or p_minut < 1 then
        return false;
    end if;
    -- Upratovanie: starsie ako 2 dni nepotrebujeme.
    delete from public.verejny_formular_pokusy where created_at < now() - interval '2 days';

    select count(*) into v_n
      from public.verejny_formular_pokusy
     where ip_hash = p_ip_hash and typ = p_typ
       and created_at > now() - make_interval(mins => p_minut);
    if v_n >= p_max then
        return false;
    end if;
    insert into public.verejny_formular_pokusy (ip_hash, typ) values (p_ip_hash, p_typ);
    return true;
end;
$$;
revoke all on function public.verejny_formular_strop(text, text, int, int) from public, anon, authenticated;
grant execute on function public.verejny_formular_strop(text, text, int, int) to service_role;

-- 5b) Prihlasenie na odber obci. Vola ju len Edge Function (service_role).
--     Odpoved je VZDY rovnaka (nezistuje sa, ci adresa uz v zozname je).
--     Ak adresa uz existuje a je nepotvrdena, riadok sa nemeni; potvrdzovaci
--     e-mail sa pripadne posle znova cez zaber_potvrdenie_odberu.
create or replace function public.prihlas_odber_obce(
    p_email text, p_obec text, p_ico text, p_kraj text, p_zdroj text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_email text := lower(trim(coalesce(p_email, '')));
begin
    if char_length(v_email) not between 5 and 254 or v_email !~ '^[^@\s,;<>"]+@[^@\s,;<>"]+\.[A-Za-z]{2,}$' then
        return jsonb_build_object('ok', false, 'kod', 'EMAIL_NEPLATNY');
    end if;
    if char_length(coalesce(p_obec, '')) > 200 or char_length(coalesce(p_ico, '')) > 20
       or char_length(coalesce(p_kraj, '')) > 80 or char_length(coalesce(p_zdroj, '')) > 80 then
        return jsonb_build_object('ok', false, 'kod', 'UDAJE_DLHE');
    end if;

    insert into public.odber_obce (email, obec, ico, kraj, zdroj)
    values (v_email, nullif(trim(p_obec), ''), nullif(trim(p_ico), ''),
            nullif(trim(p_kraj), ''), nullif(trim(p_zdroj), ''))
    on conflict (lower(email)) do nothing;

    return jsonb_build_object('ok', true);
end;
$$;
revoke all on function public.prihlas_odber_obce(text, text, text, text, text) from public, anon, authenticated;
grant execute on function public.prihlas_odber_obce(text, text, text, text, text) to service_role;

-- 5c) Atomicke zabratie riadkov, ktorym treba poslat potvrdzovaci e-mail.
--     Pouziva Edge Function aj cron (posli_potvrdenie_odberu.py). Riadok sa
--     da zabrat, ak: nie je potvrdeny, je mladsi ako 3 dni, este nema 3 pokusy
--     a posledny pokus bol pred viac ako 10 minutami (alebo este nebol).
--     Tym sa opravi, ze adresa, ktorej prvy e-mail zlyhal alebo sa stratil,
--     dostane druhy, a zaroven nemoze nikto zahltit cudziu schranku.
create or replace function public.zaber_potvrdenie_odberu(p_email text default null)
returns table (id bigint, email text, token uuid)
language plpgsql
security definer
set search_path = ''
as $$
begin
    return query
    update public.odber_obce o
       set potvrdzovaci_email_at = now(),
           potvrdzovaci_pokusy   = o.potvrdzovaci_pokusy + 1
     where o.potvrdeny = false
       and o.potvrdzovaci_pokusy < 3
       and o.created_at > now() - interval '3 days'
       and (o.potvrdzovaci_email_at is null
            or o.potvrdzovaci_email_at < now() - interval '10 minutes')
       and (p_email is null or lower(o.email) = lower(trim(p_email)))
    returning o.id, o.email, o.token;
end;
$$;
revoke all on function public.zaber_potvrdenie_odberu(text) from public, anon, authenticated;
grant execute on function public.zaber_potvrdenie_odberu(text) to service_role;

-- Ak odoslanie zlyha, riadok sa da vratit (pokus sa neráta).
create or replace function public.vrat_potvrdenie_odberu(p_id bigint)
returns void
language sql
security definer
set search_path = ''
as $$
    update public.odber_obce
       set potvrdzovaci_email_at = null,
           potvrdzovaci_pokusy   = greatest(potvrdzovaci_pokusy - 1, 0)
     where id = p_id and potvrdeny = false;
$$;
revoke all on function public.vrat_potvrdenie_odberu(bigint) from public, anon, authenticated;
grant execute on function public.vrat_potvrdenie_odberu(bigint) to service_role;


-- ═════════════════════════════════════════════════════════════════════════
--  6) ODBER (digest dodavatelov): odhlasenie odkazom + upratanie po odobrati
-- ═════════════════════════════════════════════════════════════════════════
alter table public.odber
    add column if not exists odhlasovaci_token uuid not null default gen_random_uuid();
create unique index if not exists ux_odber_odhlasovaci_token on public.odber(odhlasovaci_token);

-- Odhlasenie z e-mailoveho prehladu jednym kliknutim (bez prihlasenia).
-- Nevracia ziadne udaje, len ok/nie.
create or replace function public.odhlas_odber_prehladu(p_token uuid)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_n int;
begin
    update public.odber set chce_email = false, updated_at = now()
     where odhlasovaci_token = p_token and chce_email;
    get diagnostics v_n = row_count;
    return v_n > 0;
end;
$$;
revoke all on function public.odhlas_odber_prehladu(uuid) from public;
grant execute on function public.odhlas_odber_prehladu(uuid) to anon, authenticated;

-- Odobrany clen firmy nesmie dalej dostavat e-mailove prehlady na firemny
-- kontext (odber ma org_id) — jeho odber sa zrusi.
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
    -- Jeho e-mailovy prehlad viazany na tuto firmu uz nema opodstatnenie.
    delete from public.odber where user_id = p_user_id and org_id = v_org_id;

    insert into public.events (org_id, user_id, typ, detail)
    values (v_org_id, auth.uid(), 'clen_odobrany',
            jsonb_build_object('user_id', p_user_id));

    return jsonb_build_object('ok', true, 'kod', 'ODOBRANY');
end;
$$;
grant execute on function public.odober_clena_firmy(uuid) to authenticated;


-- ═════════════════════════════════════════════════════════════════════════
--  7) OBCE: NEKONECNA REKURZIA V RLS (obce_ucty <-> obce_clenovia)
-- ═════════════════════════════════════════════════════════════════════════
-- Politiky z 58_pozvat_kolegu.sql sa navzajom odkazovali (obce_ucty_select
-- cita obce_clenovia a obce_clenovia_select cita obce_ucty), takze kazdy
-- priamy SELECT z obce_ucty koncil chybou 42P17 "infinite recursion".
-- Zistene pri testovani migracie 65 (trh.html cita obce_ucty priamo).
-- Oprava: pomocne SECURITY DEFINER funkcie (obchadzaju RLS), politiky ich volaju.
create or replace function public._obec_vlastnika_id()
returns uuid
language sql stable security definer
set search_path = ''
as $$ select id from public.obce_ucty where owner = auth.uid() limit 1 $$;

create or replace function public._obce_clena_ids()
returns setof uuid
language sql stable security definer
set search_path = ''
as $$ select obec_id from public.obce_clenovia where user_id = auth.uid() $$;

revoke all on function public._obec_vlastnika_id() from public, anon;
revoke all on function public._obce_clena_ids()    from public, anon;
grant execute on function public._obec_vlastnika_id() to authenticated;
grant execute on function public._obce_clena_ids()    to authenticated;

drop policy if exists obce_clenovia_select on public.obce_clenovia;
create policy obce_clenovia_select on public.obce_clenovia
    for select to authenticated
    using (user_id = auth.uid() or obec_id = public._obec_vlastnika_id());

drop policy if exists obce_ucty_select on public.obce_ucty;
create policy obce_ucty_select on public.obce_ucty
    for select to authenticated
    using (owner = auth.uid() or id in (select public._obce_clena_ids()));


select 'Migracia 65 hotova: oprava rekurzie RLS obce, dopyty bez UPDATE, limity vytvor_dopyt, organizations bez priameho UPDATE, navstevy/udalosti stlpcove granty, odber_obce RPC + atomicke zabratie, odhlasenie prehladu.' as vysledok;
