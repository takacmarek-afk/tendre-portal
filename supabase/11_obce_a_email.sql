-- ════════════════════════════════════════════════════════════════════════
--  VRSTVA PRE OBCE + TÝŽDENNÝ E-MAIL
--
--  Spusti v SQL editore Supabase ako jeden celok. Je to bezpečné spustiť
--  aj opakovane — všetko je `if not exists` alebo `drop ... create`.
--
--  Vzniklo po telefonáte so starostkou malej obce: nevie, kde výzvy hľadať.
--  Zoznam otvorených výziev sa z verejných dát spoľahlivo zostaviť nedá,
--  preto tu sú dve tabuľky, ktoré sa z Centrálneho registra zmlúv zostaviť
--  DAJÚ, plus tretia na nespoľahlivé výzvy a štvrtá na odber.
-- ════════════════════════════════════════════════════════════════════════


-- ─── 1. Kto práve teraz rozdáva peniaze obciam ──────────────────────────
-- Výzva je prísľub. Podpísaná zmluva je dôkaz, že program platí.
create table if not exists public.aktivne_programy (
    poskytovatel     text primary key,
    zmluv_30d        integer,
    zmluv_90d        integer,
    obci_90d         integer,
    objem_90d        numeric,
    median_dotacie   numeric,
    najmensia        numeric,
    najvacsia        numeric,
    hlavny_ucel      text,
    posledna_zmluva  date,
    last_seen_at     date,
    refreshed_at     timestamptz not null default now()
);

create index if not exists ix_programy_objem on public.aktivne_programy(objem_90d desc);


-- ─── 2. Sprostredkovatelia ──────────────────────────────────────────────
-- VEDOME TU NIE JE ÚSPEŠNOSŤ a nikdy nebude. Dôvody:
--   1. Sprostredkovateľ v žiadosti o dotáciu nefiguruje — podáva ju obec.
--      Nedokážeme teda odlíšiť "obec dostala dotáciu vďaka firme X" od
--      "obec dostala dotáciu a zhodou okolností mala zmluvu s firmou X".
--   2. Firiem je okolo sedemdesiatich a najväčšia má necelú desiatku obcí.
--      Percento úspešnosti pri n = 2 nie je štatistika.
--   3. Nesprávne číslo pri mene firmy, ktorej z toho žije, je právny problém.
-- Zverejňujeme len fakty z verejných zmlúv a každý sa dá overiť v CRZ.
create table if not exists public.sprostredkovatelia (
    kluc              text primary key,   -- IČO, a keď chýba, názov
    sprostredkovatel  text not null,
    supplier_cin      text,
    obci              integer,
    zmluv             integer,
    kraje             text,
    median_ceny       numeric,
    prva_zmluva       date,
    posledna_zmluva   date,
    last_seen_at      date,
    refreshed_at      timestamptz not null default now()
);

create index if not exists ix_sprostred_obci on public.sprostredkovatelia(obci desc);


-- ─── 3. Otvorené výzvy (nespoľahlivý zdroj) ─────────────────────────────
-- Pipeline sa o ne pokúša z troch zdrojov. ITMS2014+ ku 16. 9. 2026 vracia
-- 403, eurofondy.gov.sk nemá výzvy ako samostatný typ obsahu. Keď je táto
-- tabuľka prázdna, stránka pre obce ukáže len aktívne programy — a to je
-- v poriadku, je to tá časť, na ktorú sa dá spoľahnúť.
create table if not exists public.vyzvy (
    id           bigserial primary key,
    nazov        text not null,
    poskytovatel text,
    url          text,
    zdroj        text not null,
    uzavretie    date,
    popis        text,
    pre_obce     boolean,
    stiahnute    date,
    last_seen_at date,
    refreshed_at timestamptz not null default now()
);

-- Ten istý záznam nechceme dvakrát. URL môže chýbať, preto dva indexy.
create unique index if not exists ux_vyzvy_url on public.vyzvy(url) where url is not null;
create unique index if not exists ux_vyzvy_nazov on public.vyzvy(nazov) where url is null;
create index if not exists ix_vyzvy_obce on public.vyzvy(pre_obce, uzavretie);


-- ─── 4. Odber pre obce ──────────────────────────────────────────────────
-- Zámerne BEZ prihlásenia. Starostka, ktorá nemá čas ani chuť sa
-- registrovať, je presne ten človek, ktorému to má pomôcť. Registračná
-- prekážka by ho odfiltrovala ako prvého.
create table if not exists public.odber_obce (
    id             bigserial primary key,
    email          text not null,
    obec           text,
    ico            text,
    kraj           text,
    potvrdeny      boolean not null default true,
    posledny_email timestamptz,
    zdroj          text,
    created_at     timestamptz not null default now()
);

create unique index if not exists ux_odber_obce_email
    on public.odber_obce(lower(email));


-- ════════════════════════════════════════════════════════════════════════
--  PRÁVA
-- ════════════════════════════════════════════════════════════════════════

alter table public.aktivne_programy   enable row level security;
alter table public.sprostredkovatelia enable row level security;
alter table public.vyzvy              enable row level security;
alter table public.odber_obce         enable row level security;

-- Tri tabuľky sú verejné na čítanie. Sú to agregáty z už verejných zmlúv
-- a celý zmysel tejto vrstvy je, že ju uvidí aj neprihlásený starosta.
drop policy if exists programy_select on public.aktivne_programy;
create policy programy_select on public.aktivne_programy
    for select to anon, authenticated using (true);

drop policy if exists sprostred_select on public.sprostredkovatelia;
create policy sprostred_select on public.sprostredkovatelia
    for select to anon, authenticated using (true);

drop policy if exists vyzvy_select on public.vyzvy;
create policy vyzvy_select on public.vyzvy
    for select to anon, authenticated using (true);

-- Odber: hocikto môže PRIDAŤ svoj e-mail, ale NIKTO ho nesmie čítať.
-- Bez toho by si ktokoľvek stiahol zoznam e-mailov všetkých starostov
-- na Slovensku jedným dopytom. Číta to výhradne pipeline cez service_role,
-- ktorý RLS obchádza.
drop policy if exists odber_obce_insert on public.odber_obce;
create policy odber_obce_insert on public.odber_obce
    for insert to anon, authenticated with check (true);

-- Žiadna select politika tu ZÁMERNE nie je. Bez nej je čítanie zakázané.

comment on table public.odber_obce is
    'Odber pre obce. Anon smie len INSERT, citanie je zakazane (ziadna select politika).';
comment on table public.sprostredkovatelia is
    'Fakty z verejnych zmluv. Uspesnost tu zamerne NIE JE, vid 11_obce_a_email.sql.';


-- ════════════════════════════════════════════════════════════════════════
--  KONTROLA
-- ════════════════════════════════════════════════════════════════════════
select 'Hotovo. Tabulky:' as vysledok
union all select '  aktivne_programy   — ' || count(*)::text || ' riadkov' from public.aktivne_programy
union all select '  sprostredkovatelia — ' || count(*)::text || ' riadkov' from public.sprostredkovatelia
union all select '  vyzvy              — ' || count(*)::text || ' riadkov' from public.vyzvy
union all select '  odber_obce         — ' || count(*)::text || ' riadkov' from public.odber_obce
union all select 'Naplni ich najblizsi beh pipeline.';


-- ════════════════════════════════════════════════════════════════════════
--  DOPLNENÉ 16. 9. 2026 — CHÝBAJÚCI STĹPEC V TABUĽKE `odber`
--
--  Tabuľka `odber` (dodávatelia) vznikla v 08_zadarmo.sql, teda skôr než
--  odosielač e-mailov. Stĺpec `posledny_email` som pridal len do novej
--  `odber_obce` a do tejto nie.
--
--  Prejavilo sa to takto: zápis po odoslaní je v try/except, takže nič
--  nespadlo — len tichý warning. Ale keďže sa nikam nezapíše, kedy e-mail
--  naposledy odišiel, každý ďalší by sa pozeral len 7 dní dozadu namiesto
--  „od posledného odoslania". Pri týždennej kadencii to náhodou vychádza,
--  pri vynechanom behu by prišli duplikáty alebo by sa niečo stratilo.
--
--  Našiel som to až pri kontrole dát po prvom behu nasucho — v logu to
--  vidieť nebolo, pretože tichý warning sa nevypísal (zápis sa spúšťa len
--  pri skutočnom odoslaní, nie nasucho).
-- ════════════════════════════════════════════════════════════════════════

alter table public.odber
    add column if not exists posledny_email timestamptz;

select 'odber ma posledny_email: ' ||
       (select count(*)::text from information_schema.columns
        where table_schema='public' and table_name='odber'
          and column_name='posledny_email') as vysledok;
