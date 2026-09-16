// Test prihlasovacej cesty. Spusti:  node public/test/test_prihlasenie.mjs
//
// PRECO TENTO TEST EXISTUJE: 16. 9. 2026 sa na portal nedalo prihlasit
// ani mne, ani Markovi. E-maily odchadzali spravne — padalo az spracovanie
// odkazu. Projekt ma flowType "implicit", takze token pride v HASH-I adresy
// a supabase-js ho spracuva asynchronne, kym sa app.html na session pytala
// okamzite. Ked tu sutaz prehrala, presmerovala na prihlasenie a hash sa
// tym zahodil — a pouzivatel skoncil v kruhu "vyziadaj novy odkaz".
//
// Funkcie nizsie su KOPIA tych z app.html. Ked ich tam zmenis, zmen ich
// aj tu, inak test chrani nieco, co uz v aplikacii nie je.

// Vytrhnute presne tie funkcie z app.html a otestovane na skutocnych
// tvaroch adries, ktore Supabase vracia.
const AUTH_V_ADRESE = /(access_token|refresh_token|[?&]code=|error_description|error_code)/;
let location;
function maPrihlasovacieUdaje() {
  return AUTH_V_ADRESE.test(location.hash) || AUTH_V_ADRESE.test(location.search);
}
function chybaZOdkazu() {
  const zdroj = new URLSearchParams(
    (location.hash.startsWith('#') ? location.hash.slice(1) : location.hash)
    || location.search.slice(1));
  const popis = zdroj.get('error_description') || zdroj.get('error');
  return popis ? decodeURIComponent(popis.replace(/\+/g, ' ')) : null;
}

const pripady = [
  // [popis, hash, search, maUdaje, ocakavanaChyba]
  ['uspesny magic link (implicit)',
   '#access_token=eyJh.abc&expires_in=3600&refresh_token=xyz&token_type=bearer&type=magiclink',
   '', true, null],
  ['vyprsany odkaz — presne to, co sme videli',
   '#error=access_denied&error_code=otp_expired&error_description=Email+link+is+invalid+or+has+expired',
   '', true, 'Email link is invalid or has expired'],
  ['chyba v query namiesto hashu',
   '', '?error=access_denied&error_description=Email+link+is+invalid+or+has+expired',
   true, 'Email link is invalid or has expired'],
  ['PKCE kod (keby sa flowType niekedy zmenil)',
   '', '?code=abc-123', true, null],
  ['obycajne otvorenie app.html', '', '', false, null],
  ['nas vlastny filter v adrese nesmie vypadat ako auth',
   '', '?kraj=Ko%C5%A1ick%C3%BD&sektor=STAVBY', false, null],
  ['hash na zalozku nesmie vypadat ako auth', '#dotacie', '', false, null],
];

let chyb = 0;
for (const [popis, hash, search, maUdaje, ocakChyba] of pripady) {
  location = { hash, search, pathname: '/app.html' };
  const u = maPrihlasovacieUdaje(), c = chybaZOdkazu();
  const ok = u === maUdaje && c === ocakChyba;
  if (!ok) chyb++;
  console.log(`${ok ? 'OK  ' : 'ZLE '} ${popis.padEnd(46)} udaje=${u} chyba=${JSON.stringify(c)}`);
}
console.log(chyb ? `\n${chyb} PRIPADOV ZLYHALO` : '\nVSETKYCH 7 PRIPADOV PRESLO');
process.exit(chyb ? 1 : 0);
