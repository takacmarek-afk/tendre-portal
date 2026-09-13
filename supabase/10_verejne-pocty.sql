-- ════════════════════════════════════════════════════════════════════════
-- VEREJNE POCTY PRE UVODNU STRANKU
--
-- Preco to vobec je: na index.html boli dve cisla napisane natvrdo v HTML,
-- "227 731 zmluv" a "4 200 sledovanych prilezitosti". Prve bolo zastarane
-- (databaza mala 228 331), druhe nezodpovedalo nicomu — prilezitosti je
-- 1 159 a dotacii 3 319. Na portali, ktoreho cela pozicia stoji na tom,
-- ze nic neprikraslujeme, je vymyslene cislo na prvej obrazovke ta
-- najlacnejsia cesta, ako tu poziciu stratit.
--
-- Tabulky opportunities a subsidies su pod RLS pre prihlasenych, takze
-- neprihlaseny navstevnik si ich spocitat nemoze — dostal by nulu, nie
-- chybu. Preto jedna maly verejna tabulka, do ktorej pipeline po kazdom
-- behu zapise hotove cisla.
--
-- Spustaj v SQL editore Supabase ako jeden celok.
-- ════════════════════════════════════════════════════════════════════════

create table if not exists public.verejne_pocty (
    kluc       text primary key,
    hodnota    bigint not null,
    updated_at timestamptz not null default now()
);

alter table public.verejne_pocty enable row level security;

-- Jedina tabulka v projekte, ktoru smie citat aj neprihlaseny. Su to
-- agregaty, ziadne riadky zmluv — nic, co by sa dalo zneuzit.
drop policy if exists verejne_pocty_select on public.verejne_pocty;
create policy verejne_pocty_select on public.verejne_pocty
    for select to anon, authenticated
    using (true);

-- Zapisuje vylucne pipeline cez service_role, ktory RLS obchadza.
-- Ziadna insert/update/delete politika tu preto zamerne NIE JE:
-- bez politiky je zapis pre anon aj authenticated zakazany.

comment on table public.verejne_pocty is
    'Agregaty pre uvodnu stranku. Zapisuje pipeline, cita ktokolvek.';

-- Prvotne naplnenie, aby stranka nebola prazdna este pred prvym behom.
insert into public.verejne_pocty (kluc, hodnota)
select 'zmluv', count(*) from public.contracts
on conflict (kluc) do update set hodnota = excluded.hodnota, updated_at = now();

insert into public.verejne_pocty (kluc, hodnota)
select 'prilezitosti', count(*) from public.opportunities
on conflict (kluc) do update set hodnota = excluded.hodnota, updated_at = now();

insert into public.verejne_pocty (kluc, hodnota)
select 'dotacie', count(*) from public.subsidies
on conflict (kluc) do update set hodnota = excluded.hodnota, updated_at = now();

insert into public.verejne_pocty (kluc, hodnota)
select 'dodavatelia', count(*) from public.dodavatelia
on conflict (kluc) do update set hodnota = excluded.hodnota, updated_at = now();

select kluc, hodnota, updated_at from public.verejne_pocty order by kluc;
