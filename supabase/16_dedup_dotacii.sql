-- ════════════════════════════════════════════════════════════════════════
--  DEDUPLIKACIA DOTACII — nove stlpce
--
--  Odmerane 16. 9. 2026 na 7 698 riadkoch:
--     1 524 nadbytocnych z DVOJITEHO ZVEREJNENIA (ten isty prispevok je
--           v CRZ zapisany raz z kazdej strany, kazdy s vlastnym id)
--       682 DODATKOV, v nich 14,4 % celeho objemu (565 M EUR z 3 932 M)
--
--  contract_id_alt  druhy zapis toho isteho prispevku, aby sa dal odkaz
--                   do CRZ otvorit na tu stranu, ktoru clovek caka
--  ma_dodatky       kolko dodatkov sa k tomuto riadku zahodilo. NIE JE to
--                   kozmetika: dodatok casto nesie AKTUALNEJSIU sumu (pri
--                   87 z 682 je vyssia), takze na riadku s ma_dodatky > 0
--                   moze byt prekonana suma. UI to hovori nahlas a odkaz
--                   do CRZ umoznuje overenie jednym klikom.
--  je_dodatok       TRUE = OSIRELY dodatok, ktoremu sa rodic nenasiel.
--                   Ponechava sa, pretoze je casto jedinym dokazom, ze
--                   peniaze boli priznane — ale jeho datum je datum
--                   dodatku, nie vznik projektu, takze odhad okna je
--                   systematicky posunuty a realne to zacalo skor.
--
--  Spusti v SQL editore Supabase. Bezpecne spustit aj opakovane.
-- ════════════════════════════════════════════════════════════════════════

alter table public.subsidies
    add column if not exists contract_id_alt bigint,
    add column if not exists ma_dodatky      integer not null default 0,
    add column if not exists je_dodatok      boolean not null default false;

comment on column public.subsidies.contract_id_alt is
    'Druhy zapis toho isteho prispevku v CRZ (dvojite zverejnenie).';
comment on column public.subsidies.ma_dodatky is
    'Kolko dodatkov sa k tomuto riadku zlucilo. > 0 znamena, ze suma mohla byt dodatkom zmenena.';
comment on column public.subsidies.je_dodatok is
    'TRUE = osirely dodatok bez najdenej materskej zmluvy. Datum je datum dodatku, nie vznik projektu.';

select 'subsidies: 3 stlpce doplnene, riadkov ' || count(*)::text
       || ' (naplni ich najblizsi beh)' as vysledok
  from public.subsidies;
