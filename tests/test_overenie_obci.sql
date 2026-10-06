\set ON_ERROR_STOP off
insert into auth.users(id,email) values
 ('a0000000-0000-0000-0000-000000000001','starosta@senec.sk'),
 ('a0000000-0000-0000-0000-000000000002','hacker@gmail.com'),
 ('a0000000-0000-0000-0000-000000000003','uctareren@senec.sk'),
 ('a0000000-0000-0000-0000-000000000004','jozo@gmail.com'),
 ('a0000000-0000-0000-0000-000000000005','poradca@firma.sk'),
 ('a0000000-0000-0000-0000-000000000006','takac.marek@gmail.com'),
 ('a0000000-0000-0000-0000-000000000007','x@gmail.com');
insert into public.kampan_obce_kontakty(ico,obec,email,stav,zdroj) values
 ('00305252','Senec','starosta@senec.sk','ok','t'),
 ('00111111','Gmailovo','obec.gmailovo@gmail.com','ok','t'),
 ('00222222','Vyluc','podatelna@vyluc.sk','vylucene','t');
insert into public.poradcovia_profily(owner,nazov,kontakt_email) values ('a0000000-0000-0000-0000-000000000005','Poradca s.r.o.','poradca@firma.sk');

select 'helper presna' t, public._email_patri_obci('starosta@senec.sk','00305252') = true as ok;
select 'helper domena' t, public._email_patri_obci('ucto@senec.sk','00305252') = true as ok;
select 'helper ina domena' t, public._email_patri_obci('x@iny.sk','00305252') = false as ok;
select 'helper gmail dom nepustí' t, public._email_patri_obci('hocikto@gmail.com','00111111') = false as ok;
select 'helper gmail presna ok' t, public._email_patri_obci('obec.gmailovo@gmail.com','00111111') = true as ok;
select 'helper vylucene' t, public._email_patri_obci('x@vyluc.sk','00222222') = false as ok;
select 'helper zle ico' t, public._email_patri_obci('starosta@senec.sk','abc') = false as ok;

create table public._ids as select 1 as x;
grant all on public._ids to authenticated;
set role authenticated;
-- 1) auto-overena obec
select set_config('request.jwt.claim.sub','a0000000-0000-0000-0000-000000000001',false);
select public.zaloz_obec_ucet('Senec','BA','00305252','starosta@senec.sk') is not null as zalozena1;
select 'obec1 overena auto' t, overena and overena_sposob='auto_email' as ok from public.obce_ucty where owner='a0000000-0000-0000-0000-000000000001';
select public.vytvor_dopyt('Dopyt senec') is not null;
select 'dopyt1 overeny' t, overeny and admin_upozorneny as ok from public.dopyty where obec_nazov='Senec';

-- 2) neoverena obec
select set_config('request.jwt.claim.sub','a0000000-0000-0000-0000-000000000002',false);
select public.zaloz_obec_ucet('Obec Podvod','BA','00305252','hacker@gmail.com') is not null as zalozena2;
select 'obec2 neoverena' t, not overena and overena_sposob is null as ok from public.obce_ucty where owner='a0000000-0000-0000-0000-000000000002';
select public.vytvor_dopyt('Dopyt podvod') is not null;
select 'dopyt2 neoverený' t, not overeny and not admin_upozorneny as ok from public.dopyty where obec_nazov='Obec Podvod';
select 'obec2 vidi svoj dopyt' t, count(*) filter (where obec_nazov='Obec Podvod')=1 as ok from public.dopyty;

-- 3) klient nemoze sam zmenit overenie
update public.obce_ucty set overena=true where owner='a0000000-0000-0000-0000-000000000002';
update public.dopyty set overeny=true where obec_nazov='Obec Podvod';
reset role;
select 'klient nepreoveril sam' t, (select not overena from public.obce_ucty where owner='a0000000-0000-0000-0000-000000000002') as ok;
set role authenticated;
reset role;
select 'ani dopyt' t, (select not overeny from public.dopyty where obec_nazov='Obec Podvod') as ok;
set role authenticated;

-- 4) poradca vidi len overeny
select set_config('request.jwt.claim.sub','a0000000-0000-0000-0000-000000000005',false);
select 'poradca vidi len 1' t, count(*)=1 and min(obec_nazov)='Senec' as ok from public.dopyty;
select public.reaguj_na_dopyt((select id from public.dopyty where obec_nazov='Senec' limit 1),'Ahoj');
select 'reakcia ulozena' t, count(*)=1 as ok from public.reakcie;
reset role;
select id as neov_id from public.dopyty where obec_nazov='Obec Podvod' \gset
select set_config('t.neov', :'neov_id', false) \gset
set role authenticated;
select set_config('request.jwt.claim.sub','a0000000-0000-0000-0000-000000000005',false);
do $$ begin
  begin
    perform public.reaguj_na_dopyt(current_setting('t.neov')::uuid,'x');
    raise notice 'FAIL: reakcia na neovereny presla';
  exception when others then raise notice 'OK: reakcia na neovereny zamietnuta: %', sqlerrm;
  end;
end $$;

-- 5) schvalenie: nie-admin nesmie
select set_config('request.jwt.claim.sub','a0000000-0000-0000-0000-000000000004',false);
do $$ begin
  begin perform public.schval_obec(current_setting('t.neov')::uuid); raise notice 'FAIL: nie-admin schvalil';
  exception when others then raise notice 'OK: nie-admin zamietnuty: %', sqlerrm; end;
  begin perform * from public.cakajuce_obce(); raise notice 'FAIL: nie-admin cakajuce';
  exception when others then raise notice 'OK: cakajuce zamietnute'; end;
end $$;
-- admin
select set_config('request.jwt.claim.sub','a0000000-0000-0000-0000-000000000006',false);
select 'cakajuce 1' t, count(*)=1 and max(prihlasovaci_email)='hacker@gmail.com' and max(otvorene_dopyty)=1 as ok from public.cakajuce_obce();
reset role;
select id as obec2_id from public.obce_ucty where owner='a0000000-0000-0000-0000-000000000002' \gset
set role authenticated;
select set_config('request.jwt.claim.sub','a0000000-0000-0000-0000-000000000006',false);
select public.schval_obec(:'obec2_id'::uuid);
select 'po schvaleni overena rucne' t, overena and overena_sposob='rucne' as ok from public.obce_ucty where id=:'obec2_id'::uuid;
select 'po schvaleni dopyt overeny' t, overeny and not admin_upozorneny as ok from public.dopyty where obec_id=:'obec2_id'::uuid;
select 'cakajuce 0' t, count(*)=0 as ok from public.cakajuce_obce();
-- poradca vidi uz oba a moze reagovat
select set_config('request.jwt.claim.sub','a0000000-0000-0000-0000-000000000005',false);
select 'poradca vidi 2' t, count(*)=2 as ok from public.dopyty;
select public.reaguj_na_dopyt(:'neov_id'::uuid,'Ahoj po schvaleni');
select 'reakcie 2' t, count(*)=2 as ok from public.reakcie;
-- dalsi dopyt overenej obce je rovno overeny
select set_config('request.jwt.claim.sub','a0000000-0000-0000-0000-000000000002',false);
select public.vytvor_dopyt('Dalsi') is not null;
reset role;
select 'novy dopyt schvalenej overeny' t, overeny as ok from public.dopyty where nazov='Dalsi';
-- anon nema pristup
set role anon;
do $$ begin
  begin perform public.schval_obec(gen_random_uuid()); raise notice 'FAIL: anon schval';
  exception when others then raise notice 'OK: anon zamietnuty'; end;
end $$;
