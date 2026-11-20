-- =============================================================================
--  106 - ZHODA SO ZDOVODNENIM (oba portaly; ceska obdoba je hledam-zakazky 014)
--  Profil vlastnej firmy z jej zmluv v CRZ za 5 rokov: pocet zmluv podla
--  odboru a podla uradu. Aplikacia z neho pri kazdej konciacej zmluve napise
--  "Sedí vám: 4 vaše zmluvy v odbore upratovanie · 2 zmluvy s týmto úradom".
--  Bez percent (rovnaky princip ako "sanca na vyhru"). Len Growth a vyssie
--  (ma_pro), rovnako ako ostatne funkcie z vlastneho ICO.
--  Bezpecne spustit opakovane.
-- =============================================================================

create or replace function public.moj_profil_zhody(p_ico text)
returns jsonb
language plpgsql stable security definer
set search_path = public
set statement_timeout = '8s'
as $$
declare
    v_cin text := ltrim(regexp_replace(upper(coalesce(p_ico, '')), '^SK|\s|\D', '', 'g'), '0');
begin
    if auth.uid() is null or not public.ma_pro() then
        return jsonb_build_object('ok', false);
    end if;
    if v_cin = '' or length(v_cin) > 8 then
        return jsonb_build_object('ok', false, 'kod', 'NEPLATNE_ICO');
    end if;
    return (
        with s as (
            select c.sector, ltrim(c.authority_cin, '0') as urad
              from public.contracts c
             where c.supplier_cin = v_cin
               and coalesce(c.signed_on, c.effective_from, current_date) >= current_date - 1826
        )
        select jsonb_build_object(
            'ok', true,
            'spolu', (select count(*) from s),
            'sektory', coalesce((select jsonb_object_agg(sector, n) from
                          (select sector, count(*) n from s where sector is not null group by sector) t), '{}'::jsonb),
            'urady', coalesce((select jsonb_object_agg(urad, n) from
                          (select urad, count(*) n from s where coalesce(urad, '') <> '' group by urad) t), '{}'::jsonb)
        )
    );
end;
$$;
revoke all on function public.moj_profil_zhody(text) from public, anon;
grant execute on function public.moj_profil_zhody(text) to authenticated, service_role;

select 'Migracia 106 hotova: moj_profil_zhody(ico).' as vysledok;
