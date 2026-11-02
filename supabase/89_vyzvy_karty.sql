-- =============================================================================
--  Migracia 89: Vyzvy pre obce (Quick Win A + B), kampan od 24. 11. 2026
--
--  1) obce_register: profil obce pre tvrdy filter (P1) + token karty (P4)
--  2) vyzvy_karty:   rucne overene vyzvy (P2). Bez overil + overene_at sa
--                    vyzva NIKDY nezobrazi ani neposle.
--  3) vyzvy_semafor: odpovede obce na 7 otazok, viazane na token OBCE (nie osoby)
--  4) vyzvy_vyber:   log mesacneho vyberu (co sme obci poslali a preco: dovod[])
--  5) RPC:  karta_vyzvy(kod, token)        - anon, data pre Kartu vyzvy
--           uloz_semafor(token, kod, json) - anon, ulozi odpovede
--           vyzvy_signaly_obci()           - len service_role, vstup pre vyber
--
--  Vzor bezpecnosti ako vsade inde: tabulky zamknute (RLS bez pravidiel pre
--  anon), verejny pristup len cez uzke SECURITY DEFINER funkcie.
--  Bezpecne spustit opakovane.
-- =============================================================================

-- ─── 1. Profil obce (P1 + P4) ────────────────────────────────────────────────
alter table public.obce_register
    add column if not exists ico                    text,
    -- obec | mesto | mestska_cast. Mesta a mestske casti doplni pipeline
    -- (zoznam miest podla zakona 369/1990, prilohy). Predvolene 'obec'.
    add column if not exists typ                    text not null default 'obec',
    add column if not exists pocet_obyvatelov       integer,
    add column if not exists obyvatelia_k           date,      -- k akemu datumu (SU SR)
    add column if not exists nro                    boolean,   -- okres je v zozname NRO
    add column if not exists mrk                    boolean,   -- obec je v Atlase romskych komunit
    add column if not exists rozpocet_bezne_prijmy  numeric,   -- eur, posledny uzavrety rok
    add column if not exists rozpocet_rok           integer,
    -- P4: token obce do odkazu ?o=. Patri OBCI, nie osobe. Pri uniku sa da
    -- vymenit (update ... set karta_token = gen_random_uuid()).
    add column if not exists karta_token            uuid not null default gen_random_uuid();

do $$ begin
    alter table public.obce_register add constraint obce_register_typ_chk
        check (typ in ('obec', 'mesto', 'mestska_cast'));
exception when duplicate_object then null; end $$;

do $$ begin
    alter table public.obce_register add constraint obce_register_obyv_chk
        check (pocet_obyvatelov is null or pocet_obyvatelov >= 0);
exception when duplicate_object then null; end $$;

create unique index if not exists obce_register_token_ux on public.obce_register (karta_token);
create index if not exists obce_register_ico_idx on public.obce_register (ico);

-- ─── 2. Enumy ─────────────────────────────────────────────────────────────────
do $$ begin create type public.vyzva_typ_ziadatela as enum
    ('obec', 'mesto', 'mestska_cast', 'zdruzenie_obci', 'VUC');
exception when duplicate_object then null; end $$;

do $$ begin create type public.vyzva_dph as enum
    ('ano', 'nie', 'podla_ziadatela');
exception when duplicate_object then null; end $$;

do $$ begin create type public.vyzva_financovanie as enum
    ('refundacia', 'predfinancovanie', 'zalohova_platba', 'kombinacia');
exception when duplicate_object then null; end $$;

do $$ begin create type public.vyzva_stupen_pd as enum
    ('ziadna', 'studia', 'DSP', 'DRS');
exception when duplicate_object then null; end $$;

-- ─── 3. Vyzvy (P2) ───────────────────────────────────────────────────────────
create table if not exists public.vyzvy_karty (
    kod                 text primary key,              -- kod vyzvy od poskytovatela
    nazov               text not null,
    poskytovatel        text not null,
    zdroj_url           text not null check (zdroj_url ~ '^https://'),
    program             text,

    typ_ziadatela       public.vyzva_typ_ziadatela[] not null
                        check (cardinality(typ_ziadatela) > 0),
    -- Nazvy presne ako v obce_register (napr. 'Banskobystrický kraj',
    -- 'Okres Revúca'). Prazdne pole = cele SR. Ak su vyplnene oba,
    -- obec musi sediet na kraj ALEBO okres (okres zuzi vyzvu na cast kraja).
    kraje               text[] not null default '{}',
    okresy              text[] not null default '{}',
    len_nro             boolean not null default false,
    len_mrk             boolean not null default false,
    obyv_min            integer check (obyv_min is null or obyv_min >= 0),
    obyv_max            integer check (obyv_max is null or obyv_max >= 0),

    nfp_min             numeric check (nfp_min is null or nfp_min >= 0),
    nfp_max             numeric check (nfp_max is null or nfp_max >= 0),
    spoluucast_pct      numeric not null check (spoluucast_pct between 0 and 100),
    dph_opravnena       public.vyzva_dph not null,
    financovanie        public.vyzva_financovanie not null,

    vyhlasenie          date,
    uzavierka           date,                           -- null = otvorena vyzva
    kolo_uzavierky      date[] not null default '{}',   -- vsetky kola (aj buduce)

    vyzaduje_ius        boolean not null default false,
    vyzaduje_phrsr      boolean not null default true,
    stupen_pd           public.vyzva_stupen_pd not null default 'ziadna',
    vyzaduje_povolenie  boolean not null default false,
    vo_pred_ziadostou   boolean not null default false,

    aktivity            text[] not null default '{}',   -- odpad, MS, ZS, kultura, cesty, voda, energetika...
    signal_sektory      text[] not null default '{}',   -- nase sektory (opportunities.sector)

    -- Rozsirenie oproti specifikacii (pouziva Karta vyzvy, sekcia Prvy krok):
    -- vyzva ma predpisane znenie uznesenia -> nas vzor sa neukaze.
    uznesenie_vlastne_znenie boolean not null default false,

    overil              text,
    overene_at          timestamptz,
    vytvorene_at        timestamptz not null default now(),
    upravene_at         timestamptz not null default now(),

    constraint vyzvy_obyv_rozsah   check (obyv_min is null or obyv_max is null or obyv_min <= obyv_max),
    constraint vyzvy_nfp_rozsah    check (nfp_min  is null or nfp_max  is null or nfp_min  <= nfp_max),
    -- overenie je vzdy dvojica: kto + kedy
    constraint vyzvy_overenie_par  check ((overil is null) = (overene_at is null)),
    constraint vyzvy_uzavierka_v_kolach check (uzavierka is null or uzavierka = any(kolo_uzavierky) or cardinality(kolo_uzavierky) = 0)
);

create index if not exists vyzvy_karty_uzavierka_idx on public.vyzvy_karty (uzavierka);

-- Kazda zmena obsahu zrusi overenie: upravena vyzva sa musi znova skontrolovat.
-- Vynimka: ked update sam nastavuje overil/overene_at (to je to overenie).
create or replace function public.vyzvy_karty_zmena()
returns trigger language plpgsql as $$
begin
    new.upravene_at := now();
    if (new.overene_at is not distinct from old.overene_at)
       and (to_jsonb(new) - array['overil','overene_at','upravene_at','vytvorene_at'])
           is distinct from (to_jsonb(old) - array['overil','overene_at','upravene_at','vytvorene_at']) then
        new.overil := null;
        new.overene_at := null;
    end if;
    return new;
end $$;

drop trigger if exists vyzvy_karty_zmena_trg on public.vyzvy_karty;
create trigger vyzvy_karty_zmena_trg before update on public.vyzvy_karty
    for each row execute function public.vyzvy_karty_zmena();

alter table public.vyzvy_karty enable row level security;
revoke all on public.vyzvy_karty from anon;
revoke insert, update, delete on public.vyzvy_karty from authenticated;
drop policy if exists vyzvy_karty_admin on public.vyzvy_karty;
create policy vyzvy_karty_admin on public.vyzvy_karty
    for select to authenticated using ((select public.je_admin()));

-- ─── 4. Semafor: odpovede obce ───────────────────────────────────────────────
create table if not exists public.vyzvy_semafor (
    kod_obce     text not null references public.obce_register(kod) on delete cascade,
    vyzva_kod    text not null references public.vyzvy_karty(kod) on delete cascade,
    odpovede     jsonb not null,           -- {"q1":"ano","q2":"nie",...}
    upravene_at  timestamptz not null default now(),
    primary key (kod_obce, vyzva_kod)
);
alter table public.vyzvy_semafor enable row level security;
revoke all on public.vyzvy_semafor from anon, authenticated;

-- ─── 5. Log mesacneho vyberu (Quick Win A) ───────────────────────────────────
create table if not exists public.vyzvy_vyber (
    mesiac       date not null,            -- 1. den mesiaca kampane
    kod_obce     text not null references public.obce_register(kod) on delete cascade,
    poradie      smallint not null check (poradie between 1 and 3),
    vyzva_kod    text not null references public.vyzvy_karty(kod),
    skore        integer not null,
    surne        boolean not null default false,
    dovod        text[] not null,
    neoverene    text[] not null default '{}',
    vytvorene_at timestamptz not null default now(),
    primary key (mesiac, kod_obce, poradie)
);
alter table public.vyzvy_vyber enable row level security;
revoke all on public.vyzvy_vyber from anon;
revoke insert, update, delete on public.vyzvy_vyber from authenticated;
drop policy if exists vyzvy_vyber_admin on public.vyzvy_vyber;
create policy vyzvy_vyber_admin on public.vyzvy_vyber
    for select to authenticated using ((select public.je_admin()));

-- ─── 6. RPC: Karta vyzvy (anon) ──────────────────────────────────────────────
-- Bez platneho tokenu vrati len vseobecnu vyzvu (obec = null).
-- Neoverenu vyzvu nevrati nikdy.
create or replace function public.karta_vyzvy(p_kod text, p_token uuid default null)
returns jsonb language sql stable security definer set search_path = public as $$
    select case when v.kod is null then null else jsonb_build_object(
        'vyzva', to_jsonb(v) - array['overil','vytvorene_at','upravene_at'],
        'obec', (select jsonb_build_object(
                    'nazov', r.nazov, 'typ', r.typ, 'kraj', r.kraj, 'okres', r.okres,
                    'pocet_obyvatelov', r.pocet_obyvatelov, 'nro', r.nro, 'mrk', r.mrk)
                 from obce_register r where p_token is not null and r.karta_token = p_token),
        'odpovede', (select s.odpovede from vyzvy_semafor s
                     join obce_register r on r.kod = s.kod_obce
                     where p_token is not null and r.karta_token = p_token and s.vyzva_kod = v.kod)
    ) end
    from (select 1) x
    left join vyzvy_karty v on v.kod = p_kod and v.overene_at is not null;
$$;

-- ─── 7. RPC: ulozenie semafora (anon) ────────────────────────────────────────
create or replace function public.uloz_semafor(p_token uuid, p_kod text, p_odpovede jsonb)
returns jsonb language plpgsql security definer set search_path = public as $$
declare
    v_obec text;
    k text;
begin
    select kod into v_obec from obce_register where karta_token = p_token;
    if v_obec is null then
        return jsonb_build_object('ok', false, 'kod', 'NEZNAMY_TOKEN');
    end if;
    if not exists (select 1 from vyzvy_karty where kod = p_kod and overene_at is not null) then
        return jsonb_build_object('ok', false, 'kod', 'NEZNAMA_VYZVA');
    end if;
    if jsonb_typeof(p_odpovede) <> 'object' then
        return jsonb_build_object('ok', false, 'kod', 'ZLY_FORMAT');
    end if;
    -- povolene len q1..q7 s hodnotou ano|nie|neviem (ziadny volny text)
    for k in select jsonb_object_keys(p_odpovede) loop
        if k !~ '^q[1-7]$' or (p_odpovede->>k) not in ('ano','nie','neviem') then
            return jsonb_build_object('ok', false, 'kod', 'ZLY_FORMAT');
        end if;
    end loop;

    insert into vyzvy_semafor (kod_obce, vyzva_kod, odpovede)
    values (v_obec, p_kod, p_odpovede)
    on conflict (kod_obce, vyzva_kod)
        do update set odpovede = excluded.odpovede, upravene_at = now();
    return jsonb_build_object('ok', true, 'kod', 'ULOZENE');
end $$;

-- ─── 8. RPC: signaly pre vyber (len server) ──────────────────────────────────
-- Jeden riadok na obec s ICO. Vstup pre vyberVyzievPreObec() (src/vyzvy/vyber.ts).
--   konciace:   zmluvy obce koniace do 24 mesiacov (sektor, koniec)
--   dotacie_3r: dotacie obce podpisane za posledne 3 roky (ucel, sektor, datum)
--   dotiahnute: obec ma vyplatenu dotaciu (PPA) alebo dotaciu starsiu ako 2 roky
--               (proxy "projekt dotiahla"; spresnit, ked budu vyplaty aj inde)
create or replace function public.vyzvy_signaly_obci()
returns table (
    kod text, ico text, nazov text, typ text, kraj text, okres text,
    pocet_obyvatelov integer, nro boolean, mrk boolean,
    konciace jsonb, dotacie_3r jsonb, dotiahnute boolean)
language sql stable security definer set search_path = public as $$
    select r.kod, r.ico, r.nazov, r.typ, r.kraj, r.okres,
           r.pocet_obyvatelov, r.nro, r.mrk,
           coalesce((select jsonb_agg(jsonb_build_object('sektor', o.sector, 'koniec', o.effective_to)
                                      order by o.effective_to)
                     from opportunities o
                     where o.authority_cin = r.ico
                       and o.effective_to between current_date and current_date + interval '24 months'), '[]'),
           coalesce((select jsonb_agg(jsonb_build_object('ucel', s.ucel, 'sektor', s.sektor_odhad, 'podpisane', s.podpisane))
                     from subsidies s
                     where s.prijimatel_ico = r.ico
                       and s.podpisane >= current_date - interval '3 years'), '[]'),
           exists (select 1 from subsidies s
                   where s.prijimatel_ico = r.ico
                     and (s.vyplatene or s.podpisane < current_date - interval '2 years'))
    from obce_register r
    where r.ico is not null;
$$;

revoke all on function public.karta_vyzvy(text, uuid)          from public;
revoke all on function public.uloz_semafor(uuid, text, jsonb)  from public;
revoke all on function public.vyzvy_signaly_obci()             from public;
grant execute on function public.karta_vyzvy(text, uuid)         to anon, authenticated;
grant execute on function public.uloz_semafor(uuid, text, jsonb) to anon, authenticated;
grant execute on function public.vyzvy_signaly_obci()            to service_role;

select 'Migracia 89 hotova: vyzvy_karty, semafor, vyber + RPC.' as vysledok;
