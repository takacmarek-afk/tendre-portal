// =============================================================================
//  Automaticke spustenie SQL migracii proti produkcnej databaze (bez klikania
//  v SQL editore).
//
//  Spustenie:
//    SUPABASE_DB_URL="postgresql://postgres.<ref>:<heslo>@aws-...pooler.supabase.com:5432/postgres" \
//    node --experimental-strip-types skripty/spusti-migracie.ts 89 90 91
//
//  SUPABASE_DB_URL: Supabase › Connect › Session pooler (port 5432). Je v nom
//  heslo databazy: nikdy ho necommitovat ani nevypisovat.
//
//  Ako to funguje:
//    - kazdu migraciu (supabase/<cislo>_*.sql) spusti v samostatnej transakcii;
//      pri chybe sa cela migracia vrati a skript skonci s chybou
//    - zaznam o spusteni (nazov + SHA-256 obsahu) ulozi do public.schema_migracie;
//      rovnaka migracia s rovnakym obsahom sa druhy raz preskoci
//    - nase migracie su napisane tak, ze sa daju spustit opakovane, takze
//      aj spustenie zmenenej migracie je bezpecne (vypise upozornenie)
// =============================================================================

import { readFileSync, readdirSync } from "node:fs";
import { createHash } from "node:crypto";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import postgres from "postgres";

const KOREN = join(dirname(fileURLToPath(import.meta.url)), "..");
const PRIECINOK = join(KOREN, "supabase");

/** "89" -> "89_vyzvy_karty.sql" (presne jeden subor s danym cislom). */
export function najdiSubor(cislo: string, subory: string[]): string {
  const k = subory.filter((s) => s.startsWith(`${cislo}_`) && s.endsWith(".sql"));
  if (k.length !== 1) throw new Error(`Migracia ${cislo}: ${k.length ? "viac suborov: " + k.join(", ") : "subor sa nenasiel"}`);
  return k[0];
}

async function main() {
  const cisla = process.argv.slice(2).filter((a) => /^\d+$/.test(a));
  if (!cisla.length) throw new Error("Zadajte cisla migracii, napr. 89 90 91");
  const url = process.env.SUPABASE_DB_URL;
  if (!url) throw new Error("Chyba SUPABASE_DB_URL (Supabase › Connect › Session pooler).");

  const subory = readdirSync(PRIECINOK);
  const plan = cisla.map((c) => najdiSubor(c, subory));

  // ssl: Supabase vyzaduje sifrovanie; onnotice: NOTICE z "if not exists" nevypisovat
  const sql = postgres(url, { ssl: process.env.PGSSLMODE === "disable" ? false : "require", max: 1, onnotice: () => {}, connect_timeout: 20 });
  try {
    await sql`create table if not exists public.schema_migracie (
      nazov text primary key, sha256 text not null, spustene_at timestamptz not null default now())`;
    await sql`alter table public.schema_migracie enable row level security`;

    for (const subor of plan) {
      const obsah = readFileSync(join(PRIECINOK, subor), "utf8");
      const hash = createHash("sha256").update(obsah).digest("hex");
      const [uz] = await sql<{ sha256: string }[]>`select sha256 from public.schema_migracie where nazov = ${subor}`;
      if (uz?.sha256 === hash) { console.log(`= ${subor}: uz spustena, preskakujem`); continue; }
      if (uz) console.log(`! ${subor}: obsah sa zmenil od posledneho spustenia, spustam znova`);

      const t0 = Date.now();
      await sql.begin(async (tx) => {
        await tx.unsafe(obsah);   // viac prikazov v jednom subore (simple query protokol)
        await tx`insert into public.schema_migracie (nazov, sha256) values (${subor}, ${hash})
                 on conflict (nazov) do update set sha256 = excluded.sha256, spustene_at = now()`;
      });
      console.log(`✓ ${subor} (${Date.now() - t0} ms)`);
    }
  } finally {
    await sql.end({ timeout: 5 });
  }
}

if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch((e) => {
    // chybova hlaska postgres neobsahuje heslo; URL nevypisujeme nikdy
    console.error(`CHYBA migracie: ${e.message}`);
    process.exit(1);
  });
}
