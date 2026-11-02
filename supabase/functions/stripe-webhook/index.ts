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
//              charge.refunded          (refund -> zapis do events, 79_refundy_a_spory.sql)
//              charge.dispute.created   (spor u banky -> zapis do events)
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

  // Refund a spor (79_refundy_a_spory.sql). Nesu len payment_intent, nie nasu
  // referenciu, preto sa sparuju cez platby.payment_intent. Predplatne sa
  // nevypina automaticky: zapise sa udalost a ty rozhodnes.
  if (typ === "charge.refunded" || typ === "charge.dispute.created") {
    const obj = udalost?.data?.object;
    const paymentIntent: string | undefined = obj?.payment_intent;
    const sumaMinor: number = typ === "charge.refunded" ? (obj?.amount_refunded ?? 0) : (obj?.amount ?? 0);
    const plna: boolean = typ === "charge.refunded" ? obj?.refunded === true : true;
    if (!paymentIntent) return new Response("OK (bez payment_intent)", { status: 200 });

    const sbRefund = createClient(
      Deno.env.get("SUPABASE_URL")!,
      Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
    );
    const { data: dRefund, error: eRefund } = await sbRefund.rpc("spracuj_refund_stripe", {
      p_payment_intent: paymentIntent,
      p_udalost: typ,
      p_suma: sumaMinor / 100,
      p_plna: plna,
    });
    if (eRefund) {
      console.error("spracuj_refund_stripe zlyhalo:", eRefund);
      return new Response("Chyba spracovania", { status: 500 });
    }
    console.log("stripe-webhook refund/spor:", dRefund);
    return new Response("OK", { status: 200 });
  }
  // ── Automaticky obnovovane predplatne (migracia 87) ─────────────────────
  if (typ === "invoice.paid" || typ === "customer.subscription.updated" || typ === "customer.subscription.deleted") {
    const obj = udalost?.data?.object ?? {};
    const sbPred = createClient(
      Deno.env.get("SUPABASE_URL")!,
      Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
    );
    if (typ === "invoice.paid") {
      // Prvu fakturu (subscription_create) spracuje checkout.session.completed.
      if (obj.billing_reason !== "subscription_cycle") {
        return new Response("OK (prva faktura)", { status: 200 });
      }
      const subId: string | undefined = typeof obj.subscription === "string"
        ? obj.subscription
        : obj.parent?.subscription_details?.subscription ?? obj.subscription?.id;
      const koniec = Number(obj.lines?.data?.[0]?.period?.end ?? obj.period_end ?? 0);
      if (!subId) return new Response("OK (bez predplatneho)", { status: 200 });
      const { data: d, error: e } = await sbPred.rpc("obnov_predplatne_stripe", {
        p_subscription_id: subId,
        p_invoice_id: obj.id,
        p_suma: Number(obj.amount_paid ?? 0) / 100,
        p_obdobie_do: koniec > 0 ? new Date(koniec * 1000).toISOString() : null,
      });
      if (e) {
        console.error("obnov_predplatne_stripe zlyhalo:", e);
        return new Response("Chyba spracovania", { status: 500 });
      }
      console.log("stripe-webhook obnova:", d);
      return new Response("OK", { status: 200 });
    }
    // Zrusenie v portali = cancel_at_period_end; pristup ostava do konca obdobia.
    const aktivne = typ === "customer.subscription.updated" &&
      !obj.cancel_at_period_end && !obj.cancel_at && ["active", "trialing", "past_due"].includes(obj.status);
    const { data: d, error: e } = await sbPred.rpc("nastav_obnovu_stripe", {
      p_subscription_id: obj.id,
      p_auto: aktivne,
    });
    if (e) {
      console.error("nastav_obnovu_stripe zlyhalo:", e);
      return new Response("Chyba spracovania", { status: 500 });
    }
    console.log("stripe-webhook predplatne:", d);
    return new Response("OK", { status: 200 });
  }

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

  // Uloz payment_intent, aby sa neskorsi refund/spor dal sparovat s platbou.
  // Chyba tu platbu nezastavi (aktivacia uz prebehla).
  if (stav === "zaplatena" && session?.payment_intent) {
    const { error: ePi } = await sbServis.rpc("zapis_payment_intent", {
      p_reference: referencia,
      p_payment_intent: session.payment_intent,
    });
    if (ePi) console.error("zapis_payment_intent zlyhalo:", ePi);
  }

  // Rezim predplatneho: ulozit subscription a customer id (migracia 87).
  if (stav === "zaplatena" && session?.mode === "subscription" && session?.subscription) {
    const { error: ePred } = await sbServis.rpc("prepoj_predplatne_stripe", {
      p_reference: referencia,
      p_subscription_id: typeof session.subscription === "string" ? session.subscription : session.subscription?.id,
      p_customer_id: typeof session.customer === "string" ? session.customer : session.customer?.id ?? null,
      p_invoice_id: typeof session.invoice === "string" ? session.invoice : session.invoice?.id ?? null,
    });
    if (ePred) {
      console.error("prepoj_predplatne_stripe zlyhalo:", ePred);
      return new Response("Chyba spracovania", { status: 500 });
    }
  }

  console.log("stripe-webhook spracovane:", data);
  return new Response("OK", { status: 200 });
});
