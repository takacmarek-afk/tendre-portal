// Testy skripty/doplnenie-registra-obci.ts
// node --experimental-strip-types --test tests/test_doplnenie_registra.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  parsujCsv, dekoduj, normNazov, normOkres, normIco, normKodObce, normTyp, cislo, spracuj, zapis,
} from "../skripty/doplnenie-registra-obci.ts";

const R = (kod, nazov, kraj, okres, extra = {}) => ({
  kod, nazov, kraj, okres, ico: null, typ: "obec", pocet_obyvatelov: null, obyvatelia_k: null, nro: null, mrk: null, ...extra,
});
const REGISTER = [
  R("SK0328516741", "Revúcka Lehota", "Banskobystrický kraj", "Okres Revúca"),
  R("SK0328516767", "Revúca", "Banskobystrický kraj", "Okres Revúca"),
  R("SK0211501166", "Trnávka", "Trnavský kraj", "Okres Dunajská Streda"),
  R("SK0427523321", "Trnávka", "Košický kraj", "Okres Trebišov"),
  R("SK0422598186", "Košice - Staré Mesto", "Košický kraj", "Okres Košice I", { ico: "00690937" }),
];

test("CSV: bodkociarka, uvodzovky, BOM, cp1250", () => {
  const r = parsujCsv('﻿nazov;pocet_obyvatelov\n"Obec ""A""";1 234\r\nB;5\n\n');
  assert.equal(r.length, 2);
  assert.equal(r[0].nazov, 'Obec "A"');
  assert.equal(cislo(r[0].pocet_obyvatelov), 1234);
  const cp = new Uint8Array([0x6e, 0x61, 0x7a, 0x6f, 0x76, 0x0a, 0x8a, 0x61, 0x9e]); // "nazov\nŠaž" v cp1250
  assert.equal(parsujCsv(dekoduj(cp))[0].nazov, "Šaž");
});
test("normalizacia", () => {
  assert.equal(normNazov("Obec Revúcka Lehota"), "revucka lehota");
  assert.equal(normNazov("Košice-Staré Mesto"), normNazov("Košice - Staré Mesto"));
  assert.equal(normOkres("Okres Revúca"), "revuca");
  assert.equal(normIco("690937"), "00690937");
  assert.equal(normKodObce("SK0328516741"), "516741");
  assert.equal(normTyp("Mesto"), "mesto");
  assert.equal(normTyp("mestská časť"), "mestska_cast");
  assert.equal(normTyp("obec"), "obec");
});

test("parovanie ico > kod > nazov+okres > nazov; duplicity a nejednoznacnost", () => {
  const v = spracuj(REGISTER, {
    demografia: [
      { ico: "690937", nazov: "Staré Mesto (iný názov)", pocet_obyvatelov: "20 000", typ: "mestská časť" },
      { kod_obce: "516767", nazov: "x", pocet_obyvatelov: "12000", typ: "mesto", ico: "00328715" },
      { nazov: "Obec Trnávka", okres: "Trebišov", pocet_obyvatelov: "500" },
      { nazov: "Trnávka", pocet_obyvatelov: "700" },                       // 2x v SR, bez okresu
      { nazov: "Revúcka Lehota", pocet_obyvatelov: "250" },                // jedinecny nazov
      { nazov: "Revúcka Lehota", okres: "Revúca", pocet_obyvatelov: "251" }, // duplicita
      { nazov: "Neexistujúca", pocet_obyvatelov: "1" },
    ],
  });
  assert.equal(v.stat.demografia_par_ico, 1);
  assert.equal(v.stat.demografia_par_kod_obce, 1);
  assert.equal(v.stat.demografia_par_nazov_okres, 1);
  assert.equal(v.stat.demografia_par_nazov, 1);
  assert.equal(v.stat.demografia_duplicita, 1);
  assert.equal(v.stat.demografia_nesparovane, 2);
  assert.ok(v.nesparovane.some((n) => n.dovod === "nazov_nejednoznacny_doplnte_okres"));
  const revuca = v.zmeny.find((o) => o.kod === "SK0328516767");
  assert.equal(revuca.typ, "mesto");
  assert.equal(revuca.ico, "00328715");
  assert.equal(v.zmeny.find((o) => o.kod === "SK0422598186").typ, "mestska_cast");
  assert.equal(v.zmeny.find((o) => o.kod === "SK0328516741").pocet_obyvatelov, 250);
});

test("konflikt ICO sa neprepise", () => {
  const v = spracuj(REGISTER, { demografia: [{ kod_obce: "598186", nazov: "x", pocet_obyvatelov: "1", ico: "11111111" }] });
  assert.equal(v.konflikty_ico.length, 1);
  assert.equal(v.zmeny[0].ico, "00690937");
});

test("NRO podla okresu, MRK podla obce, ostatne false", () => {
  const v = spracuj(REGISTER, {
    nro: [{ okres: "Revúca" }, { okres: "Okres Trebišov" }, { okres: "Neznámy" }],
    mrk: [{ nazov: "Revúcka Lehota", okres: "Revúca" }, { nazov: "Trnávka", okres: "Trebišov", mrk: "0" }],
  });
  const o = (k) => v.zmeny.find((x) => x.kod === k);
  assert.equal(o("SK0328516741").nro, true);
  assert.equal(o("SK0427523321").nro, true);
  assert.equal(o("SK0211501166").nro, false);
  assert.equal(o("SK0328516741").mrk, true);
  assert.equal(o("SK0427523321").mrk, false, "mrk=0 explicitne false");
  assert.equal(v.stat.nro_nezname_okresy, 1);
});

test("bez dat sa nic neprepise na null; zmeny len pri rozdiele", () => {
  const reg = [R("SK0328516741", "Revúcka Lehota", "Banskobystrický kraj", "Okres Revúca", { pocet_obyvatelov: 250 })];
  const v = spracuj(reg, { demografia: [{ nazov: "Revúcka Lehota", pocet_obyvatelov: "250" }] });
  assert.equal(v.zmeny.length, 0);
  const v2 = spracuj(reg, { demografia: [{ nazov: "Revúcka Lehota", pocet_obyvatelov: "" }] });
  assert.equal(v2.zmeny.length, 0);
});

test("zapis: davky po 500, upsert, rovnake kluce", async () => {
  const volania = [];
  const f = async (url, opt) => { volania.push({ url, opt }); return { ok: true, text: async () => "" }; };
  const zmeny = Array.from({ length: 1001 }, (_, i) => R(`K${i}`, "n", "k", "o"));
  assert.equal(await zapis("https://x", "kluc", zmeny, f), 1001);
  assert.equal(volania.length, 3);
  assert.match(volania[0].url, /on_conflict=kod/);
  assert.match(volania[0].opt.headers.Prefer, /merge-duplicates/);
  const telo = JSON.parse(volania[0].opt.body);
  assert.equal(telo.length, 500);
  assert.ok(!("karta_token" in telo[0]));
});
