-- =============================================================================
--  ADMIN A TESTOVANIE
--  Nie je to jednorazova migracia, ale zosit prikazov, ktore budes pouzivat
--  opakovane. Spustaj z neho JEDNOTLIVE bloky, nie cely subor naraz.
-- =============================================================================


-- ─────────────────────────────────────────────────────────────────────────
--  A. JEDNORAZOVA CAST — spusti raz
-- ─────────────────────────────────────────────────────────────────────────

-- Rola 'admin' zatial nerobi nic, ziadne admin obrazovky neexistuju.
-- Pridavam ju teraz preto, aby sa neskor nemusela menit schema, ked ich
-- postavime. Buduci admin pohlad bude filtrovat prave podla nej.
alter table public.memberships drop constraint if exists memberships_rola_check;
alter table public.memberships add constraint memberships_rola_check
    check (rola in ('owner', 'member', 'admin'));


-- ─────────────────────────────────────────────────────────────────────────
--  B. TRVALY PRISTUP PRE SEBA
--  Najprv sa normalne zaregistruj na predtendrom.sk (zalozi ti to firmu
--  s trojdnovou skuskou), potom spusti toto a skuska sa zmeni na trvaly
--  pristup. Funkcia ma_aktivny_pristup() nekontroluje pri stave 'aktivne'
--  ziadny datum, takze to nikdy nevyprsi.
-- ─────────────────────────────────────────────────────────────────────────

update public.subscriptions s
set    stav = 'aktivne',
       plan = 'admin',
       obdobie_konci = null,
       updated_at = now()
where  s.org_id = (select id from public.organizations where ico = '47586362');

update public.memberships m
set    rola = 'admin'
where  m.org_id = (select id from public.organizations where ico = '47586362');

-- Kontrola
select o.nazov, o.ico, s.stav, s.plan, s.trial_konci, s.obdobie_konci
from   public.organizations o
join   public.subscriptions s on s.org_id = o.id
where  o.ico = '47586362';


-- ─────────────────────────────────────────────────────────────────────────
--  C. RESET TESTOVACEJ FIRMY
--  Ked chces znova vyskusat, ako vyzera registracia a trojdnova skuska,
--  potrebujes IČO, ktore system nikdy nevidel. Bud pouzi ine osemciferne
--  cislo, alebo tymto blokom zmaz predchadzajuci test.
--
--  POZOR: zmaze firmu, clenstva aj historiu skusky. Nikdy to nespustaj
--  na vlastnom IČO ani na IČO skutocneho zakaznika.
-- ─────────────────────────────────────────────────────────────────────────

-- Nahrad 99999999 tym IČO, ktore chces zmazat:
-- delete from public.trial_history  where ico = '99999999';
-- delete from public.organizations  where ico = '99999999';
--   (clenstva, predplatne a udalosti odidu s firmou cez on delete cascade)


-- ─────────────────────────────────────────────────────────────────────────
--  D. PREHLAD — kto je v systeme
--  Toto je zatial tvoj "admin panel". Kym nemas desiatky firiem, staci to.
-- ─────────────────────────────────────────────────────────────────────────

select o.nazov,
       o.ico,
       s.stav,
       s.plan,
       case
         when s.stav = 'aktivne' then 'trvaly'
         when s.trial_konci > now()
              then 'skusa, zostava ' ||
                   greatest(0, ceil(extract(epoch from s.trial_konci - now()) / 86400))::text || ' dni'
         else 'skuska vyprsala'
       end                                   as pristup,
       (select count(*) from public.memberships m where m.org_id = o.id) as ludi,
       (select count(*) from public.watchlists w where w.org_id = o.id)  as sledovani,
       o.created_at
from   public.organizations o
left   join public.subscriptions s on s.org_id = o.id
order  by o.created_at desc;


-- ─────────────────────────────────────────────────────────────────────────
--  E. KTO SA REGISTROVAL A NEDOKONCIL
--  Pouzivatel, ktory sa prihlasil e-mailom, ale nezadal firmu. Uzitocne
--  cislo: ak ich je vela, onboarding je prilis zlozity.
-- ─────────────────────────────────────────────────────────────────────────

select u.email, u.created_at, u.last_sign_in_at
from   auth.users u
where  not exists (select 1 from public.memberships m where m.user_id = u.id)
order  by u.created_at desc;
