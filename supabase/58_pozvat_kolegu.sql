-- =============================================================================
--  58 — "Pozvať kolegu" na účet obce (P3.2 C)
--  Vloz do Supabase: SQL Editor -> New query -> Run. Spustit sa da opakovane.
-- =============================================================================
--
--  ZADANIE (persóna C, malá obec bez úradníkov): "V praxi to často nerobí
--  starosta, ale prednosta, ekonómka alebo zamestnanec spoločného obecného
--  úradu. Umožni pozvať ďalšiu osobu na účet obce."
--
--  ROZHODNUTIE MAREKA (29.9.2026, cez klikatelne otazky v chate): pozývací
--  kód/odkaz (moje odporúčanie), NIE zdieľané heslo/magic-link — druhá
--  osoba dostane VLASTNY prístup viazaný na jej vlastny ucet, ktory sa da
--  neskor aj odobrat, na rozdiel od zdielaneho odkazu s trvalym pristupom.
--
--  PRECO NOVA TABULKA A NIE ZMENA obce_ucty.owner
--  obce_ucty.owner je `uuid not null UNIQUE references auth.users` —
--  presne jeden vlastnik na riadok, a VSETKY doterajsie RLS politiky a
--  RPC funkcie (dopyty_select, reakcie_select, vytvor_dopyt, zatvor_dopyt,
--  uprav_kontakt_obce) su na tomto postavene. Menit typ owner na pole by
--  bola destruktivna zmena schemy. Namiesto toho: nova tabulka
--  `obce_clenovia` (M:N cez jednu obec, v praxi 1:N — viac ludi na jednu
--  obec) + `public.moj_obec_id()` (uz existujuca centralna pomocna funkcia,
--  volana zo VSETKYCH relevantnych RLS politik a RPC) sa rozsiri o
--  "vlastnik ALEBO clen" — takto sa vsetky doterajsie miesta, ktore uz
--  volaju moj_obec_id(), automaticky spravaju spravne aj pre clenov, bez
--  potreby menit kazde jedno miesto zvlast.
--
--  DVE MIESTA, KTORE moj_obec_id() NEPOUZIVALI (priamy "owner = auth.uid()"
--  namiesto volania spolocnej funkcie) — TU OPRAVENE, aby aj tade prešli
--  clenovia: vytvor_dopyt(), zatvor_dopyt(), uprav_kontakt_obce().
--
--  BEZPECNOST POZVANOK
--  Kod pozvanky je samotne UUID riadku v obce_pozvanky (nehadatelne, 122
--  bitov nahodnosti) — ziadna dalsia SELECT politika naň nie je potrebna,
--  pretoze jedina cesta k jeho pouzitiu je SECURITY DEFINER funkcia
--  prijmi_obec_pozvanku(), ktora si kod overi sama (rovnaky vzor ako
--  hladaj_obec/prvych_100_dni_suhrn — klient nikdy priamo necita citlive
--  tabulky, len cez funkcie s presne definovanym vystupom). Pozvanky
--  vyprsavaju po 14 dnoch a daju sa pouzit len raz.
--
--  KTO SMIE POZYVAT/ODOBERAT: LEN VLASTNIK (owner), nie ini clenovia —
--  zabranuje to nekontrolovanemu retazeniu pozvanok a drzi spravu tymu
--  na jednom mieste zodpovednosti, presne ako si to zadanie predstavuje
--  ("umozni [vlastnikovi] pozvat dalsiu osobu").
--
--  PRECO NIE JE TOTO 26_team_pozvanky.sql
--  V projekte uz JEDEN pozyvaci system existuje (26_team_pozvanky.sql,
--  tabulka invitations + funkcie pozvi_clena/prijmi_pozvanku/nazov_pozvanky)
--  — ale ten patri celkom inemu datovemu modelu: organizations/memberships
--  pouzivanemu platenou appkou (app.html, gatovane cez ma_pro()), kde sa
--  POZYVA NA KONKRETNY E-MAIL. Obecne ucty (obce_ucty/trh.html) su
--  samostatny, bezplatny, self-deklarovany system, ktory s
--  organizations/memberships vobec neprepojeny je. Navyse Marek si tu
--  vyslovene zvolil INY mechanizmus — zdielatelny KOD/ODKAZ, nie pozvanie
--  na konkretny e-mail — takze aj keby to bol ten isty datovy model,
--  sablona by nesedela.
--
--  CO SA PRIAMO ZNOVAPOUZIJE: uz hotovy prihlasovaci flow na
--  prihlasenie.html (?pozvanka=<kod>&dalej=trh.html -> signInWithOtp ->
--  navrat s ?pozvanka=<kod>). Aby sa NEPREPISALA existujuca funkcia
--  `nazov_pozvanky(p_token text)`/`prijmi_pozvanku(p_token text)` (tie su
--  pre organizacie a MUSIA ostat presne take, ake su), pouzivaju sa tu
--  nove nazvy `nazov_obec_pozvanky`/`prijmi_obec_pozvanku` — prihlasenie.html
--  potom skusi najprv organizacny lookup a ak ten nevyjde, obecny.
-- =============================================================================

-- ── 1) Clenovia obecneho uctu (okrem vlastnika) ─────────────────────────────
create table if not exists public.obce_clenovia (
    id         uuid primary key default gen_random_uuid(),
    obec_id    uuid not null references public.obce_ucty(id) on delete cascade,
    user_id    uuid not null unique references auth.users(id) on delete cascade,
    created_at timestamptz not null default now(),
    unique (obec_id, user_id)
);

comment on table public.obce_clenovia is
    'Dalsi pouzivatelia s pristupom k uz existujucemu obecnemu uctu (P3.2 C, '
    '"Pozvat kolegu"). user_id je UNIQUE zamerne — jeden clovek smie byt '
    'clenom najviac jednej obce naraz, rovnaky princip ako owner na obce_ucty.';

create index if not exists ix_obce_clenovia_obec on public.obce_clenovia(obec_id);

-- ── 2) Pozývacie kódy ────────────────────────────────────────────────────────
create table if not exists public.obce_pozvanky (
    id            uuid primary key default gen_random_uuid(),
    obec_id       uuid not null references public.obce_ucty(id) on delete cascade,
    vytvoril      uuid not null references auth.users(id) on delete cascade,
    vyprsi_at     timestamptz not null default (now() + interval '14 days'),
    pouzita_at    timestamptz,
    pouzil_user_id uuid references auth.users(id) on delete set null,
    created_at    timestamptz not null default now()
);

comment on table public.obce_pozvanky is
    'Pozyvacie kody na zdielany pristup k obecnemu uctu (P3.2 C). Kod = id '
    'riadku (UUID v odkaze). Bez SELECT politiky pre klienta zamerne — '
    'jedina cesta k nemu je cez prijmi_obec_pozvanku().';

create index if not exists ix_obce_pozvanky_obec on public.obce_pozvanky(obec_id);

-- ── 3) moj_obec_id(): vlastnik ALEBO clen ───────────────────────────────────
-- Nahradza povodnu definiciu (34_obce_marketplace.sql) — rovnaky nazov aj
-- signatura (bez parametrov), teda CREATE OR REPLACE upravi funkciu NA
-- MIESTE, ziadna duplicitna verzia nevznikne (na rozdiel od pripadu s
-- pridanymi parametrami v migracii 55).
create or replace function public.moj_obec_id()
returns uuid
language sql
stable
security definer
set search_path = ''
as $$
    select coalesce(
        (select id from public.obce_ucty where owner = auth.uid()),
        (select obec_id from public.obce_clenovia where user_id = auth.uid())
    );
$$;

-- ── 4) vytvor_dopyt / zatvor_dopyt / uprav_kontakt_obce: clenovia tiez smu ──
-- Rovnaka signatura ako doteraz vo vsetkych troch pripadoch — CREATE OR
-- REPLACE upravi na mieste, ziadna nova verzia.
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
    v_obec_id uuid;
    v_obec    record;
    v_id      uuid;
begin
    v_obec_id := public.moj_obec_id();
    if v_obec_id is null then
        raise exception 'Nemas obecny ucet. Najprv si ho zaloz.';
    end if;
    select id, nazov, kraj into v_obec from public.obce_ucty where id = v_obec_id;

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

create or replace function public.zatvor_dopyt(p_dopyt_id uuid)
returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
    update public.dopyty
       set stav = 'uzavrety', updated_at = now()
     where id = p_dopyt_id
       and obec_id = public.moj_obec_id();
end;
$$;

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
declare
    v_obec_id uuid;
begin
    if auth.uid() is null then
        raise exception 'Nie si prihlaseny.';
    end if;
    if p_preferovany_kontakt is not null
       and p_preferovany_kontakt not in ('email', 'telefon', 'hocijaky') then
        raise exception 'Neznamy preferovany sposob kontaktu.';
    end if;

    v_obec_id := public.moj_obec_id();
    if v_obec_id is null then
        raise exception 'Nemas obecny ucet.';
    end if;

    update public.obce_ucty
       set kontakt_email        = nullif(trim(coalesce(p_kontakt_email, '')), ''),
           kontakt_telefon      = nullif(trim(coalesce(p_kontakt_telefon, '')), ''),
           preferovany_kontakt  = p_preferovany_kontakt
     where id = v_obec_id;
end;
$$;

-- ── 5) Pozyvacie RPC (vytvorenie/zoznam/odobratie — LEN VLASTNIK) ──────────
create or replace function public.vytvor_pozvanku()
returns uuid
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_obec_id uuid;
    v_id      uuid;
begin
    select id into v_obec_id from public.obce_ucty where owner = auth.uid();
    if v_obec_id is null then
        raise exception 'Pozvat kolegu smie len vlastnik obecneho uctu.';
    end if;

    insert into public.obce_pozvanky (obec_id, vytvoril)
    values (v_obec_id, auth.uid())
    returning id into v_id;

    return v_id;
end;
$$;

grant execute on function public.vytvor_pozvanku() to authenticated;

-- Zoznam clenov + nepouzitych pozvanok, na zobrazenie vlastnikovi v trh.html.
create or replace function public.moj_tim()
returns table(
    typ          text,           -- 'clen' | 'pozvanka'
    id           uuid,
    email        text,           -- clen: e-mail z auth.users; pozvanka: null
    vytvorene_at timestamptz,
    vyprsi_at    timestamptz      -- len pri pozvanke
)
language sql
stable
security definer
set search_path = ''
as $$
    select 'clen', c.id, u.email, c.created_at, null::timestamptz
      from public.obce_clenovia c
      join auth.users u on u.id = c.user_id
     where c.obec_id = (select id from public.obce_ucty where owner = auth.uid())
    union all
    select 'pozvanka', p.id, null, p.created_at, p.vyprsi_at
      from public.obce_pozvanky p
     where p.obec_id = (select id from public.obce_ucty where owner = auth.uid())
       and p.pouzita_at is null
       and p.vyprsi_at > now();
$$;

grant execute on function public.moj_tim() to authenticated;

create or replace function public.odober_clena(p_clen_id uuid)
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_obec_id uuid;
begin
    select id into v_obec_id from public.obce_ucty where owner = auth.uid();
    if v_obec_id is null then
        raise exception 'Odobrat clena smie len vlastnik obecneho uctu.';
    end if;

    delete from public.obce_clenovia
     where id = p_clen_id and obec_id = v_obec_id;
end;
$$;

grant execute on function public.odober_clena(uuid) to authenticated;

-- ── 6) Meno obce k kodu, BEZ prihlasenia (banner na prihlasenie.html) ───────
-- Rovnaky ucel ako existujuce nazov_pozvanky(text) pre organizacie, ale
-- iny nazov (nova tabulka, iny typ parametra) — pozri hlavicku suboru.
-- Vracia len nazov obce, ZIADNY e-mail (obecna pozvanka nie je na konkretny
-- e-mail viazana, takze ziadny na zamknutie k dispozicii ani nie je).
create or replace function public.nazov_obec_pozvanky(p_kod uuid)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
    select case when o.nazov is null then jsonb_build_object('ok', false)
                else jsonb_build_object('ok', true, 'nazov', o.nazov)
           end
      from public.obce_pozvanky p
      join public.obce_ucty o on o.id = p.obec_id
     where p.id = p_kod
       and p.pouzita_at is null
       and p.vyprsi_at > now();
$$;

grant execute on function public.nazov_obec_pozvanky(uuid) to anon, authenticated;

-- ── 7) Prijatie pozvanky (druha osoba, uz prihlasena) ───────────────────────
create or replace function public.prijmi_obec_pozvanku(p_kod uuid)
returns uuid
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_pozvanka record;
begin
    if auth.uid() is null then
        raise exception 'Najprv sa prihlas.';
    end if;

    if exists (select 1 from public.obce_ucty where owner = auth.uid())
       or exists (select 1 from public.obce_clenovia where user_id = auth.uid()) then
        raise exception 'Uz mas pristup k obecnemu uctu (vlastnemu alebo cudziemu).';
    end if;

    select * into v_pozvanka
      from public.obce_pozvanky
     where id = p_kod
       and pouzita_at is null
       and vyprsi_at > now();

    if v_pozvanka.id is null then
        raise exception 'Pozvanka neplati - bola uz pouzita, alebo jej vyprsala platnost.';
    end if;

    insert into public.obce_clenovia (obec_id, user_id)
    values (v_pozvanka.obec_id, auth.uid());

    update public.obce_pozvanky
       set pouzita_at = now(), pouzil_user_id = auth.uid()
     where id = p_kod;

    return v_pozvanka.obec_id;
end;
$$;

grant execute on function public.prijmi_obec_pozvanku(uuid) to authenticated;

-- ── 8) RLS ───────────────────────────────────────────────────────────────
alter table public.obce_clenovia enable row level security;
alter table public.obce_pozvanky enable row level security;

-- Clen vidi vlastny clensky riadok, vlastnik vidi vsetkych clenov svojej obce.
drop policy if exists obce_clenovia_select on public.obce_clenovia;
create policy obce_clenovia_select on public.obce_clenovia
    for select to authenticated
    using (
        user_id = auth.uid()
        or obec_id = (select id from public.obce_ucty where owner = auth.uid())
    );
-- (insert/update/delete zamerne bez politiky — vsetko ide cez
--  vytvor_pozvanku()/prijmi_obec_pozvanku()/odober_clena(), rovnaky vzor
--  ako obce_ucty.)

-- Ziadna SELECT politika na obce_pozvanky zamerne — pozri komentar v hlavicke.
-- (insert/update/delete tiez bez politiky, vsetko cez RPC.)

-- ── 9) obce_ucty_select: aj clenovia vidia zakladne udaje svojej obce ──────
drop policy if exists obce_ucty_select on public.obce_ucty;
create policy obce_ucty_select on public.obce_ucty
    for select to authenticated
    using (
        owner = auth.uid()
        or id in (select obec_id from public.obce_clenovia where user_id = auth.uid())
    );

select 'Pozvat kolegu pripravene: obce_clenovia, obce_pozvanky, moj_obec_id() rozsireny.' as vysledok;
