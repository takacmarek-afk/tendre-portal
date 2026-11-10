-- =============================================================================
--  97 - OBSTARAVANIA Z EUROFONDOV (ITMS21+), DENNE STAHOVANIE (10. 11. 2026)
--  Vloz do Supabase: SQL Editor -> New query -> Run. Spustit sa da opakovane.
-- =============================================================================
--
--  ITMS21+ Open Data API (api.itms21.sk/public/v1/verejneobstaravanie) ma
--  ~13 700 obstaravani z eurofondovych projektov, z toho ~4 000 v stave
--  "Pripravované" (2,86 mld. €, 1 830 obci): zakazka s nazvom, uradom a
--  predpokladanou hodnotou EŠTE PRED vyhlasenim sutaze. API pusta len
--  pripojenia zo SR/EU (z GitHubu v USA timeout), preto stahuje databaza
--  sama (Frankfurt) cez rozsirenie http, kazdy den cez pg_cron.
--
--  itms_sync()          stiahne vsetky stranky (po 1000) a upsertne
--  itms_vo              surove udaje + sektor/kraj (dopocita pipeline)
--  Ziadne osobne udaje: obstaravatelia su urady a firmy (IČO, adresa sidla).
-- =============================================================================

create extension if not exists http with schema extensions;
create extension if not exists pg_cron;

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

create or replace function public.itms_sync()
returns int
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
    v_log    bigint;
    v_off    int := 0;
    v_size   int := null;
    v_spolu  int := 0;
    v_resp   record;
    v_json   jsonb;
    v_rows   jsonb;
begin
    insert into itms_sync_log default values returning id into v_log;
    perform http_set_curlopt('CURLOPT_TIMEOUT_MS', '60000');
    loop
        select * into v_resp
          from http_get('https://api.itms21.sk/public/v1/verejneobstaravanie?limit=1000&offset=' || v_off);
        if v_resp.status <> 200 then
            raise exception 'ITMS HTTP % na offsete %', v_resp.status, v_off;
        end if;
        v_json := v_resp.content::jsonb;
        v_size := coalesce((v_json->>'size')::int, 0);
        v_rows := coalesce(v_json->'result', v_json->'results', '[]'::jsonb);
        exit when jsonb_array_length(v_rows) = 0;

        insert into itms_vo (id, kod, nazov, stav, predpokladana_hodnota, obstaravatel_ico,
                             obstaravatel_nazov, obstaravatel_obec, obstaravatel_psc,
                             druh_obstaravatela, itms_updated_at, itms_created_at, synced_at)
        select (r->>'id')::bigint, r->>'kod', left(r->>'nazov', 500), r->>'stav',
               nullif(r->>'predpokladanaHodnotaZakazky', '')::numeric,
               r->'obstaravatelSubjekt'->>'ico', left(r->'obstaravatelSubjekt'->>'nazov', 300),
               r->'obstaravatelSubjekt'->'adresa'->>'obec', r->'obstaravatelSubjekt'->'adresa'->>'psc',
               left(r->'druhObstaravatelaVO'->>'nazovSk', 200),
               to_timestamp((r->>'updatedAt')::bigint / 1000.0),
               to_timestamp((r->>'createdAt')::bigint / 1000.0),
               now()
          from jsonb_array_elements(v_rows) r
        on conflict (id) do update set
               kod = excluded.kod, nazov = excluded.nazov, stav = excluded.stav,
               predpokladana_hodnota = excluded.predpokladana_hodnota,
               obstaravatel_ico = excluded.obstaravatel_ico, obstaravatel_nazov = excluded.obstaravatel_nazov,
               obstaravatel_obec = excluded.obstaravatel_obec, obstaravatel_psc = excluded.obstaravatel_psc,
               druh_obstaravatela = excluded.druh_obstaravatela,
               itms_updated_at = excluded.itms_updated_at, synced_at = now(),
               -- pri zmene nazvu sa sektor prepocita
               sektor = case when itms_vo.nazov is distinct from excluded.nazov then null else itms_vo.sektor end;

        v_spolu := v_spolu + jsonb_array_length(v_rows);
        v_off := v_off + jsonb_array_length(v_rows);
        exit when v_off >= v_size or v_off > 200000;
    end loop;
    update itms_sync_log set koniec = now(), nacitane = v_spolu where id = v_log;
    return v_spolu;
exception when others then
    update itms_sync_log set koniec = now(), chyba = left(sqlerrm, 500) where id = v_log;
    raise;
end;
$$;

revoke all on function public.itms_sync() from public, anon, authenticated;

-- Denne o 4:23 UTC (5:23 SEC), pred rannym behom pipeline a e-mailov.
select cron.unschedule(jobid) from cron.job where jobname = 'itms_sync';
select cron.schedule('itms_sync', '23 4 * * *', $c$select public.itms_sync()$c$);

select 'Migracia 97 hotova: itms_vo, itms_sync(), cron itms_sync.' as vysledok;
