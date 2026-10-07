-- =============================================================================
--  70 — PROFIL OBSTARÁVATEĽA (vlna 84, 7. 10. 2026; audit Advisory Board, funkcia č. 3)
--  Vlož do Supabase: SQL Editor -> New query -> Run. Spustiť sa dá opakovane.
-- =============================================================================
--
--  Stránka /obstaravatel?ico=... zhrnie na jednom mieste, čo úrad alebo obec
--  kupuje a komu: výdavky podľa sektorov za 36 mesiacov, najväčší dodávatelia,
--  koľko zmlúv a v akom objeme končí, dotácie, súťaže z Vestníka ÚVO a typická
--  dĺžka zmluvy. Zdroj: Centrálny register zmlúv a Vestník ÚVO (verejné údaje).
--
--  ROZSAH VÝSTUPU (zámerne úzky, rovnako ako pri /kontrola)
--  Verejná stránka dostane len agregáty, 3 najväčších dodávateľov (len právnické
--  osoby, názvy fyzických osôb sa neposielajú) a 3 najbližšie končiace zmluvy
--  bez predmetu a bez dodávateľa. Plný zoznam a predmety sú v aplikácii.
--
--  PRÍSTUP
--  Funkciu volá výhradne Edge Function `verejny-formular` (typ profil_obstaravatela)
--  po overení Cloudflare Turnstile a s limitom na IP; anon ani authenticated ju
--  priamo volať nemôžu.
-- =============================================================================

-- Je názov dodávateľa právnická osoba (alebo verejná inštitúcia)? Konzervatívne:
-- ak si nie sme istí, meno sa na verejnej stránke nezobrazí.
create or replace function public._je_pravnicka_osoba(p_nazov text)
returns boolean
language sql
immutable
set search_path = ''
as $$
    select coalesce(
        p_nazov ~* '(s\.\s?r\.\s?o|a\.\s?s\.|spol\.|k\.\s?s\.|v\.\s?o\.\s?s|š\.\s?p\.|s\.\s?p\.|o\.\s?z\.|n\.\s?o\.|\mdružstvo|\mzväz|\mzdruženie|\mnadácia|\muniverzita|\mnemocnica|\mministerstvo|\múrad|\mmesto\M|\mobec\M|\mškola|\morganizácia|\mspoločnosť|\mgroup\M|\ms\.r\.o|\mltd|\mgmbh|\ms\.a\.|\mb\.v\.)',
        false);
$$;

create or replace function public.profil_obstaravatela(p_ico text)
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
set statement_timeout = '4s'
as $$
declare
    v_ico       text;
    v_cin       text;   -- IČO bez úvodných núl (tak je uložené v contracts.authority_cin)
    v_dnes      date := current_date;
    v_od        date := (current_date - interval '36 months')::date;
    v_od_uvo    date := (current_date - interval '24 months')::date;
    v_h6        date := (current_date + interval '6 months')::date;
    v_h12       date := (current_date + interval '12 months')::date;
    v_h24       date := (current_date + interval '24 months')::date;
    v_nazov     text;
    v_pocet     int;
    v_objem     numeric;
    v_sektory   jsonb;
    v_top       jsonb;
    v_dodav     int;
    v_6         int;
    v_12        int;
    v_24        int;
    v_objem12   numeric;
    v_najblizsi date;
    v_teaser    jsonb;
    v_median    numeric;
    v_dot_n     int;
    v_dot_suma  numeric;
    v_dot_okna  int;
    v_uvo_n     int;
    v_uvo_pon   numeric;
    v_uvo_slabe int;
begin
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
    v_cin := ltrim(v_ico, '0');

    -- Názov, počet a objem zmlúv za 36 mesiacov (podpis), len zmluvy s cenou sa sčítajú.
    select mode() within group (order by c.authority_name),
           count(*),
           sum(c.price_total) filter (where c.price_total > 0)
      into v_nazov, v_pocet, v_objem
      from public.contracts c
     where c.authority_cin = v_cin
       and c.signed_on >= v_od;

    -- Výdavky podľa sektorov (top 5).
    select coalesce(jsonb_agg(jsonb_build_object(
               'sektor', t.sektor, 'pocet', t.pocet, 'objem', t.objem
           ) order by t.objem desc nulls last, t.pocet desc), '[]'::jsonb)
      into v_sektory
      from (
            select coalesce(c.sector, 'INE') as sektor, count(*) as pocet,
                   sum(c.price_total) filter (where c.price_total > 0) as objem
              from public.contracts c
             where c.authority_cin = v_cin and c.signed_on >= v_od
             group by 1
             order by sum(c.price_total) filter (where c.price_total > 0) desc nulls last, count(*) desc
             limit 5
           ) t;

    -- Najväčší dodávatelia podľa objemu (top 3). Meno len pri právnických osobách.
    select coalesce(jsonb_agg(jsonb_build_object(
               'nazov', case when public._je_pravnicka_osoba(t.nazov) then t.nazov end,
               'pocet', t.pocet, 'objem', t.objem
           ) order by t.objem desc nulls last, t.pocet desc), '[]'::jsonb)
      into v_top
      from (
            select c.supplier_cin, mode() within group (order by c.supplier_name) as nazov,
                   count(*) as pocet,
                   sum(c.price_total) filter (where c.price_total > 0) as objem
              from public.contracts c
             where c.authority_cin = v_cin and c.signed_on >= v_od and c.supplier_cin is not null
             group by c.supplier_cin
             order by sum(c.price_total) filter (where c.price_total > 0) desc nulls last, count(*) desc
             limit 3
           ) t;

    select count(distinct c.supplier_cin) into v_dodav
      from public.contracts c
     where c.authority_cin = v_cin and c.signed_on >= v_od and c.supplier_cin is not null;

    -- Končiace zmluvy.
    select count(*) filter (where c.effective_to between v_dnes and v_h6),
           count(*) filter (where c.effective_to between v_dnes and v_h12),
           count(*) filter (where c.effective_to between v_dnes and v_h24),
           sum(c.price_total) filter (where c.effective_to between v_dnes and v_h12 and c.price_total > 0),
           min(c.effective_to) filter (where c.effective_to >= v_dnes)
      into v_6, v_12, v_24, v_objem12, v_najblizsi
      from public.contracts c
     where c.authority_cin = v_cin and c.effective_to >= v_dnes;

    -- Teaser: 3 najbližšie končiace zmluvy bez predmetu a bez dodávateľa.
    select coalesce(jsonb_agg(jsonb_build_object(
               'sektor', t.sektor, 'mesiac_konca', t.mesiac, 'hodnota', t.hodnota
           ) order by t.effective_to, t.id), '[]'::jsonb)
      into v_teaser
      from (
            select c.id, coalesce(c.sector, 'INE') as sektor, c.effective_to,
                   date_trunc('month', c.effective_to)::date as mesiac,
                   case when c.price_total > 0 then c.price_total end as hodnota
              from public.contracts c
             where c.authority_cin = v_cin and c.effective_to between v_dnes and v_h24
             order by c.effective_to, c.id
             limit 3
           ) t;

    -- Typická dĺžka zmluvy (medián, dni) — z celej histórie obstarávateľa.
    select percentile_cont(0.5) within group (order by (c.effective_to - c.effective_from))
      into v_median
      from public.contracts c
     where c.authority_cin = v_cin
       and c.effective_from is not null and c.effective_to is not null
       and (c.effective_to - c.effective_from) between 30 and 3650;

    -- Dotácie, ktoré dostal (obce, školy...).
    select count(*), sum(s.suma) filter (where s.suma > 0),
           count(*) filter (where s.okno_od > v_dnes)
      into v_dot_n, v_dot_suma, v_dot_okna
      from public.subsidies s
     where s.prijimatel_ico in (v_cin, v_ico);

    -- Súťaže z Vestníka ÚVO (výsledky za 24 mesiacov).
    select count(*), avg(u.pocet_ponuk) filter (where u.pocet_ponuk > 0),
           count(*) filter (where u.pocet_ponuk between 1 and 2)
      into v_uvo_n, v_uvo_pon, v_uvo_slabe
      from public.uvo_vysledky u
     where u.obstaravatel_ico in (v_cin, v_ico)
       and coalesce(u.publikovane, u.podpisane) >= v_od_uvo;

    if v_nazov is null and v_dot_n = 0 and v_uvo_n = 0 and coalesce(v_24, 0) = 0 then
        return jsonb_build_object('ok', false, 'kod', 'NENAJDENE', 'ico', v_ico);
    end if;

    -- Názov, ak neboli zmluvy za 36 mesiacov, ale sú aktívne zmluvy.
    if v_nazov is null then
        select mode() within group (order by c.authority_name) into v_nazov
          from public.contracts c where c.authority_cin = v_cin and c.effective_to >= v_dnes;
    end if;

    return jsonb_build_object(
        'ok',                    true,
        'ico',                   v_ico,
        'nazov',                 v_nazov,
        'zmluvy_36m',            coalesce(v_pocet, 0),
        'objem_36m',             v_objem,
        'sektory',               v_sektory,
        'dodavatelia_top',       v_top,
        'dodavatelov_spolu',     coalesce(v_dodav, 0),
        'koncia_do_6',           coalesce(v_6, 0),
        'koncia_do_12',          coalesce(v_12, 0),
        'koncia_do_24',          coalesce(v_24, 0),
        'objem_koncia_do_12',    v_objem12,
        'najblizsi_koniec',      v_najblizsi,
        'zoznam',                v_teaser,
        'pocet_dalsich',         greatest(coalesce(v_24, 0) - 3, 0),
        'typicka_dlzka_dni',     case when v_median is null then null else round(v_median)::int end,
        'dotacie_pocet',         coalesce(v_dot_n, 0),
        'dotacie_suma',          v_dot_suma,
        'dotacie_buduce_okna',   coalesce(v_dot_okna, 0),
        'uvo_vysledky_24m',      coalesce(v_uvo_n, 0),
        'uvo_priemer_ponuk',     case when v_uvo_pon is null then null else round(v_uvo_pon, 1) end,
        'uvo_slabe_konkurencie', coalesce(v_uvo_slabe, 0)
    );
end;
$$;

revoke all on function public._je_pravnicka_osoba(text) from public, anon, authenticated;
revoke all on function public.profil_obstaravatela(text) from public, anon, authenticated;
grant execute on function public.profil_obstaravatela(text) to service_role;

select 'Migracia 70 hotova: profil_obstaravatela(ico) len cez Edge Function.' as vysledok;
