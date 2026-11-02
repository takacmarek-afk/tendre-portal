// =============================================================================
//  Jednorazove doplnenie obce_register z troch CSV (P1 pre kampan 24. 11.)
//
//  Spustenie (Node 22+, bez zavislosti):
//    node --experimental-strip-types skripty/doplnenie-registra-obci.ts \
//         --demografia demografia.csv --nro nro.csv --mrk mrk.csv          # NA SUCHO
//    ... rovnako + --zapis                                                 # ZAPISE
//
//  Premenne prostredia (len pri --zapis aj pri citani registra):
//    SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
//
//  Co robi:
//    1. nacita register (kod, nazov, kraj, okres, ico, typ, ...) z databazy
//    2. sparuje riadky demografia/mrk s obcami registra v poradi:
//         a) ICO (ak ho obec v registri uz ma)
//         b) kod obce SU SR (6 cislic, posledna cast kodu registra SK0101|528595)
//         c) nazov + okres (normalizovane)
//         d) nazov sam, len ak je v celom SR jedinecny
//    3. NRO podla okresu, MRK podla obce
//    4. zapise davkovo (upsert podla kod). Hodnoty, pre ktore nie su data,
//       ostanu povodne (nic sa neprepise na null). Nic sa nemaze.
//    5. vypise statistiku a ulozi nesparovane riadky do doplnenie-nesparovane.csv
//
//  Konflikt ICO (v registri je ine ICO ako v CSV) sa NEPREPISE, len nahlasi.
// =============================================================================

import { readFileSync, writeFileSync, existsSync } from "node:fs";

// --- Typy ---------------------------------------------------------------------
export interface RegisterObec {
  kod: string; nazov: string; kraj: string; okres: string | null;
  ico: string | null; typ: string; pocet_obyvatelov: number | null;
  obyvatelia_k: string | null; nro: boolean | null; mrk: boolean | null;
}
type Riadok = Record<string, string>;
type Sposob = "ico" | "kod_obce" | "nazov_okres" | "nazov";

// --- CSV ----------------------------------------------------------------------
/** Dekoduje subor: UTF-8 (aj s BOM), inak windows-1250 (casty export SU SR). */
export function dekoduj(buf: Uint8Array): string {
  try {
    return new TextDecoder("utf-8", { fatal: true }).decode(buf).replace(/^﻿/, "");
  } catch {
    return new TextDecoder("windows-1250").decode(buf);
  }
}

/** RFC 4180 parser: uvodzovky, "" vo vnutri, nove riadky v poli, oddelovac ; alebo , */
export function parsujCsv(text: string): Riadok[] {
  const prvy = text.split(/\r?\n/, 1)[0] ?? "";
  const odd = (prvy.match(/;/g)?.length ?? 0) > (prvy.match(/,/g)?.length ?? 0) ? ";" : ",";
  const riadky: string[][] = [];
  let pole = "", riadok: string[] = [], vUvodzovkach = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (vUvodzovkach) {
      if (c === '"' && text[i + 1] === '"') { pole += '"'; i++; }
      else if (c === '"') vUvodzovkach = false;
      else pole += c;
    } else if (c === '"') vUvodzovkach = true;
    else if (c === odd) { riadok.push(pole); pole = ""; }
    else if (c === "\n" || c === "\r") {
      if (c === "\r" && text[i + 1] === "\n") i++;
      riadok.push(pole); riadky.push(riadok); riadok = []; pole = "";
    } else pole += c;
  }
  if (pole !== "" || riadok.length) { riadok.push(pole); riadky.push(riadok); }
  const [hlavicka, ...data] = riadky.filter((r) => r.some((x) => x.trim() !== ""));
  if (!hlavicka) return [];
  const kluce = hlavicka.map((h) => h.trim().toLowerCase());
  return data.map((r) => Object.fromEntries(kluce.map((k, i) => [k, (r[i] ?? "").trim()])));
}

function nacitajCsv(cesta: string, povinne: string[]): Riadok[] {
  if (!existsSync(cesta)) throw new Error(`Subor neexistuje: ${cesta}`);
  const riadky = parsujCsv(dekoduj(readFileSync(cesta)));
  if (!riadky.length) throw new Error(`${cesta}: ziadne riadky`);
  const chybaju = povinne.filter((k) => !(k in riadky[0]));
  if (chybaju.length) {
    throw new Error(`${cesta}: chybaju stlpce ${chybaju.join(", ")}. Najdene: ${Object.keys(riadky[0]).join(", ")}`);
  }
  return riadky;
}

// --- Normalizacia ---------------------------------------------------------------
export function normNazov(s: string | null | undefined): string {
  return (s ?? "")
    .normalize("NFD").replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/^(obec|mesto|mestska cast|m\.\s*c\.|mc)\s+/, "")
    .replace(/\s*-\s*/g, "-")          // "Kosice - Stare Mesto" = "Kosice-Stare Mesto"
    .replace(/[.,"']/g, "")
    .replace(/\s+/g, " ")
    .trim();
}
export function normOkres(s: string | null | undefined): string {
  return normNazov((s ?? "").replace(/^\s*okres\s+/i, ""));
}
export function normIco(s: string | null | undefined): string | null {
  const d = (s ?? "").replace(/\D/g, "");
  if (!d || d.length > 8) return null;
  return d.padStart(8, "0");
}
/** Kod obce SU SR: 6 cislic. Prijme "528595" aj "SK0101528595". */
export function normKodObce(s: string | null | undefined): string | null {
  const m = (s ?? "").trim().match(/(\d{6})$/);
  return m ? m[1] : null;
}
export function cislo(s: string | null | undefined): number | null {
  const t = (s ?? "").replace(/[\s ]/g, "").replace(",", ".");
  if (!t) return null;
  const n = Number(t);
  return Number.isFinite(n) ? Math.round(n) : null;
}
export function normTyp(s: string | null | undefined): "obec" | "mesto" | "mestska_cast" | null {
  const t = (s ?? "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/_/g, " ").trim();
  if (!t) return null;
  if (t.startsWith("mest") && t.includes("cast")) return "mestska_cast";
  if (t.startsWith("mesto") || t === "m") return "mesto";
  if (t.startsWith("obec") || t === "o") return "obec";
  return null;
}
function ano(s: string | null | undefined): boolean | null {
  const t = normNazov(s);
  if (["1", "ano", "true", "a", "x"].includes(t)) return true;
  if (["0", "nie", "false", "n", ""].includes(t)) return t === "" ? null : false;
  return null;
}

// --- Parovanie ------------------------------------------------------------------
export class Index {
  poIco = new Map<string, RegisterObec>();
  poKode = new Map<string, RegisterObec>();
  poNazvuOkresu = new Map<string, RegisterObec[]>();
  poNazve = new Map<string, RegisterObec[]>();
  constructor(register: RegisterObec[]) {
    for (const o of register) {
      const ico = normIco(o.ico);
      if (ico) this.poIco.set(ico, o);
      const kod = normKodObce(o.kod);
      if (kod) this.poKode.set(kod, o);
      const n = normNazov(o.nazov);
      const no = `${n}|${normOkres(o.okres)}`;
      this.poNazvuOkresu.set(no, [...(this.poNazvuOkresu.get(no) ?? []), o]);
      this.poNazve.set(n, [...(this.poNazve.get(n) ?? []), o]);
    }
  }
  /** Vrati obec a sposob parovania, alebo dovod nesparovania. */
  najdi(r: Riadok): { obec: RegisterObec; sposob: Sposob } | { dovod: string } {
    const ico = normIco(r.ico);
    if (ico && this.poIco.has(ico)) return { obec: this.poIco.get(ico)!, sposob: "ico" };
    const kod = normKodObce(r.kod_obce);
    if (kod && this.poKode.has(kod)) return { obec: this.poKode.get(kod)!, sposob: "kod_obce" };
    const n = normNazov(r.nazov);
    if (!n) return { dovod: "chyba_nazov" };
    if (r.okres) {
      const k = this.poNazvuOkresu.get(`${n}|${normOkres(r.okres)}`) ?? [];
      if (k.length === 1) return { obec: k[0], sposob: "nazov_okres" };
      if (k.length > 1) return { dovod: "viac_obci_v_okrese" };
    }
    const k = this.poNazve.get(n) ?? [];
    if (k.length === 1) return { obec: k[0], sposob: "nazov" };
    if (k.length > 1) return { dovod: "nazov_nejednoznacny_doplnte_okres" };
    return { dovod: "nenajdena" };
  }
}

// --- Spracovanie (ciste, testovatelne) ----------------------------------------------
export interface Vstupy { demografia?: Riadok[]; nro?: Riadok[]; mrk?: Riadok[] }
export interface Vysledok {
  zmeny: RegisterObec[];
  stat: Record<string, number>;
  nesparovane: { subor: string; riadok: number; nazov: string; okres: string; dovod: string }[];
  konflikty_ico: { kod: string; nazov: string; v_registri: string; v_csv: string }[];
}

export function spracuj(register: RegisterObec[], vstup: Vstupy): Vysledok {
  const idx = new Index(register);
  const nove = new Map(register.map((o) => [o.kod, { ...o }]));
  const stat: Record<string, number> = {};
  const inc = (k: string) => (stat[k] = (stat[k] ?? 0) + 1);
  const nesparovane: Vysledok["nesparovane"] = [];
  const konflikty_ico: Vysledok["konflikty_ico"] = [];
  const pouzite = new Map<string, number>();   // kod -> riadok demografie (duplicity)

  // 1) demografia
  (vstup.demografia ?? []).forEach((r, i) => {
    const h = idx.najdi(r);
    if ("dovod" in h) {
      inc("demografia_nesparovane");
      nesparovane.push({ subor: "demografia", riadok: i + 2, nazov: r.nazov ?? "", okres: r.okres ?? "", dovod: h.dovod });
      return;
    }
    if (pouzite.has(h.obec.kod)) {
      inc("demografia_duplicita");
      nesparovane.push({ subor: "demografia", riadok: i + 2, nazov: r.nazov ?? "", okres: r.okres ?? "",
        dovod: `duplicita_s_riadkom_${pouzite.get(h.obec.kod)}` });
      return;
    }
    pouzite.set(h.obec.kod, i + 2);
    inc(`demografia_par_${h.sposob}`);
    const o = nove.get(h.obec.kod)!;

    const pocet = cislo(r.pocet_obyvatelov);
    if (pocet != null && pocet >= 0) { o.pocet_obyvatelov = pocet; inc("nastaveny_pocet"); }
    else inc("demografia_bez_poctu");
    if (r.k_datumu) o.obyvatelia_k = r.k_datumu;

    const typ = normTyp(r.typ);
    if (typ) o.typ = typ;

    const ico = normIco(r.ico);
    if (ico) {
      const stare = normIco(o.ico);
      if (!stare) { o.ico = ico; inc("doplnene_ico"); }
      else if (stare !== ico) konflikty_ico.push({ kod: o.kod, nazov: o.nazov, v_registri: stare, v_csv: ico });
    }
  });

  // 2) NRO podla okresu (zoznam = cele okresy; ostatne false)
  if (vstup.nro) {
    const okresy = new Set(vstup.nro.map((r) => normOkres(r.okres)).filter(Boolean));
    const znameOkresy = new Set(register.map((o) => normOkres(o.okres)));
    for (const ok of okresy) if (!znameOkresy.has(ok)) {
      inc("nro_nezname_okresy");
      nesparovane.push({ subor: "nro", riadok: 0, nazov: "", okres: ok, dovod: "okres_nie_je_v_registri" });
    }
    for (const o of nove.values()) {
      o.nro = okresy.has(normOkres(o.okres));
      if (o.nro) inc("nro_true");
    }
  }

  // 3) MRK podla obce (v atlase = true; ostatne false). Volitelny stlpec "mrk"
  //    s hodnotou 0/1 umozni explicitne false.
  if (vstup.mrk) {
    const mrkKody = new Set<string>();
    vstup.mrk.forEach((r, i) => {
      const h = idx.najdi(r);
      if ("dovod" in h) {
        inc("mrk_nesparovane");
        nesparovane.push({ subor: "mrk", riadok: i + 2, nazov: r.nazov ?? "", okres: r.okres ?? "", dovod: h.dovod });
        return;
      }
      if (ano(r.mrk) !== false) mrkKody.add(h.obec.kod);
    });
    for (const o of nove.values()) {
      o.mrk = mrkKody.has(o.kod);
      if (o.mrk) inc("mrk_true");
    }
  }

  // Zmeny = len obce, kde sa nieco zmenilo
  const POLIA: (keyof RegisterObec)[] = ["ico", "typ", "pocet_obyvatelov", "obyvatelia_k", "nro", "mrk"];
  const povodne = new Map(register.map((o) => [o.kod, o]));
  const zmeny = [...nove.values()].filter((o) => POLIA.some((p) => o[p] !== povodne.get(o.kod)![p]));
  stat.obci_v_registri = register.length;
  stat.obci_so_zmenou = zmeny.length;
  stat.obci_bez_poctu_po_doplneni = [...nove.values()].filter((o) => o.pocet_obyvatelov == null).length;
  stat.konflikty_ico = konflikty_ico.length;
  return { zmeny, stat, nesparovane, konflikty_ico };
}

// --- Databaza (PostgREST, bez zavislosti) -------------------------------------------
const STLPCE = "kod,nazov,kraj,okres,ico,typ,pocet_obyvatelov,obyvatelia_k,nro,mrk";

async function nacitajRegister(url: string, kluc: string, f = fetch): Promise<RegisterObec[]> {
  const out: RegisterObec[] = [];
  for (let od = 0; ; od += 1000) {
    const res = await f(`${url}/rest/v1/obce_register?select=${STLPCE}&order=kod`, {
      headers: { apikey: kluc, Authorization: `Bearer ${kluc}`, Range: `${od}-${od + 999}` },
    });
    if (!res.ok) throw new Error(`Citanie registra: HTTP ${res.status} ${await res.text()}`);
    const davka = (await res.json()) as RegisterObec[];
    out.push(...davka);
    if (davka.length < 1000) return out;
  }
}

export async function zapis(url: string, kluc: string, zmeny: RegisterObec[], f = fetch): Promise<number> {
  let spolu = 0;
  for (let i = 0; i < zmeny.length; i += 500) {
    // Vsetky objekty maju rovnaku mnozinu klucov (PostgREST to vyzaduje pri davke).
    // nazov a kraj su not null, posielame povodne hodnoty; merge-duplicates
    // prepise len poslane stlpce, ostatne (napr. karta_token) ostanu.
    const davka = zmeny.slice(i, i + 500).map((o) => ({
      kod: o.kod, nazov: o.nazov, kraj: o.kraj, okres: o.okres, ico: o.ico, typ: o.typ,
      pocet_obyvatelov: o.pocet_obyvatelov, obyvatelia_k: o.obyvatelia_k, nro: o.nro, mrk: o.mrk,
    }));
    const res = await f(`${url}/rest/v1/obce_register?on_conflict=kod`, {
      method: "POST",
      headers: {
        apikey: kluc, Authorization: `Bearer ${kluc}`, "Content-Type": "application/json",
        Prefer: "resolution=merge-duplicates,return=minimal",
      },
      body: JSON.stringify(davka),
    });
    if (!res.ok) throw new Error(`Zapis davky ${i / 500 + 1}: HTTP ${res.status} ${await res.text()}`);
    spolu += davka.length;
  }
  return spolu;
}

// --- CLI ----------------------------------------------------------------------------
function argument(meno: string): string | undefined {
  const i = process.argv.indexOf(`--${meno}`);
  return i > 0 ? process.argv[i + 1] : undefined;
}

function csvRiadok(h: unknown[]): string {
  return h.map((x) => `"${String(x ?? "").replace(/"/g, '""')}"`).join(";");
}

async function main() {
  const url = process.env.SUPABASE_URL;
  const kluc = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !kluc) throw new Error("Chyba SUPABASE_URL alebo SUPABASE_SERVICE_ROLE_KEY");
  const zapisovat = process.argv.includes("--zapis");

  const cDemo = argument("demografia"), cNro = argument("nro"), cMrk = argument("mrk");
  if (!cDemo && !cNro && !cMrk) throw new Error("Zadajte aspon jeden zo suborov --demografia, --nro, --mrk");

  const vstup: Vstupy = {};
  if (cDemo) vstup.demografia = nacitajCsv(cDemo, ["nazov", "pocet_obyvatelov"]);
  if (cNro) vstup.nro = nacitajCsv(cNro, ["okres"]);
  if (cMrk) vstup.mrk = nacitajCsv(cMrk, ["nazov"]);

  const register = await nacitajRegister(url, kluc);
  const v = spracuj(register, vstup);

  console.log(`\n=== Doplnenie registra obci (${zapisovat ? "ZAPIS" : "NA SUCHO"}) ===`);
  console.log(`Vstupy: demografia ${vstup.demografia?.length ?? "-"} | nro ${vstup.nro?.length ?? "-"} | mrk ${vstup.mrk?.length ?? "-"} riadkov`);
  for (const [k, n] of Object.entries(v.stat).sort()) console.log(`  ${k.padEnd(34)} ${n}`);

  if (v.konflikty_ico.length) {
    console.log("\nKonflikty ICO (neprepisane, skontrolujte):");
    for (const k of v.konflikty_ico.slice(0, 20)) console.log(`  ${k.kod} ${k.nazov}: register ${k.v_registri}, CSV ${k.v_csv}`);
  }
  if (v.nesparovane.length) {
    const subor = "doplnenie-nesparovane.csv";
    writeFileSync(subor, [csvRiadok(["subor", "riadok", "nazov", "okres", "dovod"]),
      ...v.nesparovane.map((x) => csvRiadok([x.subor, x.riadok, x.nazov, x.okres, x.dovod]))].join("\n"));
    console.log(`\nNesparovane: ${v.nesparovane.length} → ${subor}`);
  }

  // Poistka: ked sa sparuje menej ako 95 % demografie, nezapisovat.
  if (vstup.demografia) {
    const par = Object.entries(v.stat).filter(([k]) => k.startsWith("demografia_par_")).reduce((s, [, n]) => s + n, 0);
    const podiel = par / vstup.demografia.length;
    console.log(`\nSparovane z demografie: ${par}/${vstup.demografia.length} (${(podiel * 100).toFixed(1)} %)`);
    if (zapisovat && podiel < 0.95 && !process.argv.includes("--aj-pod-95")) {
      throw new Error("Sparovane menej ako 95 %, nezapisujem. Skontrolujte nesparovane alebo pridajte --aj-pod-95.");
    }
  }

  if (!zapisovat) { console.log("\nNa sucho, nic sa nezapisalo. Pre zapis pridajte --zapis.\n"); return; }
  const n = await zapis(url, kluc, v.zmeny);
  console.log(`\nZapisane: ${n} obci.\n`);
}

// Spusti len ako CLI (nie pri importe v testoch)
if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch((e) => { console.error(`CHYBA: ${e.message}`); process.exit(1); });
}
