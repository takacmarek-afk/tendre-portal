// Test Edge Function verejny-formular v Node 22 (bez Deno): simulovane Deno.env a fetch.
// Spustenie: node --experimental-strip-types tests/test_verejny_formular.mjs
import assert from "node:assert/strict";

const env = { SUPABASE_URL: "https://x.supabase.co", SUPABASE_SERVICE_ROLE_KEY: "svc_key_abcdefghijklmnopqrstuvwxyz",
              RESEND_API_KEY: "re_test" };
globalThis.Deno = { env: { get: (k) => env[k] }, serve() {} };

let volania = [];
let strop = { povol: true };
let zabrane = [];
let resendStatus = 200;
let turnstileOk = true;
globalThis.fetch = async (url, opt = {}) => {
  const u = String(url);
  const telo = opt.body && typeof opt.body === "string" && opt.body.startsWith("{") ? JSON.parse(opt.body) : opt.body;
  volania.push({ url: u, telo, headers: opt.headers });
  const ok = (o, s = 200) => new Response(JSON.stringify(o), { status: s });
  if (u.includes("/rpc/verejny_formular_strop")) return ok(strop.povol);
  if (u.includes("/rpc/prihlas_odber_obce")) return ok({ ok: true });
  if (u.includes("/rpc/zaber_potvrdenie_odberu")) return ok(zabrane);
  if (u.includes("/rpc/vrat_potvrdenie_odberu")) return new Response("", { status: 204 });
  if (u.includes("api.resend.com")) return ok({ id: "1" }, resendStatus);
  if (u.includes("turnstile")) return ok({ success: turnstileOk });
  if (u.includes("/rest/v1/servisne_dopyty") || u.includes("/rest/v1/spatne_volania")) return new Response("", { status: 201 });
  throw new Error("necakane volanie " + u);
};

const { obsluz } = await import("../supabase/functions/verejny-formular/index.ts");
const req = (b, h = {}) => new Request("https://x/f", { method: "POST", headers: { "content-type": "application/json", ...h }, body: JSON.stringify(b) });
const res = async (r) => await (await obsluz(r)).json();
const reset = () => { volania = []; strop.povol = true; zabrane = []; resendStatus = 200; turnstileOk = true; };

// 1) OPTIONS + GET
assert.equal((await obsluz(new Request("https://x/f", { method: "OPTIONS" }))).status, 204);
assert.equal((await obsluz(new Request("https://x/f", { method: "GET" }))).status, 405);

// 2) neznamy typ
reset(); assert.equal((await obsluz(req({ typ: "hocico", data: {} }))).status, 400);

// 3) bez TURNSTILE_SECRET prechadza; odber: RPC + zaber + e-mail
reset(); zabrane = [{ id: 7, email: "a@b.sk", token: "11111111-1111-1111-1111-111111111111" }];
let j = await res(req({ typ: "odber_obce", data: { email: "a@b.sk", obec: "Testovo" } }, { "cf-connecting-ip": "1.2.3.4" }));
assert.deepEqual(j, { ok: true });
const mail = volania.find((v) => v.url.includes("resend"));
assert.ok(mail, "e-mail sa mal poslat");
assert.deepEqual(mail.telo.to, ["a@b.sk"]);
assert.equal(mail.telo.reply_to, "info@predtendrom.sk");
assert.ok(mail.telo.text.includes("odber-obce?t=11111111-1111-1111-1111-111111111111&akcia=potvrdit"));
// IP sa neposiela v cistom tvare
assert.ok(!JSON.stringify(volania).includes("1.2.3.4"), "cista IP nesmie ist do DB");

// 4) uz potvrdena / existujuca adresa: zaber vrati [] => ziadny e-mail, odpoved rovnaka
reset();
j = await res(req({ typ: "odber_obce", data: { email: "a@b.sk", obec: "Testovo" } }));
assert.deepEqual(j, { ok: true });
assert.ok(!volania.some((v) => v.url.includes("resend")));

// 5) neplatny e-mail / chybajuca obec
reset();
assert.equal((await res(req({ typ: "odber_obce", data: { email: "zle", obec: "O" } }))).kod, "NEPLATNE");
assert.equal((await res(req({ typ: "odber_obce", data: { email: "a@b.sk", obec: "" } }))).kod, "NEPLATNE");

// 6) zlyhanie Resend => vrat_potvrdenie_odberu
reset(); resendStatus = 500; zabrane = [{ id: 9, email: "a@b.sk", token: "22222222-2222-2222-2222-222222222222" }];
await res(req({ typ: "odber_obce", data: { email: "a@b.sk", obec: "O" } }));
assert.ok(volania.some((v) => v.url.includes("vrat_potvrdenie_odberu") && v.telo.p_id === 9));

// 7) strop IP
reset(); strop.povol = false;
const r429 = await obsluz(req({ typ: "odber_obce", data: { email: "a@b.sk", obec: "O" } }));
assert.equal(r429.status, 429);
assert.ok(!volania.some((v) => v.url.includes("prihlas_odber_obce")));

// 8) Turnstile
env.TURNSTILE_SECRET = "sekret";
reset(); turnstileOk = false;
assert.equal((await res(req({ typ: "spatne_volanie", turnstile: "tok", data: { meno: "J", obec: "O", telefon: "0900123456" } }))).kod, "OVERENIE");
assert.ok(!volania.some((v) => v.url.includes("spatne_volania")));
reset();
assert.equal((await res(req({ typ: "spatne_volanie", data: { meno: "J", obec: "O", telefon: "0900123456" } }))).kod, "OVERENIE", "bez tokenu");
reset();
assert.deepEqual(await res(req({ typ: "spatne_volanie", turnstile: "tok", data: { meno: "J", obec: "O", telefon: "0900123456", najlepsi_cas: "rano" } })), { ok: true });
const ins = volania.find((v) => v.url.endsWith("/rest/v1/spatne_volania"));
assert.deepEqual(ins.telo, { meno: "J", obec: "O", telefon: "0900123456", najlepsi_cas: "rano" });
delete env.TURNSTILE_SECRET;

// 9) servisny dopyt: validacia + zapis len povolenych stlpcov
reset();
assert.equal((await res(req({ typ: "servisny_dopyt", data: { obec: "O", popis: "x", kontakt_email: "zle" } }))).kod, "NEPLATNE");
assert.equal((await res(req({ typ: "servisny_dopyt", data: { obec: "O", popis: "x".repeat(4001), kontakt_email: "a@b.sk" } }))).kod, "NEPLATNE");
reset();
assert.deepEqual(await res(req({ typ: "servisny_dopyt", data: { obec: "O", popis: "Potrebujeme", kontakt_email: "a@b.sk", kontakt_telefon: "", ico: "123", kraj: "BA", suhlas_zverejnit: true, vybavene: true, schvaleny: true } })), { ok: true });
const sd = volania.find((v) => v.url.endsWith("/rest/v1/servisne_dopyty")).telo;
assert.deepEqual(Object.keys(sd).sort(), ["ico", "kontakt_email", "kontakt_telefon", "kraj", "obec", "popis", "suhlas_zverejnit"]);
assert.equal(sd.suhlas_zverejnit, true);
assert.equal(sd.kontakt_telefon, null);

// 10) upozornenie prevadzkovatelovi pri "Zavolajte mi" aj servise
reset();
await res(req({ typ: "spatne_volanie", data: { meno: "J", obec: "O", telefon: "0900123456" } }));
let up = volania.find((v) => v.url.includes("resend"));
assert.ok(up && up.telo.to[0] === "info@predtendrom.sk" && up.telo.subject.startsWith("Zavolajte mi"), "upozornenie spatne volanie");
reset();
await res(req({ typ: "servisny_dopyt", data: { obec: "O", popis: "P", kontakt_email: "a@b.sk" } }));
up = volania.find((v) => v.url.includes("resend"));
assert.ok(up && up.telo.subject.startsWith("Nový servisný dopyt"), "upozornenie servis");
// zlyhanie e-mailu upozornenia nerozbije odpoved
reset(); resendStatus = 500;
assert.deepEqual(await res(req({ typ: "spatne_volanie", data: { meno: "J", obec: "O", telefon: "0900123456" } })), { ok: true });

console.log("OK verejny-formular");
