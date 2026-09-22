-- =============================================================================
--  "SUSED UZ STAVIA": deduplikacna tabulka pre mesacny FOMO alert
--  Vloz do Supabase: SQL Editor -> New query -> Run. Spustit sa da opakovane.
--
--  CO TOTO RIESI
--  pipeline/alerty.py posiela obciam z odber_obce (uz existujuci, GDPR-cisty
--  opt-in zoznam) mesacny alert, ked v ich okrese ina obec nedavno podpisala
--  dotacnu zmluvu (zdroj: subsidies, rovnake udaje ako obce.aktivne_programy).
--  Bez deduplikacie by rovnaka udalost mohla prist rovnakemu prijemcovi
--  viackrat (napr. pri opakovanom behu alebo pri posune casoveho okna).
-- =============================================================================

create table if not exists public.sused_alerty_odoslane (
    email       text not null,
    contract_id bigint not null references public.contracts(id) on delete cascade,
    odoslane_at timestamptz not null default now(),
    primary key (email, contract_id)
);

alter table public.sused_alerty_odoslane enable row level security;
-- Ziadna politika = nikto okrem service_role sa tam nedostane (rovnaky
-- vzor ako pipeline_meta v schema.sql) — cisto interna kniha pipeline.

comment on table public.sused_alerty_odoslane is
    'Deduplikacia FOMO alertov (pipeline/alerty.py). Ziadna RLS politika = '
    'pristup len cez service_role.';

select 'Sused-alerty pripravene: sused_alerty_odoslane.' as vysledok;
