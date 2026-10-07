-- =============================================================================
--  69 — KONTROLA IČO LEN CEZ EDGE FUNCTION (vlna 84, 7. 10. 2026; audit A5)
--  Vlož do Supabase: SQL Editor -> New query -> Run. Spustiť sa dá opakovane.
-- =============================================================================
--
--  Stránka /kontrola volala RPC kontrola_zmluv_ico priamo s verejným kľúčom,
--  takže robot mohol (v rámci limitu 600 dotazov/hod.) prechádzať IČO bez
--  overenia. Od vlny 84 ide dopyt cez Edge Function `verejny-formular`
--  (typ kontrola_ico): Cloudflare Turnstile + limit 30 dopytov/hod. na IP.
--  Táto migrácia zatvára priamy prístup: RPC môže volať už len service_role.
--
--  POSTUP NASADENIA (poradie je dôležité):
--    1) nasadiť Edge Function verejny-formular (nový typ kontrola_ico),
--    2) pushnúť web (kontrola.html + formular.js),
--    3) až potom spustiť túto migráciu. Keby sa spustila skôr, stará verzia
--       stránky by prestala fungovať.
-- =============================================================================

revoke all on function public.kontrola_zmluv_ico(text) from public, anon, authenticated;
grant execute on function public.kontrola_zmluv_ico(text) to service_role;

select 'Migracia 69 hotova: kontrola_zmluv_ico len cez Edge Function.' as vysledok;
