// =============================================================================
//  Edge Function: trustpay-initiate
//  Zavola ju prihlaseny pouzivatel (owner/admin firmy) z app.html, ked chce
//  zaplatit/predlzit predplatne. Vytvori riadok v `platby` (cez RPC
//  zaloz_platbu, ktora si sama zisti org podla auth.uid() a cenu vytiahne
//  z `cenove_plany` — suma NIKDY nepride od klienta), pozia OAuth token od
//  finby a zalozi platbu cez ich REST API. Vrati GatewayUrl, na ktory
//  frontend presmeruje prehliadac (window.location.href = gatewayUrl).
//
//  Nasadenie (rob Marek, ja sem service_role/secret kluce nedavam):
//    supabase functions deploy trustpay-initiate
//    supabase secrets set TRUSTPAY_PROJECT_ID=... TRUSTPAY_SECRET_KEY=...
//  SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY / SUPABASE_ANON_KEY su v Edge
//  Functions dostupne automaticky, nemusia sa nastavovat.
// =============================================================================

import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const CORS = {
  "Access-Control-Allow-Origin": "https://predtendrom.sk",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

const FINBY_API = "https://aapi.finby.eu";

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
  const TRUSTPAY_PROJECT_ID = Deno.env.get("TRUSTPAY_PROJECT_ID");
  const TRUSTPAY_SECRET_KEY = Deno.env.get("TRUSTPAY_SECRET_KEY");

  if (!TRUSTPAY_PROJECT_ID || !TRUSTPAY_SECRET_KEY) {
    console.error("TRUSTPAY_PROJECT_ID / TRUSTPAY_SECRET_KEY nie su nastavene");
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

  try {
    // 1. OAuth token (Client Credentials, plati 30 min - na jednu platbu
    //    ho netreba cachovat, vyziadame novy pri kazdom initiate).
    const tokenOdpoved = await fetch(`${FINBY_API}/api/oauth2/token`, {
      method: "POST",
      headers: {
        Authorization: "Basic " + btoa(`${TRUSTPAY_PROJECT_ID}:${TRUSTPAY_SECRET_KEY}`),
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: "grant_type=client_credentials",
    });

    if (!tokenOdpoved.ok) {
      console.error("finby OAuth zlyhalo:", tokenOdpoved.status, await tokenOdpoved.text());
      return json({ ok: false, kod: "FINBY_AUTH_ZLYHALA" }, 502);
    }
    const { access_token } = await tokenOdpoved.json();

    // 2. Zalozenie platby.
    const platbaOdpoved = await fetch(`${FINBY_API}/api/Payments/Payment`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${access_token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        PaymentMethod: "Card",
        MerchantIdentification: { ProjectId: TRUSTPAY_PROJECT_ID },
        PaymentInformation: {
          // finby vyzaduje Amount presne na dve desatinne miesta. JSON cislo
          // to nevie zarucit (34 by sa poslalo ako "34", nie "34.00" - presne
          // takto zlyhavalo s "Amount must have exactly two decimal places"),
          // preto sa posiela ako retazec vyrobeny z toFixed(2).
          Amount: { Amount: Number(platba.suma).toFixed(2), Currency: platba.mena },
          Localization: "SK",
          References: { MerchantReference: platba.reference },
          CardTransaction: { PaymentType: "Purchase" },
        },
        CallbackUrls: {
          Success: `${zaklad}?stav=uspech&ref=${platba.reference}`,
          Cancel: `${zaklad}?stav=zrusene&ref=${platba.reference}`,
          Error: `${zaklad}?stav=chyba&ref=${platba.reference}`,
          Notification: `${SUPABASE_URL}/functions/v1/trustpay-notify`,
        },
      }),
    });

    if (!platbaOdpoved.ok) {
      console.error("finby Payment zlyhalo:", platbaOdpoved.status, await platbaOdpoved.text());
      return json({ ok: false, kod: "FINBY_PLATBA_ZLYHALA" }, 502);
    }

    const vysledok = await platbaOdpoved.json();
    const gatewayUrl: string | undefined = vysledok.GatewayUrl ?? vysledok.gatewayUrl;
    const paymentRequestId: string | null =
      vysledok?.PaymentInformation?.References?.PaymentRequestId ?? null;

    if (!gatewayUrl) {
      console.error("finby Payment bez GatewayUrl:", JSON.stringify(vysledok));
      return json({ ok: false, kod: "FINBY_BEZ_GATEWAY_URL" }, 502);
    }

    // 3. Dopln PaymentRequestId/GatewayUrl na nas riadok (service_role -
    //    doplnit_platbu je grantnuta vyhradne jemu, viz 29_platby.sql).
    const sbServis = createClient(SUPABASE_URL, SERVICE_ROLE_KEY);
    await sbServis.rpc("doplnit_platbu", {
      p_reference: platba.reference,
      p_payment_request_id: paymentRequestId,
      p_gateway_url: gatewayUrl,
    });

    return json({ ok: true, gatewayUrl });
  } catch (e) {
    console.error("trustpay-initiate neocakavana chyba:", e);
    return json({ ok: false, kod: "NEOCAKAVANA_CHYBA" }, 500);
  }
});
