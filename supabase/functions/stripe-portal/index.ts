// =============================================================================
//  Edge Function: stripe-portal (migracia 87, audit 2. 11. 2026)
//  Vlastnik alebo admin firmy si z appky otvori Stripe Customer portal:
//  zrusi automaticku obnovu, zmeni kartu, stiahne faktury. Customer id sa
//  zisti v databaze pod JWT pouzivatela (moj_stripe_zakaznik), nikdy nepride
//  od klienta. Pred pouzitim treba v Stripe zapnut Customer portal
//  (Settings -> Billing -> Customer portal).
//  Nasadenie: Supabase -> Edge Functions -> stripe-portal, Verify JWT vypnute
//  (overuje sa v RPC). Secret STRIPE_SECRET_KEY uz existuje.
// =============================================================================
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const CORS = {
  "Access-Control-Allow-Origin": "https://predtendrom.sk",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

function json(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { ...CORS, "Content-Type": "application/json" } });
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response(null, { headers: CORS });
  if (req.method !== "POST") return json({ ok: false, kod: "METODA" }, 405);
  const auth = req.headers.get("Authorization");
  if (!auth) return json({ ok: false, kod: "NEPRIHLASENY" }, 401);

  const kluc = Deno.env.get("STRIPE_SECRET_KEY");
  if (!kluc) return json({ ok: false, kod: "PLATOBNA_BRANA_NENASTAVENA" }, 500);

  const sb = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_ANON_KEY")!, {
    global: { headers: { Authorization: auth } },
  });
  const { data: zakaznik, error } = await sb.rpc("moj_stripe_zakaznik");
  if (error) {
    console.error("moj_stripe_zakaznik:", error);
    return json({ ok: false, kod: "CHYBA" }, 500);
  }
  if (!zakaznik) return json({ ok: false, kod: "BEZ_PREDPLATNEHO" }, 404);

  const odpoved = await fetch("https://api.stripe.com/v1/billing_portal/sessions", {
    method: "POST",
    headers: { Authorization: `Bearer ${kluc}`, "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ customer: String(zakaznik), return_url: "https://predtendrom.sk/app", locale: "sk" }),
  });
  if (!odpoved.ok) {
    console.error("billing_portal:", odpoved.status, await odpoved.text());
    return json({ ok: false, kod: "STRIPE_PORTAL_ZLYHAL" }, 502);
  }
  const s = await odpoved.json();
  return json({ ok: true, url: s.url });
});
