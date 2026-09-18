// =============================================================================
//  Edge Function: trustpay-notify
//  Verejny webhook - vola ho finby (nie prehliadac), pri kazdej zmene stavu
//  platby. MUSI overit podpis PRED tym, ako co i len pozrie na obsah,
//  inak by hocikto mohol poslat falosne "Paid" a aktivovat si predplatne
//  zadarmo.
//
//  Algoritmus podpisu (z https://doc.finby.eu/aapi#signature, sekcia
//  "Creating a Notification signature"):
//    HMAC-SHA256, kluc = TRUSTPAY_SECRET_KEY.
//    Sprava = VSETKY NEPRAZDNE hodnoty z notifikacie (podla presne
//    definovaneho zoznamu poli), zoradene ASC (ASCII poradie), spojene
//    znakom '/'. Vysledny hash sa prevedie na HEX VELKYMI pismenami a
//    porovna s `Signature` poľom v notifikacii.
//
//  Spracovanie je delegovane na SECURITY DEFINER funkciu
//  spracuj_platbu_trustpay() (29_platby.sql), ktora je idempotentna -
//  opakovana notifikacia (finby vie poslat viackrat) sa aplikuje len raz.
//
//  Nasadenie: supabase functions deploy trustpay-notify --no-verify-jwt
//  (--no-verify-jwt je nutne - finby nepozna nas Supabase JWT, autentifikacia
//  je tu VYHRADNE cez HMAC podpis nizsie, nie cez Supabase Auth).
// =============================================================================

import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

// Poradie poli podla oficialneho "Signature Verification" formulara v
// dokumentacii - presne tieto cesty do notifikacneho JSON-u, v tomto
// poradi kontrolovane na neprazdnost (poradie zoznamu tu nie je poradie
// v podpise - to sa zoraduje az nizsie, ASCII vzostupne).
function ziskajHodnotyProPodpis(n: any): string[] {
  const pi = n.PaymentInformation ?? {};
  const kandidati: (string | number | undefined | null)[] = [
    n?.MerchantIdentification?.ProjectId,
    undefined, // Amount sa dopln samostatne nizsie (presny povodny retazec)
    pi?.Amount?.Currency,
    pi?.References?.MerchantReference,
    pi?.References?.EndToEnd,
    pi?.Status,
    pi?.StatusReasonInformation?.Reason?.Code,
    pi?.StatusReasonInformation?.Reason?.RejectReason,
    pi?.StatusReasonInformation?.Reason?.MerchantAdviceCode,
    pi?.CreditDebitIndicator,
    n?.PaymentMethod,
    pi?.Creditor?.Name ?? pi?.Debtor?.Name,
    pi?.Debtor?.Address?.CountryCode,
    pi?.CreditorAccount?.Iban ?? pi?.DebtorAccount?.Iban,
    pi?.CreditorAgent?.Bic ?? pi?.DebtorAgent?.Bic,
    pi?.SepaDirectDebitInformation?.MandateInformation?.UMR,
    pi?.DebtorAccount?.Other,
    pi?.References?.PaymentRequestId,
    pi?.References?.PaymentId,
    pi?.References?.ClearingSystemReference,
    pi?.References?.OriginalPaymentRequestId,
    pi?.References?.OriginalPaymentId,
    pi?.CardTransaction?.Card?.MaskedPan,
    pi?.CardTransaction?.Card?.ExpiryDate,
    pi?.CardTransaction?.Card?.Token,
    pi?.CardTransaction?.Card?.SubType,
  ];
  return kandidati
    .filter((v) => v !== undefined && v !== null && String(v) !== "")
    .map((v) => String(v));
}

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
    .join("")
    .toUpperCase();
}

Deno.serve(async (req) => {
  if (req.method !== "POST") return new Response("Metoda nepodporovana", { status: 405 });

  const TRUSTPAY_SECRET_KEY = Deno.env.get("TRUSTPAY_SECRET_KEY");
  if (!TRUSTPAY_SECRET_KEY) {
    console.error("TRUSTPAY_SECRET_KEY nie je nastaveny");
    return new Response("Server nenastaveny", { status: 500 });
  }

  const surovyText = await req.text();
  let notifikacia: any;
  try {
    notifikacia = JSON.parse(surovyText);
  } catch {
    return new Response("Neplatny JSON", { status: 400 });
  }

  const prijatyPodpis: string | undefined = notifikacia?.Signature;
  if (!prijatyPodpis) return new Response("Chyba podpis", { status: 400 });

  // Amount sa MUSI pouzit v presne povodnom textovom tvare (napr. "34.00"),
  // nie tak, ako ho JS parsuje a znova vypise cislo (34.00 -> "34", stratil
  // by sa desatinny tvar a podpis by nikdy nesedel). Vytiahneme ho preto
  // priamo regexpom zo suroveho JSON textu - v strukture je presne jedno
  // pole s klucom "Amount", ktore ma za sebou cislo (vonkajsi kluc
  // "Amount" mapuje na objekt "{", takze regex naň nesadne).
  const amountMatch = surovyText.match(/"Amount"\s*:\s*(-?\d+(?:\.\d+)?)/);
  const amountStr = amountMatch
    ? amountMatch[1]
    : notifikacia?.PaymentInformation?.Amount?.Amount !== undefined
    ? String(notifikacia.PaymentInformation.Amount.Amount)
    : undefined;

  const hodnoty = ziskajHodnotyProPodpis(notifikacia);
  if (amountStr) hodnoty.push(amountStr);
  hodnoty.sort(); // ASCII vzostupne, presne ako v dokumentacii

  const sprava = hodnoty.join("/");
  const vypocitanyPodpis = await hmacSha256Hex(TRUSTPAY_SECRET_KEY, sprava);

  if (vypocitanyPodpis !== String(prijatyPodpis).toUpperCase()) {
    console.error("trustpay-notify: neplatny podpis", {
      referencia: notifikacia?.PaymentInformation?.References?.MerchantReference,
    });
    return new Response("Neplatny podpis", { status: 400 });
  }

  const referencia = notifikacia?.PaymentInformation?.References?.MerchantReference;
  const trustpayStatus = notifikacia?.PaymentInformation?.Status; // Paid | Authorized | Rejected
  if (!referencia) return new Response("Chyba referencia", { status: 400 });

  const stav = trustpayStatus === "Paid" ? "zaplatena" : "zamietnuta";

  const sbServis = createClient(
    Deno.env.get("SUPABASE_URL")!,
    Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
  );

  const { data, error } = await sbServis.rpc("spracuj_platbu_trustpay", {
    p_reference: referencia,
    p_stav: stav,
    p_trustpay_status: trustpayStatus ?? null,
  });

  if (error) {
    console.error("spracuj_platbu_trustpay zlyhalo:", error);
    return new Response("Chyba spracovania", { status: 500 });
  }

  console.log("trustpay-notify spracovane:", data);
  return new Response("OK", { status: 200 });
});
