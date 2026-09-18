-- =============================================================================
--  TEAM POZVANKY: pozvat kolegu e-mailom (magic-link)
--  Vloz do Supabase: SQL Editor -> New query -> Run. Spustit sa da opakovane.
--  Spustaj PO 06_plany.sql (potrebuje ma_pro()) a 08_zadarmo.sql.
-- =============================================================================
--
--  CO TO JE
--  Datovy model pre viac pouzivatelov na jednu firmu uz existuje
--  (organizations/memberships/subscriptions, schema.sql) — chyba len
--  sposob, ako sa DRUHY clen do firmy dostane. Owner zadá e-mail kolegu,
--  systém pošle pozývací odkaz, kolega sa prihlási (rovnakým magic-link
--  flow ako pri bežnej registrácii) a preklikne sa rovno do organizácie.
--
--  PRECO ZNOVA POUZIVAME EXISTUJUCI MAGIC-LINK FLOW A NIE SUPABASE ADMIN API
--  Supabase vie vygenerovat magic-link priamo servisnym klucom
--  (auth.admin.generate_link), co by usetrilo jeden e-mail navyse. Zvolil
--  som radsej bezpecnejsiu a jednoduchsiu cestu: pozvanka len OZNAMI a
--  odkaze na uz existujuci prihlasenie.html?pozvanka=<token>, kde sa
--  spusti PRESNE ten isty signInWithOtp() flow, aky uz existuje pre
--  bezne prihlasenie. Ziadna nova cesta do auth systemu, ziadna zmena
--  bezpecnostnej kontroly v _obal() (ta odmieta akykolvek odkaz v e-maile,
--  ktory nevedie na predtendrom.sk — spravne, a nechcem to menit kvoli
--  jednej funkcii).
--
--  PRECO SAMOSTATNA TABULKA A NIE STLPEC V memberships
--  Pozvanka NIE JE clenstvo — je to prisľub, ktory sa moze este odmietnut,
--  vypršať alebo nikdy neprijat. `memberships` riadok vznika az v momente
--  prijatia (prijmi_pozvanku), nie skor.
--
--  PRECO stav ZOSTAVA 'cakajuca' AJ PO ODOSLANI E-MAILU
--  `sent_at` sleduje, ci uz pipeline poslala e-mail (aby ho neposlala
--  dvakrat), `stav` sleduje ZIVOTNY CYKLUS pozvanky (cakajuca -> prijata/
--  zrusena/vyprsana). Su to dve nezavisle osi, netreba ich miesat do
--  jedneho stlpca.
-- =============================================================================

create table if not exists public.invitations (
    id          uuid primary key default gen_random_uuid(),
    org_id      uuid not null references public.organizations(id) on delete cascade,
    email       text not null,
    token       text not null unique,
    stav        text not null default 'cakajuca'
                  check (stav in ('cakajuca', 'prijata', 'zrusena', 'vyprsana')),
    invited_by  uuid references auth.users(id) on delete set null,
    created_at  timestamptz not null default now(),
    expires_at  timestamptz not null default (now() + interval '14 days'),
    sent_at     timestamptz,
    accepted_at timestamptz
);

create index if not exists ix_invitations_org     on public.invitations(org_id);
create index if not exists ix_invitations_token   on public.invitations(token);
-- Pipeline (service_role) pravidelne hlada presne toto: cakajuce pozvanky,
-- ktore este neboli odoslane.
create index if not exists ix_invitations_na_odoslanie
    on public.invitations(created_at) where stav = 'cakajuca' and sent_at is null;

alter table public.invitations enable row level security;

-- Ziadna primo pristupna policy pre authenticated/anon rolu. Vsetko ide
-- cez SECURITY DEFINER funkcie nizsie (pozvi_clena, prijmi_pozvanku,
-- moje_pozvanky, nazov_pozvanky) — rovnaky princip ako "nikdy to neries
-- vo frontende" v zvysku schema.sql. service_role (pipeline) RLS
-- obchadza, takze posli_pozvanky.py cita a zapisuje bez obmedzenia.


-- ── Pozvat kolegu (volanie z app.html, len owner) ────────────────────────
create or replace function public.pozvi_clena(p_email text)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_org_id uuid;
    v_rola   text;
    v_email  text := lower(trim(coalesce(p_email, '')));
    v_token  text;
begin
    if auth.uid() is null then
        raise exception 'Nie si prihlaseny.';
    end if;

    if v_email = '' or v_email !~ '^[^@\s]+@[^@\s]+\.[^@\s]+$' then
        return jsonb_build_object('ok', false, 'kod', 'NEPLATNY_EMAIL');
    end if;

    select m.org_id, m.rola into v_org_id, v_rola
      from public.memberships m
     where m.user_id = auth.uid()
     limit 1;

    if v_org_id is null then
        return jsonb_build_object('ok', false, 'kod', 'BEZ_FIRMY');
    end if;

    if v_rola <> 'owner' then
        return jsonb_build_object('ok', false, 'kod', 'LEN_OWNER');
    end if;

    -- Pozvanky su Pro funkcia (rovnake gatovanie ako sledovane_ico,
    -- dodavatelia, ceny_sektor) — pocas otvoreneho obdobia je dostupna
    -- kazdemu, lebo ma_pro() vtedy vracia true pre vsetkych.
    if not public.ma_pro() then
        return jsonb_build_object('ok', false, 'kod', 'VYZADUJE_PRO');
    end if;

    if exists (
        select 1
          from public.memberships mm
          join auth.users u on u.id = mm.user_id
         where mm.org_id = v_org_id and lower(u.email) = v_email
    ) then
        return jsonb_build_object('ok', false, 'kod', 'UZ_CLEN');
    end if;

    -- Predoslu cakajucu pozvanku na ten isty e-mail v tej istej firme
    -- zrusime — plati vzdy len najnovsi token, rovnaky princip ako
    -- "platí len najnovší prihlasovací odkaz" v prihlasenie.html.
    update public.invitations
       set stav = 'zrusena'
     where org_id = v_org_id and email = v_email and stav = 'cakajuca';

    v_token := encode(gen_random_bytes(24), 'hex');

    insert into public.invitations (org_id, email, token, invited_by)
    values (v_org_id, v_email, v_token, auth.uid());

    insert into public.events (org_id, user_id, typ, detail)
    values (v_org_id, auth.uid(), 'pozvanka_odoslana', jsonb_build_object('email', v_email));

    return jsonb_build_object('ok', true);
end;
$$;

grant execute on function public.pozvi_clena(text) to authenticated;


-- ── Prijat pozvanku (volanie z app.html, po prihlaseni pozvaneho) ────────
create or replace function public.prijmi_pozvanku(p_token text)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_inv   record;
    v_email text;
begin
    if auth.uid() is null then
        raise exception 'Nie si prihlaseny.';
    end if;

    select email into v_email from auth.users where id = auth.uid();

    select * into v_inv from public.invitations
     where token = p_token and stav = 'cakajuca';

    if not found then
        return jsonb_build_object('ok', false, 'kod', 'POZVANKA_NEPLATNA');
    end if;

    if v_inv.expires_at < now() then
        update public.invitations set stav = 'vyprsana' where id = v_inv.id;
        return jsonb_build_object('ok', false, 'kod', 'POZVANKA_VYPRSANA');
    end if;

    if lower(v_email) <> v_inv.email then
        return jsonb_build_object('ok', false, 'kod', 'INY_EMAIL',
                                   'pozvany_email', v_inv.email);
    end if;

    if exists (select 1 from public.memberships where user_id = auth.uid()) then
        -- Uz niekam patri (bud uz prijal skor, alebo si medzitym zalozil
        -- vlastnu firmu). Pozvanku nezrusujem — nech to owner vidi a moze
        -- sa opytat, co sa stalo, namiesto tichej straty stopy.
        return jsonb_build_object('ok', false, 'kod', 'UZ_MAS_FIRMU');
    end if;

    insert into public.memberships (user_id, org_id, rola)
    values (auth.uid(), v_inv.org_id, 'member');

    update public.invitations
       set stav = 'prijata', accepted_at = now()
     where id = v_inv.id;

    insert into public.events (org_id, user_id, typ, detail)
    values (v_inv.org_id, auth.uid(), 'pozvanka_prijata', jsonb_build_object('email', v_inv.email));

    return jsonb_build_object('ok', true, 'org_id', v_inv.org_id);
end;
$$;

grant execute on function public.prijmi_pozvanku(text) to authenticated;


-- ── Nazov organizacie k tokenu, BEZ prihlasenia ──────────────────────────
-- Vola prihlasenie.html pred prihlasenim, aby vedelo zobrazit "Boli ste
-- pozvani do <firma>". Zamerne vracia len nazov firmy a pozvany e-mail —
-- nic viac (ziadne ID uzivatelov, ziadne interne udaje).
create or replace function public.nazov_pozvanky(p_token text)
returns jsonb
language sql
stable
security definer
set search_path = public
as $$
    select case when o.nazov is null then jsonb_build_object('ok', false)
                else jsonb_build_object('ok', true, 'nazov', o.nazov, 'email', i.email)
           end
      from public.invitations i
      join public.organizations o on o.id = i.org_id
     where i.token = p_token
       and i.stav = 'cakajuca'
       and i.expires_at > now()
     limit 1;
$$;

-- anon aj authenticated: pozvany este nemusi mat session, ked na odkaz
-- klikne prvykrat.
grant execute on function public.nazov_pozvanky(text) to anon, authenticated;


-- ── Kolegovia a cakajuce pozvanky vo vlastnej firme (nastavenia v app.html) ──
create or replace function public.moji_kolegovia()
returns table(user_id uuid, email text, rola text, created_at timestamptz)
language sql
stable
security definer
set search_path = public
as $$
    select m.user_id, u.email, m.rola, m.created_at
      from public.memberships m
      join auth.users u on u.id = m.user_id
     where m.org_id in (select public.moje_org_ids())
     order by m.created_at;
$$;

grant execute on function public.moji_kolegovia() to authenticated;

create or replace function public.moje_pozvanky()
returns table(id uuid, email text, stav text, created_at timestamptz, expires_at timestamptz)
language sql
stable
security definer
set search_path = public
as $$
    select i.id, i.email, i.stav, i.created_at, i.expires_at
      from public.invitations i
     where i.org_id in (select public.moje_org_ids())
       and i.stav = 'cakajuca'
     order by i.created_at desc;
$$;

grant execute on function public.moje_pozvanky() to authenticated;


-- ── Kontrola ──────────────────────────────────────────────────────────────
select tablename as tabulka_bez_rls
  from pg_tables
 where schemaname = 'public' and rowsecurity = false;

select 'Team pozvanky pripravene. Ak vyssie nie je riadok tabulka_bez_rls, '
       'RLS je vsade zapnuta.' as vysledok;
