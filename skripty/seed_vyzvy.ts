// =============================================================================
//  Seeder vyziev do vyzvy_karty (kampan 24. 11. 2026), automaticke overenie
//
//  Kazda vyzva ma stav:
//    "overena"     - Claude ju 3. 11. 2026 overil v ZVEREJNENYCH ZDROJOCH
//                    poskytovatela (zdroje[]): kod, stav (vyhlasena/otvorena),
//                    uzavierky, opravneni ziadatelia, uzemie. Seeder ju zapise
//                    rovno ako overenu (overil = "Claude AI ...").
//    "na_kontrolu" - vyzvu sa NEPODARILO potvrdit (len harmonogram, agregator,
//                    alebo nevieme, ci uz bola vyhlasena). Zapise sa NEOVERENA,
//                    takze nejde na kartu ani do e-mailu. Nic sa nevymysla.
//
//  Udaje, ktore zdroj neuvadza (spoluucast, min/max prispevok, forma platby),
//  su null alebo konzervativne nastavenie, ktore v karte vedie k otazke na obec
//  ("overte vo vyzve"), nikdy nie k tvrdeniu. Zoznam je v "neoverene_udaje".
//
//  Spustenie:
//    node --experimental-strip-types skripty/seed_vyzvy.ts            # na sucho: prehlad
//    node --experimental-strip-types skripty/seed_vyzvy.ts --zapis    # zapise (upsert podla kodu)
//    ... --over <KOD> --overil "Meno"                                 # rucne overenie dalsej vyzvy
// =============================================================================

import { db, vloz, uprav, citaj, F } from "./db.ts";
import type { VyzvaKarta } from "../src/vyzvy/vyber.ts";

export type Seed = Omit<VyzvaKarta, "overil" | "overene_at"> & {
  uznesenie_vlastne_znenie: boolean;
  stav: "overena" | "na_kontrolu";
  zdroje: string[];             // kde sme to overili (ITMS21, poskytovatel)
  neoverene_udaje: string[];    // co zdroj neuvadza; obec overi vo vyzve
};

export const OVERENE_K = "2026-11-03";
export const OVERIL = `Claude AI (automaticky z verejných zdrojov ${OVERENE_K})`;

const KRAJE_BEZ_BA = [
  "Trnavský kraj", "Trenčiansky kraj", "Nitriansky kraj", "Žilinský kraj",
  "Banskobystrický kraj", "Prešovský kraj", "Košický kraj",
];
const SAMOSPRAVA: VyzvaKarta["typ_ziadatela"] = ["obec", "mesto", "mestska_cast", "zdruzenie_obci"];
const HMG_V3 = "https://eurofondy.gov.sk/wp-content/uploads/2026/07/Program_Slovensko_harmonogram_planovanych_vyziev_2026_verzia_3_0.pdf";
const SIEA = "https://www.siea.sk/strukturalne-fondy-eu/program-slovensko/vyzvy-implementovane-siea/";

// Konzervativne predvolby: neznamy udaj = null alebo nastavenie, pri ktorom
// sa karta obce SPYTA (PD, povolenie, PHRSR), namiesto toho, aby nieco tvrdila.
const ZAKLAD = {
  spoluucast_pct: null,
  dph_opravnena: "podla_ziadatela" as const,
  financovanie: "kombinacia" as const,
  vyzaduje_phrsr: true,
  vo_pred_ziadostou: false,
  uznesenie_vlastne_znenie: false,
  obyv_min: null, obyv_max: null, nfp_min: null, nfp_max: null,
  kraje: [] as string[], okresy: [] as string[],
  len_nro: false, len_mrk: false,
  vyzaduje_ius: false,
  stupen_pd: "DSP" as const, vyzaduje_povolenie: true,
};
const NEZNAME = ["miera spolufinancovania", "min. a max. výška príspevku", "forma financovania", "oprávnenosť DPH", "požadovaný stupeň PD"];

export const VYZVY: Seed[] = [
  // ── OVERENE ────────────────────────────────────────────────────────────────
  {
    ...ZAKLAD,
    stav: "overena",
    kod: "PSK-SIEA-007-2024-ITI-EFRR",
    nazov: "Energetická efektívnosť a využívanie OZE vo verejných budovách (IÚI)",
    poskytovatel: "Slovenská inovačná a energetická agentúra",
    program: "Program Slovensko, integrované územné investície",
    zdroj_url: "https://portal.itms21.sk/vyhlasena-vyzva/?id=3633",
    zdroje: [SIEA, "https://portal.itms21.sk/vyhlasena-vyzva/?id=3633"],
    // SIEA: obce, mesta, VUC a ich rozpoctove a prispevkove organizacie; projekt musi byt
    // v schvalenom projektovom zamere IUI a ziadatel zhodny so ziadatelom v nom.
    typ_ziadatela: ["obec", "mesto", "mestska_cast", "VUC"],
    vyhlasenie: "2025-01-13", uzavierka: null, kolo_uzavierky: [],   // otvorena vyzva
    vyzaduje_ius: true,
    aktivity: ["energetika"],
    signal_sektory: ["STRECHY_IZOLACIE", "OKNA_DVERE_POVRCHY", "KURENIE_VODA_PLYN", "ELEKTROINSTALACIE"],
    neoverene_udaje: [...NEZNAME, "hodnotiace kolá (otvorená výzva)"],
  },
  {
    ...ZAKLAD,
    stav: "overena",
    kod: "PSK-SIEA-006-2024-DV-FST",
    nazov: "Energetická efektívnosť verejných budov regiónu Hornej Nitry",
    poskytovatel: "Slovenská inovačná a energetická agentúra",
    program: "Program Slovensko, Fond na spravodlivú transformáciu",
    zdroj_url: "https://portal.itms21.sk/vyhlasena-vyzva/?id=3531",
    zdroje: [SIEA, "https://portal.itms21.sk/vyhlasena-vyzva/?id=3531"],
    typ_ziadatela: ["obec", "mesto", "VUC"],
    okresy: ["Okres Prievidza", "Okres Partizánske"],                  // SIEA: len tieto okresy
    vyhlasenie: "2024-10-14", uzavierka: null, kolo_uzavierky: [],
    aktivity: ["energetika"],
    signal_sektory: ["STRECHY_IZOLACIE", "OKNA_DVERE_POVRCHY", "KURENIE_VODA_PLYN", "ELEKTROINSTALACIE"],
    neoverene_udaje: [...NEZNAME, "hodnotiace kolá (otvorená výzva)"],
  },
  {
    ...ZAKLAD,
    stav: "overena",
    kod: "PSK-UV-015-2026-DV-EFRR",
    nazov: "Dostupné bývanie v obciach z Atlasu rómskych komunít",
    poskytovatel: "Úrad vlády SR",
    program: "Program Slovensko, 4P9 / RSO4.7",
    zdroj_url: "https://portal.itms21.sk/vyhlasena-vyzva/?id=3794",
    zdroje: ["https://romovia.vlada.gov.sk/sekcia-europskych-programov/programove-obdobie-2021-2027/aktuality/vyhlasenie-vyzvy-s-nazvom-dostupne-byvanie-v-obciach-z-atlasu-romskych-komunit/"],
    typ_ziadatela: ["obec", "mesto"],
    kraje: KRAJE_BEZ_BA, len_mrk: true,
    // 1. kolo 4. 9. 2026, 2. kolo 30. 11. 2026 (vyhlasenie UV SR). Na kampan 24. 11.
    // je to menej ako 30 dni, takze filter ju do e-mailu nezaradi; karta funguje.
    vyhlasenie: "2026-07-13", uzavierka: "2026-11-30", kolo_uzavierky: ["2026-09-04", "2026-11-30"],
    aktivity: ["byvanie"], signal_sektory: ["STAVEBNE_PRACE"],
    neoverene_udaje: [...NEZNAME, "ďalšie kolá po 30. 11. 2026"],
  },

  // ── NA KONTROLU (do e-mailov nejdu) ───────────────────────────────────────
  {
    ...ZAKLAD,
    stav: "na_kontrolu",
    kod: "PSK-MZP-044-2026-DV-EFRR",
    nazov: "Centrá opätovného použitia",
    poskytovatel: "Ministerstvo životného prostredia SR",
    program: "Program Slovensko, 2P2 / RSO2.6",
    zdroj_url: "https://portal.itms21.sk/vyhlasena-vyzva/?id=3816",
    zdroje: ["https://www.minzp.sk/program-slovensko/vyzvy.html"],
    typ_ziadatela: SAMOSPRAVA, kraje: KRAJE_BEZ_BA,
    vyhlasenie: "2026-09-04", uzavierka: null, kolo_uzavierky: [],
    aktivity: ["odpad"], signal_sektory: ["ODPAD", "STAVEBNE_PRACE"],
    neoverene_udaje: ["či je ešte otvorená a termíny kôl (ITMS21 sme nevedeli načítať)", "oprávnení žiadatelia", ...NEZNAME],
  },
  {
    ...ZAKLAD,
    stav: "na_kontrolu",
    kod: "NAVRH-MZP-KF-VODA-2026",
    nazov: "Výstavba kanalizácie, čistiarní odpadových vôd a vodovodov (Kohézny fond)",
    poskytovatel: "Ministerstvo životného prostredia SR",
    program: "Program Slovensko, Kohézny fond",
    zdroj_url: "https://napisemprojekt.sk/dotacia-na-vystavbu-kanalizacie-cistiarni-odpadovych-vod-a-vodovodov-kohezny-fond-2026/",
    zdroje: ["agregátor, oficiálny zdroj sme nenašli"],
    typ_ziadatela: SAMOSPRAVA,
    vyhlasenie: null, uzavierka: "2026-11-29", kolo_uzavierky: ["2026-11-29"],
    aktivity: ["voda"], signal_sektory: ["KURENIE_VODA_PLYN", "STAVEBNE_PRACE"],
    neoverene_udaje: ["oficiálny kód a znenie", "uzávierka (podľa agregátora 29. 11. 2026)", ...NEZNAME],
  },
  {
    ...ZAKLAD,
    stav: "na_kontrolu",
    kod: "NAVRH-MIRRI-KOMUNIKACIE-DO-1000",
    nazov: "Výstavba a modernizácia miestnych komunikácií v obciach do 1 000 obyvateľov",
    poskytovatel: "Ministerstvo investícií, regionálneho rozvoja a informatizácie SR",
    program: "Program Slovensko, 3P1 / RSO3.2",
    zdroj_url: HMG_V3, zdroje: [HMG_V3],
    typ_ziadatela: ["obec"], obyv_max: 1000,
    vyhlasenie: null, uzavierka: null, kolo_uzavierky: [],
    aktivity: ["cesty"], signal_sektory: ["STAVEBNE_PRACE", "DOPRAVA_MECHANIZACIA"],
    neoverene_udaje: ["či bola vyhlásená (harmonogram: 3Q/2026, dopytová)", "oficiálny kód", ...NEZNAME],
  },
  {
    ...ZAKLAD,
    stav: "na_kontrolu",
    kod: "NAVRH-MDSR-5P2-NAJOMNE-BYVANIE",
    nazov: "Zabezpečenie prístupu k cenovo dostupnému bývaniu: nájomné sociálne bývanie (IÚS)",
    poskytovatel: "Ministerstvo dopravy SR",
    program: "Program Slovensko, 5P2 / RSO5.3, integrované územné investície",
    zdroj_url: HMG_V3, zdroje: [HMG_V3],
    typ_ziadatela: ["obec", "mesto", "mestska_cast"],
    vyhlasenie: null, uzavierka: null, kolo_uzavierky: [],
    vyzaduje_ius: true,
    aktivity: ["byvanie"], signal_sektory: ["STAVEBNE_PRACE"],
    neoverene_udaje: ["či bola vyhlásená (harmonogram: 4Q/2026)", "oficiálny kód", ...NEZNAME],
  },
  {
    ...ZAKLAD,
    stav: "na_kontrolu",
    kod: "NAVRH-MIRRI-2P4-VODA-IUS",
    nazov: "Podpora bezpečného prístupu k vode a udržateľného vodného hospodárstva (IÚS)",
    poskytovatel: "Ministerstvo investícií, regionálneho rozvoja a informatizácie SR",
    program: "Program Slovensko, 2P4 / RSO2.5, integrované územné investície",
    zdroj_url: HMG_V3, zdroje: [HMG_V3],
    typ_ziadatela: SAMOSPRAVA,
    vyhlasenie: null, uzavierka: null, kolo_uzavierky: [],
    vyzaduje_ius: true,
    aktivity: ["voda"], signal_sektory: ["KURENIE_VODA_PLYN", "STAVEBNE_PRACE"],
    neoverene_udaje: ["či bola vyhlásená (harmonogram: 3Q/2026, uzavretie 4Q/2029)", "oficiálny kód", ...NEZNAME],
  },
  {
    ...ZAKLAD,
    stav: "na_kontrolu",
    kod: "NAVRH-MZP-2P2-PREDCHADZANIE-ODPADOV",
    nazov: "Podpora vybraných aktivít v oblasti predchádzania vzniku odpadov",
    poskytovatel: "Ministerstvo životného prostredia SR",
    program: "Program Slovensko, 2P2 / RSO2.6",
    zdroj_url: "https://eurofondy.gov.sk/wp-content/uploads/2026/03/Program_Slovensko_harmonogram_planovanych_vyziev_2026_v_2_0.pdf",
    zdroje: ["harmonogram 2026 v2.0"],
    typ_ziadatela: SAMOSPRAVA, kraje: KRAJE_BEZ_BA,
    vyhlasenie: null, uzavierka: null, kolo_uzavierky: [],
    stupen_pd: "ziadna", vyzaduje_povolenie: false,
    aktivity: ["odpad"], signal_sektory: ["ODPAD"],
    neoverene_udaje: ["či bola vyhlásená a uzávierka (harmonogram: 2Q/2026, uzavretá)", "oficiálny kód", ...NEZNAME],
  },
];

// --- Validacia (zrkadlo obmedzeni z migracii 89 a 91) ---------------------------
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
  if (v.spoluucast_pct != null && !(v.spoluucast_pct >= 0 && v.spoluucast_pct <= 100)) ch.push("spoluucast_pct");
  if (!["ano", "nie", "podla_ziadatela"].includes(v.dph_opravnena)) ch.push("dph_opravnena");
  if (!["refundacia", "predfinancovanie", "zalohova_platba", "kombinacia"].includes(v.financovanie)) ch.push("financovanie");
  if (!["ziadna", "studia", "DSP", "DRS"].includes(v.stupen_pd)) ch.push("stupen_pd");
  for (const d of [v.vyhlasenie, v.uzavierka, ...v.kolo_uzavierky]) if (d != null && !DATUM.test(d)) ch.push(`datum ${d}`);
  if (v.uzavierka && v.kolo_uzavierky.length && !v.kolo_uzavierky.includes(v.uzavierka)) ch.push("uzavierka nie je v kolo_uzavierky");
  if (v.stav === "overena" && (v.kod.startsWith("NAVRH-") || !v.zdroje.some((z) => /^https:\/\//.test(z)))) ch.push("overena vyzva musi mat oficialny kod a zdroj");
  return ch;
}

/** Riadok pre databazu. Overene dostanu overil + cas, ostatne null. */
export function riadok(v: Seed, teraz = new Date()) {
  const { stav, zdroje, neoverene_udaje, ...r } = v;
  return stav === "overena"
    ? { ...r, overil: OVERIL, overene_at: teraz.toISOString() }
    : { ...r, overil: null, overene_at: null };
}

// --- CLI ----------------------------------------------------------------------
function arg(meno: string) { const i = process.argv.indexOf(`--${meno}`); return i > 0 ? process.argv[i + 1] : undefined; }

async function main() {
  const zapis = process.argv.includes("--zapis");
  const overKod = arg("over");

  if (overKod) {
    const kto = arg("overil");
    if (!kto) throw new Error('Pri --over zadajte aj --overil "Meno"');
    const n = await uprav(db(), `vyzvy_karty?kod=eq.${encodeURIComponent(overKod)}`, { overil: kto, overene_at: new Date().toISOString() });
    console.log(n ? F.zelena(`✓ ${overKod} je overená (${kto}).`) : F.cervena(`Výzvu ${overKod} sme v databáze nenašli.`));
    return;
  }

  let chyby = 0;
  const ov = VYZVY.filter((v) => v.stav === "overena").length;
  console.log(F.tucne(`\n=== Seeder výziev (${zapis ? "ZÁPIS" : "NA SUCHO"}): ${ov} overených, ${VYZVY.length - ov} na kontrolu ===\n`));
  for (const v of VYZVY) {
    const ch = validuj(v);
    chyby += ch.length;
    const znak = ch.length ? F.cervena("✕") : v.stav === "overena" ? F.zelena("✓ overená   ") : F.zlta("· na kontrolu");
    console.log(`${znak} ${F.tucne(v.kod)}  ${v.nazov}`);
    console.log(F.seda(`   uzávierka ${v.uzavierka ?? "otvorená / neuvedená"} · ${v.zdroj_url}`));
    if (ch.length) console.log(F.cervena(`   chyby: ${ch.join(", ")}`));
    console.log(F.seda(`   Obec overí vo výzve: ${v.neoverene_udaje.join(" | ")}`));
  }
  if (chyby) throw new Error(`Validácia našla ${chyby} chýb, nič sa nezapísalo.`);
  if (new Set(VYZVY.map((v) => v.kod)).size !== VYZVY.length) throw new Error("Duplicitný kód výzvy.");
  if (!zapis) { console.log(F.seda("\nNa sucho, nič sa nezapísalo. Pre zápis pridajte --zapis.")); return; }

  const d = db();
  // upsert: aktualne udaje zo seedera maju prednost (obsahuju aj overenie)
  await vloz(d, "vyzvy_karty", VYZVY.map((v) => riadok(v)), "kod", "prepis");
  const v_db = await citaj<{ kod: string; overene_at: string | null }>(d, "vyzvy_karty?select=kod,overene_at");
  const nase = v_db.filter((x) => VYZVY.some((v) => v.kod === x.kod));
  console.log(F.zelena(`\n✓ Zapísané ${nase.length}/${VYZVY.length} výziev, overených ${nase.filter((x) => x.overene_at).length}.`));
}

if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch((e) => { console.error(F.cervena(`CHYBA: ${e.message}`)); process.exit(1); });
}
