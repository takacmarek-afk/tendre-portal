-- =============================================================================
--  68 — PLANY A PRISTUP (vlna 83, 6. 10. 2026; audit Advisory Board, sekcia 6)
--
--  Opravuje to, co by sa po vypnuti je_zadarmo() ukazalo hned v prvy den:
--
--  1) ZAPLATENY PRISTUP NIKDY NEVYPRSAL. Stripe Checkout bezi ako jednorazova
--     platba (mode: payment); spracuj_platbu_stripe() nastavi stav 'aktivne'
--     a obdobie_konci = +31/+365 dni, ale ma_aktivny_pristup() obdobie_konci
--     nikdy nepozeral. Jedna mesacna platba = trvaly pristup. Teraz sa 'aktivne'
--     pocita len do obdobie_konci (NULL = rucne pridelene bez konca, napr. admin).
--  2) PLAN PORADCA (zadarmo) OTVARAL CELU DATABAZU. ma_aktivny_pristup() sa
--     nepozeral na plan. Poradca teraz vidi len to, co mu cennik sluby:
--     Dopyty od obci + obce, ktore ziadaju o dotaciu + dotacie (to su jeho
--     potencialni klienti) a vlastny profil. Nie konciace zmluvy, ÚVO, dodavatelov.
--  3) START "2 KRAJE A 2 SEKTORY" sa vynucuje aj v appke (RLS): Start vidi
--     v opportunities / subsidies / obce_ziadatelia / uvo_* len riadky zo svojho
--     vyberu (nastavenia_pouzivatela.kraje/sektory, najviac 2 + 2). Growth,
--     Team a skuska su bez obmedzenia. Pocty zvysku vracia start_skryte_pocty().
--  4) Dopyty od obci: ma_dopyty_pristup() zahrna aj skusku (Growth rozsah)
--     a neziada sirsi pristup, ktory poradca uz nema.
--  5) Ceny: Team = Growth + 29 EUR/mes. za kazdeho dalsieho pouzivatela
--     (cenove_plany.team = 89/890 ako zaklad; dalsi pouzivatel 29/290 je v plany.js).
--
--  Dormant, kym je_zadarmo() vracia true (vsetky nove funkcie sa pred tym vzdavaju).
--  Idempotentne.
-- =============================================================================

-- ── 1) Pomocne funkcie ───────────────────────────────────────────────────────

-- Je predplatne (riadok subscriptions) prave aktivne?
create or replace function public._predplatne_aktivne(p_stav text, p_trial_konci timestamptz, p_obdobie_konci timestamptz)
returns boolean
language sql
stable
set search_path = ''
as $$
    select (p_stav = 'aktivne' and (p_obdobie_konci is null or p_obdobie_konci > now()))
        or (p_stav = 'trial' and p_trial_konci > now());
$$;

revoke all on function public._predplatne_aktivne(text, timestamptz, timestamptz) from public, anon;
grant execute on function public._predplatne_aktivne(text, timestamptz, timestamptz) to authenticated, service_role;

-- ── 2) ma_aktivny_pristup: s koncom obdobia a BEZ planu Poradca ──────────────
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
               and s.plan <> 'poradca'
               and public._predplatne_aktivne(s.stav, s.trial_konci, s.obdobie_konci)
        );
$$;

create or replace function public.ma_pro_pre_org(p_org_id uuid)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
    select public.je_zadarmo()
        or (
            p_org_id is not null
            and exists (
                select 1
                  from public.subscriptions s
                 where s.org_id = p_org_id
                   and public._predplatne_aktivne(s.stav, s.trial_konci, s.obdobie_konci)
                   and s.plan in ('trial', 'pro', 'growth', 'team', 'admin')
            )
        );
$$;

-- ma_pro / ma_team: telo ostava, len sa opiera o nove ma_aktivny_pristup()
-- (ktore uz pocita koniec obdobia); poradca v ich zoznamoch nie je.

-- Dopyty od obci: Growth, Team, Poradca, admin a skuska (v rozsahu Growth).
create or replace function public.ma_dopyty_pristup()
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
    select public.je_zadarmo()
        or exists (
            select 1
              from public.subscriptions s
              join public.memberships m on m.org_id = s.org_id
             where m.user_id = auth.uid()
               and public._predplatne_aktivne(s.stav, s.trial_konci, s.obdobie_konci)
               and s.plan in ('trial', 'growth', 'team', 'poradca', 'admin')
        );
$$;

-- Dotacie a obce, ktore ziadaju o dotaciu: kazdy aktivny plan vratane Poradcu
-- (poradca pomaha obciam so ziadostami o dotacie, to je jeho trh).
create or replace function public.ma_pristup_k_dotaciam()
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
               and public._predplatne_aktivne(s.stav, s.trial_konci, s.obdobie_konci)
        );
$$;

revoke all on function public.ma_pristup_k_dotaciam() from public, anon;
grant execute on function public.ma_pristup_k_dotaciam() to authenticated;
revoke all on function public.ma_dopyty_pristup() from public, anon;
grant execute on function public.ma_dopyty_pristup() to authenticated;

-- ── 3) Start: obmedzenie na vybrane kraje a sektory ──────────────────────────

-- Je prihlaseny pouzivatel na plane Start (aktivny pristup, ale nie Growth+)?
create or replace function public.je_start_obmedzeny()
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
    select not public.je_zadarmo()
       and public.ma_aktivny_pristup()
       and not public.ma_pro();
$$;

revoke all on function public.je_start_obmedzeny() from public, anon;
grant execute on function public.je_start_obmedzeny() to authenticated;

-- Kraj riadku patri do vyberu Startu? (prve 2 kraje z nastaveni; null kraj = nie)
create or replace function public.start_kraj_ok(p_kraj text)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
    select not public.je_start_obmedzeny()
        or exists (
            select 1
              from public.nastavenia_pouzivatela n
             where n.user_id = auth.uid()
               and p_kraj is not null
               and p_kraj = any (n.kraje[1:2])
        );
$$;

-- Sektor riadku patri do vyberu Startu? p_null_ok = riadky bez sektoru sa ukazu
-- (dotacie s nezistenym sektorom, rovnako ako pri filtri v appke).
create or replace function public.start_sektor_ok(p_sektor text, p_null_ok boolean default false)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
    select not public.je_start_obmedzeny()
        or exists (
            select 1
              from public.nastavenia_pouzivatela n
             where n.user_id = auth.uid()
               and ((p_sektor is null and p_null_ok)
                    or p_sektor = any (n.sektory[1:2]))
        );
$$;

revoke all on function public.start_kraj_ok(text) from public, anon;
revoke all on function public.start_sektor_ok(text, boolean) from public, anon;
grant execute on function public.start_kraj_ok(text) to authenticated;
grant execute on function public.start_sektor_ok(text, boolean) to authenticated;

-- Politiky (SELECT)
drop policy if exists opp_select on public.opportunities;
create policy opp_select on public.opportunities
    for select to authenticated
    using (public.ma_aktivny_pristup()
           and public.start_kraj_ok(kraj)
           and public.start_sektor_ok(sector, false));

drop policy if exists subsidies_select on public.subsidies;
create policy subsidies_select on public.subsidies
    for select to authenticated
    using (public.ma_pristup_k_dotaciam()
           and public.start_kraj_ok(kraj)
           and public.start_sektor_ok(sektor_odhad, true));

drop policy if exists ziadatelia_select on public.obce_ziadatelia;
create policy ziadatelia_select on public.obce_ziadatelia
    for select to authenticated
    using (public.ma_pristup_k_dotaciam()
           and public.start_kraj_ok(kraj));

drop policy if exists uvo_vysledky_select on public.uvo_vysledky;
create policy uvo_vysledky_select on public.uvo_vysledky
    for select to authenticated
    using (public.ma_aktivny_pristup()
           and public.start_sektor_ok(sektor, true));

drop policy if exists uvo_vyzvy_select on public.uvo_vyzvy;
create policy uvo_vyzvy_select on public.uvo_vyzvy
    for select to authenticated
    using (public.ma_aktivny_pristup()
           and public.start_sektor_ok(sektor, true));

-- Start nesmie ulozit viac nez 2 kraje a 2 sektory (inak by obchadzal limit).
create or replace function public.nastavenia_start_limit()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
    if public.je_start_obmedzeny()
       and (coalesce(cardinality(new.kraje), 0) > 2 or coalesce(cardinality(new.sektory), 0) > 2) then
        raise exception 'START_LIMIT: plan Start obsahuje najviac 2 kraje a 2 sektory.'
            using errcode = '23514';
    end if;
    return new;
end;
$$;

drop trigger if exists trg_nastavenia_start_limit on public.nastavenia_pouzivatela;
create trigger trg_nastavenia_start_limit
    before insert or update on public.nastavenia_pouzivatela
    for each row execute function public.nastavenia_start_limit();

-- Kolko prilezitosti a dotacii Start nevidi (pre ponuku "odomknite Growth").
-- Pre ostatne plany vracia nuly. Pocita len aktualne (zmluvy, ktore este neskoncili).
create or replace function public.start_skryte_pocty()
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
    v_prilezitosti bigint := 0;
    v_dotacie      bigint := 0;
begin
    if not public.je_start_obmedzeny() then
        return jsonb_build_object('start', false, 'prilezitosti', 0, 'dotacie', 0);
    end if;

    select count(*) into v_prilezitosti
      from public.opportunities o
     where (o.effective_to is null or o.effective_to >= current_date)
       and not (public.start_kraj_ok(o.kraj) and public.start_sektor_ok(o.sector, false));

    select count(*) into v_dotacie
      from public.subsidies s
     where not (public.start_kraj_ok(s.kraj) and public.start_sektor_ok(s.sektor_odhad, true));

    return jsonb_build_object('start', true, 'prilezitosti', v_prilezitosti, 'dotacie', v_dotacie);
end;
$$;

revoke all on function public.start_skryte_pocty() from public, anon;
grant execute on function public.start_skryte_pocty() to authenticated;

-- ── 4) Cenove plany: Team = Growth + dalsi pouzivatel ───────────────────────
-- (zaklad 89/890 ako Growth; priplatok za dalsieho pouzivatela 29/290 je v plany.js)
insert into public.cenove_plany (plan, obdobie, suma) values
    ('team', 'mesiac',  89.00), ('team', 'rok', 890.00)
on conflict (plan, obdobie) do update set suma = excluded.suma;

-- ── 5) Pripomienka obnovy (7 dni pred koncom zaplateneho obdobia) ───────────
-- Platba je jednorazova (Stripe mode: payment), predplatne sa NEOBNOVUJE
-- automaticky. Preto 7 dni vopred posleme e-mail s odkazom na platbu.
alter table public.subscriptions
    add column if not exists pripomienka_obnovy_za timestamptz;

-- Kto ma dostat pripomienku: vlastnici firiem s aktivnym zaplatenym planom,
-- ktoremu obdobie konci do 7 dni a pre dany koniec sme este nic neposlali.
-- Len pre service_role (cron v GitHub Actions); nikdy nie pre klienta.
create or replace function public.pripomienky_obnovy()
returns table (org_id uuid, email text, plan text, obdobie_konci timestamptz)
language sql
stable
security definer
set search_path = ''
as $$
    select s.org_id, u.email::text, s.plan, s.obdobie_konci
      from public.subscriptions s
      join public.memberships m on m.org_id = s.org_id and m.rola in ('owner', 'admin')
      join auth.users u on u.id = m.user_id
     where s.stav = 'aktivne'
       and s.plan in ('start', 'growth', 'team', 'poradca', 'pro')
       and s.obdobie_konci is not null
       and s.obdobie_konci > now()
       and s.obdobie_konci <= now() + interval '7 days'
       and s.pripomienka_obnovy_za is distinct from s.obdobie_konci
       and u.email is not null;
$$;

create or replace function public.oznac_pripomienku_obnovy(p_org_id uuid, p_obdobie_konci timestamptz)
returns void
language sql
security definer
set search_path = ''
as $$
    update public.subscriptions
       set pripomienka_obnovy_za = p_obdobie_konci
     where org_id = p_org_id and obdobie_konci = p_obdobie_konci;
$$;

revoke all on function public.pripomienky_obnovy() from public, anon, authenticated;
revoke all on function public.oznac_pripomienku_obnovy(uuid, timestamptz) from public, anon, authenticated;
grant execute on function public.pripomienky_obnovy() to service_role;
grant execute on function public.oznac_pripomienku_obnovy(uuid, timestamptz) to service_role;

select 'Migracia 68 hotova: koniec zaplateneho obdobia, Poradca bez DB zmluv, Start 2+2.' as vysledok;
