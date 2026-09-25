-- =============================================================================
--  48 — KAMPAŇ PRE OBCE PO VOĽBÁCH 2026: kontakty, starostovia, evidencia
--  odoslaných e-mailov a odhlásenie. Plní pipeline/kampan_obce.py a
--  pipeline/volby.py (.github/workflows/kampan-obce.yml).
--  Vlož do Supabase: SQL Editor -> New query -> Run. Spustiť sa dá opakovane.
--
--  PRÁVNY RÁMEC (Claude Doc „Kampaň pre obce po voľbách 2026"): píšeme len
--  na ZVEREJNENÚ úradnú adresu obce (právnická osoba). Poslancom nepíšeme.
--  Každý e-mail má odkaz na odhlásenie; odhlásená obec už nič nedostane.
--
--  ČÍTANIE: nič z toho nie je verejné. Tabuľky majú RLS bez select politiky
--  pre bežných používateľov — číta a zapisuje len pipeline (service_role).
--  Admin (je_admin) vidí stav kampane. Anon smie jedine zavolať
--  kampan_obce_odhlas(token) zo stránky /odhlasenie-obce.html.
-- =============================================================================

-- ─── 1. Vestník ÚVO: oficiálny e-mail obstarávateľa (BT-506) ─────────────
alter table public.uvo_vysledky add column if not exists obstaravatel_email text;
alter table public.uvo_vyzvy    add column if not exists obstaravatel_email text;

-- Verzia parsera, ktorou bolo číslo spracované (pipeline/uvo.py PARSER_VERZIA).
-- Staršie čísla (null) spracuje bežný beh znova a doplní e-maily.
alter table public.uvo_vestniky add column if not exists verzia_parsera int;

-- ─── 2. Zvolení starostovia a primátori (ŠÚ SR, otvorené dáta volieb) ────
create table if not exists public.obce_starostovia (
    rok              int  not null,             -- rok volieb (2022, 2026)
    kod_obce         text not null,             -- 6-miestny kód obce ŠÚ SR
    obec             text not null,
    okres            text,
    kraj             text,
    meno             text,
    priezvisko       text,
    titul_pred       text,
    subjekt          text,                       -- politický subjekt / NEKA
    zdroj_url        text,
    nacitane_at      timestamptz not null default now(),
    primary key (rok, kod_obce)
);

create index if not exists ix_starostovia_obec on public.obce_starostovia(obec);

-- ─── 3. Kontakty obcí pre kampaň ─────────────────────────────────────────
--  stav:  'ok'           — všeobecná úradná adresa (podatelna@, obec@, …)
--                          alebo adresa na doméne obce → smie sa použiť
--         'na_kontrolu'  — adresa vyzerá ako osobná (meno.priezvisko@)
--                          alebo je na doméne inej firmy (externý
--                          obstarávateľ) → Marek ju skontroluje ručne
--         'vylucene'     — nepoužiť (ručne)
create table if not exists public.kampan_obce_kontakty (
    ico              text primary key,
    obec             text not null,
    kraj             text,
    kod_obce         text,                       -- väzba na obce_starostovia
    email            text not null,
    stav             text not null default 'na_kontrolu'
                     check (stav in ('ok', 'na_kontrolu', 'vylucene')),
    dovod            text,                        -- prečo taký stav
    zdroj            text not null,               -- 'uvo' | 'web' | 'minv' | 'rucne'
    zdroj_url        text,                        -- kde je adresa zverejnená
    zdroj_datum      date,
    token            uuid not null default gen_random_uuid() unique,  -- odhlásenie
    odhlasene_at     timestamptz,
    vytvorene_at     timestamptz not null default now(),
    upravene_at      timestamptz not null default now()
);

create index if not exists ix_kampan_kontakty_stav on public.kampan_obce_kontakty(stav);

-- ─── 4. Evidencia odoslaných e-mailov (nikomu dvakrát v tej istej vlne) ──
create table if not exists public.kampan_obce_odoslane (
    id               bigserial primary key,
    ico              text not null,
    vlna             text not null,               -- 'vlna1' | 'vlna2'
    segment          text,                         -- 'poradca' | 'uvo' | 'crz' | 'dotacie'
    email            text not null,
    predmet          text,
    stav             text not null default 'odosiela sa'
                     check (stav in ('odosiela sa', 'odoslane', 'chyba')),
    chyba            text,
    resend_id        text,
    odoslane_at      timestamptz not null default now(),
    unique (ico, vlna)
);

create index if not exists ix_kampan_odoslane_cas on public.kampan_obce_odoslane(odoslane_at desc);

-- ─── 5. RLS ──────────────────────────────────────────────────────────────
alter table public.obce_starostovia     enable row level security;
alter table public.kampan_obce_kontakty enable row level security;
alter table public.kampan_obce_odoslane enable row level security;

drop policy if exists starostovia_admin on public.obce_starostovia;
create policy starostovia_admin on public.obce_starostovia
    for select to authenticated using (public.je_admin());

drop policy if exists kampan_kontakty_admin on public.kampan_obce_kontakty;
create policy kampan_kontakty_admin on public.kampan_obce_kontakty
    for select to authenticated using (public.je_admin());

drop policy if exists kampan_odoslane_admin on public.kampan_obce_odoslane;
create policy kampan_odoslane_admin on public.kampan_obce_odoslane
    for select to authenticated using (public.je_admin());

-- ─── 6. Odhlásenie (volá /odhlasenie-obce.html, aj bez prihlásenia) ─────
--  Token je náhodné UUID z e-mailu. Funkcia nič neprezradí o iných
--  obciach; vráti len názov obce, ktorej token patrí, aby stránka mohla
--  potvrdiť „Obec X sme odhlásili".
create or replace function public.kampan_obce_odhlas(p_token text)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_obec text;
begin
    if p_token is null or p_token !~ '^[0-9a-fA-F-]{36}$' then
        return jsonb_build_object('ok', false);
    end if;
    update public.kampan_obce_kontakty
       set odhlasene_at = coalesce(odhlasene_at, now()),
           upravene_at  = now()
     where token = p_token::uuid
    returning obec into v_obec;
    if v_obec is null then
        return jsonb_build_object('ok', false);
    end if;
    return jsonb_build_object('ok', true, 'obec', v_obec);
end;
$$;

revoke all on function public.kampan_obce_odhlas(text) from public;
grant execute on function public.kampan_obce_odhlas(text) to anon, authenticated;

select 'uvo e-maily, obce_starostovia, kampan_obce_kontakty, kampan_obce_odoslane, kampan_obce_odhlas pripravené.' as vysledok;
