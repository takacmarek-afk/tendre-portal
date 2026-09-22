-- =============================================================================
--  TRH.HTML: samoobslužná úprava kontaktných údajov (obec aj poradca)
--  Vloz do Supabase: SQL Editor -> New query -> Run. Spustit sa da opakovane.
--
--  CO TOTO RIESI
--  trh.html (16. vlna, 64ab0f1) doteraz po registrácii nemal žiadnu úpravu
--  profilu — jediná cesta bola napísať na info@predtendrom.sk. Marek chcel
--  samoobslužnú úpravu, ale len kontaktných údajov (e-mail, telefón, popis,
--  kraje pôsobenia u poradcu) — NIE identifikačných polí (kraj obce, IČO),
--  ktoré určujú matching/filtrovanie a nemajú sa meniť ľahkovážne.
--
--  PRECO RPC, NIE PRIAMY UPDATE Z KLIENTA
--  34_obce_marketplace.sql mal pripravené obce_ucty_update/poradcovia_update
--  RLS politiky pre "for update ... using (owner = auth.uid())" — teda BEZ
--  obmedzenia na stĺpce, čo by dovolilo klientovi cez priamy PostgREST
--  PATCH zmeniť aj kraj/ico. Nič v appke doteraz priamy update nepoužívalo
--  (overené: trh.html robí len .select(), zápisy vždy cez RPC — rovnaký
--  vzor ako zaloz_obec_ucet/zaloz_poradcu_profil/vytvor_dopyt). Preto tieto
--  dve nepoužívané, príliš voľné politiky rušíme a nahrádzame RPC funkciami,
--  ktoré fyzicky neprijímajú kraj/ico ako parameter — nedá sa to obísť ani
--  priamym volaním REST API.
-- =============================================================================

drop policy if exists obce_ucty_update on public.obce_ucty;
drop policy if exists poradcovia_update on public.poradcovia_profily;

create or replace function public.uprav_kontakt_obce(
    p_kontakt_email text
)
returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
    if auth.uid() is null then
        raise exception 'Nie si prihlaseny.';
    end if;

    update public.obce_ucty
       set kontakt_email = nullif(trim(coalesce(p_kontakt_email, '')), '')
     where owner = auth.uid();

    if not found then
        raise exception 'Nemas obecny ucet.';
    end if;
end;
$$;

grant execute on function public.uprav_kontakt_obce(text) to authenticated;

create or replace function public.uprav_kontakt_poradcu(
    p_kontakt_email   text,
    p_kontakt_telefon text default null,
    p_popis           text default null,
    p_kraje           text[] default '{}'
)
returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
    if auth.uid() is null then
        raise exception 'Nie si prihlaseny.';
    end if;
    if trim(coalesce(p_kontakt_email, '')) = '' then
        raise exception 'Zadaj kontaktny e-mail.';
    end if;

    update public.poradcovia_profily
       set kontakt_email   = trim(p_kontakt_email),
           kontakt_telefon = nullif(trim(coalesce(p_kontakt_telefon, '')), ''),
           popis            = nullif(trim(coalesce(p_popis, '')), ''),
           kraje_posobenia  = coalesce(p_kraje, '{}')
     where owner = auth.uid();

    if not found then
        raise exception 'Nemas profil poradcu.';
    end if;
end;
$$;

grant execute on function public.uprav_kontakt_poradcu(text, text, text, text[]) to authenticated;

select 'Samoobsluzna uprava kontaktu pripravena: uprav_kontakt_obce, uprav_kontakt_poradcu.' as vysledok;
