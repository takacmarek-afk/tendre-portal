-- =============================================================================
--  59 — Servisný dopyt -> automatický dopyt na Trhu (P3.2 C, druhá polovica)
--  Vloz do Supabase: SQL Editor -> New query -> Run. Spustit sa da opakovane.
-- =============================================================================
--
--  ZADANIE: "Zo žiadosti o pomoc sa so súhlasom obce automaticky stane
--  dopyt na trhu."
--
--  ROZHODNUTIE MAREKA (29.9.2026, klikatelne otazky): "Ano, e-mail s
--  rychlou registraciou" — po SCHVALENI servisneho dopytu (Marek alebo ja
--  v Supabase Studio, rucne — ide o volne pisany text, ludska kontrola
--  pred zverejnenim je namieste) posleme obci e-mail s odkazom na rychlu
--  registraciu, ktora jednym klikom prevezme text dopytu.
--
--  PRECO RUCNE SCHVALENIE (novy stlpec schvaleny), NIE AUTOMATICKY HNED PO
--  suhlas_zverejnit=true
--  servisny_dopyt.popis je volny text napisany obcou bez akejkolvek
--  kontroly formatu ci obsahu. Predtym, nez sa z neho stane VEREJNY dopyt
--  viditelny vsetkym poradcom, dava zmysel jedno rychle rucne prekontrolovanie
--  (rovnaky duvod, preco su servisne_dopyty spracovavane rucne uz od zaciatku
--  — 38_servisny_segment.sql, "toto NIE JE len softver").
--
--  PRECO TOKEN (nahodne uuid), NIE PRIAMO bigserial id V ODKAZE
--  id by dovolilo hocikomu skusat susedne cisla a uhadnut/enumerovat cudzie
--  servisne dopyty (aj ked citanie samotnej tabulky je aj tak zakazane —
--  token je druha vrstva opatrnosti, rovnaky princip ako obce_pozvanky.id
--  vo vlne 58).
--
--  PRECO DVE RPC (over_servisny_token anon + moj_servisny_dopyt authenticated)
--  Rovnaky vzor ako nazov_obec_pozvanky/prijmi_obec_pozvanku vo vlne 58:
--  pred prihlasenim smie prihlasenie.html vediet LEN nazov obce (na banner
--  a zamknutie e-mailu), nie citlivy text ziadosti (popis) — ten sa nacita
--  az PO prihlaseni a len tomu, koho e-mail sa zhoduje s kontakt_email
--  (druha vrstva kontroly navyse k tokenu).
-- =============================================================================

alter table public.servisne_dopyty
    add column if not exists token uuid not null default gen_random_uuid() unique;

alter table public.servisne_dopyty
    add column if not exists schvaleny boolean not null default false;

alter table public.servisne_dopyty
    add column if not exists email_poslany_at timestamptz;

alter table public.servisne_dopyty
    add column if not exists prevzaty_at timestamptz;

comment on column public.servisne_dopyty.schvaleny is
    'Rucne nastavene (Marek/Claude v Supabase Studio) po precitani popis-u. '
    'Bez tohto sa e-mail s rychlou registraciou neposle, aj ked ma obec '
    'zaskrtnute suhlas_zverejnit.';
comment on column public.servisne_dopyty.email_poslany_at is
    'Kedy posli_servis_email.py poslal e-mail s odkazom na rychlu '
    'registraciu. Bran proti opakovanemu poslaniu.';
comment on column public.servisne_dopyty.prevzaty_at is
    'Kedy sa zo servisneho dopytu naozaj stal verejny dopyt na Trhu '
    '(po dokonceni rychlej registracie). Bran proti duplicitnemu vytvoreniu '
    'dopytu pri opakovanom kliku na ten isty odkaz.';

-- ── Meno obce k tokenu, BEZ prihlasenia (banner na prihlasenie.html) ───────
-- Vracia LEN nazov obce a e-mail (na zamknutie prihlasovacieho pola,
-- rovnaky vzor ako nazov_pozvanky/nazov_obec_pozvanky) — ZIADNY popis,
-- ten je citlivejsi a caka na prihlasenie so zhodnym e-mailom.
create or replace function public.over_servisny_token(p_token uuid)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
    select case when id is null then jsonb_build_object('ok', false)
                else jsonb_build_object('ok', true, 'obec', obec, 'email', kontakt_email)
           end
      from public.servisne_dopyty
     where token = p_token
       and suhlas_zverejnit = true
       and schvaleny = true
       and prevzaty_at is null;
$$;

grant execute on function public.over_servisny_token(uuid) to anon, authenticated;

-- ── Plny obsah k tokenu, LEN pre prihlaseneho s rovnakym e-mailom ──────────
create or replace function public.moj_servisny_dopyt(p_token uuid)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_sd    record;
    v_email text;
begin
    if auth.uid() is null then
        raise exception 'Najprv sa prihlas.';
    end if;

    select email into v_email from auth.users where id = auth.uid();

    select * into v_sd
      from public.servisne_dopyty
     where token = p_token
       and suhlas_zverejnit = true
       and schvaleny = true
       and prevzaty_at is null;

    if v_sd.id is null then
        return jsonb_build_object('ok', false, 'kod', 'NEPLATNY');
    end if;

    if lower(v_email) <> lower(v_sd.kontakt_email) then
        return jsonb_build_object('ok', false, 'kod', 'INY_EMAIL');
    end if;

    return jsonb_build_object('ok', true, 'obec', v_sd.obec, 'kraj', v_sd.kraj,
                               'ico', v_sd.ico, 'email', v_sd.kontakt_email,
                               'popis', v_sd.popis);
end;
$$;

grant execute on function public.moj_servisny_dopyt(uuid) to authenticated;

-- ── Oznacenie ako prevzaty (po uspesnej registracii + vytvoreni dopytu) ────
create or replace function public.oznac_servis_prevzaty(p_token uuid)
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_email text;
begin
    if auth.uid() is null then
        raise exception 'Najprv sa prihlas.';
    end if;

    select email into v_email from auth.users where id = auth.uid();

    update public.servisne_dopyty
       set prevzaty_at = now()
     where token = p_token
       and lower(kontakt_email) = lower(v_email)
       and prevzaty_at is null;
end;
$$;

grant execute on function public.oznac_servis_prevzaty(uuid) to authenticated;

select 'Servis -> dopyt prevod pripraveny: token/schvaleny/email_poslany_at/prevzaty_at, '
       'over_servisny_token, moj_servisny_dopyt, oznac_servis_prevzaty.' as vysledok;
