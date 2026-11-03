// Testy seed_vyzvy.ts a generuj-kampan.ts (vratane behu CLI proti falosnemu PostgREST).
// node --experimental-strip-types --test tests/test_kampan_pilot.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import http from "node:http";
import { execFile } from "node:child_process";
import { readFileSync, rmSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { VYZVY, validuj, riadok } from "../skripty/seed_vyzvy.ts";
import { vzorka, variant, predmet, teloEmailu, csv, velkostnaSkupina } from "../skripty/generuj-kampan.ts";

test("seeder: validacia, unikatne kody, overene len s oficialnym kodom a zdrojom", () => {
  assert.ok(VYZVY.length >= 8);
  for (const v of VYZVY) assert.deepEqual(validuj(v), [], v.kod);
  assert.equal(new Set(VYZVY.map((v) => v.kod)).size, VYZVY.length);
  for (const v of VYZVY) {
    const r = riadok(v, new Date("2026-11-03T10:00:00Z"));
    assert.ok(!("stav" in r) && !("zdroje" in r) && !("neoverene_udaje" in r));
    if (v.stav === "overena") { assert.match(r.overil, /^Claude AI/); assert.equal(r.overene_at, "2026-11-03T10:00:00.000Z"); assert.ok(!v.kod.startsWith("NAVRH-")); }
    else { assert.equal(r.overil, null); assert.equal(r.overene_at, null); }
  }
  // vsetky riadky maju rovnake kluce (PostgREST hromadny insert)
  const kluce = VYZVY.map((v) => Object.keys(riadok(v)).sort().join(","));
  assert.equal(new Set(kluce).size, 1);
  assert.ok(VYZVY.filter((v) => v.stav === "overena").length >= 2);
});
test("seeder: NAVRH- kod nemoze byt overeny", () => {
  const v = { ...VYZVY.find((x) => x.stav === "na_kontrolu" && x.kod.startsWith("NAVRH-")), stav: "overena" };
  assert.ok(validuj(v).some((c) => c.includes("oficialny kod")));
});
test("seeder: validacia chyta chyby", () => {
  const zla = { ...VYZVY[0], zdroj_url: "http://x", obyv_min: 10, obyv_max: 1, uzavierka: "2027-01-01", kolo_uzavierky: ["2027-02-01"] };
  const ch = validuj(zla);
  assert.ok(ch.some((c) => c.includes("https")));
  assert.ok(ch.includes("obyv_min > obyv_max"));
  assert.ok(ch.includes("uzavierka nie je v kolo_uzavierky"));
});

const obec = (kod, kraj, pocet) => ({ obec: { kod, kraj, pocet_obyvatelov: pocet } });
test("vzorka: mix krajov a velkosti, deterministicka", () => {
  const k = [];
  for (let i = 0; i < 40; i++) k.push(obec(`A${i}`, "Prešovský kraj", 300));
  for (let i = 0; i < 3; i++) k.push(obec(`B${i}`, "Žilinský kraj", 8000));
  k.push(obec("C0", "Nitriansky kraj", 1500));
  const v = vzorka(k, 10, 1);
  assert.equal(v.length, 10);
  assert.ok(v.some((x) => x.obec.kod === "C0"));
  assert.equal(v.filter((x) => x.obec.kod.startsWith("B")).length, 3);
  assert.deepEqual(vzorka(k, 10, 1).map((x) => x.obec.kod), v.map((x) => x.obec.kod));
  assert.equal(velkostnaSkupina(500), "do 500");
  assert.equal(vzorka(k, 100, 1).length, 44);
});
test("A/B stabilne", () => {
  assert.equal(variant("00328707"), variant("00328707"));
  assert.ok(["A", "B"].includes(variant("1")));
});

const V1 = { ...riadok(VYZVY[0]), spoluucast_pct: 5, kod: "X1", nazov: "Centrá opätovného použitia", uzavierka: "2027-02-26", kolo_uzavierky: ["2027-02-26"], financovanie: "refundacia", nfp_min: 30000, nfp_max: 400000 };
const PILOT = {
  obec: { kod: "SK0328516741", ico: "00328707", nazov: "Revúcka Lehota", kraj: "Banskobystrický kraj", okres: "Okres Revúca", pocet_obyvatelov: 250, karta_token: "11111111-2222-3333-4444-555555555555" },
  kontakt: { ico: "00328707", email: "obec@x.sk", token: "tok-1" },
  vyber: { kod_obce: "SK0328516741", posielat: true, vyzvy: [{ kod: "X1", nazov: V1.nazov, poskytovatel: V1.poskytovatel, skore: 6, surne: false, dni_do_uzavierky: 94, dovod: ["výzva je pre obce", "zmluva v tejto oblasti vám končí 6/2027"], neoverene: ["aktivity projektu podľa výzvy", "vlastníctvo pozemku alebo budovy", "povolenie stavby"] }] },
  variant: "A",
};
test("texty e-mailu", () => {
  const m = new Map([["X1", V1]]);
  assert.equal(predmet(PILOT, m), "Revúcka Lehota: 1 výzva, na ktorú ste oprávnení (uzávierka od 26. 2.)");
  assert.equal(predmet({ ...PILOT, variant: "B" }, m), "Revúcka Lehota spĺňa podmienky výzvy „Centrá opätovného použitia“, máte 94 dní");
  const t = teloEmailu(PILOT, m);
  assert.match(t, /okres Revúca, 250 obyvateľov/);
  assert.match(t, /dotácia 30 000 €–400 000 € · spoluúčasť 5 %/);
  assert.match(t, /⚠ Dotácia sa vypláca spätne/);
  assert.match(t, /✓ zmluva v tejto oblasti vám končí 6\/2027/);
  assert.match(t, /vyzva\?k=X1&o=11111111-2222-3333-4444-555555555555&utm_source=email/);
  assert.match(t, /odhlasenie-obce\.html\?t=tok-1/);
  assert.doesNotMatch(t, /šanc|garant|%\s*zhod/i);
  assert.equal(csv([["a", 'b"c'], ["x\ny", "z"]]), '"a","b""c"\r\n"x\ny","z"\r\n');
});

// --- Beh CLI proti falosnemu PostgREST ----------------------------------------------
function falosnyServer() {
  const zapisy = [];
  const obce = Array.from({ length: 60 }, (_, i) => ({
    kod: `SK0000${String(100000 + i)}`, ico: String(10000000 + i), nazov: `Obec ${i}`, typ: "obec",
    kraj: ["Prešovský kraj", "Košický kraj", "Žilinský kraj"][i % 3], okres: "Okres Test", pocet_obyvatelov: 200 + i * 50,
    nro: false, mrk: false, konciace: i % 4 === 0 ? [{ sektor: "ODPAD", koniec: "2027-06-30" }] : [], dotacie_3r: [], dotiahnute: i % 2 === 0,
  }));
  const vyzva = { ...V1, overil: "test", overene_at: "2026-11-20T10:00:00Z", kraje: [], typ_ziadatela: ["obec"], obyv_max: 5000, signal_sektory: ["ODPAD"] };
  const s = http.createServer((q, r) => {
    let telo = "";
    q.on("data", (c) => (telo += c));
    q.on("end", () => {
      const u = q.url;
      const json = (x) => { r.writeHead(200, { "Content-Type": "application/json" }); r.end(JSON.stringify(x)); };
      if (q.method === "POST" && u.startsWith("/rest/v1/rpc/vyzvy_signaly_obci")) return json(obce);
      if (q.method === "POST") { zapisy.push({ u, telo: JSON.parse(telo) }); r.writeHead(201); return r.end(); }
      if (u.startsWith("/rest/v1/vyzvy_karty")) return json([vyzva]);
      if (u.startsWith("/rest/v1/obce_register")) return json(obce.map((o) => ({ kod: o.kod, karta_token: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee" })));
      if (u.startsWith("/rest/v1/kampan_obce_kontakty")) return json(obce.slice(0, 55).map((o) => ({ ico: o.ico, email: `${o.kod}@obec.sk`, token: "t" })));
      if (u.startsWith("/rest/v1/vyzvy_vyber")) return json([]);
      r.writeHead(404); r.end();
    });
  });
  return { s, zapisy };
}

function spusti(args, env) {
  return new Promise((res) => execFile(process.execPath, ["--experimental-strip-types", "--no-warnings", "skripty/generuj-kampan.ts", ...args],
    { env: { ...process.env, ...env, NO_COLOR: "1" } }, (err, out, errOut) => res({ code: err?.code ?? 0, out: out + errOut })));
}

test("CLI: na sucho nahlad, so --zapis CSV + log", async () => {
  const { s, zapisy } = falosnyServer();
  await new Promise((r) => s.listen(0, r));
  const env = { SUPABASE_URL: `http://127.0.0.1:${s.address().port}`, SUPABASE_SERVICE_ROLE_KEY: "test" };
  try {
    const a = await spusti([], env);
    assert.equal(a.code, 0, a.out);
    assert.match(a.out, /Vzorka: 50 obcí/);
    assert.equal((a.out.match(/Predmet:/g) || []).length, 3);
    assert.equal(zapisy.length, 0, "na sucho sa nic nezapisuje");

    const dir = mkdtempSync(join(tmpdir(), "kampan-"));
    const subor = join(dir, "kampan_pilot.csv");
    const b = await spusti(["--zapis", "--vystup", subor], env);
    assert.equal(b.code, 0, b.out);
    const obsah = readFileSync(subor, "utf8");
    assert.ok(obsah.startsWith('﻿"ico","email_obce","predmet","telo_text"'));
    assert.equal(zapisy.length, 1);
    assert.match(zapisy[0].u, /vyzvy_vyber\?on_conflict=mesiac,kod_obce,poradie/);
    assert.equal(zapisy[0].telo.length, 50);
    rmSync(dir, { recursive: true });
  } finally { s.close(); }
});

test("neznama spoluucast: e-mail ju netvrdi, kalkulacka nepocita", async () => {
  const { spocitajPeniaze } = await import("../public/semafor.js");
  assert.equal(spocitajPeniaze({ spoluucast_pct: null }, { cena_s_dph: 1000 }), null);
  const m = new Map([["X1", { ...V1, spoluucast_pct: null }]]);
  const t = teloEmailu(PILOT, m);
  assert.match(t, /spoluúčasť podľa výzvy/);
  assert.doesNotMatch(t, /null|undefined|NaN/);
  assert.match(t, /overené podľa zverejnených podkladov/);
});
