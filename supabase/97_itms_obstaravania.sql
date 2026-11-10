-- =============================================================================
--  97 - OBSTARAVANIA Z EUROFONDOV (ITMS21+), IMPORT CEZ PREHLIADAC (10. 11. 2026)
--  Vloz do Supabase: SQL Editor -> New query -> Run. Spustit sa da opakovane.
-- =============================================================================
--
--  ITMS21+ Open Data API (api.itms21.sk/public/v1/verejneobstaravanie) ma
--  ~13 700 obstaravani z eurofondovych projektov, z toho ~4 000 v stave
--  "Pripravované" (2,86 mld. €, 1 830 obci): zakazka s nazvom, uradom a
--  predpokladanou hodnotou EŠTE PRED vyhlasenim sutaze. API pusta len
--  pripojenia zo SR (z GitHubu v USA aj zo Supabase vo Frankfurte odmietnute), preto stahuje
--  prehliadac na Marekovom pocitaci (slovenska adresa) a posle ich cez itms_import().
--
--  itms_import(token, rows)  upsert jednej stranky (najviac 2000 riadkov)
--  itms_vo                   surove udaje + sektor/kraj (dopocita pipeline)
--  Ziadne osobne udaje: obstaravatelia su urady a firmy (IČO, adresa sidla).
-- =============================================================================

create table if not exists public.itms_vo (
    id                    bigint primary key,
    kod                   text,
    nazov                 text,
    stav                  text,
    predpokladana_hodnota numeric,
    obstaravatel_ico      text,
    obstaravatel_nazov    text,
    obstaravatel_obec     text,
    obstaravatel_psc      text,
    druh_obstaravatela    text,
    itms_updated_at       timestamptz,
    itms_created_at       timestamptz,
    sektor                text,      -- dopocita pipeline (klasifikacia nazvu)
    kraj                  text,      -- dopocita pipeline (PSC -> kraj)
    synced_at             timestamptz not null default now()
);

create index if not exists ix_itms_vo_stav on public.itms_vo(stav);
create index if not exists ix_itms_vo_sektor_kraj on public.itms_vo(sektor, kraj) where stav = 'Pripravované';
create index if not exists ix_itms_vo_ico on public.itms_vo(obstaravatel_ico);

alter table public.itms_vo enable row level security;
revoke all on public.itms_vo from public, anon, authenticated;

create table if not exists public.itms_sync_log (
    id          bigserial primary key,
    zaciatok    timestamptz not null default now(),
    koniec      timestamptz,
    nacitane    int,
    chyba       text
);
alter table public.itms_sync_log enable row level security;
revoke all on public.itms_sync_log from public, anon, authenticated;

-- API ITMS21+ pusta len slovenske adresy (z Frankfurtu aj z GitHubu odmietnute,
-- overene 10. 11. 2026). Data preto stiahne prehliadac na Marekovom pocitaci
-- (slovenska adresa) a posle ich sem. Import chrani tajny token; v repozitari
-- je len jeho SHA-256. Funkcia prijme len polia, ktore pozna.
create or replace function public.itms_import(p_token text, p_rows jsonb)
returns int
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
    v_n int;
begin
    if encode(digest(coalesce(p_token, ''), 'sha256'), 'hex')
       <> '16643f922144d0624863245a4ee5e744503ba160b308739b426e289686782681' then
        raise exception 'Neplatny token' using errcode = '42501';
    end if;
    if jsonb_typeof(p_rows) <> 'array' or jsonb_array_length(p_rows) > 2000 then
        raise exception 'Neplatne data';
    end if;
    insert into itms_vo (id, kod, nazov, stav, predpokladana_hodnota, obstaravatel_ico,
                         obstaravatel_nazov, obstaravatel_obec, obstaravatel_psc,
                         druh_obstaravatela, itms_updated_at, itms_created_at, synced_at)
    select (r->>'id')::bigint, left(r->>'kod', 40), left(r->>'nazov', 500), left(r->>'stav', 60),
           nullif(r->>'predpokladanaHodnotaZakazky', '')::numeric,
           left(r->'obstaravatelSubjekt'->>'ico', 20), left(r->'obstaravatelSubjekt'->>'nazov', 300),
           left(r->'obstaravatelSubjekt'->'adresa'->>'obec', 120), left(r->'obstaravatelSubjekt'->'adresa'->>'psc', 10),
           left(r->'druhObstaravatelaVO'->>'nazovSk', 200),
           to_timestamp((r->>'updatedAt')::bigint / 1000.0),
           to_timestamp((r->>'createdAt')::bigint / 1000.0),
           now()
      from jsonb_array_elements(p_rows) r
     where (r->>'id') ~ '^\d+$'
    on conflict (id) do update set
           kod = excluded.kod, nazov = excluded.nazov, stav = excluded.stav,
           predpokladana_hodnota = excluded.predpokladana_hodnota,
           obstaravatel_ico = excluded.obstaravatel_ico, obstaravatel_nazov = excluded.obstaravatel_nazov,
           obstaravatel_obec = excluded.obstaravatel_obec, obstaravatel_psc = excluded.obstaravatel_psc,
           druh_obstaravatela = excluded.druh_obstaravatela,
           itms_updated_at = excluded.itms_updated_at, synced_at = now(),
           sektor = case when itms_vo.nazov is distinct from excluded.nazov then null else itms_vo.sektor end;
    get diagnostics v_n = row_count;
    insert into itms_sync_log (koniec, nacitane) values (now(), v_n);
    return v_n;
end;
$$;

revoke all on function public.itms_import(text, jsonb) from public;
grant execute on function public.itms_import(text, jsonb) to anon, authenticated;

select 'Migracia 97 hotova: itms_vo, itms_import().' as vysledok;
