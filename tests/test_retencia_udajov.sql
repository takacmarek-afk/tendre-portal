-- Test migracie 71 (retencia_udajov). Spustenie na lokalnej DB postavenej do 71:
--   su postgres -c "psql -q -d t71 -f /tmp/test_retencia_udajov.sql"
\set ON_ERROR_STOP off
\pset format unaligned
\pset fieldsep ' | '

-- staré aj čerstvé riadky
insert into public.odber_obce(email, obec, potvrdeny, created_at) values
  ('stary-nepotvrdeny@t.sk','A', false, now() - interval '40 days'),
  ('cerstvy-nepotvrdeny@t.sk','B', false, now() - interval '5 days'),
  ('stary-potvrdeny@t.sk','C', true,  now() - interval '400 days');
insert into public.spatne_volania(meno, obec, telefon, created_at) values
  ('Stary','A','0900111222', now() - interval '13 months'),
  ('Cerstvy','B','0900333444', now() - interval '2 months');
insert into public.servisne_dopyty(obec, popis, kontakt_email, created_at) values
  ('A','x','a@t.sk', now() - interval '25 months'),
  ('B','y','b@t.sk', now() - interval '3 months');
insert into public.navstevy(cesta, created_at) values
  ('/', now() - interval '27 months'), ('/', now() - interval '1 month');
insert into public.udalosti(nazov, cesta, created_at) values
  ('suhlas_prijaty','/', now() - interval '27 months'), ('suhlas_prijaty','/', now() - interval '1 month');

select 'T1 anon nemoze volat' as t,
       has_function_privilege('anon','public.retencia_udajov()','execute')::text as v;
select 'T2 authenticated nemoze volat' as t,
       has_function_privilege('authenticated','public.retencia_udajov()','execute')::text as v;
select 'T3 service_role moze volat' as t,
       has_function_privilege('service_role','public.retencia_udajov()','execute')::text as v;

select 'T4 vysledok' as t, public.retencia_udajov()::text as v;

select 'T5 odber_obce zostali (cerstvy nepotvrdeny + potvrdeny)' as t,
       string_agg(email, ',' order by email) as v from public.odber_obce;
select 'T6 spatne_volania zostal' as t, string_agg(meno, ',') as v from public.spatne_volania;
select 'T7 servisne_dopyty zostal' as t, string_agg(obec, ',') as v from public.servisne_dopyty;
select 'T8 navstevy zostala 1' as t, count(*)::text as v from public.navstevy;
select 'T9 udalosti zostala 1' as t, count(*)::text as v from public.udalosti;
select 'T10 druhy beh nic nezmaze' as t, public.retencia_udajov()::text as v;
