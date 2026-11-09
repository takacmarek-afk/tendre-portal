-- =============================================================================
--  94 - KOLEGA SA PRIPOJI SAM PODLA FIREMNEJ DOMENY (9. 11. 2026)
--  Vloz do Supabase: SQL Editor -> New query -> Run. Spustit sa da opakovane.
--  Predpoklad: migracia 63 (zaloz_organizaciu vracia FIRMA_UZ_EXISTUJE).
-- =============================================================================
--
--  Problem (naživo 9. 11.): kolega z firmy, ktora uz ucet ma, sa zaregistroval,
--  zadal IČO a dostal "Táto firma už prístup má" — dnu sa dostane len
--  pozvankou, a tie su v plane Team. Pre malu firmu to znamena, ze druhy
--  clovek odpadne.
--
--  pripoj_sa_k_firme(p_ico): pripoji prihlaseneho ako 'member', ak
--   - este nie je v ziadnej firme,
--   - jeho prihlasovaci e-mail je overeny (prihlasenie kodom) a je na FIREMNEJ
--     domene (nie gmail.com, azet.sk ...),
--   - firma s tym IČO ma clena s e-mailom na TEJ ISTEJ domene,
--   - firma ma zatial len 1 clena (1 kolega navyse k Start/Growth/skuske;
--     dalsi su pozvankou v Team — cennik sa nemeni).
--  IČO samo o sebe stale NEPRIPAJA nikoho (K1 z migracie 63 plati): rozhoduje
--  overena firemna domena, ktoru cudzi clovek nema.
-- =============================================================================

create or replace function public._verejna_domena(p_domena text)
returns boolean
language sql
immutable
set search_path = ''
as $$
    select lower(coalesce(p_domena, '')) = any (array[
        'gmail.com', 'googlemail.com', 'azet.sk', 'zoznam.sk', 'centrum.sk', 'post.sk',
        'pobox.sk', 'atlas.sk', 'orangemail.sk', 'stonline.sk', 'szm.sk', 'seznam.cz',
        'email.cz', 'centrum.cz', 'post.cz', 'yahoo.com', 'hotmail.com', 'outlook.com',
        'outlook.sk', 'live.com', 'icloud.com', 'me.com', 'gmx.com', 'gmx.net', 'gmx.de',
        'proton.me', 'protonmail.com', 'aol.com', ''])
$$;

create or replace function public.pripoj_sa_k_firme(p_ico text)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_ico    text := regexp_replace(coalesce(p_ico, ''), '\D', '', 'g');
    v_email  text;
    v_dom    text;
    v_org_id uuid;
    v_clenov int;
begin
    if auth.uid() is null then
        return jsonb_build_object('ok', false, 'kod', 'NEPRIHLASENY');
    end if;
    if exists (select 1 from public.memberships where user_id = auth.uid()) then
        return jsonb_build_object('ok', false, 'kod', 'UZ_V_FIRME');
    end if;

    select lower(u.email) into v_email
      from auth.users u
     where u.id = auth.uid() and u.email_confirmed_at is not null;
    v_dom := split_part(coalesce(v_email, ''), '@', 2);
    if v_email is null or public._verejna_domena(v_dom) then
        return jsonb_build_object('ok', false, 'kod', 'INA_DOMENA');
    end if;

    select o.id into v_org_id
      from public.organizations o
     where o.ico = v_ico
       and exists (select 1
                     from public.memberships m
                     join auth.users u on u.id = m.user_id
                    where m.org_id = o.id
                      and lower(split_part(u.email, '@', 2)) = v_dom)
     limit 1;
    if v_org_id is null then
        return jsonb_build_object('ok', false, 'kod', 'INA_DOMENA');
    end if;

    -- zamok na firmu, aby dvaja kolegovia naraz neobsadili jedno miesto dvakrat
    perform 1 from public.organizations where id = v_org_id for update;
    select count(*) into v_clenov from public.memberships where org_id = v_org_id;
    if v_clenov >= 2 then
        return jsonb_build_object('ok', false, 'kod', 'MIESTA_PLNE');
    end if;

    insert into public.memberships (user_id, org_id, rola)
    values (auth.uid(), v_org_id, 'member');

    insert into public.events (org_id, user_id, typ, detail)
    values (v_org_id, auth.uid(), 'kolega_pripojeny_domenou', jsonb_build_object('domena', v_dom));

    return jsonb_build_object('ok', true, 'kod', 'PRIPOJENY');
end;
$$;

revoke all on function public.pripoj_sa_k_firme(text) from public, anon;
grant execute on function public.pripoj_sa_k_firme(text) to authenticated;
revoke all on function public._verejna_domena(text) from public, anon, authenticated;
