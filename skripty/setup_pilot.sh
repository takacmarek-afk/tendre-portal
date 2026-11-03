#!/usr/bin/env bash
# =============================================================================
#  setup_pilot.sh: 1-click priprava pilotnej kampane "Vyzvy pre obce"
#
#  Bezi OSTRO a bez otazok, v tomto poradi:
#    1. SQL migracie 89, 90, 91           (skripty/spusti-migracie.ts)
#    2. demografia, NRO, MRK do registra  (skripty/doplnenie-registra-obci.ts)
#    3. faza A: zmluvy o odpade v DB + prepocet prilezitosti
#    4. vyzvy (overene aj na kontrolu)    (skripty/seed_vyzvy.ts)
#    5. kampan_pilot.csv                  (skripty/generuj-kampan.ts)
#
#  Kazdy krok sa zastavi pri chybe (nic dalsie sa nespusti). Poistky, ktore
#  ostali: import registra nezapise, ak sa sparuje < 95 % obci; neoverene
#  vyzvy nejdu do e-mailov; nic sa neodosiela (CSV importujete do maileru vy).
#
#  Pouzitie (z korena repozitara, raz si nastavte premenne):
#    export SUPABASE_URL=https://kcpgqchdyhbvssybbaaz.supabase.co
#    export SUPABASE_SERVICE_ROLE_KEY=...   # Supabase › Settings › API › service_role
#    export SUPABASE_DB_URL=...             # Supabase › Connect › Session pooler (s heslom DB)
#    ./skripty/setup_pilot.sh --data ~/pilot-data
#  Priecinok --data: demografia.csv, nro.csv, mrk.csv.
#  Volitelne: --vystup kampan_pilot.csv  --datum 2026-11-24  --pocet 50
#  Premenne mozu byt aj v subore .env.pilot v koreni (nie je v gite).
# =============================================================================
set -euo pipefail

KOREN="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA="."; VYSTUP="kampan_pilot.csv"; DATUM="2026-11-24"; POCET=50
while [ $# -gt 0 ]; do
  case "$1" in
    --data) DATA="$2"; shift 2 ;;
    --vystup) VYSTUP="$2"; shift 2 ;;
    --datum) DATUM="$2"; shift 2 ;;
    --pocet) POCET="$2"; shift 2 ;;
    -h|--help) sed -n '2,27p' "$0"; exit 0 ;;
    *) echo "Neznámy prepínač: $1"; exit 2 ;;
  esac
done
DATA="$(cd "$DATA" && pwd)"
case "$VYSTUP" in /*) ;; *) VYSTUP="$PWD/$VYSTUP" ;; esac

if [ -t 1 ]; then B=$'\e[1m'; G=$'\e[32m'; Y=$'\e[33m'; R=$'\e[31m'; C=$'\e[36m'; N=$'\e[0m'; else B=; G=; Y=; R=; C=; N=; fi
krok()  { echo; echo "${C}${B}━━ $1 ━━${N}"; }
ok()    { echo "${G}✓ $1${N}"; }
chyba() { echo "${R}✕ $1${N}"; exit 1; }
trap 'echo "${R}✕ Krok zlyhal (riadok $LINENO). Nič ďalšie sa nespustilo; po oprave spustite skript znova.${N}"' ERR
NODE=(node --experimental-strip-types --no-warnings)

cd "$KOREN"
# shellcheck disable=SC1091
[ -f .env.pilot ] && { set -a; . ./.env.pilot; set +a; }

# ── 0. Kontrola prostredia ────────────────────────────────────────────────────
krok "0/5 Kontrola prostredia"
command -v node >/dev/null || chyba "Chýba Node.js 22.6+."
NV=$(node -p 'process.versions.node.split(".").map(Number).reduce((a,x,i)=>a+x*[1e6,1e3,1][i],0)')
[ "$NV" -ge 22006000 ] || chyba "Node $(node -v) je starý, treba 22.6+."
PY=$(command -v python3 || command -v python) || chyba "Chýba Python 3."
for v in SUPABASE_URL SUPABASE_SERVICE_ROLE_KEY SUPABASE_DB_URL; do [ -n "${!v:-}" ] || chyba "Nastavte $v (pozri hlavičku skriptu)."; done
for s in demografia.csv nro.csv mrk.csv; do [ -f "$DATA/$s" ] || chyba "Chýba $DATA/$s."; done
[ -d node_modules/postgres ] || { echo "Inštalujem závislosti (npm ci)…"; npm ci --silent; }
"$PY" -c "import supabase, pandas, requests" 2>/dev/null || { echo "Inštalujem Python balíčky…"; "$PY" -m pip install -q -r pipeline/requirements.txt; }
ok "Node $(node -v), $("$PY" --version), dáta v $DATA"

# ── 1. Migracie ───────────────────────────────────────────────────────────────
krok "1/5 SQL migrácie 89, 90, 91"
"${NODE[@]}" skripty/spusti-migracie.ts 89 90 91
ok "Migrácie hotové."

# ── 2. Register obci ──────────────────────────────────────────────────────────
krok "2/5 Demografia, NRO a MRK do registra obcí"
"${NODE[@]}" skripty/doplnenie-registra-obci.ts --demografia "$DATA/demografia.csv" --nro "$DATA/nro.csv" --mrk "$DATA/mrk.csv" --zapis
ok "Register doplnený."

# ── 3. ODPAD faza A + prepocet ────────────────────────────────────────────────
krok "3/5 Zmluvy o odpade (fáza A) a prepočet príležitostí"
( cd pipeline && "$PY" reprocess_odpad.py --len-a --zapis )
( cd pipeline && "$PY" main.py --iba-prepocet )
ok "Zmluvy o odpade zaradené, príležitosti prepočítané."

# ── 4. Vyzvy ──────────────────────────────────────────────────────────────────
krok "4/5 Výzvy"
"${NODE[@]}" skripty/seed_vyzvy.ts --zapis
ok "Výzvy zapísané."

# ── 5. Kampan ─────────────────────────────────────────────────────────────────
krok "5/5 Pilotná kampaň"
"${NODE[@]}" skripty/generuj-kampan.ts --zapis --vystup "$VYSTUP" --datum "$DATUM" --pocet "$POCET"

echo
if [ -f "$VYSTUP" ]; then
  ok "Hotovo: $VYSTUP ($(($(grep -c '^"[0-9]' "$VYSTUP" || true))) e-mailov). Importujte ho do maileru; skript nič neodoslal."
else
  echo "${Y}Hotovo, ale CSV nevzniklo: žiadna obec nemá vhodnú overenú výzvu (pozri výpis vyššie).${N}"
fi
echo "Fáza B (staré zmluvy o odpade priamo z CRZ, trvá hodiny) beží samostatne: cd pipeline && $PY reprocess_odpad.py --len-b --zapis"
