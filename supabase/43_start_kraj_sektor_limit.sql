-- =============================================================================
--  OPRAVA: Start plán sľubuje "1 kraj alebo 1–2 sektory podľa výberu"
--  (cennik.html) oproti Growth "Celé Slovensko, všetky sektory" — v
--  databáze to doteraz nebolo nijak vynútené.
--  Vloz do Supabase: SQL Editor -> New query -> Run. Spustit sa da opakovane.
-- =============================================================================
--
--  NALEZ (zivy audit 22.9.2026, pokracovanie "oprav vsetko")
--  public.odber.sektor a public.odber.kraj su text stlpce, kde NULL
--  znamena "vsetko" (08_zadarmo.sql: "sektor text, -- null = vsetky" /
--  "kraj text, -- null = cele Slovensko"). Ani appka, ani RLS doteraz
--  nebranili Start ucastu nechat oboje prazdne — teda dostat presne tu
--  istu sirku zaberu (cele Slovensko, vsetky sektory) ako Growth (89 EUR),
--  hoci Start (34 EUR) ma v cenniku sluby uzsi zaber.
--
--  ROZHODNUTIE (Marek, 22.9.2026, po odporucani v tejto session)
--  Obmedzit LEN e-mailovy/webhook odber (public.odber), NIE prehliadanie
--  v appke (zalozky Konciace zmluvy/Dotacie/Dodavatelia ostavaju volne
--  pre kohokolvek prihlaseneho, bez ohladu na plan) — dovod: appkove
--  filtre su o aktivnom skumani dat, odber je o pasivnom, opakovanom
--  doruceni hodnoty, presne tak, ako uz existujuci Growth-only gate na
--  frekvencia='denne'/webhook_url (25_odber_pro_gating.sql) rozlisuje
--  Start/Growth len na urovni doruceni, nie prehliadania.
--
--  POZNAMKA K "1-2 SEKTORY": schema podporuje presne 1 sektor a 1 kraj
--  naraz (jednoduchy text stlpec, nie pole/tabulka) — viacnasobny vyber
--  sektorov by vyzadoval zmenu schemy. Tato migracia to nerozsiruje, len
--  vynucuje, ze Start si MUSI vybrat konkretny 1 kraj a 1 sektor (nie
--  "vsetko"), co je najsilnejsi krok dostupny bez zmeny schemy. Ak by
--  Marek chcel realne "1-2 sektory" pre Start, treba samostatnu vlnu na
--  zmenu sektor na pole + upravu filtracnej logiky v pipeline/posli_email.py.
--
--  DORMANT, KYM je_zadarmo() VRACIA true — rovnaky vzor ako
--  25_odber_pro_gating.sql: RLS s public.ma_pro() gate (ma_pro() OR-uje
--  s je_zadarmo(), teda pocas otvoreneho obdobia toto nikoho neobmedzuje).
--
--  PIPELINE (service_role): netreba samostatny ma_pro_pre_org() gate ako
--  pri frekvencia='denne' — tam islo o to, ci sa dany e-mail vobec ma
--  poslat (rozhodnutie navyse k ulozenym datam). Tu ide len o to, AKE
--  hodnoty sektor/kraj su v riadku ulozene — RLS pri zapise uz zarucuje,
--  ze Start riadok nikdy nema oboje NULL, takze pipeline/posli_email.py
--  proste pouzije, co tam je, bez potreby vlastnej kontroly planu.
--
--  ZNAMY HRANICNY PRIPAD (k rieseniu az pri prepnuti je_zadarmo()):
--  existujuci Start riadok s sektor/kraj = NULL (vytvoreny pred touto
--  migraciou) by po prepnuti je_zadarmo() na false nemohol byt UPDATE-ovany
--  (ani na nesuvisiace pole), kym si majitel nedoplni konkretny kraj aj
--  sektor — v momente tejto migracie sa to netyka ziadneho existujuceho
--  riadku (v produkcii je len 1 organizacia, testovaci Growth ucet).
-- =============================================================================

drop policy if exists odber_insert on public.odber;
create policy odber_insert on public.odber
    for insert to authenticated
    with check (
        user_id = auth.uid()
        and (frekvencia is distinct from 'denne' or public.ma_pro())
        and (webhook_url is null or public.ma_pro())
        and (public.ma_pro() or (sektor is not null and kraj is not null))
    );

drop policy if exists odber_update on public.odber;
create policy odber_update on public.odber
    for update to authenticated
    using (user_id = auth.uid())
    with check (
        user_id = auth.uid()
        and (frekvencia is distinct from 'denne' or public.ma_pro())
        and (webhook_url is null or public.ma_pro())
        and (public.ma_pro() or (sektor is not null and kraj is not null))
    );

select polname, pg_get_expr(polwithcheck, polrelid) as with_check
  from pg_policy
 where polrelid = 'public.odber'::regclass;

select 'odber RLS: Start plan (nie ma_pro()) musi mat vybrany konkretny '
       'kraj AJ sektor (nie "vsetko"), presne ako cennik.html sluby pre '
       'e-mailovy odber. Dormant, kym je_zadarmo() vracia true.' as vysledok;
