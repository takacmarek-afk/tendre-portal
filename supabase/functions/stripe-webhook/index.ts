// =============================================================================
//  Edge Function: stripe-webhook
//  Nahradza trustpay-notify (prechod finby -> Stripe, dovod a detaily v
//  30_stripe_platby.sql). Verejny webhook - vola ho Stripe (nie
//  prehliadac), pri zmene stavu Checkout Session. MUSI overit podpis PRED
//  tym, ako co i len pozrie na obsah, inak by hocikto mohol poslat falosne
//  "completed" a aktivovat si predplatne zadarmo (rovnaky dovod, aky mala
//  aj predchadzajuca finby integracia).
//
//  Algoritmus podpisu (https://docs.stripe.com/webhooks#verify-manually):
//  hlavicka `Stripe-Signature: t=<unix timestamp>,v1=<hex hmac-sha256>`.
//  Podpisovana sprava je `${t}.${surovy_text_tela}` (bez akehokolvek
//  reparsovania JSON-u - presne surovy text, inak by sa podpis nezhodoval),
//  kluc je STRIPE_WEBHOOK_SECRET (whsec_..., z Stripe Dashboardu - INY
//  kluc nez STRIPE_SECRET_KEY). Timestamp tolerancia 5 minut, tak ako
//  odporuca Stripe dokumentacia - obrana proti prehratiu zachytenej
//  notifikacie.
//
//  Spracovanie je delegovane na SECURITY DEFINER funkciu
//  spracuj_platbu_stripe() (30_stripe_platby.sql), ktora je idempotentna -
//  opakovana notifikacia (Stripe vie poslat viackrat, kym nedostane 2xx)
//  sa aplikuje len raz.
//
//  Nasadenie: supabase functions deploy stripe-webhook --no-verify-jwt
//  (--no-verify-jwt je nutne - Stripe nepozna nas Supabase JWT,
//  autentifikacia je tu VYHRADNE cez HMAC podpis nizsie).
//  Potom v Stripe Dashboarde: Developers -> Webhooks -> Add endpoint:
//    URL:      https://<projekt-ref>.supabase.co/functions/v1/stripe-webhook
//    Udalosti: checkout.session.completed
//              checkout.session.async_payment_succeeded
//              checkout.session.async_payment_failed
//              checkout.session.expired
//  Signing secret, ktory tam Stripe ukaze po vytvoreni endpointu, skopiruj
//  do STRIPE_WEBHOOK_SECRET (supabase secrets set STRIPE_WEBHOOK_SECRET=whsec_...).
// =============================================================================

import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

async function hmacSha256Hex(kluc: string, sprava: string): Promise<string> {
  const enc = new TextEncoder();
  const cryptoKey = await crypto.subtle.importKey(
    "raw",
    enc.encode(kluc),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const podpis = await crypto.subtle.sign("HMAC", cryptoKey, enc.encode(sprava));
  return Array.from(new Uint8Array(podpis))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join(""); // Stripe pouziva malymi pismenami hex (na rozdiel od predoslej finby, ktora chcela VELKE)
}

function rozparsujHlavickuPodpisu(hlavicka: string): { t?: string; v1?: string } {
  const vysledok: Record<string, string> = {};
  for (const cast of hlavicka.split(",")) {
    const [kluc, hodnota] = cast.split("=");
    if (kluc && hodnota) vysledok[kluc.trim()] = hodnota.trim();
  }
  return vysledok;
}

Deno.serve(async (req) => {
  if (req.method !== "POST") return new Response("Metoda nepodporovana", { status: 405 });

  const STRIPE_WEBHOOK_SECRET = Deno.env.get("STRIPE_WEBHOOK_SECRET");
  if (!STRIPE_WEBHOOK_SECRET) {
    console.error("STRIPE_WEBHOOK_SECRET nie je nastaveny");
    return new Response("Server nenastaveny", { status: 500 });
  }

  const hlavickaPodpisu = req.headers.get("stripe-signature");
  if (!hlavickaPodpisu) return new Response("Chyba podpis", { status: 400 });

  // Surovy text tela sa musi precitat PRED akymkolvek JSON.parse - podpis
  // sa pocita nad presnym byte-tvarom, nie nad znovu-serializovanym JSON-om.
  const surovyText = await req.text();

  const { t, v1 } = rozparsujHlavickuPodpisu(hlavickaPodpisu);
  if (!t || !v1) return new Response("Neplatna hlavicka podpisu", { status: 400 });

  const vekSekundy = Math.abs(Date.now() / 1000 - Number(t));
  if (!Number.isFinite(vekSekundy) || vekSekundy > 300) {
    console.error("stripe-webhook: notifikacia mimo tolerancie (prehratie?)", { vekSekundy });
    return new Response("Notifikacia je prilis stara", { status: 400 });
  }

  const vypocitanyPodpis = await hmacSha256Hex(STRIPE_WEBHOOK_SECRET, `${t}.${surovyText}`);
  if (vypocitanyPodpis !== v1) {
    console.error("stripe-webhook: neplatny podpis");
    return new Response("Neplatny podpis", { status: 400 });
  }

  let udalost: any;
  try {
    udalost = JSON.parse(surovyText);
  } catch {
    return new Response("Neplatny JSON", { status: 400 });
  }

  const typ: string = udalost?.type ?? "";
  const NAS_STAV: Record<string, "zaplatena" | "zamietnuta"> = {
    "checkout.session.completed": "zaplatena",
    "checkout.session.async_payment_succeeded": "zaplatena",
    "checkout.session.async_payment_failed": "zamietnuta",
    "checkout.session.expired": "zamietnuta",
  };

  const stav = NAS_STAV[typ];
  if (!stav) {
    // Ina udalost, nez ake su v Stripe Dashboarde pre tento endpoint
    // zapnute (alebo ich niekedy pribudne viac) - potvrd prijatie, nech ju
    // Stripe neskusa opakovane dorucovat, ale nic nesprac.
    return new Response("OK (ignorovane)", { status: 200 });
  }

  const session = udalost?.data?.object;
  // "completed" s payment_status 'unpaid' znamena, ze platba sa este len
  // asynchronne dokoncuje (napr. SEPA prevod) - skutocnu aktivaciu sposobi
  // az nasledujuci "async_payment_succeeded", nie tento event. Pre karty
  // (jediny sposob platby, ktory dnes ponukame) je payment_status vzdy
  // rovno 'paid' priamo v "completed".
  if (typ === "checkout.session.completed" && session?.payment_status !== "paid") {
    return new Response("OK (caka sa na async potvrdenie)", { status: 200 });
  }

  const referencia: string | undefined = session?.client_reference_id ?? session?.metadata?.reference;
  if (!referencia) return new Response("Chyba referencia", { status: 400 });

  const sbServis = createClient(
    Deno.env.get("SUPABASE_URL")!,
    Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
  );

  const { data, error } = await sbServis.rpc("spracuj_platbu_stripe", {
    p_reference: referencia,
    p_stav: stav,
    p_gateway_status: typ,
  });

  if (error) {
    console.error("spracuj_platbu_stripe zlyhalo:", error);
    return new Response("Chyba spracovania", { status: 500 });
  }

  console.log("stripe-webhook spracovane:", data);
  return new Response("OK", { status: 200 });
});
