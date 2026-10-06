// =============================================================================
//  Edge Function: potvrd-odber-email  (vlna 79, 5. 10. 2026)
//  Okamzite posle potvrdzovaci e-mail (double opt-in) po prihlaseni na odber
//  prehladov pre obce. Doteraz ho posielal az planovany GitHub workflow, ktory
//  GitHub spusta nepravidelne (po hodinach). Tento workflow zostava ako
//  zalozna cesta (posli_potvrdenie_odberu.py v dopyty-email.yml).
//
//  Vola ju prehliadac zo stranky /obce hned po uspesnom zapise do odber_obce:
//      POST { "email": "<adresa>" }   (hlavicky apikey + Authorization: anon)
//
//  BEZPECNOST
//   - Verejne volatelna, preto robi len to, co by spravil aj cron: najde riadok
//     odber_obce s TOUTO adresou, ktory je nepotvrdeny a este nema vycerpane
//     pokusy (max. 3, aspon 10 minut medzi nimi) a je mladsi nez 3 dni. Poslat sa da najviac raz na
//     riadok (riadok sa "zabere" atomicky pred odoslanim). Adresa, ktoru
//     vyplnil niekto iny, dostane najviac jeden e-mail — rovnako ako pri crone.
//   - Odpoved je vzdy rovnaka ({ok:true}), neprezradza, ci adresa v zozname je.
//   - E-mail ide vzdy na adresu z DB riadku, nikdy na hodnotu z poziadavky.
//   - Odkaz v e-maile vedie len na https://predtendrom.sk/odber-obce.
//
//  Premenne prostredia: SUPABASE_URL a SUPABASE_SERVICE_ROLE_KEY dodava
//  Supabase sam. RESEND_API_KEY treba nastavit (Edge Functions -> Secrets).
//  Volitelne ODOSIELATEL (predvolene "PredTendrom.sk <noreply@predtendrom.sk>").
// =============================================================================

const POVOLENY_ORIGIN = "https://predtendrom.sk";
const PREDMET = "Potvrďte odber prehľadov pre obce — PredTendrom.sk";

const CORS = {
  "Access-Control-Allow-Origin": POVOLENY_ORIGIN,
  "Access-Control-Allow-Headers": "apikey, authorization, content-type, x-client-info",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Vary": "Origin",
};

function odpoved(stav = 200): Response {
  return new Response(JSON.stringify({ ok: true }), {
    status: stav,
    headers: { ...CORS, "Content-Type": "application/json" },
  });
}

function bezpecne(t: unknown): string {
  return String(t ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

const EMAIL_RE = /^[^@\s,;<>"]+@[^@\s,;<>"]+\.[A-Za-z]{2,}$/;

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

// Rovnaky vzhlad ako _obal() v pipeline/posli_email.py (tabulkovy layout,
// inline styly, funguje aj v Outlooku).
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

export async function obsluz(req: Request): Promise<Response> {
  if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: CORS });
  if (req.method !== "POST") return odpoved(405);

  const url = Deno.env.get("SUPABASE_URL");
  const servis = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  const resend = Deno.env.get("RESEND_API_KEY");
  const od = Deno.env.get("ODOSIELATEL") ?? "PredTendrom.sk <noreply@predtendrom.sk>";
  if (!url || !servis || !resend) {
    console.error("potvrd-odber-email: chyba SUPABASE_URL / SERVICE_ROLE_KEY / RESEND_API_KEY");
    return odpoved(); // zalozna cesta (cron) to dorobi
  }

  let email = "";
  try {
    const telo = await req.json();
    email = String(telo?.email ?? "").trim();
  } catch (_) {
    return odpoved();
  }
  if (email.length < 5 || email.length > 254 || !EMAIL_RE.test(email)) return odpoved();

  const hlavicky = {
    apikey: servis,
    Authorization: `Bearer ${servis}`,
    "Content-Type": "application/json",
  };
  try {
    // Atomicky "zaber" cez RPC (migracia 65): najviac 3 pokusy na riadok,
    // medzi pokusmi aspon 10 minut. E-mail dostane len ten, kto riadok zabral.
    const zabrat = await fetch(`${url}/rest/v1/rpc/zaber_potvrdenie_odberu`, {
      method: "POST",
      headers: hlavicky,
      body: JSON.stringify({ p_email: email }),
    });
    if (!zabrat.ok) {
      console.error("potvrd-odber-email: zabratie riadku zlyhalo", zabrat.status);
      return odpoved();
    }
    const riadky = await zabrat.json();
    if (!Array.isArray(riadky) || riadky.length === 0) return odpoved();

    for (const r of riadky) {
      const komu = String(r.email ?? "").trim();
      if (!r.token || !EMAIL_RE.test(komu)) continue;
      const odkaz = odkazPotvrdenia(String(r.token));
      let poslane = false;
      try {
        const rs = await fetch("https://api.resend.com/emails", {
          method: "POST",
          headers: { Authorization: `Bearer ${resend}`, "Content-Type": "application/json" },
          body: JSON.stringify({
            from: od, to: [komu], reply_to: "info@predtendrom.sk", subject: PREDMET,
            html: htmlEmailu(odkaz), text: textEmailu(odkaz),
          }),
        });
        poslane = rs.status === 200 || rs.status === 201;
        if (!poslane) console.error("potvrd-odber-email: Resend HTTP", rs.status);
      } catch (e) {
        console.error("potvrd-odber-email: siet zlyhala", String(e));
      }
      if (!poslane) {
        // Vratit riadok do stavu "caka", nech to zopakuje zalozny cron.
        await fetch(`${url}/rest/v1/rpc/vrat_potvrdenie_odberu`, {
          method: "POST",
          headers: hlavicky,
          body: JSON.stringify({ p_id: r.id }),
        }).catch(() => {});
      }
    }
  } catch (e) {
    console.error("potvrd-odber-email: neocakavana chyba", String(e));
  }
  return odpoved();
}

Deno.serve(obsluz);
