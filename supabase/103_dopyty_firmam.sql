-- 103: Dopyt obce -> e-mail firmam (11. 11. 2026).
-- Kampan pre obce ponuka obciam zverejnit pripravovane obstaravanie na Trhu
-- dopytov "a ozvu sa firmy z regionu". Doteraz o novom dopyte dostali e-mail
-- len poradcovia. Teraz aj firmy so skuskou alebo platenym planom (Growth,
-- Team), ktorym dopyt sedi krajom a odborom. Odpovedaju cez Trh dopytov.

alter table public.dopyty
    add column if not exists firmy_notifikovane boolean not null default false;

-- Doterajsie dopyty firmam neposielame spatne.
update public.dopyty set firmy_notifikovane = true where firmy_notifikovane = false;

create index if not exists ix_dopyty_firmy_nenotifikovane
    on public.dopyty(firmy_notifikovane) where firmy_notifikovane = false;

-- Adresati: pouzivatelia s pristupom k dopytom (ma_pro_pre_org: skuska, Growth,
-- Team), kraj v ich vybere (prazdny vyber = cele Slovensko) a odbor, ak ho
-- vieme z textu dopytu urcit (p_sektor null = vsetci v kraji).
create or replace function public.dopyt_firmy_adresati(p_kraj text, p_sektor text)
returns table (user_id uuid, email text)
language sql
stable
security definer
set search_path = ''
as $$
    select distinct u.id, u.email::text
      from public.nastavenia_pouzivatela n
      join auth.users u on u.id = n.user_id
      join public.memberships m on m.user_id = u.id
     where u.email is not null
       and public.ma_pro_pre_org(m.org_id)
       and (p_kraj is null or cardinality(n.kraje) = 0 or p_kraj = any (n.kraje))
       and (p_sektor is null or p_sektor = any (n.sektory))
       and not exists (select 1 from public.poradcovia_profily p
                        where p.owner = u.id and p.aktivny);   -- poradcovia ho uz dostali
$$;
revoke all on function public.dopyt_firmy_adresati(text, text) from public, anon, authenticated;
grant execute on function public.dopyt_firmy_adresati(text, text) to service_role;

select 'Migracia 103 hotova: dopyty.firmy_notifikovane, dopyt_firmy_adresati().' as vysledok;
