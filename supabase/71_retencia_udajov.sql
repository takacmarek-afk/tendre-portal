-- =============================================================================
--  71 — RETENCIA ÚDAJOV (vlna 85, 7. 10. 2026; príprava na ostré spustenie)
--  Vlož do Supabase: SQL Editor -> New query -> Run. Spustiť sa dá opakovane.
-- =============================================================================
--
--  Zásady ochrany osobných údajov (public/ochrana-osobnych-udajov.html) hovoria,
--  ako dlho ktoré údaje uchovávame. Táto funkcia tie lehoty vynucuje, aby text
--  nebol len sľub:
--
--    nepotvrdený odber prehľadov pre obce ....... 30 dní
--    „Zavolajte mi“ (spatne_volania) ............ 12 mesiacov
--    servisné dopyty obcí ....................... 24 mesiacov
--    návštevy a udalosti (bez identifikácie) .... 26 mesiacov
--    záznamy kontroly IČO a limitov formulárov .. 7 dní / 2 dni (už mažú vlastné funkcie,
--                                                  tu len poistka)
--
--  Účty, platby a členstvá sa tu NEmažú: účty sa rušia na požiadanie a platobné
--  záznamy sa uchovávajú kvôli účtovníctvu (10 rokov).
--
--  Volá ju týždenne GitHub Action `retencia.yml` (pipeline/retencia_udajov.py)
--  cez service_role. Anon ani authenticated ju volať nemôžu.
-- =============================================================================

create or replace function public.retencia_udajov()
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_odber   int;
    v_volania int;
    v_servis  int;
    v_nav     int;
    v_udal    int;
    v_kontr   int;
    v_pokusy  int;
begin
    delete from public.odber_obce
     where potvrdeny = false and created_at < now() - interval '30 days';
    get diagnostics v_odber = row_count;

    delete from public.spatne_volania
     where created_at < now() - interval '12 months';
    get diagnostics v_volania = row_count;

    delete from public.servisne_dopyty
     where created_at < now() - interval '24 months';
    get diagnostics v_servis = row_count;

    delete from public.navstevy
     where created_at < now() - interval '26 months';
    get diagnostics v_nav = row_count;

    delete from public.udalosti
     where created_at < now() - interval '26 months';
    get diagnostics v_udal = row_count;

    delete from public.kontrola_ico_dotazy
     where created_at < now() - interval '7 days';
    get diagnostics v_kontr = row_count;

    delete from public.verejny_formular_pokusy
     where created_at < now() - interval '2 days';
    get diagnostics v_pokusy = row_count;

    return jsonb_build_object(
        'odber_obce_nepotvrdeny', v_odber,
        'spatne_volania',         v_volania,
        'servisne_dopyty',        v_servis,
        'navstevy',               v_nav,
        'udalosti',               v_udal,
        'kontrola_ico_dotazy',    v_kontr,
        'verejny_formular_pokusy', v_pokusy
    );
end;
$$;

revoke all on function public.retencia_udajov() from public, anon, authenticated;
grant execute on function public.retencia_udajov() to service_role;

select 'Migracia 71 hotova: retencia_udajov() len pre service_role.' as vysledok;
