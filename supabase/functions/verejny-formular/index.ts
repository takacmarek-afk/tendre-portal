// =============================================================================
//  Edge Function: verejny-formular  (vlna 81, 6. 10. 2026)
//  Jediny vstup pre VEREJNE formulare bez prihlasenia:
//     typ = "odber_obce"      (obce.html)    -> prihlasenie na prehlady + potvrdzovaci e-mail
//     typ = "servisny_dopyt"  (servis.html)  -> tabulka servisne_dopyty
//     typ = "spatne_volanie"  (starosta.html)-> tabulka spatne_volania
//     typ = "kontrola_ico"    (kontrola.html)-> RPC kontrola_zmluv_ico (vlna 84;
//                                od migracie 69 ju anon priamo volat nemoze)
//     typ = "profil_obstaravatela" (obstaravatel.html) -> RPC profil_obstaravatela (migracia 70)
//
//  PREC? Doteraz stranky zapisovali priamo cez REST (anon kluc). To sa nedalo
//  chranit captchou ani limitom na jedneho navstevnika. Tato funkcia:
//    1) overi Cloudflare Turnstile (ak je nastavene tajomstvo TURNSTILE_SECRET;
//       bez neho prechadza bez overenia a zapise varovanie do logu),
//    2) obmedzi pocet pokusov na jednu IP (ulozenu len ako SHA-256 odtlacok),
//    3) validuje vstup a zapise ho cez service_role,
//    4) pri odbere obci posle potvrdzovaci e-mail (double opt-in) a pritom
//       NIKDY neprezradi, ci adresa uz v zozname je (odpoved je vzdy rovnaka).
//  Po nasadeni tejto funkcie a novych stranok sa migraciou 66 odoberu priame
//  zapisy anonyma do tychto troch tabuliek.
//
//  Vstup:  POST { typ, turnstile, data: { ... } }
//  Odpoved: { ok: true }  alebo  { ok: false, kod: "OVERENIE" | "PRILIS_VELA" |
//           "NEPLATNE" | "CHYBA" }
//
//  Nastavenie (Edge Functions -> Secrets):
//    RESEND_API_KEY      (uz nastavene)
//    TURNSTILE_SECRET    tajny kluc Turnstile (zadava Marek sam)
//    IP_SALT             volitelne, nahodny retazec pre odtlacky IP
//    ODOSIELATEL         volitelne
//  "Verify JWT with legacy secret" musi byt VYPNUTE (rovnako ako pri
//  potvrd-odber-email), lebo publikovatelny kluc nie je JWT.
// =============================================================================

const POVOLENY_ORIGIN = "https://predtendrom.sk";
const PREDMET = "Potvrďte odber prehľadov pre obce — PredTendrom.sk";

const CORS = {
  "Access-Control-Allow-Origin": POVOLENY_ORIGIN,
  "Access-Control-Allow-Headers": "apikey, authorization, content-type, x-client-info",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Vary": "Origin",
};

const EMAIL_RE = /^[^@\s,;<>"]+@[^@\s,;<>"]+\.[A-Za-z]{2,}$/;

function json(telo: Record<string, unknown>, stav = 200): Response {
  return new Response(JSON.stringify(telo), {
    status: stav,
    headers: { ...CORS, "Content-Type": "application/json" },
  });
}

function bezpecne(t: unknown): string {
  return String(t ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function retazec(v: unknown, max: number): string | null {
  if (v === null || v === undefined) return null;
  const t = String(v).trim();
  if (t === "") return null;
  return t.length > max ? null : t;
}

// ── E-mail (rovnaky obsah ako v potvrd-odber-email) ─────────────────────────
export function odkazPotvrdenia(token: string): string {
  return `https://predtendrom.sk/odber-obce?t=${encodeURIComponent(token)}&akcia=potvrdit`;
}

export function textEmailu(odkaz: string): string {
  return "Dobrý deň,\n\n" +
    "niekto (pravdepodobne Vy) zadal túto adresu na predtendrom.sk/obce, " +
    "aby dostával prehľad, aké peniaze môže obec získať.\n\n" +
    `Ak ste to boli Vy, potvrďte odber: ${odkaz}\n\n` +
    "Ak nie, nič nerobte — e-maily Vám posielať nebudeme.\n\nPredTendrom.sk\n";
}

export function htmlEmailu(odkaz: string): string {
  const uvod = "Dobrý deň, niekto (pravdepodobne Vy) zadal túto adresu na " +
    "predtendrom.sk/obce, aby dostával prehľad, aké peniaze môže obec získať. " +
    "Ak ste to boli Vy, potvrďte odber kliknutím na tlačidlo nižšie.";
  return `<!doctype html>
<html lang="sk"><body style="margin:0;padding:0;background:#f5f6f8;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f5f6f8;">
<tr><td align="center" style="padding:24px 12px;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
         style="max-width:560px;background:#ffffff;border:1px solid #e4e8ee;border-radius:8px;">
    <tr><td style="padding:22px 24px 0;">
      <div style="font:700 17px/1.2 Arial,sans-serif;color:#0f1a2b;">
        PredTendrom<span style="color:#1a56c4;">.sk</span></div>
    </td></tr>
    <tr><td style="padding:16px 24px 0;">
      <div style="font:700 20px/1.3 Arial,sans-serif;color:#0f1a2b;">Potvrďte odber prehľadov pre obce</div>
      <div style="font:14px/1.6 Arial,sans-serif;color:#5a6472;margin-top:8px;">${bezpecne(uvod)}</div>
    </td></tr>
    <tr><td style="padding:22px 24px;">
      <a href="${bezpecne(odkaz)}" style="display:inline-block;background:#0f1a2b;color:#ffffff;
         font:600 15px/1 Arial,sans-serif;text-decoration:none;padding:13px 22px;border-radius:6px;">
        Potvrdiť odber</a>
    </td></tr>
    <tr><td style="padding:0 24px 22px;">
      <div style="font:12px/1.6 Arial,sans-serif;color:#8a929e;border-top:1px solid #e4e8ee;padding-top:14px;">
        Údaje pochádzajú z Centrálneho registra zmlúv a zo služby Slovensko.Digital.
        Majú informatívny charakter, pred rozhodnutím si ich overte v zdroji.<br><br>
        Ak ste to nezadali Vy, nič nerobte — e-maily Vám posielať nebudeme.<br>
        LoveHome s.r.o., Černyševského 40, 851 01 Bratislava, IČO 47 586 362
      </div>
    </td></tr>
  </table>
</td></tr></table></body></html>`;
}

// ── Pomocne volania ─────────────────────────────────────────────────────────
async function odtlacokIp(ip: string, sol: string): Promise<string> {
  const data = new TextEncoder().encode(`${sol}|${ip}`);
  const h = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(h)).map((b) => b.toString(16).padStart(2, "0")).join("");
}

function ipZ(req: Request): string {
  const cf = req.headers.get("cf-connecting-ip");
  if (cf) return cf.trim();
  const xff = req.headers.get("x-forwarded-for");
  if (xff) return xff.split(",")[0].trim();
  return "neznama";
}

async function overTurnstile(secret: string, token: string, ip: string): Promise<boolean> {
  if (!token || token.length > 4096) return false;
  try {
    const telo = new URLSearchParams({ secret, response: token });
    if (ip && ip !== "neznama") telo.set("remoteip", ip);
    const r = await fetch("https://challenges.cloudflare.com/turnstile/v0/siteverify", {
      method: "POST",
      body: telo,
    });
    if (!r.ok) return false;
    const j = await r.json();
    return j?.success === true;
  } catch (_) {
    return false;
  }
}

type Ctx = { url: string; hlavicky: Record<string, string>; resend: string | undefined; od: string };

async function rpc(c: Ctx, nazov: string, telo: Record<string, unknown>): Promise<unknown> {
  const r = await fetch(`${c.url}/rest/v1/rpc/${nazov}`, {
    method: "POST",
    headers: c.hlavicky,
    body: JSON.stringify(telo),
  });
  if (!r.ok) throw new Error(`rpc ${nazov} HTTP ${r.status}`);
  const t = await r.text();
  return t ? JSON.parse(t) : null;
}

async function vloz(c: Ctx, tabulka: string, riadok: Record<string, unknown>): Promise<boolean> {
  const r = await fetch(`${c.url}/rest/v1/${tabulka}`, {
    method: "POST",
    headers: { ...c.hlavicky, Prefer: "return=minimal" },
    body: JSON.stringify(riadok),
  });
  if (!r.ok) console.error(`verejny-formular: insert ${tabulka} HTTP ${r.status}`);
  return r.ok;
}

// Upozornenie prevadzkovatelovi: o "Zavolajte mi" a servisnom dopyte sa inak
// nikto nedozvie (citaju sa len v Supabase Studiu). Zlyhanie nic nerozbije.
async function upozorni(c: Ctx, predmet: string, riadky: Array<[string, string | null]>): Promise<void> {
  if (!c.resend) return;
  const komu = Deno.env.get("NOTIFIKACIA_KOMU") ?? "info@predtendrom.sk";
  const text = riadky.map(([k, v]) => `${k}: ${v ?? "—"}`).join("\n") +
    "\n\n(Automatické upozornenie z predtendrom.sk. Záznam nájdete v Supabase.)\n";
  try {
    const r = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: { Authorization: `Bearer ${c.resend}`, "Content-Type": "application/json" },
      body: JSON.stringify({ from: c.od, to: [komu], subject: predmet, text }),
    });
    if (r.status !== 200 && r.status !== 201) console.error("verejny-formular: upozornenie HTTP", r.status);
  } catch (e) {
    console.error("verejny-formular: upozornenie zlyhalo", String(e));
  }
}

// ── Obsluha typov ───────────────────────────────────────────────────────────
async function odberObce(c: Ctx, d: Record<string, unknown>): Promise<Response> {
  const email = String(d.email ?? "").trim();
  const obec = retazec(d.obec, 200);
  if (email.length < 5 || email.length > 254 || !EMAIL_RE.test(email) || !obec) {
    return json({ ok: false, kod: "NEPLATNE" });
  }
  const zdroj = retazec(d.zdroj, 80) ?? "obce.html";
  try {
    await rpc(c, "prihlas_odber_obce", {
      p_email: email, p_obec: obec, p_ico: retazec(d.ico, 20),
      p_kraj: retazec(d.kraj, 80), p_zdroj: zdroj,
    });
    // Atomicky "zaber" — e-mail dostane len ten, kto riadok zabral. Adresa,
    // ktorej predosly e-mail sa stratil, dostane novy po 10 minutach
    // (najviac 3 pokusy), uz potvrdena adresa nedostane nic.
    const riadky = await rpc(c, "zaber_potvrdenie_odberu", { p_email: email }) as
      Array<{ id: number; email: string; token: string }> | null;
    if (c.resend && Array.isArray(riadky)) {
      for (const r of riadky) {
        const komu = String(r.email ?? "").trim();
        if (!r.token || !EMAIL_RE.test(komu)) continue;
        const odkaz = odkazPotvrdenia(String(r.token));
        let poslane = false;
        try {
          const rs = await fetch("https://api.resend.com/emails", {
            method: "POST",
            headers: { Authorization: `Bearer ${c.resend}`, "Content-Type": "application/json" },
            body: JSON.stringify({
              from: c.od, to: [komu], reply_to: "info@predtendrom.sk", subject: PREDMET,
              html: htmlEmailu(odkaz), text: textEmailu(odkaz),
            }),
          });
          poslane = rs.status === 200 || rs.status === 201;
          if (!poslane) console.error("verejny-formular: Resend HTTP", rs.status);
        } catch (e) {
          console.error("verejny-formular: siet zlyhala", String(e));
        }
        if (!poslane) {
          await rpc(c, "vrat_potvrdenie_odberu", { p_id: r.id }).catch(() => {});
        }
      }
    }
  } catch (e) {
    console.error("verejny-formular: odber_obce", String(e));
    return json({ ok: false, kod: "CHYBA" });
  }
  return json({ ok: true });
}

async function servisnyDopyt(c: Ctx, d: Record<string, unknown>): Promise<Response> {
  const obec = retazec(d.obec, 200);
  const popis = retazec(d.popis, 4000);
  const email = String(d.kontakt_email ?? "").trim();
  const telefon = retazec(d.kontakt_telefon, 40);
  if (!obec || !popis || email.length < 5 || email.length > 254 || !EMAIL_RE.test(email)) {
    return json({ ok: false, kod: "NEPLATNE" });
  }
  if (telefon !== null && telefon.length < 5) return json({ ok: false, kod: "NEPLATNE" });
  const ok = await vloz(c, "servisne_dopyty", {
    obec, popis, kontakt_email: email, kontakt_telefon: telefon,
    ico: retazec(d.ico, 20), kraj: retazec(d.kraj, 80),
    suhlas_zverejnit: d.suhlas_zverejnit === true,
  });
  if (ok) {
    await upozorni(c, `Nový servisný dopyt: ${obec}`, [
      ["Obec", obec], ["IČO", retazec(d.ico, 20)], ["Kraj", retazec(d.kraj, 80)],
      ["E-mail", email], ["Telefón", telefon], ["Popis", popis],
    ]);
  }
  return ok ? json({ ok: true }) : json({ ok: false, kod: "CHYBA" });
}

async function spatneVolanie(c: Ctx, d: Record<string, unknown>): Promise<Response> {
  const meno = retazec(d.meno, 120);
  const obec = retazec(d.obec, 200);
  const telefon = retazec(d.telefon, 40);
  if (!meno || !obec || !telefon || telefon.length < 5 || !/\d/.test(telefon)) {
    return json({ ok: false, kod: "NEPLATNE" });
  }
  const ok = await vloz(c, "spatne_volania", {
    meno, obec, telefon, najlepsi_cas: retazec(d.najlepsi_cas, 200),
  });
  if (ok) {
    await upozorni(c, `Zavolajte mi: ${obec}`, [
      ["Meno", meno], ["Obec", obec], ["Telefón", telefon],
      ["Najlepší čas", retazec(d.najlepsi_cas, 200)],
    ]);
  }
  return ok ? json({ ok: true }) : json({ ok: false, kod: "CHYBA" });
}

// Kontrola zmlúv podľa IČO (vlna 84): RPC vracia len agregáty a 3 riadky teaseru.
// Pred touto funkciou ju volal priamo prehliadač s anon kľúčom, takže robot mohol
// prechádzať IČO bez overenia. Teraz ide cez Turnstile + limit na IP.
async function hladajPodlaIco(c: Ctx, rpcNazov: string, d: Record<string, unknown>): Promise<Response> {
  const ico = retazec(d.ico, 20);
  if (!ico) return json({ ok: false, kod: "NEPLATNE" });
  try {
    const r = await fetch(`${c.url}/rest/v1/rpc/${rpcNazov}`, {
      method: "POST",
      headers: c.hlavicky,
      body: JSON.stringify({ p_ico: ico }),
    });
    if (!r.ok) {
      let kod = "";
      try { kod = String((await r.json())?.code ?? ""); } catch (_) { /* telo nie je JSON */ }
      if (kod === "54000" || r.status === 429) return json({ ok: false, kod: "PRILIS_VELA" }, 429);
      console.error(`verejny-formular: ${rpcNazov} HTTP ${r.status}`);
      return json({ ok: false, kod: "CHYBA" });
    }
    return json({ ok: true, data: await r.json() });
  } catch (e) {
    console.error(`verejny-formular: ${rpcNazov}`, String(e));
    return json({ ok: false, kod: "CHYBA" });
  }
}

export async function obsluz(req: Request): Promise<Response> {
  if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: CORS });
  if (req.method !== "POST") return json({ ok: false, kod: "METODA" }, 405);

  const url = Deno.env.get("SUPABASE_URL");
  const servis = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  if (!url || !servis) {
    console.error("verejny-formular: chyba SUPABASE_URL / SERVICE_ROLE_KEY");
    return json({ ok: false, kod: "CHYBA" }, 500);
  }
  const c: Ctx = {
    url,
    hlavicky: { apikey: servis, Authorization: `Bearer ${servis}`, "Content-Type": "application/json" },
    resend: Deno.env.get("RESEND_API_KEY") ?? undefined,
    od: Deno.env.get("ODOSIELATEL") ?? "PredTendrom.sk <noreply@predtendrom.sk>",
  };

  let telo: Record<string, unknown>;
  try {
    telo = await req.json();
  } catch (_) {
    return json({ ok: false, kod: "NEPLATNE" }, 400);
  }
  const typ = String(telo?.typ ?? "");
  const d = (telo?.data && typeof telo.data === "object") ? telo.data as Record<string, unknown> : {};
  if (!["odber_obce", "servisny_dopyt", "spatne_volanie", "kontrola_ico", "profil_obstaravatela"].includes(typ)) {
    return json({ ok: false, kod: "NEPLATNE" }, 400);
  }

  const ip = ipZ(req);

  // 1) Turnstile (ak je nastavene tajomstvo).
  const secret = Deno.env.get("TURNSTILE_SECRET");
  if (secret) {
    const ok = await overTurnstile(secret, String(telo?.turnstile ?? ""), ip);
    if (!ok) return json({ ok: false, kod: "OVERENIE" });
  } else {
    console.warn("verejny-formular: TURNSTILE_SECRET nie je nastavene — overenie sa preskakuje");
  }

  // 2) Limity na IP: formulare 5 / hodinu na typ a 15 / hodinu spolu; kontrola IČO
  //    je vyhladavanie (nie zapis), preto 30 / hodinu a nezapocitava sa do "spolu".
  const sol = Deno.env.get("IP_SALT") ?? servis.slice(-24);
  const h = await odtlacokIp(ip, sol);
  const jeKontrola = typ === "kontrola_ico" || typ === "profil_obstaravatela";
  try {
    const vTypu = await rpc(c, "verejny_formular_strop", { p_ip_hash: h, p_typ: typ, p_max: jeKontrola ? 30 : 5, p_minut: 60 });
    // Vyhladavania maju navyse spolocny strop pre vsetkych navstevnikov (ochrana pred
    // distribuovanym zberom z viacerych IP): 1 200 dopytov za hodinu na typ.
    const celkovo = jeKontrola && vTypu
      ? await rpc(c, "verejny_formular_strop", { p_ip_hash: "*", p_typ: typ, p_max: 1200, p_minut: 60 })
      : true;
    const spolu = jeKontrola ? (vTypu && celkovo)
      : (vTypu ? await rpc(c, "verejny_formular_strop", { p_ip_hash: h, p_typ: "spolu", p_max: 15, p_minut: 60 }) : false);
    if (!vTypu || !spolu) return json({ ok: false, kod: "PRILIS_VELA" }, 429);
  } catch (e) {
    console.error("verejny-formular: strop", String(e));
    return json({ ok: false, kod: "CHYBA" });
  }

  // 3) Samotny zapis.
  if (typ === "kontrola_ico") return await hladajPodlaIco(c, "kontrola_zmluv_ico", d);
  if (typ === "profil_obstaravatela") return await hladajPodlaIco(c, "profil_obstaravatela", d);
  if (typ === "odber_obce") return await odberObce(c, d);
  if (typ === "servisny_dopyt") return await servisnyDopyt(c, d);
  return await spatneVolanie(c, d);
}

// deno-lint-ignore no-explicit-any
const D = (globalThis as any).Deno;
if (D && typeof D.serve === "function") D.serve(obsluz);
