-- =============================================================================
--  P3.3 (zadanie: claude/predtendrom-p3-cesta-pre-starostov-zadanie.md) —
--  vieckrokovy formular dopytu namiesto jedneho prazdneho pola.
--
--  Dva druhy novych udajov, zamerne na DVOCH roznych miestach:
--
--  1. sablona/termin/rozpocet -> pribudaju na `dopyty`. Su to netraze
--     udaje o samotnom dopyte (co, dokedy, priblizny rozpocet) a
--     poradcovia ich uz dnes smu vidiet (rovnaka RLS politika ako
--     doterajsie typ/nazov/popis) — pomahaju im rozhodnut sa, ci
--     reagovat, presne ako v zadani P3.3 krok 2.
--
--  2. kontakt_telefon/preferovany_kontakt -> NEidu na `dopyty`, ale na
--     `obce_ucty` (rovnako ako uz existujuci kontakt_email). Dovod: RLS
--     politika `dopyty_select` pusta KAZDEHO aktivneho poradcu k
--     otvorenym dopytom (34_obce_marketplace.sql), a Row Level Security
--     je v Postgrese na urovni RIADKOV, nie stlpcov — ak by telefon/
--     preferovany kontakt boli na `dopyty`, kazdy poradca by ich videl
--     PRIAMO na otvorenom dopyte, este pred tym, ako by obec vobec
--     videla jeho reakciu. To by obisilo cely mechanizmus "obec vidi
--     kontakt na poradcu az po jeho reakcii, poradca kontakt na obec
--     nikdy priamo" (rovnaky dovod, preco uz 37_marketplace_kontakt.sql
--     rusi priamy klientsky update tychto tabuliek). Preto e-mail/telefon/
--     preferovany-kontakt ostavaju tam, kde uz kontakt_email je — na
--     obce_ucty, chranene RLS "owner = auth.uid()" a nikdy nie na
--     poradca-vidiacej tabulke.
-- =============================================================================

alter table public.dopyty
    add column if not exists sablona  text,
    add column if not exists termin   text,
    add column if not exists rozpocet text;

alter table public.obce_ucty
    add column if not exists kontakt_telefon      text,
    add column if not exists preferovany_kontakt   text
        check (preferovany_kontakt in ('email', 'telefon', 'hocijaky') or preferovany_kontakt is null);

-- ── uprav_kontakt_obce: rozsirenie o telefon a preferovany sposob ──────────
create or replace function public.uprav_kontakt_obce(
    p_kontakt_email      text,
    p_kontakt_telefon    text default null,
    p_preferovany_kontakt text default null
)
returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
    if auth.uid() is null then
        raise exception 'Nie si prihlaseny.';
    end if;
    if p_preferovany_kontakt is not null
       and p_preferovany_kontakt not in ('email', 'telefon', 'hocijaky') then
        raise exception 'Neznamy preferovany sposob kontaktu.';
    end if;

    update public.obce_ucty
       set kontakt_email        = nullif(trim(coalesce(p_kontakt_email, '')), ''),
           kontakt_telefon      = nullif(trim(coalesce(p_kontakt_telefon, '')), ''),
           preferovany_kontakt  = p_preferovany_kontakt
     where owner = auth.uid();

    if not found then
        raise exception 'Nemas obecny ucet.';
    end if;
end;
$$;

grant execute on function public.uprav_kontakt_obce(text, text, text) to authenticated;

-- ── vytvor_dopyt: rozsirenie o sablonu, terminu a rozpocet ─────────────────
-- Poznamka: CREATE OR REPLACE smie pridat len NOVE parametre na koniec, so
-- vsetkymi default hodnotami — presne to tu robime, povodne 4 parametre
-- (p_nazov, p_popis, p_typ, p_contract_id) ostavaju bezo zmeny.
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
    v_obec record;
    v_id   uuid;
begin
    select id, nazov, kraj into v_obec
      from public.obce_ucty where owner = auth.uid();

    if v_obec.id is null then
        raise exception 'Nemas obecny ucet. Najprv si ho zaloz.';
    end if;
    if trim(coalesce(p_nazov, '')) = '' then
        raise exception 'Zadaj, co potrebujes.';
    end if;
    if p_typ is not null and p_typ not in ('zmluva', 'dotacia', 'ine') then
        raise exception 'Neznamy typ.';
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

grant execute on function public.vytvor_dopyt(text, text, text, bigint, text, text, text) to authenticated;

select 'Dopyty maju sablonu/termin/rozpocet, obce maju telefon/preferovany kontakt.' as vysledok;
