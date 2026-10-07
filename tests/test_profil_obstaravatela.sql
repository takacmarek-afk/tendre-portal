-- Test migracie 70 (profil_obstaravatela). Spustenie na lokalnej DB po migraciach 1-70:
--   psql -d <db> -v ON_ERROR_STOP=1 -f tests/test_profil_obstaravatela.sql
-- IČO 00151742 je platné (kontrolná číslica); v contracts.authority_cin je bez núl: 151742.
\set ON_ERROR_STOP on
begin;

create temp table _t(ok boolean, popis text);
create function pg_temp.over(p_podmienka boolean, p_popis text) returns void language plpgsql as $$
begin
    insert into _t values (coalesce(p_podmienka, false), p_popis);
end $$;

insert into public.contracts (id, authority_name, authority_cin, supplier_name, supplier_cin, subject, signed_on, effective_from, effective_to, price_total, sector) values
 (9001, 'Mesto Test', '151742', 'Upratovanie Test s.r.o.', '11111111', 'Upratovanie 2024', current_date - 400, current_date - 400, current_date + 100, 100000, 'UPRATOVANIE'),
 (9002, 'Mesto Test', '151742', 'Upratovanie Test s.r.o.', '11111111', 'Upratovanie dodatok', current_date - 300, current_date - 300, current_date + 200, 50000, 'UPRATOVANIE'),
 (9003, 'Mesto Test', '151742', 'Ján Novák', '22222222', 'Oprava', current_date - 200, current_date - 200, current_date + 700, 20000, 'STAVEBNE_PRACE'),
 (9004, 'Mesto Test', '151742', 'Stara s.r.o.', '33333333', 'Stara zmluva', current_date - 2000, current_date - 2000, current_date - 1000, 999999, 'UPRATOVANIE'),
 (9005, 'Mesto Test', '151742', 'Bez ceny a.s.', '44444444', 'Bez ceny', current_date - 100, current_date - 100, current_date + 50, null, null);
insert into public.subsidies (contract_id, prijimatel, prijimatel_ico, poskytovatel, suma, podpisane, okno_od)
values (9003, 'Mesto Test', '151742', 'MF SR', 70000, current_date - 50, current_date + 30);
insert into public.uvo_vysledky (oznamenie_id, vestnik, obstaravatel_ico, vitaz_ico, vitaz_nazov, pocet_ponuk, publikovane, cast_id)
values (1, '1/2026', '00151742', 'x', 'X', 1, current_date - 30, ''),
       (2, '2/2026', '151742', 'y', 'Y', 5, current_date - 20, ''),
       (3, '3/2020', '151742', 'z', 'Z', 1, current_date - 2000, '');

create temp table r as select public.profil_obstaravatela('  SK 00151742 ') as j;

select pg_temp.over((j->>'ok')::boolean, 'ok pri platnom IČO s medzerami a predponou SK') from r;
select pg_temp.over(j->>'nazov' = 'Mesto Test', 'nazov') from r;
select pg_temp.over((j->>'zmluvy_36m')::int = 4, 'zmluvy za 36 mesiacov = 4 (stará z pred 2000 dní sa nepočíta)') from r;
select pg_temp.over((j->>'objem_36m')::numeric = 170000, 'objem len zmluvy s cenou: 100000+50000+20000') from r;
select pg_temp.over(j->'sektory'->0->>'sektor' = 'UPRATOVANIE' and (j->'sektory'->0->>'objem')::numeric = 150000, 'prvý sektor UPRATOVANIE 150000') from r;
select pg_temp.over(exists(select 1 from jsonb_array_elements(j->'sektory') e where e->>'sektor' = 'INE'), 'zmluva bez sektora je INE') from r;
select pg_temp.over(j->'dodavatelia_top'->0->>'nazov' = 'Upratovanie Test s.r.o.' and (j->'dodavatelia_top'->0->>'pocet')::int = 2, 'top dodávateľ = firma s.r.o., 2 zmluvy') from r;
select pg_temp.over((select e->>'nazov' is null from jsonb_array_elements(j->'dodavatelia_top') e where (e->>'objem')::numeric = 20000), 'meno fyzickej osoby sa nezobrazuje (null)') from r;
select pg_temp.over(not (j::text like '%Ján Novák%'), 'meno fyzickej osoby nie je nikde vo výstupe') from r;
select pg_temp.over((j->>'dodavatelov_spolu')::int = 3, 'dodavatelov spolu 3 za 36 mesiacov (stará zmluva sa nepočíta)') from r;
select pg_temp.over((j->>'koncia_do_6')::int = 2 and (j->>'koncia_do_12')::int = 3 and (j->>'koncia_do_24')::int = 4, 'končiace: 2 do 6, 3 do 12, 4 do 24 mesiacov') from r;
select pg_temp.over((j->>'objem_koncia_do_12')::numeric = 150000, 'objem končiacich do 12 mesiacov') from r;
select pg_temp.over(jsonb_array_length(j->'zoznam') = 3 and not (j->'zoznam'->0 ? 'dodavatel') and not (j->'zoznam'->0 ? 'predmet'), 'teaser: 3 riadky, bez dodávateľa a predmetu') from r;
select pg_temp.over((j->>'pocet_dalsich')::int = 1, 'pocet_dalsich = 4 do 24 mesiacov - 3 v teaseri') from r;
select pg_temp.over(j->>'typicka_dlzka_dni' is not null, 'typická dĺžka zmluvy je vyplnená') from r;
select pg_temp.over((j->>'dotacie_pocet')::int = 1 and (j->>'dotacie_suma')::numeric = 70000 and (j->>'dotacie_buduce_okna')::int = 1, 'dotácie: 1 ks, 70000, 1 okno v budúcnosti') from r;
select pg_temp.over((j->>'uvo_vysledky_24m')::int = 2 and (j->>'uvo_priemer_ponuk')::numeric = 3.0 and (j->>'uvo_slabe_konkurencie')::int = 1, 'ÚVO: 2 výsledky za 24 mesiacov (IČO s nulami aj bez), priemer 3, 1 slabá konkurencia') from r;

-- neplatné a nenájdené IČO
select pg_temp.over(public.profil_obstaravatela('12345678')->>'kod' = 'ICO_NEPLATNE', 'neplatná kontrolná číslica');
select pg_temp.over(public.profil_obstaravatela('abc')->>'kod' = 'ICO_NEPLATNE', 'neplatný tvar');
select pg_temp.over(public.profil_obstaravatela(null)->>'kod' = 'ICO_NEPLATNE', 'null');
select pg_temp.over(public.profil_obstaravatela('47586362')->>'kod' = 'NENAJDENE', 'platné IČO bez dát = NENAJDENE');

-- práva: anon a authenticated funkciu volať nemôžu, service_role áno
select pg_temp.over(not has_function_privilege('anon', 'public.profil_obstaravatela(text)', 'execute'), 'anon nemá execute');
select pg_temp.over(not has_function_privilege('authenticated', 'public.profil_obstaravatela(text)', 'execute'), 'authenticated nemá execute');
select pg_temp.over(has_function_privilege('service_role', 'public.profil_obstaravatela(text)', 'execute'), 'service_role má execute');
select pg_temp.over(not has_function_privilege('anon', 'public.kontrola_zmluv_ico(text)', 'execute'), 'migrácia 69: anon nemá execute na kontrola_zmluv_ico');
select pg_temp.over(has_function_privilege('service_role', 'public.kontrola_zmluv_ico(text)', 'execute'), 'migrácia 69: service_role má execute na kontrola_zmluv_ico');

-- _je_pravnicka_osoba
select pg_temp.over(public._je_pravnicka_osoba('ABC, s.r.o.') and public._je_pravnicka_osoba('Slovenská pošta, a. s.') and public._je_pravnicka_osoba('Mesto Košice') and public._je_pravnicka_osoba('Ministerstvo vnútra SR'), 'právnické osoby sa rozpoznajú');
select pg_temp.over(not public._je_pravnicka_osoba('Ján Novák') and not public._je_pravnicka_osoba('Mgr. Eva Kováčová') and not public._je_pravnicka_osoba(null), 'mená fyzických osôb a null nie sú právnická osoba');

select popis || case when ok then '  OK' else '  CHYBA' end as vysledok from _t;
select case when count(*) filter (where not ok) = 0 then 'VSETKY TESTY OK (' || count(*) || ')' else 'CHYBY: ' || count(*) filter (where not ok) end as suhrn from _t;
rollback;
