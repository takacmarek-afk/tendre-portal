// =============================================================================
//  Edge Function: stripe-checkout
//  Nahradza trustpay-initiate (prechod finby -> Stripe, dovod a detaily v
//  30_stripe_platby.sql). Zavola ju prihlaseny pouzivatel (owner/admin
//  firmy) z app.html, ked chce zaplatit/predlzit predplatne. Vytvori
//  riadok v `platby` (cez RPC zaloz_platbu, ktora si sama zisti org podla
//  auth.uid() a cenu vytiahne z `cenove_plany` — suma NIKDY nepride od
//  klienta), zalozi Stripe Checkout Session cez REST API (ziadny SDK,
//  rovnaky styl ako predtym finby) a vrati jej `url`, na ktoru frontend
//  presmeruje prehliadac (window.location.href = gatewayUrl).
//
//  Nasadenie (rob Marek, ja sem secret kluce nedavam):
//    supabase functions deploy stripe-checkout
//    supabase secrets set STRIPE_SECRET_KEY=sk_live_... (alebo sk_test_...)
//  SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY / SUPABASE_ANON_KEY su v Edge
//  Functions dostupne automaticky, nemusia sa nastavovat.
// =============================================================================

import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const CORS = {
  "Access-Control-Allow-Origin": "https://predtendrom.sk",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

const STRIPE_API = "https://api.stripe.com/v1";

const NAZOV_PLANU: Record<string, string> = {
  start: "PredTendrom.sk — Start",
  growth: "PredTendrom.sk — Growth",
};

function json(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { ...CORS, "Content-Type": "application/json" },
  });
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response(null, { headers: CORS });
  if (req.method !== "POST") return json({ ok: false, kod: "METODA" }, 405);

  const authHeader = req.headers.get("Authorization");
  if (!authHeader) return json({ ok: false, kod: "NEPRIHLASENY" }, 401);

  let telo: { plan?: string; obdobie?: string };
  try {
    telo = await req.json();
  } catch {
    return json({ ok: false, kod: "NEPLATNE_TELO" }, 400);
  }

  const plan = telo.plan;
  const obdobie = telo.obdobie;
  if (!plan || !obdobie) return json({ ok: false, kod: "CHYBAJU_PARAMETRE" }, 400);

  const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
  const ANON_KEY = Deno.env.get("SUPABASE_ANON_KEY")!;
  const SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
  const STRIPE_SECRET_KEY = Deno.env.get("STRIPE_SECRET_KEY");

  if (!STRIPE_SECRET_KEY) {
    console.error("STRIPE_SECRET_KEY nie je nastaveny");
    return json({ ok: false, kod: "PLATOBNA_BRANA_NENASTAVENA" }, 500);
  }

  // Klient s JWT prihlaseneho pouzivatela - RPC bezi POD jeho auth.uid(),
  // takze zaloz_platbu() sama overi, ci je owner/admin svojej firmy.
  const sbUzivatel = createClient(SUPABASE_URL, ANON_KEY, {
    global: { headers: { Authorization: authHeader } },
  });

  const { data: platba, error: chybaZalozenia } = await sbUzivatel
    .rpc("zaloz_platbu", { p_plan: plan, p_obdobie: obdobie })
    .single();

  if (chybaZalozenia || !platba) {
    const kod = (chybaZalozenia?.message || "").includes("NEPRIHLASENY")
      ? "NEPRIHLASENY"
      : (chybaZalozenia?.message || "").includes("BEZ_OPRAVNENIA")
      ? "BEZ_OPRAVNENIA"
      : (chybaZalozenia?.message || "").includes("NEZNAMY_PLAN")
      ? "NEZNAMY_PLAN"
      : "CHYBA_ZALOZENIA";
    console.error("zaloz_platbu zlyhalo:", chybaZalozenia);
    return json({ ok: false, kod }, 400);
  }

  const zaklad = "https://predtendrom.sk/platba-vysledok.html";
  // Stripe Checkout ocakava sumu v najmensej menovej jednotke (centy pre
  // EUR). Math.round namiesto priameho *100, aby sa predislo pripadnym
  // floating-point artefaktom (napr. 0.1 + 0.2 problem pri inych sumach).
  const centy = Math.round(Number(platba.suma) * 100);

  const parametre = new URLSearchParams({
    mode: "payment",
    success_url: `${zaklad}?stav=uspech&ref=${platba.reference}`,
    cancel_url: `${zaklad}?stav=zrusene&ref=${platba.reference}`,
    // Oba spoluidentifikatory nastavene na to iste UUID - client_reference_id
    // je pohodlnejsi na citanie v Stripe Dashboarde, metadata.reference je
    // zaloha pre pripad, ze by ho niektory typ udalosti neniesol.
    client_reference_id: platba.reference,
    "metadata[reference]": platba.reference,
    "line_items[0][quantity]": "1",
    "line_items[0][price_data][currency]": String(platba.mena).toLowerCase(),
    "line_items[0][price_data][unit_amount]": String(centy),
    "line_items[0][price_data][product_data][name]":
      `${NAZOV_PLANU[platba.plan] ?? platba.plan} (${platba.obdobie === "rok" ? "ročné" : "mesačné"} predplatné)`,
  });

  try {
    const odpoved = await fetch(`${STRIPE_API}/checkout/sessions`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${STRIPE_SECRET_KEY}`,
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: parametre,
    });

    if (!odpoved.ok) {
      console.error("Stripe Checkout Session zlyhala:", odpoved.status, await odpoved.text());
      return json({ ok: false, kod: "STRIPE_PLATBA_ZLYHALA" }, 502);
    }

    const session = await odpoved.json();
    const gatewayUrl: string | undefined = session.url;

    if (!gatewayUrl) {
      console.error("Stripe Checkout Session bez url:", JSON.stringify(session));
      return json({ ok: false, kod: "STRIPE_BEZ_GATEWAY_URL" }, 502);
    }

    // Dopln session id/url na nas riadok (service_role - doplnit_platbu je
    // grantnuta vyhradne jemu, viz 29_platby.sql).
    const sbServis = createClient(SUPABASE_URL, SERVICE_ROLE_KEY);
    await sbServis.rpc("doplnit_platbu", {
      p_reference: platba.reference,
      p_payment_request_id: session.id ?? null,
      p_gateway_url: gatewayUrl,
    });

    return json({ ok: true, gatewayUrl });
  } catch (e) {
    console.error("stripe-checkout neocakavana chyba:", e);
    return json({ ok: false, kod: "NEOCAKAVANA_CHYBA" }, 500);
  }
});
