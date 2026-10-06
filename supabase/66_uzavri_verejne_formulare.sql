-- =============================================================================
--  66 — UZAVRETIE PRIAMYCH ZAPISOV ANONYMA (vlna 81, 6. 10. 2026)
--
--  SPUSTIT AZ PO:  (1) migracii 65,  (2) nasadeni Edge Function
--  `verejny-formular`,  (3) nasadeni novych stranok obce.html / servis.html /
--  starosta.html (volaju funkciu namiesto priameho REST zapisu).
--  Inak by formulare na starych strankach prestali fungovat.
--
--  Po tejto migracii sa do odber_obce, servisne_dopyty a spatne_volania da
--  zapisovat LEN cez Edge Function (Turnstile + limit na IP + validacia).
--  Citanie a ostatne operacie sa nemenia. Idempotentne.
-- =============================================================================

revoke insert on public.odber_obce       from anon, authenticated;
revoke insert on public.servisne_dopyty  from anon, authenticated;
revoke insert on public.spatne_volania   from anon, authenticated;

drop policy if exists odber_obce_insert      on public.odber_obce;
drop policy if exists servisne_dopyty_insert on public.servisne_dopyty;
drop policy if exists spatne_volania_insert  on public.spatne_volania;

revoke usage on sequence public.odber_obce_id_seq      from anon, authenticated;
revoke usage on sequence public.servisne_dopyty_id_seq from anon, authenticated;
revoke usage on sequence public.spatne_volania_id_seq  from anon, authenticated;

select 'Migracia 66 hotova: odber_obce, servisne_dopyty a spatne_volania sa zapisuju len cez Edge Function verejny-formular.' as vysledok;
