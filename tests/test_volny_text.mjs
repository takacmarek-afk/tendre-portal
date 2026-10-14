// Test hladania vlastnymi slovami (app.html, rozpoznajVolnyText). Bez AI, len pravidla.
// Spustenie: node tests/test_volny_text.mjs
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const html = readFileSync(new URL("../public/app.html", import.meta.url), "utf8");
const a = html.indexOf("// ── HLADANIE VLASTNYMI SLOVAMI");
const b = html.indexOf("// ── EXPORT ───");
assert.ok(a > 0 && b > a, "blok sa nenasiel");
const rozpoznaj = new Function(html.slice(a, b) + "\nreturn rozpoznajVolnyText;")();

const r = (t) => rozpoznaj(t);
assert.deepEqual(r("ostraha Košice"), { sektor: "OSTRAHA", kraj: "Košický kraj", predstih: "", zvysok: "Košice" });
assert.deepEqual(r("upratovanie škôl v Prešovskom kraji"), { sektor: "UPRATOVANIE", kraj: "Prešovský kraj", predstih: "", zvysok: "škôl" });
assert.deepEqual(r("stravovanie 3 až 6 mesiacov Žilina"), { sektor: "STRAVOVANIE", kraj: "Žilinský kraj", predstih: "3-6", zvysok: "Žilina" });
assert.equal(r("upratovanie a ostraha"), null, "dva sektory = nejednoznacne");
assert.equal(r("Mesto Nitra"), null, "samotne mesto nema menit hladanie");
assert.equal(r("nemocnica"), null);
assert.equal(r(""), null);
assert.equal(r("úrady v košickom kraji").kraj, "Košický kraj");
assert.equal(r("IT technika").sektor, "IT_TECHNIKA");
console.log("OK volny text");
