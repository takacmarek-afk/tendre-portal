// =============================================================================
//  Quick Win A: vyber max. 3 vyziev pre mesacny e-mail obci
//
//  Ciste funkcie bez I/O. Bezi v Deno (Edge Function) aj v Node 22+
//  (node --experimental-strip-types). Vstupy:
//    - obec:  riadok z RPC vyzvy_signaly_obci() (migracia 89)
//    - vyzvy: riadky z vyzvy_karty (service_role select *)
//
//  Kroky podla specifikacie:
//    1. tvrdy filter (jedno NIE = vyzva vypadne)
//    2. bodovanie (body, nie percenta)
//    3. max 3 vyzvy, max 2 od jedneho poskytovatela
//    4. pravidlo ticha: 0 vyziev = obci tento mesiac nepiseme
//  Kazda vybrana vyzva nesie dovod[] (co sme overili, ide do e-mailu s ✓)
//  a neoverene[] (co musi overit obec, ide do e-mailu s ?).
// =============================================================================

export type TypZiadatela = "obec" | "mesto" | "mestska_cast" | "zdruzenie_obci" | "VUC";
export type Financovanie = "refundacia" | "predfinancovanie" | "zalohova_platba" | "kombinacia";
export type StupenPD = "ziadna" | "studia" | "DSP" | "DRS";

export interface VyzvaKarta {
  kod: string;
  nazov: string;
  poskytovatel: string;
  zdroj_url: string;
  program?: string | null;
  typ_ziadatela: TypZiadatela[];
  kraje: string[];
  okresy: string[];
  len_nro: boolean;
  len_mrk: boolean;
  obyv_min: number | null;
  obyv_max: number | null;
  nfp_min: number | null;
  nfp_max: number | null;
  spoluucast_pct: number | null;   // null = vyzva/zdroj ju neuvadza (migracia 91)
  dph_opravnena: "ano" | "nie" | "podla_ziadatela";
  financovanie: Financovanie;
  vyhlasenie: string | null;      // ISO datum
  uzavierka: string | null;       // ISO datum, null = otvorena
  kolo_uzavierky: string[];
  vyzaduje_ius: boolean;
  vyzaduje_phrsr: boolean;
  stupen_pd: StupenPD;
  vyzaduje_povolenie: boolean;
  vo_pred_ziadostou: boolean;
  aktivity: string[];
  signal_sektory: string[];
  overil: string | null;
  overene_at: string | null;
}

export interface ObecSignaly {
  kod: string;
  ico: string | null;
  nazov: string;
  typ: "obec" | "mesto" | "mestska_cast";
  kraj: string;
  okres: string | null;
  pocet_obyvatelov: number | null;
  nro: boolean | null;
  mrk: boolean | null;
  konciace: { sektor: string | null; koniec: string }[];
  dotacie_3r: { ucel: string | null; sektor: string | null; podpisane: string | null }[];
  dotiahnute: boolean;
}

export interface VybranaVyzva {
  kod: string;
  nazov: string;
  poskytovatel: string;
  skore: number;
  surne: boolean;
  dni_do_uzavierky: number | null;   // null = otvorena
  dovod: string[];
  neoverene: string[];
}

export interface VysledokVyberu {
  kod_obce: string;
  posielat: boolean;                  // false = pravidlo ticha
  vyzvy: VybranaVyzva[];
  vyradene?: { kod: string; dovod: string }[];   // len s ladenim, na kontrolu
}

// --- Konfiguracia (jedno miesto na ladenie) ----------------------------------
export const PRAVIDLA = {
  MIN_DNI: 30,              // kratsia uzavierka sa neposiela
  SURNE_DO: 45,             // 30-44 dni = stitok "surne", 0 bodov
  OPTIMUM_OD: 45,
  OPTIMUM_DO: 120,          // 45-120 dni = +2
  MAX_VYZIEV: 3,
  MAX_NA_POSKYTOVATELA: 2,
  BODY_KONCIACA_ZMLUVA: 3,
  BODY_BEZ_DOTACIE_NA_AKTIVITU: 2,
  BODY_DOTIAHNUTY_PROJEKT: 1,
  BODY_OPTIMALNA_UZAVIERKA: 2,
  BODY_IUS: -1,
} as const;

// Klasifikacia ucelu dotacie do tagov aktivit (pre +2 "nemala dotaciu na
// rovnaku aktivitu"). Tagy musia sediet s vyzvy_karty.aktivity.
// Zamerne konzervativne: co nesedi na ziadny vzor, sa za aktivitu nepovazuje.
// Skratky (MŠ, ZŠ, KD, ČOV) cez lookaround s \p{L}: \b v JS nepozna diakritiku.
const SKR = (s: string) => `(?<!\\p{L})${s}(?!\\p{L})`;
export const AKTIVITA_VZORY: Record<string, RegExp> = {
  odpad:      new RegExp(`odpad|zbern[ýy] dvor|kompost|opätovného použitia`, "iu"),
  MS:         new RegExp(`matersk|škôlk|${SKR("MŠ")}`, "iu"),
  ZS:         new RegExp(`základn(á|ej|ú|ou) škol|${SKR("ZŠ")}`, "iu"),
  kultura:    new RegExp(`kultúr|knižnic|pamätn|${SKR("KD")}`, "iu"),
  cesty:      new RegExp(`miestn(a|ej|ych|e|u) komunik|chodník|${SKR("cest[ay]?")}|parkovisk|${SKR("most(a|y|u)?")}`, "iu"),
  voda:       new RegExp(`vodovod|kanaliz|čistiar|vodn(ý|é|ého) zdroj|retenč|dažďov|${SKR("ČOV")}`, "iu"),
  energetika: new RegExp(`zatepl|energetick|fotovolt|tepeln(é|ého) čerp|osvetlen|obnoviteľn`, "iu"),
  byvanie:    new RegExp(`nájomn(é|ých|ého) byt|bytov(ý|ého|é) dom|bývani|sociáln(e|ych) byt`, "iu"),
  socialne:   new RegExp(`sociáln(a|ej|u|e) služ|komunitn|terénn(a|ej|u) sociáln|opatrovateľ`, "iu"),
};

// --- Pomocne ------------------------------------------------------------------
const DEN_MS = 86_400_000;

/** Porovnanie nazvov bez diakritiky, velkosti a predpon "Okres", "kraj". */
export function norm(s: string | null | undefined): string {
  return (s ?? "")
    .normalize("NFD").replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/^okres\s+/, "")
    .replace(/\s+kraj$/, "")
    .replace(/\s+/g, " ")
    .trim();
}

/** Cele dni medzi dvoma datumami (UTC polnoc), b - a. */
export function dniMedzi(a: Date, b: Date): number {
  const ua = Date.UTC(a.getUTCFullYear(), a.getUTCMonth(), a.getUTCDate());
  const ub = Date.UTC(b.getUTCFullYear(), b.getUTCMonth(), b.getUTCDate());
  return Math.round((ub - ua) / DEN_MS);
}

function mesiacRok(iso: string): string {
  const d = new Date(iso);
  return `${d.getUTCMonth() + 1}/${d.getUTCFullYear()}`;
}

const NAZOV_TYPU: Record<string, string> = {
  obec: "obce", mesto: "mestá", mestska_cast: "mestské časti",
};

const NAZOV_PD: Record<StupenPD, string> = {
  ziadna: "", studia: "štúdia", DSP: "dokumentácia pre povolenie stavby", DRS: "realizačná dokumentácia",
};

/** Co obec musi overit sama (ide do e-mailu a karty ako "?"). */
export function neoverene(v: VyzvaKarta): string[] {
  const out = ["aktivity projektu podľa výzvy", "vlastníctvo pozemku alebo budovy"];
  if (v.vyzaduje_phrsr) out.push("súlad s programom rozvoja obce (PHRSR)");
  if (v.vyzaduje_ius) out.push("zaradenie projektu v IÚS kraja");
  if (v.stupen_pd !== "ziadna") out.push(`projektová dokumentácia (${NAZOV_PD[v.stupen_pd]})`);
  if (v.vyzaduje_povolenie) out.push("povolenie stavby");
  if (v.vo_pred_ziadostou) out.push("ukončené verejné obstarávanie pred podaním");
  return out;
}

// --- Krok 1: tvrdy filter -----------------------------------------------------
/** Vrati null, ak vyzva prejde; inak dovod vyradenia (na ladenie). */
export function tvrdyFilter(obec: ObecSignaly, v: VyzvaKarta, odoslanie: Date): string | null {
  if (!v.overene_at || !v.overil) return "neoverena";

  if (!v.typ_ziadatela.includes(obec.typ)) return "typ_ziadatela";

  // Uzemie: prazdne kraje aj okresy = cele SR. Inak musi sediet kraj alebo okres.
  if (v.kraje.length || v.okresy.length) {
    const krajOk = v.kraje.some((k) => norm(k) === norm(obec.kraj));
    const okresOk = v.okresy.some((o) => norm(o) === norm(obec.okres));
    if (!krajOk && !okresOk) return "uzemie";
  }
  // NRO/MRK: neznama hodnota (null) = nesplna. Radsej nepisat, ako napisat zle.
  if (v.len_nro && obec.nro !== true) return "nro";
  if (v.len_mrk && obec.mrk !== true) return "mrk";

  // Velkost: bez poctu obyvatelov neprejde ziadna vyzva s limitom.
  if (v.obyv_min != null || v.obyv_max != null) {
    if (obec.pocet_obyvatelov == null) return "pocet_obyvatelov_neznamy";
    if (v.obyv_min != null && obec.pocet_obyvatelov < v.obyv_min) return "velkost";
    if (v.obyv_max != null && obec.pocet_obyvatelov > v.obyv_max) return "velkost";
  }

  if (v.uzavierka) {
    const dni = dniMedzi(odoslanie, new Date(v.uzavierka));
    if (dni < PRAVIDLA.MIN_DNI) return "uzavierka_blizko";
  }
  return null;
}

/** Dovody tvrdeho filtra, ktore sme overili (✓ v e-maile). */
function dovodyFiltra(obec: ObecSignaly, v: VyzvaKarta): string[] {
  const d: string[] = [];
  d.push(`výzva je pre ${NAZOV_TYPU[obec.typ] ?? obec.typ}`);
  if (v.kraje.length || v.okresy.length) {
    d.push(`územie: ${obec.okres ?? obec.kraj}${v.len_nro ? " (najmenej rozvinutý okres)" : ""}`);
  } else if (v.len_nro) {
    d.push(`najmenej rozvinutý okres: ${obec.okres}`);
  }
  if (v.len_mrk) d.push("obec je v Atlase rómskych komunít");
  if (v.obyv_min != null || v.obyv_max != null) {
    const rozsah = `${v.obyv_min ?? 0}–${v.obyv_max ?? "∞"}`;
    d.push(`veľkosť: ${obec.pocet_obyvatelov} obyvateľov (výzva ${rozsah})`);
  }
  return d;
}

// --- Krok 2: bodovanie --------------------------------------------------------
export function ohodnot(
  obec: ObecSignaly, v: VyzvaKarta, odoslanie: Date,
): { skore: number; surne: boolean; dni: number | null; dovod: string[] } {
  let skore = 0;
  let surne = false;
  const dovod = dovodyFiltra(obec, v);

  // +3 koniaca zmluva v sektore vyzvy (najblizsia)
  const sektory = new Set(v.signal_sektory);
  const konci = obec.konciace.find((z) => z.sektor && sektory.has(z.sektor));
  if (konci) {
    skore += PRAVIDLA.BODY_KONCIACA_ZMLUVA;
    dovod.push(`zmluva v tejto oblasti vám končí ${mesiacRok(konci.koniec)}`);
  }

  // +2 za 3 roky ziadna dotacia na rovnaku aktivitu
  if (v.aktivity.length) {
    const mala = obec.dotacie_3r.some((dt) =>
      v.aktivity.some((a) => AKTIVITA_VZORY[a]?.test(dt.ucel ?? "")),
    );
    if (!mala) {
      skore += PRAVIDLA.BODY_BEZ_DOTACIE_NA_AKTIVITU;
      dovod.push("za posledné 3 roky ste na túto oblasť dotáciu nedostali");
    }
  }

  // +1 obec projekt uz dotiahla
  if (obec.dotiahnute) {
    skore += PRAVIDLA.BODY_DOTIAHNUTY_PROJEKT;
    dovod.push("obec už dotovaný projekt dotiahla");
  }

  // Uzavierka: +2 v optime, 0 a "surne" pri 30-44 dnoch, otvorena = 0
  let dni: number | null = null;
  if (v.uzavierka) {
    dni = dniMedzi(odoslanie, new Date(v.uzavierka));
    if (dni >= PRAVIDLA.OPTIMUM_OD && dni <= PRAVIDLA.OPTIMUM_DO) {
      skore += PRAVIDLA.BODY_OPTIMALNA_UZAVIERKA;
    } else if (dni < PRAVIDLA.SURNE_DO) {
      surne = true;
    }
  }

  // -1 vyzaduje IUS (nevyradujeme)
  if (v.vyzaduje_ius) skore += PRAVIDLA.BODY_IUS;

  return { skore, surne, dni, dovod };
}

// --- Krok 3 + 4: vyber a pravidlo ticha ---------------------------------------
export function vyberVyzievPreObec(
  obec: ObecSignaly,
  vyzvy: VyzvaKarta[],
  odoslanie: Date = new Date(),
  ladenie = false,
): VysledokVyberu {
  const vyradene: { kod: string; dovod: string }[] = [];
  const kandidati: (VybranaVyzva & { _nfp: number })[] = [];

  for (const v of vyzvy) {
    const dovodVyradenia = tvrdyFilter(obec, v, odoslanie);
    if (dovodVyradenia) {
      vyradene.push({ kod: v.kod, dovod: dovodVyradenia });
      continue;
    }
    const h = ohodnot(obec, v, odoslanie);
    kandidati.push({
      kod: v.kod, nazov: v.nazov, poskytovatel: v.poskytovatel,
      skore: h.skore, surne: h.surne, dni_do_uzavierky: h.dni,
      dovod: h.dovod, neoverene: neoverene(v), _nfp: v.nfp_max ?? 0,
    });
  }

  // Poradie: skore ↓, potom skorsia uzavierka (otvorene na koniec), potom vacsia dotacia, potom kod (stabilita)
  kandidati.sort((a, b) =>
    b.skore - a.skore ||
    (a.dni_do_uzavierky ?? Infinity) - (b.dni_do_uzavierky ?? Infinity) ||
    b._nfp - a._nfp ||
    a.kod.localeCompare(b.kod),
  );

  const vybrane: VybranaVyzva[] = [];
  const naPoskytovatela = new Map<string, number>();
  for (const k of kandidati) {
    if (vybrane.length >= PRAVIDLA.MAX_VYZIEV) break;
    const p = norm(k.poskytovatel);
    const n = naPoskytovatela.get(p) ?? 0;
    if (n >= PRAVIDLA.MAX_NA_POSKYTOVATELA) continue;
    naPoskytovatela.set(p, n + 1);
    const { _nfp, ...vyzva } = k;
    vybrane.push(vyzva);
  }

  const vysledok: VysledokVyberu = {
    kod_obce: obec.kod,
    posielat: vybrane.length > 0,   // pravidlo ticha
    vyzvy: vybrane,
  };
  if (ladenie) vysledok.vyradene = vyradene;
  return vysledok;
}

/** Riadky do tabulky vyzvy_vyber (log kampane). mesiac = 1. den mesiaca. */
export function riadkyLogu(v: VysledokVyberu, mesiac: string) {
  return v.vyzvy.map((x, i) => ({
    mesiac, kod_obce: v.kod_obce, poradie: i + 1, vyzva_kod: x.kod,
    skore: x.skore, surne: x.surne, dovod: x.dovod, neoverene: x.neoverene,
  }));
}
