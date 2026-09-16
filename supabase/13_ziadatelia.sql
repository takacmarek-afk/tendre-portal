-- ════════════════════════════════════════════════════════════════════════
--  TRETIA VRSTVA: OBCE, KTORÉ SI NAJALI PROJEKTANTA
--
--  Najdlhší predstih v celom produkte.
--
--  REŤAZ:  obec si najme projektanta  →  dotácia  →  tender
--                   ~382 dní               6 až 18 mesiacov
--
--  ODMERANÉ 16. 9. 2026 na vlastných dátach:
--      101 obcí si najalo sprostredkovateľa na napísanie žiadosti
--       70 z nich (69,3 %) potom dotáciu DOSTALO
--      medián odstupu najatie → dotácia: 382 dní (p25 219, p75 584)
--      medián sumy takej dotácie: 129 094 €
--
--  Tých 69,3 % NIE JE príčinnosť — obec, ktorá si najme poradcu, je už typ
--  obce, čo o peniaze ide. Na predikciu to nevadí, na tvrdenie „vďaka
--  poradcovi" by vadilo, a to nikde netvrdíme. A je to spodná hranica:
--  obce, ktoré si poradcu najali nedávno, dotáciu dostať nestihli.
--
--  Spusti v SQL editore Supabase. Bezpečné spustiť aj opakovane.
-- ════════════════════════════════════════════════════════════════════════

create table if not exists public.obce_ziadatelia (
    contract_id      bigint primary key references public.contracts(id) on delete cascade,
    obec             text not null,
    obec_ico         text,
    mesto            text,
    kraj             text,
    sprostredkovatel text,
    cena_sluzby      numeric,
    najate           date,          -- kedy obec podpisala zmluvu s poradcom
    okno_od          date,          -- najate + 219 dni (p25)
    ocakavane        date,          -- najate + 382 dni (median)
    okno_do          date,          -- najate + 584 dni (p75)
    odkaz            text,
    last_seen_at     date,
    refreshed_at     timestamptz not null default now()
);

create index if not exists ix_ziadatelia_najate on public.obce_ziadatelia(najate desc);
create index if not exists ix_ziadatelia_kraj   on public.obce_ziadatelia(kraj);
create index if not exists ix_ziadatelia_okno   on public.obce_ziadatelia(ocakavane);

alter table public.obce_ziadatelia enable row level security;

-- Rovnaký režim ako príležitosti a dotácie: je to obsah dodávateľskej
-- časti portálu, teda len pre prihlásených s platným prístupom.
-- NIE JE to verejné ako stránka pre obce — toto je predikcia tendra
-- a tá je jadrom produktu.
drop policy if exists ziadatelia_select on public.obce_ziadatelia;
create policy ziadatelia_select on public.obce_ziadatelia
    for select to authenticated
    using (public.ma_aktivny_pristup());

comment on table public.obce_ziadatelia is
    'Obce, ktore si najali projektanta a dotaciu este nemaju. Median 382 dni po najati prichadza dotacia (odmerane na 70 obciach).';

select 'obce_ziadatelia: ' || count(*)::text || ' riadkov (naplni ich beh pipeline)'
    as vysledok from public.obce_ziadatelia;
