// =============================================================================
//  Quick Win B: Karta vyzvy, logika bez UI
//    - vyhodnotSemafor(): stav 🟢/🟠/🔴 zo 7 odpovedi + jeden prvy krok
//    - spocitajPeniaze(): spoluucast v € a potreba predfinancovania
//
//  Ciste ES modul, bez zavislosti. V prehliadaci: <script type="module">
//  import { vyhodnotSemafor, spocitajPeniaze } from "/semafor.js".
//  Testy: tests/test_vyzvy_semafor.mjs (node --test).
//  Vyzva = riadok z RPC karta_vyzvy(...).vyzva (migracia 89).
// =============================================================================

/** @typedef {"ano"|"nie"|"neviem"} Odpoved */
/** @typedef {{q1?:Odpoved,q2?:Odpoved,q3?:Odpoved,q4?:Odpoved,q5?:Odpoved,q6?:Odpoved,q7?:Odpoved}} Odpovede */
/** @typedef {"zelena"|"oranzova"|"cervena"|"neuplne"} Stav */

// --- Konfiguracia ---------------------------------------------------------------
// Specifikacia ma dve citania pravidla pre zelenu:
//   (a) "7/7 ANO, alebo vsetky NIE su 🟠 a stihnu sa"  → vtedy oranzova takmer nenastane
//   (b) zelena = 7/7, oranzova = NIE su len 🟠 a sucet casu sa zmesti
// Predvolene (b), lebo oranzova ma inak prazdny vyznam. Prepnutim na true
// sa pouzije doslovne citanie (a).
export const ZELENA_AJ_PRI_STIHNUTELNYCH = false;

/**
 * Definicia otazok. naprava_dni = horna hranica rozpatia (konzervativne),
 * naprava_text = co ukazeme cloveku.
 * vaha(vyzva, dniDoUzavierky) vrati "cervena" | "oranzova".
 */
export const OTAZKY = {
  q1: {
    text: "Je projekt (zámer) uvedený v programe rozvoja obce (PHRSR)?",
    naprava_dni: 60, naprava_text: "1 – 2 mesiace (najbližšie zasadnutie)",
    vaha: () => "oranzova",
  },
  q2: {
    text: "Má obec k pozemku alebo budove vlastnícke právo alebo iné právo podľa výzvy?",
    naprava_dni: 365, naprava_text: "2 – 12 mesiacov",
    vaha: () => "cervena",
  },
  q3: {
    text: "Máte projektovú dokumentáciu v stupni, ktorý výzva vyžaduje?",
    naprava_dni: 180, naprava_text: "2 – 6 mesiacov",
    vaha: (v, dni) => (dni != null && dni < mesiaceVDnoch(6) ? "cervena" : "oranzova"),
  },
  q4: {
    text: "Máte povolenie stavby alebo potvrdenie, že ho nepotrebujete?",
    naprava_dni: 180, naprava_text: "2 – 6 mesiacov",
    vaha: (v, dni) => (dni != null && dni < mesiaceVDnoch(4) ? "cervena" : "oranzova"),
  },
  q5: {
    text: "Máte predpokladanú hodnotu zákazky podloženú prieskumom trhu alebo už ukončené verejné obstarávanie?",
    naprava_dni: 28, naprava_text: "2 – 4 týždne",
    vaha: () => "oranzova",
  },
  q6: {
    text: "Vie obec zaplatiť spoluúčasť a predfinancovať projekt?",
    naprava_dni: 90, naprava_text: "1 – 3 mesiace",
    vaha: (v) => (v.financovanie === "refundacia" ? "cervena" : "oranzova"),
  },
  q7: {
    // znenie aj vaha zavisia od vyzaduje_ius, pozri otazkaQ7()
    text: "", naprava_dni: 0, naprava_text: "",
    vaha: (v) => (v.vyzaduje_ius ? "cervena" : "oranzova"),
  },
};

const Q7_IUS = { text: "Je projekt v zásobníku IÚS kraja?", naprava_dni: 180, naprava_text: "1 – 6 mesiacov" };
const Q7_PORADCA = { text: "Má obec človeka alebo poradcu, ktorý žiadosť pripraví?", naprava_dni: 14, naprava_text: "2 týždne" };

/** Prvy krok: identifikatory pre UI (texty a tlacidla su v sablone karty). */
export const PRVE_KROKY = {
  uznesenie: "Uznesenie zastupiteľstva (vzor)",
  trh_pd: "Vyžiadať nacenenie projektovej dokumentácie (Trh dopytov)",
  trh_prieskum: "Zadať prieskum trhu (Trh dopytov)",
  lv_prednosta: "Úloha prednostovi: výpis z listu vlastníctva",
  poslat_poradcovi: "Poslať kartu poradcovi / začať písať žiadosť",
  // Rozsirenie: specifikacia nepokryva pripad, ked je NIE len pri Q4 alebo Q7.
  povolenie_stavby: "Podať žiadosť o povolenie stavby",
  ius_kraj: "Kontaktovať kraj kvôli zaradeniu do IÚS",
  najst_poradcu: "Nájsť poradcu (zoznam partnerov)",
};

// --- Pomocne ---------------------------------------------------------------------
const DEN = 86_400_000;
function mesiaceVDnoch(m) { return Math.round(m * 30.44); }
function dnes(d) { const x = d ? new Date(d) : new Date(); return new Date(Date.UTC(x.getUTCFullYear(), x.getUTCMonth(), x.getUTCDate())); }
function plusDni(d, n) { return new Date(d.getTime() + n * DEN); }
function iso(d) { return d.toISOString().slice(0, 10); }
function dniDo(od, isoDatum) { return isoDatum ? Math.round((dnes(isoDatum) - od) / DEN) : null; }

/** Ktore otazky sa obce tykaju. Netykajuca sa = splnena (v UI sa neukaze). */
export function platneOtazky(vyzva) {
  return {
    q1: !!vyzva.vyzaduje_phrsr,
    q2: true,
    q3: vyzva.stupen_pd && vyzva.stupen_pd !== "ziadna",
    q4: !!vyzva.vyzaduje_povolenie,
    q5: true,
    q6: true,
    q7: true,
  };
}

/** Znenie Q7 podla vyzvy (UI potrebuje text). */
export function otazkaQ7(vyzva) { return vyzva.vyzaduje_ius ? Q7_IUS : Q7_PORADCA; }

/** Najblizsie dalsie kolo po aktualnej uzavierke (alebo po dnesku pri otvorenej). */
export function dalsieKolo(vyzva, dnesD) {
  const hranica = vyzva.uzavierka ? dnes(vyzva.uzavierka) : dnesD;
  const kola = (vyzva.kolo_uzavierky || []).map(dnes).filter((d) => d > hranica).sort((a, b) => a - b);
  return kola.length ? iso(kola[0]) : null;
}

// --- Semafor ---------------------------------------------------------------------
/**
 * @param {object} vyzva     riadok vyzvy (uzavierka, kolo_uzavierky, financovanie, vyzaduje_* , stupen_pd)
 * @param {Odpovede} odpovede
 * @param {Date|string} [teraz]
 */
export function vyhodnotSemafor(vyzva, odpovede, teraz) {
  const d0 = dnes(teraz);
  const dniDoUzavierky = dniDo(d0, vyzva.uzavierka);   // null = otvorena
  const platne = platneOtazky(vyzva);

  const polozky = [];   // detail ku kazdej otazke pre UI
  const chyba = [];     // nezodpovedane platne otazky
  for (const q of ["q1", "q2", "q3", "q4", "q5", "q6", "q7"]) {
    const def = q === "q7" ? { ...OTAZKY.q7, ...otazkaQ7(vyzva) } : OTAZKY[q];
    if (!platne[q]) { polozky.push({ q, platna: false, splnena: true }); continue; }
    const o = odpovede?.[q];
    if (!o) { chyba.push(q); polozky.push({ q, platna: true, splnena: null, text: def.text }); continue; }
    const splnena = o === "ano";                         // "neviem" = NIE
    polozky.push({
      q, platna: true, splnena, neviem: o === "neviem", text: def.text,
      vaha: splnena ? null : def.vaha(vyzva, dniDoUzavierky),
      naprava_dni: splnena ? 0 : def.naprava_dni,
      naprava_text: splnena ? null : def.naprava_text,
    });
  }

  const nie = polozky.filter((p) => p.splnena === false);
  const splnene = polozky.filter((p) => p.splnena === true).length;  // vratane netykajucich sa
  const suma_napravy_dni = nie.reduce((s, p) => s + p.naprava_dni, 0);
  const cervene = nie.filter((p) => p.vaha === "cervena").map((p) => p.q);

  /** @type {Stav} */
  let stav;
  let dovod = null;
  if (chyba.length) {
    stav = "neuplne";
  } else if (nie.length === 0) {
    stav = "zelena";
  } else if (cervene.length) {
    stav = "cervena"; dovod = "cervena_odpoved";
  } else if (dniDoUzavierky != null && suma_napravy_dni >= dniDoUzavierky) {
    stav = "cervena"; dovod = "nestihnete_sucet";      // vsetko 🟠, ale spolu sa to nezmesti
  } else {
    stav = ZELENA_AJ_PRI_STIHNUTELNYCH ? "zelena" : "oranzova";
  }

  const kolo = stav === "cervena" ? dalsieKolo(vyzva, d0) : null;
  const krok = prvyKrok(vyzva, polozky, d0);

  return {
    stav,
    dovod,                                   // null | cervena_odpoved | nestihnete_sucet
    pripravenost: `${splnene} zo 7`,         // nikdy percenta
    splnene, celkom: 7,
    nezodpovedane: chyba,
    cervene,
    suma_napravy_dni,
    dni_do_uzavierky: dniDoUzavierky,
    najblizsie_kolo: kolo,
    text_cervena: stav === "cervena"
      ? `Na túto uzávierku to nestihnete. ${kolo ? `Ďalšie kolo: ${kolo}.` : "Ďalšie kolo zatiaľ nie je vyhlásené."}`
      : null,
    polozky,
    prvy_krok: krok,
  };
}

/**
 * Jeden prvy krok podla priority zo specifikacie:
 *   Q1|Q6 NIE → uznesenie; Q3 → trh_pd; Q5 → trh_prieskum; Q2 → lv_prednosta;
 *   vsetko ANO → poslat_poradcovi. (Rozsirenie: len Q4/Q7 NIE.)
 * Nezodpovedane otazky sa pre vyber kroku neratajú.
 */
export function prvyKrok(vyzva, polozky, d0) {
  const nie = new Set(polozky.filter((p) => p.splnena === false).map((p) => p.q));
  const uz = vyzva.uzavierka ? dnes(vyzva.uzavierka) : null;
  const najskor = plusDni(d0, 7);
  const ohranic = (d) => (d < najskor ? najskor : d);

  let id;
  let termin;
  if (nie.has("q1") || nie.has("q6")) {
    id = "uznesenie";
    // najblizsie zasadnutie nepozname: do 30 dni, najneskor uzavierka - 45 dni
    const max30 = plusDni(d0, 30);
    termin = ohranic(uz && plusDni(uz, -45) < max30 ? plusDni(uz, -45) : max30);
  } else if (nie.has("q3")) {
    id = "trh_pd"; termin = plusDni(d0, 7);
  } else if (nie.has("q5")) {
    id = "trh_prieskum"; termin = plusDni(d0, 7);
  } else if (nie.has("q2")) {
    id = "lv_prednosta"; termin = plusDni(d0, 14);
  } else if (nie.has("q4")) {
    id = "povolenie_stavby"; termin = plusDni(d0, 14);
  } else if (nie.has("q7")) {
    id = vyzva.vyzaduje_ius ? "ius_kraj" : "najst_poradcu"; termin = plusDni(d0, 14);
  } else {
    id = "poslat_poradcovi";
    termin = uz ? ohranic(plusDni(uz, -21)) : plusDni(d0, 14);
  }

  return {
    id,
    nazov: PRVE_KROKY[id],
    termin: iso(termin),
    // vzor uznesenia sa neukaze, ak vyzva predpisuje vlastne znenie
    vzor_uznesenia: id === "uznesenie" && !vyzva.uznesenie_vlastne_znenie,
    trh_dopytov: id === "trh_pd" || id === "trh_prieskum",
    interna_uzavierka: uz ? iso(plusDni(uz, -21)) : null,   // pre ICS
    uzavierka: uz ? iso(uz) : null,
  };
}

// --- Kalkulacka (bod 2.3) ----------------------------------------------------------
/**
 * @param {object} vyzva  {spoluucast_pct, nfp_min, nfp_max, dph_opravnena, financovanie}
 * @param {object} vstup
 * @param {number} vstup.cena_s_dph              celkova cena projektu s DPH
 * @param {number} [vstup.neopravnene_s_dph=0]   neopravnene vydavky s DPH
 * @param {boolean} [vstup.dph_je_opravnena]     len pri dph_opravnena = "podla_ziadatela";
 *                                               nevyplnene = konzervativne NIE (obec plati viac)
 * @param {number} [vstup.sadzba_dph=0.23]
 *
 * Vzorce:
 *   COV (celkove opravnene vydavky) = (cena - neopravnene)            ak DPH je opravnena
 *                                   = (cena - neopravnene) / (1+DPH)  inak
 *   NFP = min(COV × (1 - p), nfp_max)
 *   spoluucast = COV × p
 *   obec_zaplati_navzdy = cena - NFP
 *                       = spoluucast + neopravnene + neopravnena DPH + cast nad stropom
 *   predfinancovanie: refundacia → do vysky NFP (obec plati vsetko, NFP sa vrati)
 *                     predfinancovanie / zalohova_platba → ~0 (overit podmienky)
 *                     kombinacia → rozpatie 0 az NFP
 */
export function spocitajPeniaze(vyzva, vstup) {
  // Neznama miera spolufinancovania (migracia 91): nepocitame, UI to vysvetli
  if (vyzva.spoluucast_pct == null) return null;
  const cena = Math.max(0, Number(vstup.cena_s_dph) || 0);
  const neopr = Math.min(cena, Math.max(0, Number(vstup.neopravnene_s_dph) || 0));
  const sadzba = vstup.sadzba_dph ?? 0.23;
  const p = Number(vyzva.spoluucast_pct) / 100;

  const upozornenia = [];
  let dphOk;
  if (vyzva.dph_opravnena === "ano") dphOk = true;
  else if (vyzva.dph_opravnena === "nie") dphOk = false;
  else {
    dphOk = vstup.dph_je_opravnena === true;
    if (vstup.dph_je_opravnena == null) upozornenia.push("dph_nezadana_pocitame_ako_neopravnenu");
  }

  const opravneneSDph = cena - neopr;
  const cov = dphOk ? opravneneSDph : opravneneSDph / (1 + sadzba);
  const dphNeopravnena = opravneneSDph - cov;

  const nfpTeor = cov * (1 - p);
  const nfp = vyzva.nfp_max != null ? Math.min(nfpTeor, Number(vyzva.nfp_max)) : nfpTeor;
  const nadStropom = nfpTeor - nfp;
  const spoluucast = cov * p;
  const obecNavzdy = cena - nfp;

  if (vyzva.nfp_min != null && nfp < Number(vyzva.nfp_min) && cena > 0) upozornenia.push("pod_minimom_nfp");
  if (nadStropom > 0.5) upozornenia.push("nad_maximom_nfp_doplaca_obec");

  let predfinancovanie;
  switch (vyzva.financovanie) {
    case "refundacia":
      predfinancovanie = { od: nfp, do: nfp, poznamka: "refundacia" };
      upozornenia.push("refundacia_obec_plati_vsetko_vopred");
      break;
    case "predfinancovanie":
    case "zalohova_platba":
      predfinancovanie = { od: 0, do: 0, poznamka: "overte_podmienky_vo_vyzve" };
      break;
    default: // kombinacia
      predfinancovanie = { od: 0, do: nfp, poznamka: "zavisi_od_sposobu_platby" };
  }

  const r = (x) => Math.round(x);
  return {
    cena_s_dph: r(cena),
    cov: r(cov),
    nfp: r(nfp),
    spoluucast: r(spoluucast),
    spoluucast_pct: Number(vyzva.spoluucast_pct),
    neopravnene: r(neopr),
    dph_neopravnena: r(dphNeopravnena),
    nad_stropom_nfp: r(nadStropom),
    obec_zaplati_navzdy: r(obecNavzdy),
    max_vydavok_vopred: vyzva.financovanie === "refundacia" ? r(cena) : null,
    predfinancovanie: { ...predfinancovanie, od: r(predfinancovanie.od), do: r(predfinancovanie.do) },
    odhad: true,                    // UI: vzdy oznacit ako odhad
    upozornenia,
  };
}
