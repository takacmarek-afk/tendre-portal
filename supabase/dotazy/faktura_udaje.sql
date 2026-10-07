-- =============================================================================
--  Podklad pre faktúry za zaplatené predplatné (vlna 85, 7. 10. 2026).
--  NIE JE migrácia — len SELECT. Vlož do Supabase SQL Editor a daj Run.
--
--  LoveHome s.r.o. zatiaľ nie je platca DPH, takže faktúra je "bez DPH"
--  (poznámka na faktúre: "Dodávateľ nie je platcom DPH."). Až sa stane
--  platcom, k sume sa pripočíta DPH — cenník sa nemení.
--
--  Chýbajúce DIČ/adresu organizácie doplň zo Stripe (Payments -> detail
--  platby -> Billing details; Checkout ich vyžaduje) alebo e-mailom od
--  zákazníka.
-- =============================================================================
select
    p.spracovane_at::date                       as datum_uhrady,
    p.reference                                 as referencia_platby,
    o.nazov                                     as odberatel,
    o.ico,
    o.dic,
    o.adresa,
    p.plan,
    p.obdobie,
    p.suma,
    p.mena
from public.platby p
join public.organizations o on o.id = p.org_id
where p.stav = 'zaplatena'
order by p.spracovane_at desc
limit 100;
