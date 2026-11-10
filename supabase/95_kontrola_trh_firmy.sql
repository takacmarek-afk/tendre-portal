-- =============================================================================
--  95 - TRHOVY REPORT FIRMY NA /kontrola (10. 11. 2026)
--  Vloz do Supabase: SQL Editor -> New query -> Run. Spustit sa da opakovane.
--  Predpoklad: migracie 05, 47, 64, 69 uz bezali.
-- =============================================================================
--
--  Prieskum trhu 10. 11.: najviac predaja robi to, ze clovek UVIDI hodnotu pre
--  seba skor, nez sa registruje. /kontrola (kam vedu aj e-maily o vlastnej
--  konciacej zmluve) ukazovala len zmluvy firmy. Teraz prida aj jej trh:
--   - odbor firmy (dodavatelia.hlavny_sektor, inak najcastejsi odbor jej zmluv),
--   - kraje, kde firma pracuje (kraje uradov z jej zmluv),
--   - kolko zmluv INYCH dodavatelov v tom odbore a krajoch konci do 12 mesiacov
--     a za kolko,
--   - kolko sutazi v odbore a krajoch malo za 2 roky len 1 ponuku,
--   - kolko sutazi v odbore a krajoch je prave otvorenych.
--  Len pocty a sumy, ziadne nazvy ani dodavatelia (tie su v skuske/plane).
--
--  Technika: povodna funkcia sa premenuje na _kontrola_zmluv_ico_zaklad a nova
--  kontrola_zmluv_ico k jej vysledku prida kluc 'trh'. Telo povodnej funkcie
--  (limity, log dotazov) sa tak nemeni.
-- =============================================================================

do $$
begin
    if not exists (select 1 from pg_proc p join pg_namespace n on n.oid = p.pronamespace
                    where n.nspname = 'public' and p.proname = '_kontrola_zmluv_ico_zaklad') then
        alter function public.kontrola_zmluv_ico(text) rename to _kontrola_zmluv_ico_zaklad;
    end if;
end $$;

revoke all on function public._kontrola_zmluv_ico_zaklad(text) from public, anon, authenticated;

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
        'otvorene_sutaze',     (select count(*) from otv)
    ) end;
$$;

revoke all on function public._trh_firmy(text) from public, anon, authenticated;

create or replace function public.kontrola_zmluv_ico(p_ico text)
returns jsonb
language plpgsql
security definer
set search_path = ''
set statement_timeout = '4s'
as $$
declare
    v jsonb := public._kontrola_zmluv_ico_zaklad(p_ico);
begin
    if coalesce((v->>'ok')::boolean, false) then
        begin
            v := v || jsonb_build_object('trh', public._trh_firmy(ltrim(v->>'ico', '0')));
        exception when others then
            null;   -- trh je bonus: pri chybe sa vrati povodna odpoved
        end;
    end if;
    return v;
end;
$$;

revoke all on function public.kontrola_zmluv_ico(text) from public, anon, authenticated;
grant execute on function public.kontrola_zmluv_ico(text) to service_role;

select 'Migracia 95 hotova: kontrola_zmluv_ico vracia aj trh firmy.' as vysledok;
