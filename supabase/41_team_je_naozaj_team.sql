-- =============================================================================
--  OPRAVA: pozvanie kolegov gatovalo na ma_pro() (Growth+), hoci cennik.html
--  "Viacero používateľov v jednej organizácii" / "Pozvánka kolegov e-mailom" /
--  "Zdieľaný zoznam sledovaných firiem naprieč tímom" sľubuje vyslovne len
--  na úrovni Team (249 €), nie Growth (89 €).
--  Vloz do Supabase: SQL Editor -> New query -> Run. Spustit sa da opakovane.
-- =============================================================================
--
--  NALEZ (zivy audit 22.9.2026, pokracovanie po oprave Start/benchmarku)
--  pozvi_clena() (26_team_pozvanky.sql) bola napisana v case, ked "Pro"
--  bola najvyssia platena uroven ("Pozvanky su Pro funkcia, rovnake
--  gatovanie ako sledovane_ico/dodavatelia/ceny_sektor" - vid povodny
--  komentar). Po rozdeleni na Start/Growth/Team (06_plany.sql, 29_platby.sql)
--  zostala pozvi_clena() nezmenena - kontroluje ma_pro(), ktora zahrna aj
--  'growth'. cennik.html pritom viacpouzivatelsky pristup vyslovne pocita
--  len do stlpca Team. Kym je_zadarmo() vracia true, chyba je mrtva; v
--  momente prepnutia by kazdy platiaci Growth zakaznik (89 €) mohol
--  pozyvat neobmedzene kolegov zadarmo - presne tu funkciu, za ktoru Team
--  zakaznik plati o 160 € mesacne viac.
--
--  OPRAVA: pozvi_clena() prechadza z ma_pro() na ma_team(). Kod chyby
--  premenovany z VYZADUJE_PRO na VYZADUJE_TEAM (presnejsie pomenovanie,
--  frontend upraveny sucasne v tej istej vlne). Citanie zoznamu clenov
--  (moji_kolegovia) a vlastnych pozvanok (moje_pozvanky) NIE JE menene -
--  clen uz prijatej pozvanky ma clenstvo nezavisle od aktualneho stavu
--  predplatneho (rovnaky princip ako existujuce sledovane_ico: citanie
--  vlastnych dat nie je viazane na ma_pro()/ma_team()).
-- =============================================================================

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

    -- OPRAVA 22.9.2026: pozvanky su Team funkcia (cennik.html), nie Growth/
    -- Pro. Povodne tu bolo ma_pro() - vid komentar vyssie.
    if not public.ma_team() then
        return jsonb_build_object('ok', false, 'kod', 'VYZADUJE_TEAM');
    end if;

    if exists (
        select 1
          from public.memberships mm
          join auth.users u on u.id = mm.user_id
         where mm.org_id = v_org_id and lower(u.email) = v_email
    ) then
        return jsonb_build_object('ok', false, 'kod', 'UZ_CLEN');
    end if;

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

select prosrc from pg_proc where proname = 'pozvi_clena' and pronamespace = 'public'::regnamespace;

select 'pozvi_clena() opravena: pozyvanie kolegov je odteraz Team+ (ma_team()), '
       'presne ako cennik.html sluby. Citanie clenov/pozvanok nezmenene.' as vysledok;
