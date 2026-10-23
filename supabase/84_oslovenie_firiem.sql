-- =============================================================================
--  84 - OSLOVENIE FIRIEM E-MAILOM (plan prvych 50 platiacich, 23. 10. 2026)
--  Vloz do Supabase: SQL Editor -> New query -> Run. Spustit sa da opakovane.
-- =============================================================================
--
--  Skript pipeline/oslovenie_firiem.py posiela dodavatelom verejneho sektora
--  (upratovanie, ostraha, ...) tri osobne e-maily (den 0, 4, 9) z adresy
--  marek@predtendrom.sk cez Zoho SMTP. NIE cez Resend (jeho pravidla
--  zakazuju studene e-maily).
--
--  PRAVNY ZAKLAD: § 116 ods. 15 zakona c. 452/2021 Z. z. — priamy marketing
--  na ZVEREJNENE kontaktne udaje pravnickej osoby alebo podnikatela bez
--  suhlasu, s moznostou odhlasenia v kazdej sprave. Zdroj adries: Vestnik
--  UVO, pole BT-506 (oficialny e-mail vitaza sutaze). Osobne adresy
--  (meno.priezvisko@) sa bez rucneho schvalenia nepouziju.
--
--  Tabulky su zatvorene: anon ani prihlaseny pouzivatel nema ziadne pravo,
--  admin len citat. Odhlasenie ide cez funkciu oslovenie_firiem_odhlas(token),
--  ktora nevrati nic okrem nazvu firmy, ktorej token patri.
-- =============================================================================

create table if not exists public.oslovenie_firiem_kontakty (
    ico              text primary key,
    nazov            text not null,
    email            text not null,
    --  'ok'          — vseobecna firemna adresa (info@, obchod@ ...) → smie sa pouzit
    --  'na_kontrolu' — osobna alebo nejasna adresa → len po rucnom schvaleni
    --  'vylucene'    — nepouzit (rucne, alebo firma uz je nasim zakaznikom)
    --  'odpovedal'   — firma odpovedala, sekvencia sa zastavi (pise Marek osobne)
    stav             text not null default 'na_kontrolu'
                     check (stav in ('ok', 'na_kontrolu', 'vylucene', 'odpovedal')),
    dovod            text,
    segment          text,                         -- sektor, napr. UPRATOVANIE, OSTRAHA
    kraj             text,                         -- napr. "Bratislavský kraj"
    posledny_urad    text,                         -- posledny obstaravatel, kde vyhrali
    zdroj            text not null default 'uvo',
    zdroj_url        text,                         -- zakazka vo Vestniku, kde je adresa
    zdroj_datum      date,
    token            uuid not null default gen_random_uuid() unique,
    odhlasene_at     timestamptz,
    vytvorene_at     timestamptz not null default now(),
    upravene_at      timestamptz not null default now(),
    constraint oslovenie_firiem_dlzky check (
        char_length(email) <= 254 and char_length(nazov) <= 300
        and (dovod is null or char_length(dovod) <= 300)
    )
);

create index if not exists ix_oslovenie_kontakty_stav on public.oslovenie_firiem_kontakty(stav, segment);
create unique index if not exists ux_oslovenie_kontakty_email on public.oslovenie_firiem_kontakty(lower(email));

create table if not exists public.oslovenie_firiem_odoslane (
    id               bigserial primary key,
    ico              text not null references public.oslovenie_firiem_kontakty(ico) on delete cascade,
    krok             smallint not null check (krok between 1 and 3),
    variant          text,                         -- A/B predmet
    email            text not null,
    predmet          text,
    hook             jsonb,                        -- ktoru zmluvu sme ukazali
    stav             text not null default 'odosiela sa'
                     check (stav in ('odosiela sa', 'odoslane', 'chyba')),
    chyba            text,
    message_id       text,
    odoslane_at      timestamptz not null default now(),
    unique (ico, krok)
);

create index if not exists ix_oslovenie_odoslane_cas on public.oslovenie_firiem_odoslane(odoslane_at desc);

alter table public.oslovenie_firiem_kontakty enable row level security;
alter table public.oslovenie_firiem_odoslane enable row level security;
revoke all on table public.oslovenie_firiem_kontakty from anon, authenticated;
revoke all on table public.oslovenie_firiem_odoslane from anon, authenticated;
revoke all on sequence public.oslovenie_firiem_odoslane_id_seq from anon, authenticated;
grant select on table public.oslovenie_firiem_kontakty to authenticated;
grant select on table public.oslovenie_firiem_odoslane to authenticated;

drop policy if exists oslovenie_kontakty_admin on public.oslovenie_firiem_kontakty;
create policy oslovenie_kontakty_admin on public.oslovenie_firiem_kontakty
    for select to authenticated using ((select public.je_admin()));

drop policy if exists oslovenie_odoslane_admin on public.oslovenie_firiem_odoslane;
create policy oslovenie_odoslane_admin on public.oslovenie_firiem_odoslane
    for select to authenticated using ((select public.je_admin()));

comment on table public.oslovenie_firiem_kontakty is
    'Studene oslovenie firiem (§ 116 ods. 15 z. 452/2021): zverejnene adresy z Vestnika UVO. Odhlaseni ostavaju ako zoznam "neoslovovat". Len service_role zapisuje.';

-- Odhlasenie (volá /odhlasenie-firmy.html po kliknuti na tlacidlo, aj bez prihlasenia)
create or replace function public.oslovenie_firiem_odhlas(p_token text)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_nazov text;
begin
    if p_token is null or p_token !~ '^[0-9a-fA-F-]{36}$' then
        return jsonb_build_object('ok', false);
    end if;
    update public.oslovenie_firiem_kontakty
       set odhlasene_at = coalesce(odhlasene_at, now()),
           upravene_at  = now()
     where token = p_token::uuid
    returning nazov into v_nazov;
    if v_nazov is null then
        return jsonb_build_object('ok', false);
    end if;
    return jsonb_build_object('ok', true, 'firma', v_nazov);
end;
$$;

revoke all on function public.oslovenie_firiem_odhlas(text) from public;
grant execute on function public.oslovenie_firiem_odhlas(text) to anon, authenticated;

select 'Migracia 84 hotova: oslovenie_firiem_kontakty, oslovenie_firiem_odoslane, oslovenie_firiem_odhlas.' as vysledok;
