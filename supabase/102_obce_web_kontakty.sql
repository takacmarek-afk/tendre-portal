-- 102: E-maily obcí z ich webov (extrakcia Marek, 11. 11. 2026) — pracovná tabuľka.
-- Plní sa jednorazovo (Supabase SQL), spracuje ju pipeline/obce_web_kontakty.py:
-- dohľadá IČO obce, posúdi adresu pravidlami kampane a zapíše do
-- kampan_obce_kontakty so zdrojom 'web'. Len service_role.

create table if not exists public.obce_web_kontakty (
    kod_obce     text primary key,          -- 6-miestny kód ŠÚ SR
    obec         text not null,
    okres        text,
    email        text,
    web          text,
    zdroj_url    text,
    poznamka     text,                       -- diagnostika extrakcie (chyba / pozor)
    nacitane_at  timestamptz not null default now()
);

alter table public.obce_web_kontakty enable row level security;
revoke all on public.obce_web_kontakty from public, anon, authenticated;

select 'Migracia 102 hotova: obce_web_kontakty.' as vysledok;
