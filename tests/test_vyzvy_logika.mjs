// Testy Quick Win A (vyber) a B (semafor, kalkulacka).
// Spustit: node --experimental-strip-types --test tests/test_vyzvy_logika.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { vyberVyzievPreObec, tvrdyFilter, AKTIVITA_VZORY } from "../src/vyzvy/vyber.ts";
import { vyhodnotSemafor, spocitajPeniaze } from "../public/semafor.js";

const VZOR = JSON.parse(readFileSync(new URL("../supabase/vzory/vyzva_karta_vzor.json", import.meta.url)));
const TERAZ = new Date("2026-11-24T08:00:00Z");
const over = (v) => ({ ...VZOR, overil: "marek", overene_at: "2026-11-20T10:00:00Z", ...v });

const OBEC = {
  kod: "SK0328599999", ico: "00999999", nazov: "Testovo", typ: "obec",
  kraj: "Banskobystrický kraj", okres: "Okres Revúca", pocet_obyvatelov: 812, nro: true, mrk: false,
  konciace: [{ sektor: "STAVEBNE_PRACE", koniec: "2027-06-30" }],
  dotacie_3r: [{ ucel: "Rekonštrukcia MŠ", sektor: "STAVEBNE_PRACE", podpisane: "2025-03-01" }],
  dotiahnute: true,
};

// --- Krok 1 -------------------------------------------------------------------
test("neoverena vyzva vypadne", () => {
  assert.equal(tvrdyFilter(OBEC, VZOR, TERAZ), "neoverena");
});
test("tvrdy filter: typ, uzemie, NRO, MRK, velkost, uzavierka", () => {
  assert.equal(tvrdyFilter(OBEC, over({ typ_ziadatela: ["VUC"] }), TERAZ), "typ_ziadatela");
  assert.equal(tvrdyFilter(OBEC, over({ kraje: ["Košický kraj"] }), TERAZ), "uzemie");
  assert.equal(tvrdyFilter(OBEC, over({ kraje: ["Banskobystricky kraj"] }), TERAZ), null, "bez diakritiky sedi");
  assert.equal(tvrdyFilter(OBEC, over({ kraje: ["Košický kraj"], okresy: ["Revúca"] }), TERAZ), null, "okres staci");
  assert.equal(tvrdyFilter({ ...OBEC, nro: null }, over({ len_nro: true }), TERAZ), "nro");
  assert.equal(tvrdyFilter(OBEC, over({ len_mrk: true }), TERAZ), "mrk");
  assert.equal(tvrdyFilter(OBEC, over({ obyv_min: 1000 }), TERAZ), "velkost");
  assert.equal(tvrdyFilter({ ...OBEC, pocet_obyvatelov: null }, over({}), TERAZ), "pocet_obyvatelov_neznamy");
  assert.equal(tvrdyFilter(OBEC, over({ uzavierka: "2026-12-23", kolo_uzavierky: [] }), TERAZ), "uzavierka_blizko"); // 29 dni
  assert.equal(tvrdyFilter(OBEC, over({ uzavierka: "2026-12-24", kolo_uzavierky: [] }), TERAZ), null);              // 30 dni
  assert.equal(tvrdyFilter(OBEC, over({ uzavierka: null }), TERAZ), null, "otvorena prechadza");
});

// --- Krok 2 -------------------------------------------------------------------
test("bodovanie: +3 +2 +1 +2, dovod[]", () => {
  // 2027-02-26 je o 94 dni → optimum
  const r = vyberVyzievPreObec(OBEC, [over({})], TERAZ);
  assert.equal(r.posielat, true);
  const v = r.vyzvy[0];
  assert.equal(v.skore, 3 + 2 + 1 + 2);
  assert.equal(v.surne, false);
  assert.ok(v.dovod.some((d) => d.includes("končí 6/2027")));
  assert.ok(v.dovod.some((d) => d.includes("812 obyvateľov")));
  assert.ok(v.neoverene.includes("povolenie stavby"));
});
test("dotacia na rovnaku aktivitu zrusi +2; IUS -1; surne", () => {
  const obec = { ...OBEC, dotacie_3r: [{ ucel: "Zberný dvor obce", sektor: null, podpisane: "2025-01-01" }] };
  const r = vyberVyzievPreObec(obec, [over({ vyzaduje_ius: true, uzavierka: "2027-01-01", kolo_uzavierky: [] })], TERAZ);
  assert.equal(r.vyzvy[0].skore, 3 + 1 - 1);   // 38 dni: 0 bodov
  assert.equal(r.vyzvy[0].surne, true);
});
test("skratky s diakritikou", () => {
  assert.ok(AKTIVITA_VZORY.MS.test("Rekonštrukcia MŠ Testovo"));
  assert.ok(AKTIVITA_VZORY.voda.test("Rozšírenie ČOV"));
  assert.ok(!AKTIVITA_VZORY.cesty.test("Cestovné náhrady"));
});

// --- Krok 3 + 4 ---------------------------------------------------------------
test("max 3, max 2 od poskytovatela, poradie", () => {
  const vyzvy = [
    over({ kod: "A", poskytovatel: "Envirofond", aktivity: [] }),
    over({ kod: "B", poskytovatel: "Envirofond" }),
    over({ kod: "C", poskytovatel: "envirofond " }),
    over({ kod: "D", poskytovatel: "MIRRI", signal_sektory: [] }),
    over({ kod: "E", poskytovatel: "PPA", signal_sektory: [], aktivity: [] }),
  ];
  const r = vyberVyzievPreObec(OBEC, vyzvy, TERAZ);
  assert.deepEqual(r.vyzvy.map((x) => x.kod), ["B", "C", "D"]);
});
test("pravidlo ticha", () => {
  const r = vyberVyzievPreObec(OBEC, [VZOR], TERAZ, true);
  assert.equal(r.posielat, false);
  assert.equal(r.vyzvy.length, 0);
  assert.equal(r.vyradene[0].dovod, "neoverena");
});

// --- Semafor ------------------------------------------------------------------
const VSETKO_ANO = { q1: "ano", q2: "ano", q3: "ano", q4: "ano", q5: "ano", q6: "ano", q7: "ano" };
const V = over({});   // uzavierka 26. 2. 2027 = 94 dni, refundacia, DSP, povolenie

test("7/7 → zelena, prvy krok poradca 21 dni pred uzavierkou", () => {
  const s = vyhodnotSemafor(V, VSETKO_ANO, TERAZ);
  assert.equal(s.stav, "zelena");
  assert.equal(s.pripravenost, "7 zo 7");
  assert.equal(s.prvy_krok.id, "poslat_poradcovi");
  assert.equal(s.prvy_krok.termin, "2027-02-05");
});
test("neuplne odpovede", () => {
  assert.equal(vyhodnotSemafor(V, { q1: "ano" }, TERAZ).stav, "neuplne");
});
test("Q5 NIE → oranzova + trh_prieskum", () => {
  const s = vyhodnotSemafor(V, { ...VSETKO_ANO, q5: "nie" }, TERAZ);
  assert.equal(s.stav, "oranzova");
  assert.equal(s.prvy_krok.id, "trh_prieskum");
  assert.equal(s.prvy_krok.trh_dopytov, true);
});
test("Q3 NIE pri 94 dnoch → cervena + dalsie kolo; krok trh_pd", () => {
  const s = vyhodnotSemafor(V, { ...VSETKO_ANO, q3: "neviem" }, TERAZ);
  assert.equal(s.stav, "cervena");
  assert.equal(s.najblizsie_kolo, "2027-09-30");
  assert.match(s.text_cervena, /Ďalšie kolo: 2027-09-30/);
  assert.equal(s.prvy_krok.id, "trh_pd");
});
test("Q6 NIE pri refundacii = cervena; krok uznesenie ma prednost", () => {
  const s = vyhodnotSemafor(V, { ...VSETKO_ANO, q6: "nie", q5: "nie" }, TERAZ);
  assert.equal(s.stav, "cervena");
  assert.equal(s.prvy_krok.id, "uznesenie");
  assert.equal(s.prvy_krok.vzor_uznesenia, true);
  assert.equal(s.prvy_krok.termin, "2026-12-24");   // min(+30 dni, uzavierka-45)
});
test("vsetko oranzove, ale sucet sa nezmesti → cervena", () => {
  const v = over({ financovanie: "predfinancovanie", uzavierka: "2027-01-28", kolo_uzavierky: [] }); // 65 dni
  const s = vyhodnotSemafor(v, { ...VSETKO_ANO, q1: "nie", q5: "nie" }, TERAZ);           // 60+28
  assert.equal(s.stav, "cervena");
  assert.equal(s.dovod, "nestihnete_sucet");
});
test("otvorena vyzva: Q3/Q4 nikdy cervene", () => {
  const s = vyhodnotSemafor(over({ uzavierka: null }), { ...VSETKO_ANO, q3: "nie", q4: "nie" }, TERAZ);
  assert.equal(s.stav, "oranzova");
});
test("netykajuce sa otazky = splnene", () => {
  const v = over({ stupen_pd: "ziadna", vyzaduje_povolenie: false });
  const s = vyhodnotSemafor(v, { q1: "ano", q2: "ano", q5: "ano", q6: "ano", q7: "ano" }, TERAZ);
  assert.equal(s.stav, "zelena");
  assert.equal(s.splnene, 7);
});

// --- Kalkulacka ---------------------------------------------------------------
test("DPH opravnena, refundacia", () => {
  const p = spocitajPeniaze(over({ dph_opravnena: "ano", nfp_max: null }), { cena_s_dph: 400000 });
  assert.equal(p.spoluucast, 20000);
  assert.equal(p.nfp, 380000);
  assert.equal(p.obec_zaplati_navzdy, 20000);
  assert.deepEqual([p.predfinancovanie.od, p.predfinancovanie.do], [380000, 380000]);
  assert.equal(p.max_vydavok_vopred, 400000);
});
test("DPH neopravnena + strop NFP + identita", () => {
  const p = spocitajPeniaze(over({ dph_opravnena: "nie", nfp_max: 250000 }), { cena_s_dph: 369000, neopravnene_s_dph: 0 });
  // COV = 300000, NFP teor 285000 → strop 250000
  assert.equal(p.cov, 300000);
  assert.equal(p.nfp, 250000);
  assert.equal(p.nad_stropom_nfp, 35000);
  assert.equal(p.dph_neopravnena, 69000);
  assert.equal(p.obec_zaplati_navzdy, p.spoluucast + p.neopravnene + p.dph_neopravnena + p.nad_stropom_nfp);
  assert.ok(p.upozornenia.includes("nad_maximom_nfp_doplaca_obec"));
});
test("podla_ziadatela bez volby = konzervativne", () => {
  const p = spocitajPeniaze(V, { cena_s_dph: 123000 });
  assert.equal(p.cov, 100000);
  assert.ok(p.upozornenia.includes("dph_nezadana_pocitame_ako_neopravnenu"));
});
test("pod minimom NFP", () => {
  const p = spocitajPeniaze(V, { cena_s_dph: 20000, dph_je_opravnena: true });
  assert.ok(p.upozornenia.includes("pod_minimom_nfp"));
});
