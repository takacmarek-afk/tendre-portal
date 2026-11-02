#!/usr/bin/env bash
# =============================================================================
#  setup_pilot.sh: priprava pilotnej kampane "Vyzvy pre obce" (24. 11. 2026)
#
#  Poradie:
#    0. kontrola prostredia (node 22+, python 3, premenne, subory)
#    1. doplnenie registra obci (demografia, NRO, MRK)
#    2. spatne zaradenie zmluv do ODPAD + prepocet prilezitosti
#    3. seeder vyziev (vklada NEOVERENE)
#    4. generator kampane NA SUCHO (nahlad 3 e-mailov)
#
#  Predvolene vsetko NA SUCHO. S prepinacom --zapis zapisuje kroky 1 – 3
#  (pred kazdym zapisom sa este raz spyta). Krok 4 je vzdy na sucho;
#  export CSV je samostatny prikaz na konci, az po kontrole.
#
#  Pouzitie (z korena repozitara):
#    export SUPABASE_URL=https://kcpgqchdyhbvssybbaaz.supabase.co
#    export SUPABASE_SERVICE_ROLE_KEY=...        # kluc nikdy necommitovat
#    ./skripty/setup_pilot.sh --data ~/pilot-data            # na sucho
#    ./skripty/setup_pilot.sh --data ~/pilot-data --zapis    # ostro
#  Priecinok --data obsahuje demografia.csv, nro.csv, mrk.csv.
#  Volby: --preskoc-odpad-b (faza B CRZ trva hodiny), --budget 45
#
#  Migracie 89 a 90 musia byt spustene v databaze pred prvym --zapis.
# =============================================================================
set -euo pipefail

KOREN="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA="."; ZAPIS=0; PRESKOC_B=0; BUDGET=45
while [ $# -gt 0 ]; do
  case "$1" in
    --data) DATA="$2"; shift 2 ;;
    --zapis) ZAPIS=1; shift ;;
    --preskoc-odpad-b) PRESKOC_B=1; shift ;;
    --budget) BUDGET="$2"; shift 2 ;;
    -h|--help) sed -n '2,27p' "$0"; exit 0 ;;
    *) echo "Neznámy prepínač: $1"; exit 2 ;;
  esac
done

if [ -t 1 ]; then B=$'\e[1m'; G=$'\e[32m'; Y=$'\e[33m'; R=$'\e[31m'; C=$'\e[36m'; N=$'\e[0m'; else B=; G=; Y=; R=; C=; N=; fi
krok() { echo; echo "${C}${B}━━ $1 ━━${N}"; }
ok()   { echo "${G}✓ $1${N}"; }
pozor(){ echo "${Y}! $1${N}"; }
chyba(){ echo "${R}✕ $1${N}"; exit 1; }
potvrd() {
  [ "$ZAPIS" = 1 ] || return 0
  read -r -p "${Y}$1 Zapísať do databázy? [a/N] ${N}" o
  [ "$o" = "a" ] || [ "$o" = "A" ] || { pozor "Preskočené."; return 1; }
}
ZAP=(); [ "$ZAPIS" = 1 ] && ZAP=(--zapis)
NODE=(node --experimental-strip-types --no-warnings)

# ── 0. Kontrola prostredia ────────────────────────────────────────────────────
krok "0/4 Kontrola prostredia"
command -v node >/dev/null || chyba "Chýba Node.js (treba 22.6+)."
NV=$(node -p 'process.versions.node.split(".").map(Number).reduce((a,x,i)=>a+x*[1e6,1e3,1][i],0)')
[ "$NV" -ge 22006000 ] || chyba "Node $(node -v) je starý, treba 22.6+ (kvôli --experimental-strip-types)."
PY=$(command -v python3 || command -v python) || chyba "Chýba Python 3."
[ -n "${SUPABASE_URL:-}" ] || chyba "Nastavte SUPABASE_URL."
[ -n "${SUPABASE_SERVICE_ROLE_KEY:-}" ] || chyba "Nastavte SUPABASE_SERVICE_ROLE_KEY (Supabase › Settings › API › service_role)."
for s in demografia.csv nro.csv mrk.csv; do [ -f "$DATA/$s" ] || chyba "Chýba $DATA/$s (hlavičky: pozri skripty/doplnenie-registra-obci.ts)."; done
"$PY" -c "import supabase, pandas, requests" 2>/dev/null || chyba "Chýbajú Python balíčky: $PY -m pip install -r pipeline/requirements.txt"
ok "Node $(node -v), $("$PY" --version), dáta v $DATA"
[ "$ZAPIS" = 1 ] && pozor "REŽIM ZÁPISU: pred každým zápisom sa spýtam." || ok "Režim NA SUCHO (nič sa nezapíše)."

cd "$KOREN"

# ── 1. Register obci ──────────────────────────────────────────────────────────
krok "1/4 Doplnenie registra obcí (demografia, NRO, MRK)"
"${NODE[@]}" skripty/doplnenie-registra-obci.ts --demografia "$DATA/demografia.csv" --nro "$DATA/nro.csv" --mrk "$DATA/mrk.csv"
if potvrd "Štatistiku párovania máte vyššie."; then
  "${NODE[@]}" skripty/doplnenie-registra-obci.ts --demografia "$DATA/demografia.csv" --nro "$DATA/nro.csv" --mrk "$DATA/mrk.csv" --zapis
fi

# ── 2. ODPAD ──────────────────────────────────────────────────────────────────
krok "2/4 Spätné zaradenie zmlúv do sektora ODPAD"
( cd pipeline && "$PY" reprocess_odpad.py --len-a )
if potvrd "Fáza A (zmluvy, ktoré už sú v databáze)."; then
  ( cd pipeline && "$PY" reprocess_odpad.py --len-a --zapis )
fi
if [ "$PRESKOC_B" = 1 ]; then
  pozor "Fáza B (prechod CRZ) preskočená. Spustite neskôr: cd pipeline && $PY reprocess_odpad.py --len-b --zapis"
elif [ "$ZAPIS" = 1 ] && potvrd "Fáza B prejde CRZ od 2023 (rozpočet $BUDGET min na beh, opakuje sa, kým nie je HOTOVO)."; then
  while true; do
    set +e; ( cd pipeline && "$PY" reprocess_odpad.py --len-b --zapis --budget "$BUDGET" ); RC=$?; set -e
    [ "$RC" = 0 ] && { ok "Fáza B hotová."; break; }
    [ "$RC" = 3 ] || chyba "Fáza B skončila chybou ($RC). Spustite znova, pokračuje od checkpointu."
    read -r -p "${Y}Pokračovať ďalším behom? [a/N] ${N}" o; [ "$o" = "a" ] || [ "$o" = "A" ] || { pozor "Pokračovanie neskôr rovnakým príkazom."; break; }
  done
else
  pozor "Fáza B sa na sucho nespúšťa (trvá hodiny)."
fi
if [ "$ZAPIS" = 1 ] && potvrd "Prepočet príležitostí (opportunities), aby sa ODPAD prejavil v bodovaní."; then
  ( cd pipeline && "$PY" main.py --iba-prepocet )
fi

# ── 3. Vyzvy ──────────────────────────────────────────────────────────────────
krok "3/4 Seeder výziev"
"${NODE[@]}" skripty/seed_vyzvy.ts
if potvrd "Výzvy sa vložia NEOVERENÉ (do kampane nejdú, kým ich neoveríte)."; then
  "${NODE[@]}" skripty/seed_vyzvy.ts --zapis
fi

# ── 4. Kampan na sucho ────────────────────────────────────────────────────────
krok "4/4 Generátor kampane (na sucho)"
"${NODE[@]}" skripty/generuj-kampan.ts

echo
echo "${B}Ďalšie kroky:${N}"
echo "  1. Skontrolujte výzvy (body „Overiť“ v kroku 3) a overte ich:"
echo "     ${C}node --experimental-strip-types skripty/seed_vyzvy.ts --over <KOD> --overil \"Vaše meno\"${N}"
echo "  2. Znova náhľad:  ${C}node --experimental-strip-types skripty/generuj-kampan.ts${N}"
echo "  3. Export CSV:    ${C}node --experimental-strip-types skripty/generuj-kampan.ts --zapis${N}"
echo "  4. CSV si prezrite a pošlite z mailingového nástroja (skript nič neodosiela)."
