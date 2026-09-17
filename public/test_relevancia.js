// Testuje REALNY kod z public/app.html (nie reimplementaciu) — vytiahne
// cisté JS bloky (platneIco, num, blok "OSOBNA RELEVANCIA") a spusti ich vo
// vm kontexte s minimalnym mockom el()/supabase. Rovnaky duch ako pytest
// style testy v pipeline/test_*.py: print + assert, ziadny framework.
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');

const html = fs.readFileSync(require('path').join(__dirname, 'app.html'), 'utf-8');

function vyrez(zac, kon, label) {
  const i = html.indexOf(zac);
  const j = html.indexOf(kon, i);
  assert(i !== -1 && j !== -1, `nenasiel som blok: ${label}`);
  return html.slice(i, j);
}

const numFn = vyrez('function num(v) {', '\nfunction suma', 'num()');
const platneIcoFn = vyrez('function platneIco(v) {', '\n\nasync function nastavOdber', 'platneIco()');
const relevanciaBlok = vyrez(
  '// ── OSOBNA RELEVANCIA (#7, 17.9.2026) ──────────────────────────────────',
  '\n\n  const STLPCE_Z',
  'blok relevancie');

// ── mock prostredie ─────────────────────────────────────────────────────
const domHodnoty = { 'f-radenie': 'signal' };
function el(id) {
  return {
    get value() { return domHodnoty[id] ?? ''; },
    set value(v) { domHodnoty[id] = v; },
  };
}

let dodavatelData = null; // co "vrati" supabase pre dodavatelia lookup
const supabase = {
  from(tabulka) {
    return {
      select() { return this; },
      eq() { return this; },
      async maybeSingle() { return { data: dodavatelData }; },
    };
  },
};

const posledne = { zmluvy: [], benchmark: null };

function riadok(x) { return String(x.contract_id); }
const sandbox = { el, supabase, posledne, Math, console, riadok };
vm.createContext(sandbox);
vm.runInContext(numFn + '\n' + platneIcoFn + '\n' + relevanciaBlok, sandbox);

let zlyhania = 0;
function over(popis, ok) {
  if (ok) { console.log('OK  ', popis); }
  else { console.log('FAIL', popis); zlyhania++; }
}

// 1) platneIco: format
over('platneIco akceptuje 8 cislic', sandbox.platneIco('12345678') === '12345678');
over('platneIco orezava medzery', sandbox.platneIco('  12345678  ') === '12345678');
over('platneIco odmieta 7 cislic', sandbox.platneIco('1234567') === '');
over('platneIco odmieta pismena', sandbox.platneIco('1234567a') === '');
over('platneIco odmieta prazdne', sandbox.platneIco('') === '');
over('platneIco odmieta undefined', sandbox.platneIco(undefined) === '');

// 2) zoradPodlaRelevancie: bez preferencii nemeni poradie
posledne.zmluvy = [
  { contract_id: 1, sector: 'STAVEBNICTVO', kraj: 'Košický', price_total: 50000, skore: 40 },
  { contract_id: 2, sector: 'IT', kraj: 'Bratislavský', price_total: 200000, skore: 80 },
  { contract_id: 3, sector: 'STAVEBNICTVO', kraj: 'Bratislavský', price_total: 60000, skore: 60 },
];
const povodnePoradie = posledne.zmluvy.map(x => x.contract_id);
sandbox.nastavRelevanciu(null).then(() => {
  over('bez profilu ostava poradie nezmenene',
    JSON.stringify(posledne.zmluvy.map(x => x.contract_id)) === JSON.stringify(povodnePoradie));

  // 3) so sektorovou preferenciou: STAVEBNICTVO by malo predbehnut vyssie skore z IT
  posledne.zmluvy = [
    { contract_id: 1, sector: 'STAVEBNICTVO', kraj: null, price_total: 50000, skore: 40 },
    { contract_id: 2, sector: 'IT', kraj: null, price_total: 200000, skore: 45 },
  ];
  return sandbox.nastavRelevanciu({ sektor: 'STAVEBNICTVO', kraj: null, moje_ico: null });
}).then(() => {
  over('sektorova zhoda (40+15=55) predbehne IT (45) bez zhody',
    posledne.zmluvy[0].contract_id === 1);

  // 4) vlastna historia (moje_ico -> dodavatelia) dvihne sektor este viac
  //    a cenova blizkost pridá bonus tej zakazke, ktora je najblizsie
  //    priemernej vlastnej zmluve.
  dodavatelData = { hlavny_sektor: 'IT', priemerna_zmluva_eur: 190000 };
  posledne.zmluvy = [
    { contract_id: 1, sector: 'STAVEBNICTVO', kraj: null, price_total: 50000, skore: 50 },
    { contract_id: 2, sector: 'IT', kraj: null, price_total: 195000, skore: 50 },
  ];
  return sandbox.nastavRelevanciu({ sektor: null, kraj: null, moje_ico: '12345678' });
}).then(() => {
  over('vlastna historia (sektor IT + cena blizko) vyhra pri rovnakom skore',
    posledne.zmluvy[0].contract_id === 2);

  // 5) pri inom triedeni (nie "signal") sa poradie NEDOTYKA
  domHodnoty['f-radenie'] = 'hodnota';
  posledne.zmluvy = [
    { contract_id: 1, sector: 'STAVEBNICTVO', kraj: null, price_total: 50000, skore: 10 },
    { contract_id: 2, sector: 'IT', kraj: null, price_total: 195000, skore: 90 },
  ];
  const predOdber = [...posledne.zmluvy];
  sandbox.mojOdber = null; // reset pred volanim
  return sandbox.nastavRelevanciu({ sektor: 'STAVEBNICTVO', kraj: null, moje_ico: null })
    .then(() => {
      over('pri f-radenie != signal sa poradie nemeni',
        JSON.stringify(posledne.zmluvy.map(x => x.contract_id)) ===
        JSON.stringify(predOdber.map(x => x.contract_id)));
      domHodnoty['f-radenie'] = 'signal';
    });
}).then(() => {
  console.log(zlyhania === 0 ? '\nVSETKO OK' : `\n${zlyhania} ZLYHANI`);
  process.exit(zlyhania === 0 ? 0 : 1);
}).catch(e => { console.error(e); process.exit(1); });
