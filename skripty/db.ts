// =============================================================================
//  Tenky klient Supabase REST (PostgREST) pre skripty v skripty/*.ts.
//  Bez zavislosti. Kluc: SUPABASE_SERVICE_ROLE_KEY (nikdy nie do prehliadaca,
//  nikdy nevypisovat do logu).
// =============================================================================

export interface Db {
  url: string;
  kluc: string;
  f: typeof fetch;
}

export function db(f: typeof fetch = fetch): Db {
  const url = process.env.SUPABASE_URL;
  const kluc = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !kluc) throw new Error("Chyba SUPABASE_URL alebo SUPABASE_SERVICE_ROLE_KEY");
  return { url: url.replace(/\/$/, ""), kluc, f };
}

function hlavicky(d: Db, extra: Record<string, string> = {}) {
  return { apikey: d.kluc, Authorization: `Bearer ${d.kluc}`, "Content-Type": "application/json", ...extra };
}

async function over(res: Response, co: string) {
  if (!res.ok) throw new Error(`${co}: HTTP ${res.status} ${(await res.text()).slice(0, 300)}`);
}

/** GET so strankovanim (po 1000). cesta napr. "vyzvy_karty?select=*&overene_at=not.is.null" */
export async function citaj<T>(d: Db, cesta: string): Promise<T[]> {
  const out: T[] = [];
  for (let od = 0; ; od += 1000) {
    const res = await d.f(`${d.url}/rest/v1/${cesta}`, { headers: hlavicky(d, { Range: `${od}-${od + 999}` }) });
    await over(res, `GET ${cesta.split("?")[0]}`);
    const kus = (await res.json()) as T[];
    out.push(...kus);
    if (kus.length < 1000) return out;
  }
}

export async function rpc<T>(d: Db, fn: string, telo: Record<string, unknown> = {}): Promise<T> {
  const res = await d.f(`${d.url}/rest/v1/rpc/${fn}`, { method: "POST", headers: hlavicky(d), body: JSON.stringify(telo) });
  await over(res, `RPC ${fn}`);
  return (await res.json()) as T;
}

/** Vlozi riadky. rezim "ignoruj" = existujuce (podla kluca) nechaj, "prepis" = upsert. */
export async function vloz(d: Db, tabulka: string, riadky: unknown[], kluc: string, rezim: "ignoruj" | "prepis") {
  if (!riadky.length) return;
  const res = await d.f(`${d.url}/rest/v1/${tabulka}?on_conflict=${kluc}`, {
    method: "POST",
    headers: hlavicky(d, {
      Prefer: `resolution=${rezim === "prepis" ? "merge-duplicates" : "ignore-duplicates"},return=minimal`,
    }),
    body: JSON.stringify(riadky),
  });
  await over(res, `POST ${tabulka}`);
}

export async function uprav(d: Db, cesta: string, zmena: Record<string, unknown>): Promise<number> {
  const res = await d.f(`${d.url}/rest/v1/${cesta}`, {
    method: "PATCH", headers: hlavicky(d, { Prefer: "return=representation" }), body: JSON.stringify(zmena),
  });
  await over(res, `PATCH ${cesta.split("?")[0]}`);
  return ((await res.json()) as unknown[]).length;
}

// Farby do konzoly (vypnute, ked vystup nejde do terminalu alebo NO_COLOR)
const farby = process.stdout.isTTY && !process.env.NO_COLOR;
const c = (k: string) => (s: string) => (farby ? `\x1b[${k}m${s}\x1b[0m` : s);
export const F = { tucne: c("1"), seda: c("90"), zelena: c("32"), zlta: c("33"), cervena: c("31"), modra: c("36") };
