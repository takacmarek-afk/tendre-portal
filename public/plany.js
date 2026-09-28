// =============================================================================
//  PLÁNY A PODMIENKY — jedna verzia pravdy (audit 27. 9. 2026, P1.1)
//
//  Čísla o skúšobnej dobe, cenách a limitoch sú TU. Statické stránky
//  (index, cenník, prihlásenie) ich majú v texte natvrdo, aby sa zobrazili
//  aj bez JavaScriptu, ale test pipeline/test_plany.py pri každom behu
//  porovná všetky stránky s týmto súborom a zlyhá, keď sa rozídu.
//  Databáza: supabase/50_plany_14_dni.sql (cenove_plany, trial 14 dní).
//
//  Zmena ceny = zmeniť tu + v cenove_plany + v texte cenníka; test povie,
//  čo ste zabudli.
// =============================================================================
window.PLANY = {
  "skusobneDni": 14,
  "limitFiriemNaDopyt": 5,
  "plany": {
    "start":   { "nazov": "Start",   "mesiac": 34,  "rok": 340 },
    "growth":  { "nazov": "Growth",  "mesiac": 89,  "rok": 890 },
    "team":    { "nazov": "Team",    "mesiac": 249, "rok": 2490 },
    "poradca": { "nazov": "Poradca", "mesiac": 59,  "rok": 590 }
  }
};
