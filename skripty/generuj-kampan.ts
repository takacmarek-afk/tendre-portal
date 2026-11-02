// =============================================================================
//  Generator pilotnej kampane "Vyzvy pre vasu obec" (Quick Win A)
//
//  1. nacita overene vyzvy, signaly obci, tokeny kariet a kontakty uradov
//  2. kazdu obec s pouzitelnym kontaktom prezenie vyberVyzievPreObec()
//     (pravidlo ticha: obec bez vyzvy vypadne)
//  3. vyberie 50 obci ako reprezentativnu vzorku (kraj x velkost, round-robin,
//     deterministicky podla --seed)
//  4. vygeneruje predmet (A/B podla ICO) a text e-mailu
//
//  Rezimy:
//    node --experimental-strip-types skripty/generuj-kampan.ts            # NA SUCHO: farebny nahlad 3 e-mailov + statistika
//    ... --zapis                                                         # kampan_pilot.csv + zaznam do vyzvy_vyber
//  Volby: --pocet 50  --seed 2411  --datum 2026-11-24  --vystup kampan_pilot.csv
//
//  Skript NIC NEODOSIELA. CSV je vstup do mailingoveho nastroja; odoslanie
//  robi Marek rucne po kontrole.
//  Kontakty: kampan_obce_kontakty so stavom 'ok' a bez odhlasenia (migracia 48).
// =============================================================================

import { writeFileSync } from "node:fs";
import { db, citaj, rpc, vloz, F } from "./db.ts";
import { vyberVyzievPreObec, riadkyLogu, type ObecSignaly, type VyzvaKarta, type VysledokVyberu } from "../src/vyzvy/vyber.ts";

const WEB = "https://predtendrom.sk";

export interface Kontakt { ico: string; email: string; token: string }
export interface Pilot {
  obec: ObecSignaly & { karta_token: string };
  kontakt: Kontakt;
  vyber: VysledokVyberu;
  variant: "A" | "B";
}

// --- Vzorka ---------------------------------------------------------------------
export function velkostnaSkupina(p: number | null): string {
  if (p == null) return "neznáma";
  if (p <= 500) return "do 500";
  if (p <= 2000) return "501–2 000";
  if (p <= 5000) return "2 001–5 000";
  return "nad 5 000";
}

/** Deterministicky PRNG (mulberry32), aby sa vzorka dala zopakovat. */
function prng(seed: number) {
  return () => {
    seed |= 0; seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Round-robin cez skupiny kraj x velkost, aby vzorka pokryla mix. */
export function vzorka<T extends { obec: ObecSignaly }>(kandidati: T[], pocet: number, seed: number): T[] {
  const nahoda = prng(seed);
  const skupiny = new Map<string, T[]>();
  for (const k of kandidati) {
    const kluc = `${k.obec.kraj}|${velkostnaSkupina(k.obec.pocet_obyvatelov)}`;
    skupiny.set(kluc, [...(skupiny.get(kluc) ?? []), k]);
  }
  const zoznamy = [...skupiny.keys()].sort().map((kl) => {
    const z = [...skupiny.get(kl)!].sort((a, b) => a.obec.kod.localeCompare(b.obec.kod));
    for (let i = z.length - 1; i > 0; i--) { const j = Math.floor(nahoda() * (i + 1)); [z[i], z[j]] = [z[j], z[i]]; }
    return z;
  });
  const out: T[] = [];
  for (let kolo = 0; out.length < pocet; kolo++) {
    let pridane = false;
    for (const z of zoznamy) {
      if (kolo < z.length && out.length < pocet) { out.push(z[kolo]); pridane = true; }
    }
    if (!pridane) break;
  }
  return out;
}

/** A/B: stabilne podla ICO (ta ista obec dostane vzdy rovnaky variant). */
export function variant(ico: string): "A" | "B" {
  let h = 0;
  for (const ch of ico) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return h % 2 === 0 ? "A" : "B";
}

// --- Texty ----------------------------------------------------------------------
const eur = (n: number | null) => n == null ? "" : new Intl.NumberFormat("sk-SK", { maximumFractionDigits: 0 }).format(n).replace(/ /g, " ") + " €";
const datum = (iso: string) => { const [r, m, d] = iso.slice(0, 10).split("-"); return `${+d}. ${+m}. ${r}`; };
const kratkyDatum = (iso: string) => { const [, m, d] = iso.slice(0, 10).split("-"); return `${+d}. ${+m}.`; };

export function predmet(p: Pilot, vyzvy: Map<string, VyzvaKarta>): string {
  const v = p.vyber.vyzvy;
  const n = v.length;
  if (p.variant === "B") {
    const prva = v[0];
    const dni = prva.dni_do_uzavierky;
    return `${p.obec.nazov} spĺňa podmienky výzvy „${prva.nazov}“${dni != null ? `, máte ${dni} dní` : ""}`;
  }
  const slovo = n === 1 ? "výzva, na ktorú ste oprávnení" : `výzvy, na ktoré ste oprávnení`;
  const uzavierky = v.map((x) => vyzvy.get(x.kod)?.uzavierka).filter(Boolean).sort() as string[];
  return `${p.obec.nazov}: ${n} ${slovo}${uzavierky.length ? ` (uzávierka od ${kratkyDatum(uzavierky[0])})` : ""}`;
}

export function odkazKarty(kod: string, token: string, v: string) {
  return `${WEB}/vyzva?k=${encodeURIComponent(kod)}&o=${token}&utm_source=email&utm_medium=kampan&utm_campaign=pilot-vyzvy&utm_content=${v}`;
}

export function teloEmailu(p: Pilot, vyzvy: Map<string, VyzvaKarta>): string {
  const ciara = "━".repeat(30);
  const o = p.obec;
  const n = p.vyber.vyzvy.length;
  const casti = p.vyber.vyzvy.map((x, i) => {
    const v = vyzvy.get(x.kod)!;
    const nfp = v.nfp_min != null || v.nfp_max != null
      ? `dotácia ${[eur(v.nfp_min), eur(v.nfp_max)].filter(Boolean).join("–")} · ` : "";
    const uz = v.uzavierka
      ? `Uzávierka: ${datum(v.uzavierka)} (${x.dni_do_uzavierky} dní)${x.surne ? " [SÚRNE]" : ""}`
      : "Otvorená výzva (do vyčerpania prostriedkov)";
    return [
      ciara,
      `${i + 1}) ${v.nazov}`,
      `   ${v.poskytovatel} · ${nfp}spoluúčasť ${v.spoluucast_pct} %`,
      `   ${uz}`,
      v.financovanie === "refundacia" ? "   ⚠ Dotácia sa vypláca spätne, obec celý projekt najprv zaplatí." : null,
      "",
      "   Prečo vám to posielame:",
      ...x.dovod.map((d) => `   ✓ ${d}`),
      `   ? Overiť musíte vy: ${x.neoverene.slice(0, 2).join(", ")}`,
      "",
      `   → Karta výzvy a prvý krok: ${odkazKarty(x.kod, o.karta_token, p.variant)}`,
    ].filter((r) => r !== null).join("\n");
  });

  return [
    "Dobrý deň, pán starosta / pani starostka,",
    "",
    `posielame vám prehľad výziev, ktoré sme vybrali pre ${o.nazov} (${(o.okres ?? o.kraj).replace(/^Okres\s+/, "okres ")}, ${o.pocet_obyvatelov} obyvateľov).`,
    "Výzvu ponúkneme len vtedy, keď obec spĺňa základné podmienky: typ žiadateľa, územie a veľkosť.",
    `Tento mesiac ${n === 1 ? "je to 1" : `sú to ${n}`}:`,
    "",
    ...casti,
    ciara,
    "",
    "Na každej karte nájdete:",
    "• kontrolu pripravenosti v 7 otázkach (2 minúty),",
    "• výpočet spoluúčasti a toho, koľko budete musieť predfinancovať,",
    "• vzor uznesenia zastupiteľstva a termíny do kalendára.",
    "",
    "Žiadosti za obce nepíšeme. Ak už máte poradcu, kartu mu pošlite, ušetrí mu čas.",
    "",
    "S pozdravom",
    "Marek Takáč, PredTendrom.sk",
    "Služba je pre obce bezplatná.",
    "",
    "—",
    `Údaje: Centrálny register zmlúv, Vestník ÚVO, výzvy poskytovateľov (ručne overené).`,
    "Nie sme poskytovateľ dotácie ani poradca. Rozhodujúce je vždy znenie výzvy.",
    `Nechcete tieto e-maily? ${WEB}/odhlasenie-obce.html?t=${p.kontakt.token}`,
    "Iný kontakt na úrad? Stačí odpovedať na tento e-mail.",
    "LoveHome s.r.o., Černyševského 40, 851 01 Bratislava, IČO 47 586 362",
  ].join("\n");
}

export function csv(riadky: string[][]): string {
  return riadky.map((r) => r.map((x) => `"${String(x).replace(/"/g, '""')}"`).join(",")).join("\r\n") + "\r\n";
}

// --- CLI ------------------------------------------------------------------------
function arg(meno: string, pred: string) { const i = process.argv.indexOf(`--${meno}`); return i > 0 ? process.argv[i + 1] : pred; }

async function main() {
  const zapis = process.argv.includes("--zapis");
  const pocet = Number(arg("pocet", "50"));
  const seed = Number(arg("seed", "2411"));
  const odoslanie = new Date(`${arg("datum", "2026-11-24")}T08:00:00Z`);
  const vystup = arg("vystup", "kampan_pilot.csv");
  const mesiac = `${odoslanie.toISOString().slice(0, 7)}-01`;
  const d = db();

  console.log(F.tucne(`\n=== Pilotná kampaň: výzvy pre obce (${zapis ? "ZÁPIS" : "NA SUCHO"}) ===`));
  const [vyzvyZoz, signaly, tokeny, kontakty, uzPoslane] = await Promise.all([
    citaj<VyzvaKarta>(d, "vyzvy_karty?select=*&overene_at=not.is.null"),
    rpc<ObecSignaly[]>(d, "vyzvy_signaly_obci"),
    citaj<{ kod: string; karta_token: string }>(d, "obce_register?select=kod,karta_token"),
    citaj<{ ico: string; email: string; token: string }>(d, "kampan_obce_kontakty?select=ico,email,token&stav=eq.ok&odhlasene_at=is.null"),
    citaj<{ kod_obce: string }>(d, `vyzvy_vyber?select=kod_obce&mesiac=eq.${mesiac}`),
  ]);
  console.log(`Overené výzvy: ${vyzvyZoz.length} · obce s IČO: ${signaly.length} · použiteľné kontakty: ${kontakty.length}`);
  if (!vyzvyZoz.length) {
    console.log(F.zlta("\nŽiadna výzva nie je overená. Najprv skontrolujte výzvy a označte ich: seed_vyzvy.ts --over <KOD> --overil \"Meno\""));
    return;
  }

  const vyzvy = new Map(vyzvyZoz.map((v) => [v.kod, v]));
  const tok = new Map(tokeny.map((t) => [t.kod, t.karta_token]));
  const kon = new Map(kontakty.map((k) => [k.ico.padStart(8, "0"), k]));
  const poslane = new Set(uzPoslane.map((x) => x.kod_obce));

  let bezKontaktu = 0, ticho = 0, uzMali = 0;
  const kandidati: Pilot[] = [];
  for (const s of signaly) {
    const k = s.ico ? kon.get(s.ico.padStart(8, "0")) : undefined;
    if (!k) { bezKontaktu++; continue; }
    if (poslane.has(s.kod)) { uzMali++; continue; }
    const v = vyberVyzievPreObec(s, vyzvyZoz, odoslanie);
    if (!v.posielat) { ticho++; continue; }
    kandidati.push({ obec: { ...s, karta_token: tok.get(s.kod)! }, kontakt: k, vyber: v, variant: variant(s.ico!) });
  }
  const pilot = vzorka(kandidati, pocet, seed);

  console.log(`Bez kontaktu ${bezKontaktu} · pravidlo ticha ${ticho} · už v tomto mesiaci ${uzMali} · ${F.zelena(`s výzvou ${kandidati.length}`)}`);
  console.log(F.tucne(`Vzorka: ${pilot.length} obcí`) + ` (A ${pilot.filter((p) => p.variant === "A").length} / B ${pilot.filter((p) => p.variant === "B").length})`);
  const rozlozenie = new Map<string, number>();
  for (const p of pilot) {
    for (const kl of [p.obec.kraj, velkostnaSkupina(p.obec.pocet_obyvatelov)]) rozlozenie.set(kl, (rozlozenie.get(kl) ?? 0) + 1);
  }
  console.log(F.seda([...rozlozenie].map(([k, n]) => `${k}: ${n}`).join(" · ")));
  const pocVyziev = new Map<string, number>();
  for (const p of pilot) for (const x of p.vyber.vyzvy) pocVyziev.set(x.kod, (pocVyziev.get(x.kod) ?? 0) + 1);
  console.log(F.seda("Výzvy vo vzorke: " + [...pocVyziev].map(([k, n]) => `${k} ${n}×`).join(" · ")));

  if (!pilot.length) {
    console.log(F.zlta("\nŽiadna obec s kontaktom nemá vhodnú výzvu. Skontrolujte register obcí (IČO, počet obyvateľov) a overené výzvy."));
    return;
  }

  if (!zapis) {
    for (const p of pilot.slice(0, 3)) {
      console.log("\n" + F.modra("┌" + "─".repeat(78)));
      console.log(F.modra("│ ") + F.seda(`Komu: ${p.kontakt.email}  ·  variant ${p.variant}  ·  skóre ${p.vyber.vyzvy.map((x) => x.skore).join("/")}`));
      console.log(F.modra("│ ") + F.tucne(`Predmet: ${predmet(p, vyzvy)}`));
      console.log(F.modra("├" + "─".repeat(78)));
      for (const r of teloEmailu(p, vyzvy).split("\n")) {
        const farba = r.includes("✓") ? F.zelena : r.includes("⚠") || r.includes("SÚRNE") ? F.zlta : r.includes("→") ? F.modra : (s: string) => s;
        console.log(F.modra("│ ") + farba(r));
      }
      console.log(F.modra("└" + "─".repeat(78)));
    }
    console.log(F.seda(`\nNa sucho: nič sa nezapísalo. Pre export ${vystup} pridajte --zapis.`));
    return;
  }

  const riadky = [["ico", "email_obce", "predmet", "telo_text"],
    ...pilot.map((p) => [p.obec.ico!, p.kontakt.email, predmet(p, vyzvy), teloEmailu(p, vyzvy)])];
  writeFileSync(vystup, "﻿" + csv(riadky));
  // Zaznam vyberu: chrani pred dvojitym poslanim v tom istom mesiaci a sluzi na vyhodnotenie
  await vloz(d, "vyzvy_vyber", pilot.flatMap((p) => riadkyLogu(p.vyber, mesiac)), "mesiac,kod_obce,poradie", "ignoruj");
  console.log(F.zelena(`\n✓ ${vystup}: ${pilot.length} e-mailov. Výber zapísaný do vyzvy_vyber (${mesiac}).`));
  console.log("E-maily sa NEODOSLALI. Pred odoslaním si CSV prezrite.");
}

if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch((e) => { console.error(F.cervena(`CHYBA: ${e.message}`)); process.exit(1); });
}
