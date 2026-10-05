// =============================================================================
//  JEDINÝ SÚBOR, KTORÝ MUSÍŠ UPRAVIŤ TY
//
//  Obe hodnoty nájdeš v Supabase:
//  Project Settings (ozubené koliesko vľavo dole) → Data API
//
//  Kľúč "anon public" je zámerne verejný — je určený na to, aby bol
//  v prehliadači. Bezpečnosť nezabezpečuje on, ale Row Level Security
//  v databáze, ktorú sme už nastavili. Pokojne ho commitni do repozitára.
//
//  Kľúč "service_role" sem NIKDY nedávaj. Ten obchádza všetky pravidlá
//  a patrí výhradne do GitHub Secrets pre pipeline.
// =============================================================================

window.CONFIG = {
  SUPABASE_URL: "https://kcpgqchdyhbvssybbaaz.supabase.co",

  SUPABASE_ANON_KEY: "sb_publishable_q3oov5jf4ij70hP4f_4JWg_lrwVl7zl",

  // Cloudflare Turnstile (ochrana prihlasovacieho formulara pred robotmi).
  // Verejny "site key" (nie secret!). Kym je prazdny, stranka overenie
  // nezobrazuje a prihlasenie funguje ako doteraz. Vyplnit az ked je v Supabase
  // (Authentication -> Attack Protection) zapnuty Turnstile, inak prihlasenie
  // zlyha na chybajucom tokene.
  TURNSTILE_SITE_KEY: "0x4AAAAAAFOg6N9a_gBGX4Jl",
};
