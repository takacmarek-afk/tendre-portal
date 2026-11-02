// =============================================================================
//  Seeder vyziev do vyzvy_karty (P2 pre kampan 24. 11. 2026)
//
//  ZASADA (Marekove pravidlo c. 3): stroj navrhne parametre, clovek ich za
//  20 minut skontroluje. Preto seeder vklada vyzvy NEOVERENE (overil = null).
//  Neoverena vyzva sa nikdy nezobrazi na karte ani neposle e-mailom. Kazda
//  vyzva nesie zoznam "kontrola": co presne treba overit v zneni vyzvy.
//
//  Vsetky vyzvy nizsie su REALNE (zdroj_url) k 2. 11. 2026. Ziadna nie je
//  vymyslena. Udaje, ktore zdroj neuvadza, su prazdne (null) alebo konzervativny
//  predpoklad a su uvedene v "kontrola". Kod "NAVRH-..." = oficialny kod sme
//  nenasli; pri overeni ho prepiste na kod z ITMS21.
//
//  Spustenie:
//    node --experimental-strip-types skripty/seed_vyzvy.ts               # na sucho + kontrolny zoznam
//    node --experimental-strip-types skripty/seed_vyzvy.ts --zapis       # vlozi nove (existujuce necha)
//    ... --zapis --prepisat                                              # prepise aj existujuce (zrusi ich overenie!)
//    ... --over PSK-MZP-044-2026-DV-EFRR --overil "Marek Takáč"          # po rucnej kontrole oznaci ako overenu
// =============================================================================

import { db, vloz, uprav, citaj, F } from "./db.ts";
import type { VyzvaKarta } from "../src/vyzvy/vyber.ts";

type Seed = Omit<VyzvaKarta, "overil" | "overene_at"> & { uznesenie_vlastne_znenie: boolean; kontrola: string[] };

const KRAJE_BEZ_BA = [
  "Trnavský kraj", "Trenčiansky kraj", "Nitriansky kraj", "Žilinský kraj",
  "Banskobystrický kraj", "Prešovský kraj", "Košický kraj",
];
const SAMOSPRAVA: VyzvaKarta["typ_ziadatela"] = ["obec", "mesto", "mestska_cast", "zdruzenie_obci"];
const HMG_2026 = "https://eurofondy.gov.sk/wp-content/uploads/2026/03/Program_Slovensko_harmonogram_planovanych_vyziev_2026_v_2_0.pdf";

// Spolocne predpoklady pre Program Slovensko (kazdy je v "kontrola")
const PS = {
  spoluucast_pct: 5,
  dph_opravnena: "podla_ziadatela" as const,
  financovanie: "kombinacia" as const,
  vyzaduje_phrsr: true,
  vo_pred_ziadostou: false,
  uznesenie_vlastne_znenie: false,
  obyv_min: null, obyv_max: null, nfp_min: null, nfp_max: null,
  okresy: [] as string[],
};
const KONTROLA_PS = [
  "spolufinancovanie obce (predpoklad 5 %)",
  "forma financovania (refundácia / predfinancovanie / zálohová platba)",
  "oprávnenosť DPH",
  "min. a max. výška príspevku, limit obyvateľov",
];

export const VYZVY: Seed[] = [
  {
    ...PS,
    kod: "PSK-MZP-044-2026-DV-EFRR",
    nazov: "Centrá opätovného použitia",
    poskytovatel: "Ministerstvo životného prostredia SR",
    program: "Program Slovensko, 2P2 / RSO2.6",
    zdroj_url: "https://portal.itms21.sk/vyhlasena-vyzva/?id=3816",
    typ_ziadatela: SAMOSPRAVA,
    kraje: KRAJE_BEZ_BA,                       // ITMS21: 8 krajov okrem Bratislavského
    len_nro: false, len_mrk: false,
    vyhlasenie: "2026-09-04", uzavierka: null, kolo_uzavierky: [],
    vyzaduje_ius: false, stupen_pd: "DSP", vyzaduje_povolenie: true,
    aktivity: ["odpad"], signal_sektory: ["ODPAD", "STAVEBNE_PRACE"],
    kontrola: [...KONTROLA_PS, "uzávierky hodnotiacich kôl (dopytová výzva)", "stupeň PD a potreba povolenia stavby"],
  },
  {
    ...PS,
    kod: "NAVRH-KF-VODA-2026",
    nazov: "Výstavba kanalizácie, čistiarní odpadových vôd a vodovodov (Kohézny fond)",
    poskytovatel: "Ministerstvo životného prostredia SR",
    program: "Program Slovensko, Kohézny fond",
    // sekundarny zdroj (agregator); oficialne znenie najst v ITMS21 a URL nahradit
    zdroj_url: "https://napisemprojekt.sk/dotacia-na-vystavbu-kanalizacie-cistiarni-odpadovych-vod-a-vodovodov-kohezny-fond-2026/",
    typ_ziadatela: SAMOSPRAVA,
    kraje: [], len_nro: false, len_mrk: false,
    vyhlasenie: null, uzavierka: "2026-11-29", kolo_uzavierky: ["2026-11-29"],
    vyzaduje_ius: false, stupen_pd: "DSP", vyzaduje_povolenie: true,
    aktivity: ["voda"], signal_sektory: ["KURENIE_VODA_PLYN", "STAVEBNE_PRACE"],
    kontrola: ["OFICIÁLNY KÓD a URL v ITMS21 (zdroj je agregátor)", "uzávierka 29. 11. 2026 a ďalšie kolá",
      "aglomerácie / veľkosť obcí", ...KONTROLA_PS],
  },
  {
    ...PS,
    kod: "NAVRH-PS-4P6-MIESTNE-SLUZBY",
    nazov: "Miestne obecné služby (obce z Atlasu rómskych komunít)",
    poskytovatel: "Úrad splnomocnenca vlády SR pre rómske komunity",
    program: "Program Slovensko, 4P6 / ESO4.10",
    zdroj_url: HMG_2026,
    typ_ziadatela: ["obec", "mesto", "mestska_cast"],
    kraje: [], len_nro: false, len_mrk: true,
    vyhlasenie: null, uzavierka: null, kolo_uzavierky: [],
    vyzaduje_ius: false, stupen_pd: "ziadna", vyzaduje_povolenie: false,
    aktivity: ["socialne"], signal_sektory: [],
    kontrola: ["či a kedy bola vyhlásená (harmonogram: 2Q/2026, otvorená do vyčerpania)", "OFICIÁLNY KÓD a URL",
      "poskytovateľ (predpoklad: ÚSVRK)", ...KONTROLA_PS],
  },
  {
    ...PS,
    kod: "NAVRH-PS-4P9-BYVANIE-MRK",
    nazov: "Dostupné bývanie v obciach z Atlasu rómskych komunít",
    poskytovatel: "Úrad splnomocnenca vlády SR pre rómske komunity",
    program: "Program Slovensko, 4P9 / RSO4.7",
    zdroj_url: HMG_2026,
    typ_ziadatela: ["obec", "mesto", "mestska_cast"],
    kraje: [], len_nro: false, len_mrk: true,
    vyhlasenie: null, uzavierka: null, kolo_uzavierky: [],
    vyzaduje_ius: false, stupen_pd: "DSP", vyzaduje_povolenie: true,
    aktivity: ["byvanie"], signal_sektory: ["STAVEBNE_PRACE"],
    kontrola: ["či a kedy bola vyhlásená (harmonogram: 2Q/2026, otvorená do vyčerpania)", "OFICIÁLNY KÓD a URL",
      "poskytovateľ", ...KONTROLA_PS],
  },
  {
    ...PS,
    kod: "NAVRH-PS-5P2-BYVANIE-IUS",
    nazov: "Zabezpečenie prístupu k cenovo dostupnému a udržateľnému bývaniu (IÚS)",
    poskytovatel: "Ministerstvo investícií, regionálneho rozvoja a informatizácie SR",
    program: "Program Slovensko, 5P2 / RSO5.3, integrované územné investície",
    zdroj_url: HMG_2026,
    typ_ziadatela: ["obec", "mesto", "mestska_cast"],
    kraje: [], len_nro: false, len_mrk: false,
    vyhlasenie: null, uzavierka: null, kolo_uzavierky: [],
    vyzaduje_ius: true, stupen_pd: "DSP", vyzaduje_povolenie: true,
    aktivity: ["byvanie"], signal_sektory: ["STAVEBNE_PRACE"],
    kontrola: ["či a kedy bola vyhlásená (harmonogram: 2Q/2026)", "OFICIÁLNY KÓD a URL",
      "poskytovateľ (predpoklad: MIRRI ako RO pre IÚZ)", "kraje (IÚS jednotlivých krajov)", ...KONTROLA_PS],
  },
  {
    ...PS,
    kod: "NAVRH-PS-2P5-SIEA-BYVANIE",
    nazov: "Podpora prístupu k cenovo dostupnému a udržateľnému bývaniu (SIEA)",
    poskytovatel: "Slovenská inovačná a energetická agentúra",
    program: "Program Slovensko, 2P5 / RSO2.11",
    zdroj_url: HMG_2026,
    typ_ziadatela: ["obec", "mesto", "mestska_cast"],
    kraje: [], len_nro: false, len_mrk: false,
    vyhlasenie: null, uzavierka: null, kolo_uzavierky: [],
    vyzaduje_ius: false, stupen_pd: "DSP", vyzaduje_povolenie: true,
    aktivity: ["byvanie", "energetika"], signal_sektory: ["STAVEBNE_PRACE", "STRECHY_IZOLACIE"],
    kontrola: ["vyhlásenie (harmonogram: 4Q/2026, uzavretie 1Q/2027) a presná uzávierka", "OFICIÁLNY KÓD a URL",
      "oprávnenosť obcí (harmonogram: aj subjekty územnej samosprávy)", ...KONTROLA_PS],
  },
  {
    ...PS,
    kod: "NAVRH-PS-2P4-VODA-IUS",
    nazov: "Podpora bezpečného prístupu k vode a udržateľného vodného hospodárstva (IÚS)",
    poskytovatel: "Ministerstvo investícií, regionálneho rozvoja a informatizácie SR",
    program: "Program Slovensko, 2P4 / RSO2.5, integrované územné investície",
    zdroj_url: HMG_2026,
    typ_ziadatela: SAMOSPRAVA,
    kraje: [], len_nro: false, len_mrk: false,
    vyhlasenie: null, uzavierka: null, kolo_uzavierky: [],
    vyzaduje_ius: true, stupen_pd: "DSP", vyzaduje_povolenie: true,
    aktivity: ["voda"], signal_sektory: ["KURENIE_VODA_PLYN", "STAVEBNE_PRACE"],
    kontrola: ["či a kedy bola vyhlásená (harmonogram: 2Q/2026, uzavretie 4Q/2029)", "OFICIÁLNY KÓD a URL",
      "poskytovateľ a kraje", ...KONTROLA_PS],
  },
  {
    ...PS,
    kod: "NAVRH-PS-2P2-PREDCHADZANIE-ODPADOV",
    nazov: "Podpora vybraných aktivít v oblasti predchádzania vzniku odpadov",
    poskytovatel: "Ministerstvo životného prostredia SR",
    program: "Program Slovensko, 2P2 / RSO2.6",
    zdroj_url: HMG_2026,
    typ_ziadatela: SAMOSPRAVA,
    kraje: KRAJE_BEZ_BA, len_nro: false, len_mrk: false,
    vyhlasenie: null, uzavierka: null, kolo_uzavierky: [],
    vyzaduje_ius: false, stupen_pd: "ziadna", vyzaduje_povolenie: false,
    aktivity: ["odpad"], signal_sektory: ["ODPAD"],
    kontrola: ["či a kedy bola vyhlásená (harmonogram: 2Q/2026, uzavretá dopytová) a uzávierka", "OFICIÁLNY KÓD a URL",
      "kraje (predpoklad: bez Bratislavského)", "stupeň PD (aktivity môžu byť aj stavebné)", ...KONTROLA_PS],
  },
];

// --- Validacia (zrkadlo obmedzeni z migracie 89) -----------------------------
const TYPY = ["obec", "mesto", "mestska_cast", "zdruzenie_obci", "VUC"];
const DATUM = /^\d{4}-\d{2}-\d{2}$/;
export function validuj(v: Seed): string[] {
  const ch: string[] = [];
  if (!v.kod || v.kod.length > 80) ch.push("kod");
  if (!v.nazov || !v.poskytovatel) ch.push("nazov/poskytovatel");
  if (!/^https:\/\//.test(v.zdroj_url)) ch.push("zdroj_url musi byt https");
  if (!v.typ_ziadatela.length || v.typ_ziadatela.some((t) => !TYPY.includes(t))) ch.push("typ_ziadatela");
  if (v.obyv_min != null && v.obyv_max != null && v.obyv_min > v.obyv_max) ch.push("obyv_min > obyv_max");
  if (v.nfp_min != null && v.nfp_max != null && v.nfp_min > v.nfp_max) ch.push("nfp_min > nfp_max");
  if (!(v.spoluucast_pct >= 0 && v.spoluucast_pct <= 100)) ch.push("spoluucast_pct");
  if (!["ano", "nie", "podla_ziadatela"].includes(v.dph_opravnena)) ch.push("dph_opravnena");
  if (!["refundacia", "predfinancovanie", "zalohova_platba", "kombinacia"].includes(v.financovanie)) ch.push("financovanie");
  if (!["ziadna", "studia", "DSP", "DRS"].includes(v.stupen_pd)) ch.push("stupen_pd");
  for (const d of [v.vyhlasenie, v.uzavierka, ...v.kolo_uzavierky]) if (d != null && !DATUM.test(d)) ch.push(`datum ${d}`);
  if (v.uzavierka && v.kolo_uzavierky.length && !v.kolo_uzavierky.includes(v.uzavierka)) ch.push("uzavierka nie je v kolo_uzavierky");
  if (!v.kontrola.length) ch.push("chyba zoznam kontrola");
  return ch;
}

/** Riadok pre databazu: bez "kontrola", vzdy neovereny. */
export function riadok(v: Seed) {
  const { kontrola, ...r } = v;
  return { ...r, overil: null, overene_at: null };
}

// --- CLI ----------------------------------------------------------------------
function arg(meno: string) { const i = process.argv.indexOf(`--${meno}`); return i > 0 ? process.argv[i + 1] : undefined; }

async function main() {
  const zapis = process.argv.includes("--zapis");
  const prepisat = process.argv.includes("--prepisat");
  const overKod = arg("over");

  // 1) Rezim overenia jednej vyzvy (po rucnej kontrole)
  if (overKod) {
    const kto = arg("overil");
    if (!kto) throw new Error('Pri --over zadajte aj --overil "Meno"');
    const d = db();
    const n = await uprav(d, `vyzvy_karty?kod=eq.${encodeURIComponent(overKod)}`, { overil: kto, overene_at: new Date().toISOString() });
    console.log(n ? F.zelena(`✓ ${overKod} je overená (${kto}). Odteraz sa zobrazí na karte a môže ísť do kampane.`) : F.cervena(`Výzvu ${overKod} sme v databáze nenašli.`));
    return;
  }

  // 2) Validacia
  let chyby = 0;
  console.log(F.tucne(`\n=== Seeder výziev (${zapis ? "ZÁPIS" : "NA SUCHO"}) – ${VYZVY.length} výziev ===\n`));
  for (const v of VYZVY) {
    const ch = validuj(v);
    chyby += ch.length;
    console.log(`${ch.length ? F.cervena("✕") : F.zelena("✓")} ${F.tucne(v.kod)}  ${v.nazov}`);
    console.log(F.seda(`   ${v.poskytovatel} · uzávierka ${v.uzavierka ?? "otvorená/neznáma"} · ${v.zdroj_url}`));
    if (ch.length) console.log(F.cervena(`   chyby: ${ch.join(", ")}`));
    console.log(F.zlta(`   Overiť: ${v.kontrola.join(" | ")}`));
  }
  if (chyby) throw new Error(`Validácia našla ${chyby} chýb, nič sa nezapísalo.`);
  if (new Set(VYZVY.map((v) => v.kod)).size !== VYZVY.length) throw new Error("Duplicitný kód výzvy.");

  if (!zapis) {
    console.log(F.seda("\nNa sucho, nič sa nezapísalo. Pre zápis pridajte --zapis."));
    return;
  }

  // 3) Zapis (neoverene). Bez --prepisat sa existujuce vyzvy nemenia.
  const d = db();
  await vloz(d, "vyzvy_karty", VYZVY.map(riadok), "kod", prepisat ? "prepis" : "ignoruj");
  const v_db = await citaj<{ kod: string; overene_at: string | null }>(d, "vyzvy_karty?select=kod,overene_at");
  const nase = v_db.filter((x) => VYZVY.some((v) => v.kod === x.kod));
  console.log(F.zelena(`\n✓ V databáze je ${nase.length}/${VYZVY.length} výziev zo seedera, overených ${nase.filter((x) => x.overene_at).length}.`));
  console.log(`Ďalej: skontrolujte body "Overiť" v znení výzvy, opravte údaje (Supabase › Table editor › vyzvy_karty)`);
  console.log(`a potom: node --experimental-strip-types skripty/seed_vyzvy.ts --over <KOD> --overil "Vaše meno"`);
}

if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch((e) => { console.error(F.cervena(`CHYBA: ${e.message}`)); process.exit(1); });
}
