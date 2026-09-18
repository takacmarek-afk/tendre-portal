-- =============================================================================
--  SANCA NA VYHRU (#13) — PRO tabulka
--  Vloz do Supabase: SQL Editor -> New query -> Run. Spustit sa da opakovane.
--  Spustaj PO 07_revizia.sql (potrebuje ma_pro()) a PO 23_moje_ico.sql.
-- =============================================================================
--
--  CO TO JE
--  Osobny signal "kto tu historicky vyhrava" pre konkretneho pouzivatela:
--  appka porovna vlastne ICO (odber.moje_ico) s `supplier_cin` (kto ma
--  zakazku TERAZ) a s `top_dodavatel_cin` (kto v tomto obstaravatel+sektor
--  historicky vyhrava najcastejsie, z pipeline/score.py::_historia()).
--  Vysledok su TRI KVALITATIVNE STAVY (ziadne cislo/percento — data su
--  riedke, viz audit 17.9.2026: len 1.7% prilezitosti ma riziko=VYSOKE):
--    1. "ste to vy"          — moje_ico == top_dodavatel_cin
--    2. "silny iny hrac"     — top_dodavatel_cin existuje a nie je to ja
--    3. (ticho, ziadny riadok alebo riziko=NEZNAME) — historia je prilis
--       riedka na akykolvek signal, appka radsej mlci nez si vymysla
--
--  PRECO VLASTNA TABULKA, NIE STLPCE V ceny_prilezitosti
--  Ina PRO funkcia, iny ucel — rovnaky vzor ako tam_sektor/trhovy_podiel
--  dostali vlastne tabulky. RLS je riadkova (nie stlpcova), takze Pro-only
--  data nemozu byt navyse stlpce v `opportunities` (Start plan by ich
--  vytiahol cez ?select=*) ani v uz existujucej Pro tabulke s inym ucelom.
--
--  GDPR
--  top_dodavatel_cin/top_dodavatel_pravnicky pochadzaju z _historia(), ktora
--  ich pocita LEN z pravnickych osob (analytics.je_pravnicka_osoba) —
--  fyzicka osoba (zivnostnik) sa sem nikdy nedostane, rovnako ako v
--  dodavatelia/trhovy_podiel.
-- =============================================================================

create table if not exists public.sanca_na_vyhru (
    contract_id                     bigint primary key,
    supplier_cin                    text,
    top_dodavatel_cin               text,
    top_dodavatel_pravnicky         text,
    podiel_top_dodavatela_pravnicky numeric,
    riziko                          text,
    last_seen_at                    date,
    refreshed_at                    timestamptz not null default now()
);

alter table public.sanca_na_vyhru enable row level security;

drop policy if exists sanca_na_vyhru_select on public.sanca_na_vyhru;
create policy sanca_na_vyhru_select on public.sanca_na_vyhru
    for select to authenticated
    using (public.ma_pro());

select 'sanca_na_vyhru pripravena (Pro-only, rovnako ako ceny_prilezitosti).' as vysledok;
