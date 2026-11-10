-- =============================================================================
--  99 - EUROFONDY: KTORE "PRIPRAVOVANE" UZ URAD VYHLASIL (10. 11. 2026)
--  Vloz do Supabase: SQL Editor -> New query -> Run. Spustit sa da opakovane.
--  Predpoklad: migracie 97 a 98.
-- =============================================================================
--  ITMS21+ meni stav s oneskorenim: z 4 000 "Pripravované" je asi 500 uz
--  vyhlasenych vo Vestniku (rovnake ICO obstaravatela, rovnaky nazov).
--  pipeline/itms_parovanie.py ich denne paruje a zapise sem odkaz na sutaz.
--  Pouzitie: (1) pripravovane = len nevyhlasene, (2) upozornenie firmam,
--  ze obstaravanie z eurofondov v ich odbore a kraji prave vyhlasili.
--  itms_import() tieto stlpce neprepisuje.
-- =============================================================================

alter table public.itms_vo add column if not exists vyhlasene_oznamenie_id bigint;
alter table public.itms_vo add column if not exists vyhlasene_nazov        text;
alter table public.itms_vo add column if not exists vyhlasene_url          text;
alter table public.itms_vo add column if not exists vyhlasene_publikovane  date;
alter table public.itms_vo add column if not exists vyhlasene_lehota       timestamptz;
alter table public.itms_vo add column if not exists vyhlasene_skore        numeric;
alter table public.itms_vo add column if not exists vyhlasene_zistene_at   timestamptz;
create index if not exists ix_itms_vo_vyhlasene on public.itms_vo(vyhlasene_zistene_at) where vyhlasene_zistene_at is not null;

create or replace function public._trh_firmy(p_cin text)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
    with nuts(kraj, kod) as (values
        ('Bratislavský kraj', 'SK010'), ('Trnavský kraj', 'SK021'), ('Trenčiansky kraj', 'SK022'),
        ('Nitriansky kraj', 'SK023'), ('Žilinský kraj', 'SK031'), ('Banskobystrický kraj', 'SK032'),
        ('Prešovský kraj', 'SK041'), ('Košický kraj', 'SK042')),
    moje as (
        select c.authority_cin, c.sector
          from public.contracts c
         where c.supplier_cin = p_cin
           and coalesce(c.signed_on, c.effective_from) >= current_date - 1826
    ),
    sektor as (
        select coalesce(
            (select d.hlavny_sektor from public.dodavatelia d
              where d.supplier_cin in (p_cin, lpad(p_cin, 8, '0')) and d.hlavny_sektor is not null
              limit 1),
            (select m.sector from moje m where m.sector is not null and m.sector <> 'DOTACIE_NFP'
              group by m.sector order by count(*) desc, m.sector limit 1)) as s
    ),
    kraje as (
        select distinct op.kraj
          from public.opportunities op
         where op.kraj is not null
           and op.authority_cin in (select authority_cin from moje)
    ),
    kody as (
        select n.kod from nuts n
         where n.kraj in (select kraj from kraje) or not exists (select 1 from kraje)
    ),
    opp as (
        select op.price_total
          from public.opportunities op
          join public.contracts c on c.id = op.contract_id
         where op.sector = (select s from sektor)
           and (op.kraj in (select kraj from kraje) or not exists (select 1 from kraje))
           and op.effective_to between current_date and current_date + 365
           and c.supplier_cin <> p_cin
    ),
    vys as (
        select v.pocet_ponuk
          from public.uvo_vysledky v
         where v.sektor = (select s from sektor)
           and v.podpisane >= current_date - 730
           and v.pocet_ponuk is not null
           and left(coalesce(v.nuts, ''), 5) in (select kod from kody)
    ),
    itms as (
        select i.predpokladana_hodnota
          from public.itms_vo i
         where i.stav = 'Pripravované'
           and i.vyhlasene_zistene_at is null
           and i.sektor = (select s from sektor)
           and (i.kraj in (select kraj from kraje) or not exists (select 1 from kraje))
           and i.itms_updated_at >= now() - interval '24 months'
    ),
    otv as (
        select 1
          from public.uvo_vyzvy z
         where z.typ = 'sutaz'
           and z.sektor = (select s from sektor)
           and z.lehota_ponuk >= now()
           and left(coalesce(z.nuts, ''), 5) in (select kod from kody)
    )
    select case when (select s from sektor) is null then null else jsonb_build_object(
        'sektor',              (select s from sektor),
        'kraje',               coalesce((select jsonb_agg(kraj order by kraj) from kraje), '[]'::jsonb),
        'prilezitosti_12m',    (select count(*) from opp),
        'prilezitosti_objem',  (select sum(price_total) filter (where price_total > 0) from opp),
        'vysledkov_24m',       (select count(*) from vys),
        'jedna_ponuka_24m',    (select count(*) filter (where pocet_ponuk = 1) from vys),
        'otvorene_sutaze',     (select count(*) from otv),
        'eurofondy_pripravovane', (select count(*) from itms),
        'eurofondy_objem',     (select sum(predpokladana_hodnota) filter (where predpokladana_hodnota > 0) from itms)
    ) end;
$$;

revoke all on function public._trh_firmy(text) from public, anon, authenticated;

create or replace function public.itms_pripravovane(p_sektory text[] default null, p_kraje text[] default null)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
    with z as (
        select i.id, i.kod, i.nazov, i.obstaravatel_nazov, i.obstaravatel_ico, i.obstaravatel_obec,
               i.kraj, i.sektor, i.predpokladana_hodnota, i.itms_updated_at
          from public.itms_vo i
         where i.stav = 'Pripravované'
           and i.vyhlasene_zistene_at is null
           and i.itms_updated_at >= now() - interval '24 months'
           and (p_sektory is null or cardinality(p_sektory) = 0 or i.sektor = any (p_sektory))
           and (p_kraje is null or cardinality(p_kraje) = 0 or i.kraj = any (p_kraje))
    )
    select jsonb_build_object(
        'pocet',     (select count(*) from z),
        'objem',     (select sum(predpokladana_hodnota) filter (where predpokladana_hodnota > 0) from z),
        'zamknute',  not coalesce(public.ma_pro(), false),
        'polozky',   case when coalesce(public.ma_pro(), false) then coalesce((
            select jsonb_agg(to_jsonb(t) order by t.predpokladana_hodnota desc nulls last)
              from (select * from z order by predpokladana_hodnota desc nulls last limit 300) t), '[]'::jsonb)
            else '[]'::jsonb end)
    where auth.uid() is not null;
$$;

revoke all on function public.itms_pripravovane(text[], text[]) from public, anon;
grant execute on function public.itms_pripravovane(text[], text[]) to authenticated;


-- ── Upozornenie: pripravovane obstaravanie z eurofondov urad prave vyhlasil ──
-- Pre pouzivatelov s aktivnym pristupom (skuska alebo platene), ktorych vyber
-- (nastavenia_pouzivatela: sektory a kraje) obstaravanie obsahuje. Kazde
-- obstaravanie kazdemu pouzivatelovi najviac raz. Len service_role.
create table if not exists public.eurofondy_alerty_odoslane (
    user_id     uuid   not null references auth.users(id) on delete cascade,
    itms_id     bigint not null,
    odoslane_at timestamptz not null default now(),
    primary key (user_id, itms_id)
);
alter table public.eurofondy_alerty_odoslane enable row level security;
revoke all on public.eurofondy_alerty_odoslane from public, anon, authenticated;

create or replace function public.eurofondy_vyhlasene_alerty(p_dni integer default 7)
returns table (
    user_id uuid, email text, itms_id bigint, nazov text, obstaravatel_nazov text,
    sektor text, kraj text, predpokladana_hodnota numeric, vyhlasene_nazov text,
    vyhlasene_url text, vyhlasene_lehota timestamptz, itms_created_at timestamptz
)
language sql
stable
security definer
set search_path = ''
as $$
    select distinct on (u.id, i.id)
           u.id, u.email::text, i.id, i.nazov, i.obstaravatel_nazov, i.sektor, i.kraj,
           i.predpokladana_hodnota, i.vyhlasene_nazov, i.vyhlasene_url, i.vyhlasene_lehota, i.itms_created_at
      from public.itms_vo i
      join public.nastavenia_pouzivatela n
        on i.sektor = any (n.sektory)
       and (cardinality(n.kraje) = 0 or i.kraj = any (n.kraje))
      join auth.users u on u.id = n.user_id
      join public.memberships m on m.user_id = u.id
     where i.vyhlasene_zistene_at >= now() - make_interval(days => least(greatest(coalesce(p_dni, 7), 1), 30))
       and (i.vyhlasene_lehota is null or i.vyhlasene_lehota >= now() + interval '2 days')
       and u.email is not null
       and public.ma_pro_pre_org(m.org_id)
       and not exists (select 1 from public.eurofondy_alerty_odoslane a
                        where a.user_id = u.id and a.itms_id = i.id)
     order by u.id, i.id;
$$;
revoke all on function public.eurofondy_vyhlasene_alerty(integer) from public, anon, authenticated;
grant execute on function public.eurofondy_vyhlasene_alerty(integer) to service_role;

select 'Migracia 99 hotova: itms_vo.vyhlasene_*, pripravovane bez uz vyhlasenych.' as vysledok;
