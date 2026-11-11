// Planovac PredTendrom.sk (11. 11. 2026)
//
// GitHub spusta planovane workflowy (cron) s oneskorenim 7 az 9 hodin a niektore
// vobec. Tento Cloudflare Worker bezi kazdu minutu (Cron Trigger "* * * * *"),
// porovna cas (UTC) s tabulkou ULOHY a prislusne workflowy spusti cez GitHub API
// (workflow_dispatch s planovane=true). Workflow sa potom sprava presne ako pri
// GitHub crone (env.UDALOST == 'schedule').
//
// Tajomstvo GH_TOKEN: fine-grained token GitHubu len pre repozitar tendre-portal,
// opravnenie Actions: Read and write. Vklada ho Marek v Cloudflare (Settings ->
// Variables and Secrets). Kod ho nikde nevypisuje.
//
// GET /           -> stav: ktore ulohy pobezia v najblizsich 60 minutach
// GET /posledne   -> vysledok posledneho spustenia (v pamati instancie, len orientacne)

const REPO = "takacmarek-afk/tendre-portal";

// [workflow, cron v UTC] — rovnake casy ako v .github/workflows (schedule)
export const ULOHY = [
  ["bezplatny-email.yml", "42 6 * * 1"],
  ["dopyty-email.yml", "*/15 * * * *"],
  ["email.yml", "20 6 * * 1-5"],
  ["itms.yml", "31 5 * * *"],
  ["kampan-obce.yml", "23 7 * * 2-4"],
  ["limit-emailov.yml", "47 15 * * *"],
  ["obce-podstranky.yml", "20 6 * * 3"],
  ["obec-mesacny-email.yml", "0 6 1 * *"],
  ["obrana-zmluv.yml", "22 7 * * *"],
  ["odber-firmy.yml", "17 7 * * *"],
  ["odpovede.yml", "47 7 * * 1-5"],
  ["odpovede.yml", "47 13 * * 1-5"],
  ["onboarding.yml", "7 7,11,15 * * *"],
  ["oslovenie-firiem.yml", "17 7 * * 1-4"],
  ["pipeline.yml", "10 5 * * 1-5"],
  ["pozvanky.yml", "*/15 * * * *"],
  ["prehlad-navstev.yml", "41 6 * * 1"],
  ["pripomienka-obnovy.yml", "17 6 * * *"],
  ["retencia.yml", "23 4 * * 0"],
  ["ruz-financie.yml", "40 4 * * *"],
  ["servis-email.yml", "*/30 * * * *"],
  ["tyzdenny-report.yml", "37 6 * * 1"],
  ["upozornenie-konkurent.yml", "11 7 * * *"],
  ["uvo.yml", "30 6 * * *"],
  ["zaloha-db.yml", "17 2 * * *"],
  ["zdravie-dat.yml", "47 7 * * *"],
  ["zmluvy-podstranky.yml", "35 6 * * 1-5"],
];

// ── cron: minuta hodina den mesiac den_v_tyzdni (0 = nedela), UTC ─────────
function pole(vyraz, hodnota) {
  return vyraz.split(",").some((cast) => {
    let [rozsah, krok] = cast.split("/");
    krok = krok ? parseInt(krok, 10) : 1;
    let od, po;
    if (rozsah === "*") { od = 0; po = 99; }
    else if (rozsah.includes("-")) { [od, po] = rozsah.split("-").map((x) => parseInt(x, 10)); }
    else { od = po = parseInt(rozsah, 10); }
    return hodnota >= od && hodnota <= po && (hodnota - (rozsah === "*" ? 0 : od)) % krok === 0;
  });
}

export function zhoda(cron, d) {
  const [mi, h, dm, mo, dw] = cron.trim().split(/\s+/);
  return pole(mi, d.getUTCMinutes()) && pole(h, d.getUTCHours()) && pole(dm, d.getUTCDate())
    && pole(mo, d.getUTCMonth() + 1) && pole(dw, d.getUTCDay());
}

export function naRade(d) {
  return [...new Set(ULOHY.filter(([, c]) => zhoda(c, d)).map(([w]) => w))];
}

async function spusti(workflow, token) {
  const r = await fetch(`https://api.github.com/repos/${REPO}/actions/workflows/${workflow}/dispatches`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "predtendrom-planovac",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ ref: "main", inputs: { planovane: "true" } }),
  });
  return r.status;      // 204 = OK
}

let posledne = null;

export default {
  async scheduled(event, env, ctx) {
    const d = new Date(event.scheduledTime);
    const ulohy = naRade(d);
    if (!ulohy.length) return;
    if (!env.GH_TOKEN) { console.log("Chyba GH_TOKEN"); return; }
    const vysledky = {};
    for (const w of ulohy) {
      try { vysledky[w] = await spusti(w, env.GH_TOKEN); }
      catch (e) { vysledky[w] = "chyba " + e.name; }
    }
    posledne = { cas: d.toISOString(), vysledky };
    console.log(JSON.stringify(posledne));
  },

  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/posledne") {
      return Response.json(posledne || { info: "od spustenia instancie este nic" });
    }
    const teraz = new Date();
    const plan = [];
    for (let i = 0; i < 60; i++) {
      const d = new Date(Math.floor(teraz.getTime() / 60000) * 60000 + i * 60000);
      const u = naRade(d);
      if (u.length) plan.push({ utc: d.toISOString().slice(11, 16), ulohy: u });
    }
    return Response.json({ token_nastaveny: Boolean(env.GH_TOKEN), najblizsich_60_minut: plan });
  },
};
