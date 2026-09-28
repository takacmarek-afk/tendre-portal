-- =============================================================================
--  50 — SKÚŠOBNÁ DOBA 14 DNÍ, PLÁNY TEAM A PORADCA V cenove_plany
--  Rozhodnutie zakladateľa 28. 9. 2026 (audit 27. 9., P1.1 a P2.2).
--  Zdroj pravdy pre stránky: public/plany.js; test: pipeline/test_plany.py.
--  Spustiť sa dá opakovane.
--
--  ČO SA NEMENÍ: je_zadarmo() ostáva true (testovacia prevádzka, kým Marek
--  nespustí ostré platby). Dovtedy má každý prihlásený plný prístup a
--  skúšobná doba sa len eviduje. Po prepnutí je_zadarmo() na false začne
--  nový účet so 14 dňami skúšky.
-- =============================================================================

-- 1. Predvolený koniec skúšky pre nové predplatné
alter table public.subscriptions
    alter column trial_konci set default (now() + interval '14 days');

-- 2. zaloz_organizaciu() zapisuje koniec skúšky explicitne (42_trial_plan_
--    default.sql, "3 days" na dvoch miestach). Prepíšeme len interval —
--    zvyšok funkcie ostáva presne taký, aký je v databáze.
do $$
declare
    f record;
    def text;
begin
    for f in
        select p.oid from pg_proc p join pg_namespace n on n.oid = p.pronamespace
         where n.nspname = 'public' and p.proname = 'zaloz_organizaciu'
    loop
        def := pg_get_functiondef(f.oid);
        if position('interval ''3 days''' in def) > 0 then
            execute replace(def, 'interval ''3 days''', 'interval ''14 days''');
        end if;
    end loop;
end;
$$;

-- 3. Plán Poradca smie byť v subscriptions (zatiaľ ho nikto nemá)
alter table public.subscriptions drop constraint if exists subscriptions_plan_check;
alter table public.subscriptions add constraint subscriptions_plan_check
    check (plan in ('trial', 'start', 'growth', 'team', 'poradca', 'pro', 'admin'));

-- 4. Ceny (rovnaké čísla ako public/plany.js)
insert into public.cenove_plany (plan, obdobie, suma) values
    ('start',   'mesiac',   34.00), ('start',   'rok',  340.00),
    ('growth',  'mesiac',   89.00), ('growth',  'rok',  890.00),
    ('team',    'mesiac',  249.00), ('team',    'rok', 2490.00),
    ('poradca', 'mesiac',   59.00), ('poradca', 'rok',  590.00)
on conflict (plan, obdobie) do update set suma = excluded.suma;

select 'trial_default=' || (select column_default from information_schema.columns
                             where table_schema = 'public' and table_name = 'subscriptions'
                               and column_name = 'trial_konci')
    || ' | zaloz_14=' || (select bool_and(position('interval ''14 days''' in pg_get_functiondef(p.oid)) > 0)::text
                            from pg_proc p join pg_namespace n on n.oid = p.pronamespace
                           where n.nspname = 'public' and p.proname = 'zaloz_organizaciu')
    || ' | plany=' || (select string_agg(plan || ':' || obdobie || '=' || suma, ', ' order by plan, obdobie)
                         from public.cenove_plany) as vysledok;
