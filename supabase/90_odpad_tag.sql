-- =============================================================================
--  Migracia 90: tag "odpad" pre koniace zmluvy (rozhodnutie 2. 11. 2026)
--  Odpad nie je nas sektor. Ak predmet koniacej zmluvy obsahuje odpad, vyvoz,
--  kuka, smeti alebo zber, vyzvy_signaly_obci() prida do "konciace" aj zaznam
--  so sektorom 'odpad'. Vyzva s signal_sektory = {odpad} potom dostane +3.
--  POZOR: opportunities obsahuje len zmluvy z nasich sektorov, takze zmluvy
--  ciste na vyvoz odpadu tu zatial vacsinou nie su (pozri poznamku v projekte).
-- =============================================================================

create or replace function public.vyzvy_signaly_obci()
returns table (
    kod text, ico text, nazov text, typ text, kraj text, okres text,
    pocet_obyvatelov integer, nro boolean, mrk boolean,
    konciace jsonb, dotacie_3r jsonb, dotiahnute boolean)
language sql stable security definer set search_path = public as $$
    select r.kod, r.ico, r.nazov, r.typ, r.kraj, r.okres,
           r.pocet_obyvatelov, r.nro, r.mrk,
           coalesce((select jsonb_agg(x.z order by x.koniec)
                     from (
                        select jsonb_build_object('sektor', o.sector, 'koniec', o.effective_to) z, o.effective_to koniec
                          from opportunities o
                         where o.authority_cin = r.ico
                           and o.effective_to between current_date and current_date + interval '24 months'
                        union all
                        select jsonb_build_object('sektor', 'odpad', 'koniec', o.effective_to), o.effective_to
                          from opportunities o
                         where o.authority_cin = r.ico
                           and o.effective_to between current_date and current_date + interval '24 months'
                           and coalesce(o.subject, '') ~* '(odpad|v[ýy]voz|kuka|smet|zber)'
                     ) x), '[]'),
           coalesce((select jsonb_agg(jsonb_build_object('ucel', s.ucel, 'sektor', s.sektor_odhad, 'podpisane', s.podpisane))
                     from subsidies s
                     where s.prijimatel_ico = r.ico
                       and s.podpisane >= current_date - interval '3 years'), '[]'),
           exists (select 1 from subsidies s
                   where s.prijimatel_ico = r.ico
                     and (s.vyplatene or s.podpisane < current_date - interval '2 years'))
    from obce_register r
    where r.ico is not null;
$$;

revoke all on function public.vyzvy_signaly_obci() from public;
grant execute on function public.vyzvy_signaly_obci() to service_role;

select 'Migracia 90 hotova: tag odpad v signaloch obci.' as vysledok;
