-- =============================================================================
--  OTVORENE OBDOBIE: cely portal zadarmo
--  Vloz do Supabase: SQL Editor -> New query -> Run. Spustit sa da opakovane.
--  Spustaj PO 07_revizia.sql.
-- =============================================================================
--
--  DOVOD
--  Portal za platenou stenou nema komu ukazat hodnotu. Zadarmo je z neho
--  argument do rozhovoru ("pozri sa, nic to nestoji") a jediny marketingovy
--  kanal, ktory sa da uzivit bez rozpoctu.
--
--  Cena sa NESTANOVUJE. Kazdy odhad ceny je presne ten druh nepodlozeneho
--  predpokladu, ktory nas v tomto projekte uz stal jednu vyhodenu funkciu
--  (`price_total` ako suma vratane dodatkov, namerane 0,15 %). Cenu povedia
--  zakaznici, ktori budu chodit na tyzdenny e-mail.
--
--  AKO SA TO VRATI SPAT
--  Jedina zmena: v `je_zadarmo()` vrat `false`. Stlpce `plan`, `stav`
--  a `trial_konci` zostavaju nedotknute a fungujuce, takze delenie na
--  Start a Pro sa zapne v tej istej sekunde.
-- =============================================================================

-- ── 1. GLOBALNY PREPINAC ─────────────────────────────────────────────────
create or replace function public.je_zadarmo()
returns boolean
language sql
immutable
as $$ select true; $$;      -- <<<<<< SEM sa siaha pri spopatneni

comment on function public.je_zadarmo() is
    'Otvorene obdobie. Kym vracia true, cely portal je zadarmo pre kazdeho '
    'prihlaseneho. Spoplatnenie = zmenit na false, nic ine.';

grant execute on function public.je_zadarmo() to authenticated;


-- ── 2. PRISTUP ───────────────────────────────────────────────────────────
-- Povodna logika zostava, len sa pred nu dava prepinac. Skuska na tri dni
-- teda uz nikoho neobmedzuje, ale zaznamy o nej sa dalej vedu.
create or replace function public.ma_aktivny_pristup()
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
    select public.je_zadarmo()
        or exists (
            select 1
            from public.memberships m
            join public.subscriptions s on s.org_id = m.org_id
            where m.user_id = auth.uid()
              and (s.stav = 'aktivne'
                   or (s.stav = 'trial' and s.trial_konci > now()))
        );
$$;

create or replace function public.ma_pro()
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
    select public.je_zadarmo()
        or (public.ma_aktivny_pristup()
            and exists (
                select 1
                  from public.subscriptions s
                  join public.memberships m on m.org_id = s.org_id
                 where m.user_id = auth.uid()
                   and s.plan in ('trial', 'pro')
            ));
$$;

grant execute on function public.ma_aktivny_pristup() to authenticated;
grant execute on function public.ma_pro() to authenticated;


-- ── 3. UZ ZALOZENE FIRMY NESMU VYPRSAT ───────────────────────────────────
-- Aby to fungovalo aj keby sa prepinac vypol, existujucim skuskam
-- posunieme koniec. Nikoho tym nepripravime o nic.
update public.subscriptions
   set trial_konci = greatest(trial_konci, now() + interval '365 days')
 where stav = 'trial';


-- ── 4. ODBER TYZDENNEHO E-MAILU ──────────────────────────────────────────
--
--  Toto je jediny udaj, ktory teraz naozaj potrebujeme: KTO chce, aby mu
--  prilezitosti chodili samy. Portal, do ktoreho sa treba prihlasit, ma
--  nespravny tvar — v malej firme nie je cinnost "pozerat tendrovy portal"
--  nikoho ulohou. Kto si tu zaskrtne odber, je zaroven zoznam ludi, ktorych
--  ma zmysel zavolat a spytat sa ich na cenu.
--
--  Rozosielanie tu NIE JE. Zbierame len zaujem.
create table if not exists public.odber (
    user_id     uuid primary key references auth.users(id) on delete cascade,
    org_id      uuid references public.organizations(id) on delete cascade,
    chce_email  boolean not null default true,
    sektor      text,                    -- null = vsetky
    kraj        text,                    -- null = cele Slovensko
    email       text,
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);

create index if not exists ix_odber_chce on public.odber(chce_email) where chce_email;

alter table public.odber enable row level security;

drop policy if exists odber_select on public.odber;
create policy odber_select on public.odber
    for select to authenticated
    using (user_id = auth.uid());

drop policy if exists odber_insert on public.odber;
create policy odber_insert on public.odber
    for insert to authenticated
    with check (user_id = auth.uid());

drop policy if exists odber_update on public.odber;
create policy odber_update on public.odber
    for update to authenticated
    using (user_id = auth.uid())
    with check (user_id = auth.uid());


-- ── 5. KONTROLA ──────────────────────────────────────────────────────────
select tablename as tabulka_bez_rls
  from pg_tables
 where schemaname = 'public' and rowsecurity = false;

select 'Otvorene obdobie zapnute. Tabulka odber vytvorena. '
       'Ak vyssie nie je riadok tabulka_bez_rls, RLS je vsade zapnuta.' as vysledok;
