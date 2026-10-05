-- =============================================================================
--  64 — KONTROLA ZMLÚV PODĽA IČO: verejný súhrn pre jedného dodávateľa
--  Vlož do Supabase: SQL Editor -> New query -> Run. Spustiť sa dá opakovane.
-- =============================================================================
--
--  CO TO JE
--  Stránka /kontrola (public/kontrola.html): dodávateľ zadá svoje IČO a bez
--  registrácie uvidí, koľko jeho zmlúv s verejným sektorom sa končí v najbližších
--  6 / 12 / 24 mesiacoch, ich orientačný objem a tri najbližšie končiace zmluvy
--  (obstarávateľ, mesiac konca, hodnota). Zvyšok (celý zoznam, predmety zmlúv,
--  konkurenti) je v aplikácii po registrácii.
--
--  ROZSAH VÝSTUPU (zámerne úzky)
--  Verejná RPC vracia VÝLUČNE agregáty a najviac 3 riadky teaseru bez predmetu
--  zmluvy a bez čísla zmluvy; mesiac konca je zaokrúhlený na mesiac. Tabuľky
--  `contracts` a `opportunities` ostávajú čitateľné len pre authenticated
--  (politiky sa tu nemenia) — anonym k nim nedostane žiadny nový prístup.
--
--  OCHRANA PROTI HROMADNÉMU ZBIERANIU
--  Každé volanie s platným IČO sa zapíše do `kontrola_ico_dotazy` (RLS zapnuté,
--  žiadna politika, žiadne granty — číta ju iba service_role). Funkcia odmietne
--  volanie, ak za poslednú hodinu prišlo viac ako 600 dotazov celkovo, alebo
--  viac ako 20 dotazov na jedno IČO. Chyba má kód 54000.
--
--  VÝKON
--  Dopyt je rovnostný filter na supplier_cin + rozsah na effective_to, preto
--  sa pridáva zložený index (supplier_cin, effective_to). Existujúce indexy
--  ix_contracts_effto (len effective_to) a ix_contracts_auth_sector
--  (authority_cin, sector) tento dopyt nepokryjú.
-- =============================================================================


-- ═════════════════════════════════════════════════════════════════════════
--  1) INDEX
-- ═════════════════════════════════════════════════════════════════════════
create index if not exists ix_contracts_supplier_effto
    on public.contracts (supplier_cin, effective_to);


-- ═════════════════════════════════════════════════════════════════════════
--  2) LOG DOTAZOV (len pre limity; bez prístupu pre anon/authenticated)
-- ═════════════════════════════════════════════════════════════════════════
create table if not exists public.kontrola_ico_dotazy (
    id               bigserial primary key,
    ico              text not null,
    created_at       timestamptz not null default now(),
    pocet_aktivnych  int
);

create index if not exists ix_kontrola_ico_dotazy_cas
    on public.kontrola_ico_dotazy (created_at);
create index if not exists ix_kontrola_ico_dotazy_ico_cas
    on public.kontrola_ico_dotazy (ico, created_at);

alter table public.kontrola_ico_dotazy enable row level security;

-- Žiadna politika = nikto okrem service_role (obchádza RLS). Granty tiež preč,
-- takže anon/authenticated dostanú "permission denied", nie len prázdny výsledok.
revoke all on public.kontrola_ico_dotazy from public, anon, authenticated;
revoke all on sequence public.kontrola_ico_dotazy_id_seq from public, anon, authenticated;


-- ═════════════════════════════════════════════════════════════════════════
--  3) RPC kontrola_zmluv_ico
-- ═════════════════════════════════════════════════════════════════════════
create or replace function public.kontrola_zmluv_ico(p_ico text)
returns jsonb
language plpgsql
security definer
set search_path = ''
set statement_timeout = '3s'
as $$
declare
    v_ico       text;
    v_cin       text;   -- IČO v tvare, v akom je uložené v contracts.supplier_cin (bez úvodných núl)
    v_dnes      date := current_date;
    v_h6        date := (current_date + interval '6 months')::date;
    v_h12       date := (current_date + interval '12 months')::date;
    v_h24       date := (current_date + interval '24 months')::date;
    v_od        date := (current_date - interval '6 months')::date;
    v_glob      int;
    v_na_ico    int;
    v_nazov     text;
    v_akt       int;
    v_6         int;
    v_12        int;
    v_24        int;
    v_skoncene  int;
    v_objem     numeric;
    v_najblizsi date;
    v_teaser    jsonb;
begin
    -- Vstup: medzery preč, prípadná predpona SK preč, potom presne 8 číslic.
    if p_ico is null or char_length(p_ico) > 40 then
        return jsonb_build_object('ok', false, 'kod', 'ICO_NEPLATNE');
    end if;
    v_ico := upper(regexp_replace(p_ico, '\s', '', 'g'));
    if left(v_ico, 2) = 'SK' then
        v_ico := substr(v_ico, 3);
    end if;
    if v_ico !~ '^\d{8}$' or not public._ico_platne(v_ico) then
        return jsonb_build_object('ok', false, 'kod', 'ICO_NEPLATNE');
    end if;

    -- V contracts.supplier_cin je IČO uložené BEZ úvodných núl (napr. 151742
    -- namiesto 00151742; overené na produkcii 5. 10. 2026: 63 270 z 211 498
    -- riadkov má menej ako 8 číslic a žiadny nezačína nulou). Preto sa
    -- porovnáva tvar bez núl; zadané IČO ostáva 8-ciferné pre log a výstup.
    v_cin := ltrim(v_ico, '0');

    -- Stropy za poslednú hodinu: celkovo a na jedno IČO.
    select count(*) into v_glob
      from public.kontrola_ico_dotazy
     where created_at > now() - interval '1 hour';
    if v_glob >= 600 then
        raise exception 'Prilis vela poziadaviek. Skuste to prosim neskor.' using errcode = '54000';
    end if;

    select count(*) into v_na_ico
      from public.kontrola_ico_dotazy
     where ico = v_ico
       and created_at > now() - interval '1 hour';
    if v_na_ico >= 20 then
        raise exception 'Prilis vela poziadaviek. Skuste to prosim neskor.' using errcode = '54000';
    end if;

    -- Jeden prechod indexom: zmluvy tohto dodávateľa, ktoré sa skončili
    -- najviac pred 6 mesiacmi alebo ešte nie sú skončené.
    select
        mode() within group (order by c.supplier_name),
        count(*) filter (where c.effective_to >= v_dnes),
        count(*) filter (where c.effective_to between v_dnes and v_h6),
        count(*) filter (where c.effective_to between v_dnes and v_h12),
        count(*) filter (where c.effective_to between v_dnes and v_h24),
        count(*) filter (where c.effective_to < v_dnes),
        sum(c.price_total) filter (where c.effective_to between v_dnes and v_h12 and c.price_total > 0),
        min(c.effective_to) filter (where c.effective_to >= v_dnes)
      into v_nazov, v_akt, v_6, v_12, v_24, v_skoncene, v_objem, v_najblizsi
      from public.contracts c
     where c.supplier_cin = v_cin
       and c.effective_to >= v_od;

    -- Teaser: 3 najbližšie končiace zmluvy v horizonte 24 mesiacov.
    -- Zámerne bez predmetu, bez čísla zmluvy a s mesiacom namiesto presného dňa.
    select coalesce(jsonb_agg(jsonb_build_object(
               'obstaravatel', t.authority_name,
               'mesiac_konca', t.mesiac,
               'hodnota',      t.hodnota
           ) order by t.effective_to, t.id), '[]'::jsonb)
      into v_teaser
      from (
            select c.id, c.authority_name, c.effective_to,
                   date_trunc('month', c.effective_to)::date as mesiac,
                   case when c.price_total > 0 then c.price_total end as hodnota
              from public.contracts c
             where c.supplier_cin = v_cin
               and c.effective_to between v_dnes and v_h24
             order by c.effective_to, c.id
             limit 3
           ) t;

    insert into public.kontrola_ico_dotazy (ico, pocet_aktivnych)
    values (v_ico, coalesce(v_akt, 0));

    -- Údržba logu: záznamy staršie ako 7 dní sa mažú pri každom volaní
    -- (index na created_at, zvyčajne 0 riadkov), takže sa neuchovávajú dlhšie.
    delete from public.kontrola_ico_dotazy
     where created_at < now() - interval '7 days';

    return jsonb_build_object(
        'ok',                      true,
        'ico',                     v_ico,
        'nazov',                   v_nazov,
        'pocet_aktivnych',         coalesce(v_akt, 0),
        'pocet_do_6_mesiacov',     coalesce(v_6, 0),
        'pocet_do_12_mesiacov',    coalesce(v_12, 0),
        'pocet_do_24_mesiacov',    coalesce(v_24, 0),
        'pocet_skoncenych_6_mesiacov', coalesce(v_skoncene, 0),
        'objem_do_12_mesiacov',    v_objem,
        'najblizsi_koniec',        v_najblizsi,
        'zoznam',                  v_teaser,
        'pocet_dalsich',           greatest(coalesce(v_24, 0) - 3, 0)
    );
end;
$$;

revoke all on function public.kontrola_zmluv_ico(text) from public;
grant execute on function public.kontrola_zmluv_ico(text) to anon, authenticated;

select 'kontrola_zmluv_ico: index, log dotazov a RPC pripravené.' as vysledok;
