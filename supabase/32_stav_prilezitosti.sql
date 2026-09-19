-- =============================================================================
--  PIPELINE/CRM STAV PRI PRILEZITOSTIACH (audit 18.9., stredna polozka)
--  Vloz do Supabase: SQL Editor -> New query -> Run. Spustit sa da opakovane.
-- =============================================================================
--
--  CO TO RIESI
--  Audit: "appka neponuka spôsob, ako označiť príležitosť ako 'sledujeme',
--  'pripravujeme ponuku', 'nezaujíma nás' — iba globálne 'sledovať' pri
--  celých firmách, nie pri jednotlivých zmluvách/dotáciách. Bez toho si
--  obchodný tím skoro isto povedie svoj vlastný excel vedľa appky."
--
--  Toto je per-organizacia, per-prilezitost stav — nie globalny udaj ako
--  `skore`/`riziko` v opportunities, preto vlastna tabulka s RLS na
--  vlastnu organizaciu (rovnaky vzor ako `watchlists`/`sledovane_ico`).
--
--  GATOVANIE: rovnaky vzor ako denny digest/webhook (25_odber_pro_gating.sql)
--  — v tomto projekte "Pro" gate = akakolvek platena uroven (Growth/Team),
--  vid 31_oprava_ma_pro_planov.sql. Dormant, kym je_zadarmo() vracia true.
-- =============================================================================

create table if not exists public.moj_stav_prilezitosti (
    org_id      uuid not null references public.organizations(id) on delete cascade,
    typ         text not null check (typ in ('zmluva', 'dotacia')),
    contract_id bigint not null,
    stav        text not null default 'sledujeme'
                  check (stav in ('sledujeme', 'ponuka', 'nezaujima')),
    poznamka    text,
    updated_by  uuid references auth.users(id) on delete set null,
    updated_at  timestamptz not null default now(),
    primary key (org_id, typ, contract_id)
);

create index if not exists ix_stav_pril_org on public.moj_stav_prilezitosti(org_id);

alter table public.moj_stav_prilezitosti enable row level security;

drop policy if exists stav_pril_all on public.moj_stav_prilezitosti;
create policy stav_pril_all on public.moj_stav_prilezitosti
    for all to authenticated
    using (org_id in (select public.moje_org_ids()) and public.ma_pro())
    with check (org_id in (select public.moje_org_ids()) and public.ma_pro());

-- Upsert cez RPC, nie priamy insert z klienta — jedno miesto, kde sa
-- doplni org_id (klient ho nema poznat naspamat) a updated_by/updated_at
-- sa vzdy nastavia servrom, nie tym, co posle prehliadac.
create or replace function public.nastav_stav_prilezitosti(
    p_typ         text,
    p_contract_id bigint,
    p_stav        text,
    p_poznamka    text default null
)
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_org_id uuid;
begin
    if auth.uid() is null then
        raise exception 'Nie si prihlaseny.';
    end if;
    if not public.ma_pro() then
        raise exception 'Toto je funkcia platenej urovne.';
    end if;
    if p_typ not in ('zmluva', 'dotacia') then
        raise exception 'Neznamy typ.';
    end if;
    if p_stav not in ('sledujeme', 'ponuka', 'nezaujima') then
        raise exception 'Neznamy stav.';
    end if;

    select org_id into v_org_id
      from public.memberships
     where user_id = auth.uid()
     limit 1;

    if v_org_id is null then
        raise exception 'Nemas priradenu organizaciu.';
    end if;

    insert into public.moj_stav_prilezitosti
        (org_id, typ, contract_id, stav, poznamka, updated_by, updated_at)
    values
        (v_org_id, p_typ, p_contract_id, p_stav, nullif(trim(p_poznamka), ''), auth.uid(), now())
    on conflict (org_id, typ, contract_id) do update
        set stav       = excluded.stav,
            poznamka   = excluded.poznamka,
            updated_by = excluded.updated_by,
            updated_at = now();
end;
$$;

grant execute on function public.nastav_stav_prilezitosti(text, bigint, text, text) to authenticated;

-- Zmazanie stavu (naspat na "bez stavu") — samostatna funkcia, aby RLS
-- politika na "all" vyssie stacila aj bez dalsieho odhalovania org_id.
create or replace function public.zmaz_stav_prilezitosti(p_typ text, p_contract_id bigint)
returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
    delete from public.moj_stav_prilezitosti
     where org_id in (select public.moje_org_ids())
       and typ = p_typ
       and contract_id = p_contract_id;
end;
$$;

grant execute on function public.zmaz_stav_prilezitosti(text, bigint) to authenticated;

select 'moj_stav_prilezitosti pripravena: RLS + nastav_stav_prilezitosti()/zmaz_stav_prilezitosti() RPC.' as vysledok;
