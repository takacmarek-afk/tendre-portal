-- =============================================================================
--  Migracia 88: zmluvy bez dohladatelnej sutaze (prototyp 2. 11. 2026)
--  Pipeline pipeline/bez_sutaze.py denne porovna velke zmluvy z CRZ
--  s Vestnikom UVO (uvo_vysledky, uvo_vyzvy) a zapise sem tie, ku ktorym
--  sutaz nenasla. ZATIAL LEN PRE ADMINA: presnost este nie je overena
--  a verejne oznacenie konkretneho uradu by mohlo poskodit jeho povest.
--  Vo verejnom texte nikdy "nekale", len "bez dohladatelnej sutaze".
--  Bezpecne spustit opakovane.
-- =============================================================================

create table if not exists public.zmluvy_bez_sutaze (
    contract_id      bigint primary key,
    authority_ico    text,
    authority_name   text,
    supplier_ico     text,
    supplier_name    text,
    subject          text,
    sector           text,
    price_total      numeric,
    signed_on        date,
    kategoria        text not null check (kategoria in ('inhouse', 'ostatne')),
    podobnost        numeric,          -- najlepsia zhoda nazvu s oznamenim uradu (0-1)
    stav             text not null check (stav in ('predbezne', 'potvrdene', 'vyriesene')),
    duplicita_k      bigint,           -- ta ista zmluva zverejnena viackrat
    kontrola         text check (kontrola in ('sedi', 'nesedi', 'nejasne')),  -- rucna kontrola
    poznamka         text,
    prvy_krat        date not null default current_date,
    aktualizovane_at timestamptz not null default now()
);

create index if not exists ix_bez_sutaze_urad on public.zmluvy_bez_sutaze (authority_ico);
create index if not exists ix_bez_sutaze_datum on public.zmluvy_bez_sutaze (signed_on desc);

alter table public.zmluvy_bez_sutaze enable row level security;

drop policy if exists bez_sutaze_admin on public.zmluvy_bez_sutaze;
create policy bez_sutaze_admin on public.zmluvy_bez_sutaze
    for select to authenticated
    using (public.je_admin());

revoke all on public.zmluvy_bez_sutaze from anon;
revoke insert, update, delete on public.zmluvy_bez_sutaze from authenticated;

select 'Migracia 88 hotova: zmluvy_bez_sutaze (len admin).' as vysledok;
