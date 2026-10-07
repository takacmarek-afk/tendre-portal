// Verejne formulare (obce.html, servis.html, starosta.html): odoslanie cez Edge
// Function "verejny-formular" s overenim Cloudflare Turnstile (vlna 81).
//   ptFormular.widget('#ts-box')            -> vykresli overenie (ak je kluc v config.js)
//   await ptFormular.posli(typ, data)       -> { ok: true, data? } | { ok:false, kod }
//   await ptFormular.pockaj(ms)             -> pocka, kym widget vyda token (max ms)
// kod: OVERENIE_CAKA (widget este nedobehol / bol zablokovany), OVERENIE
// (server overenie odmietol), PRILIS_VELA, NEPLATNE, SIET, CHYBA.
(function () {
  var cfg = window.CONFIG || {};
  var KLUC = cfg.TURNSTILE_SITE_KEY || '';
  var token = '';
  var widgetId = null;

  function widget(selector) {
    if (!KLUC) return;
    var s = document.createElement('script');
    s.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';
    s.async = true;
    s.onload = function () {
      try {
        widgetId = window.turnstile.render(selector, {
          sitekey: KLUC,
          language: 'sk',
          callback: function (t) { token = t; },
          'expired-callback': function () { token = ''; },
          'error-callback': function () { token = ''; },
        });
      } catch (e) { /* bez widgetu sa odoslanie ukaze hlaskou OVERENIE_CAKA */ }
    };
    document.head.appendChild(s);
  }

  function obnov() {
    token = '';
    try { if (window.turnstile && widgetId !== null) window.turnstile.reset(widgetId); } catch (e) {}
  }

  async function posli(typ, data) {
    if (!cfg.SUPABASE_URL || !cfg.SUPABASE_ANON_KEY) return { ok: false, kod: 'CHYBA' };
    if (KLUC && !token) return { ok: false, kod: 'OVERENIE_CAKA' };
    try {
      var r = await fetch(cfg.SUPABASE_URL + '/functions/v1/verejny-formular', {
        method: 'POST',
        headers: {
          apikey: cfg.SUPABASE_ANON_KEY,
          Authorization: 'Bearer ' + cfg.SUPABASE_ANON_KEY,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ typ: typ, turnstile: token, data: data }),
      });
      var j = null;
      try { j = await r.json(); } catch (e) {}
      obnov();   // jednorazovy token je pouzity (uspesne aj neuspesne)
      if (j && j.ok === true) return { ok: true, data: j.data };
      if (r.status === 429) return { ok: false, kod: 'PRILIS_VELA' };
      return { ok: false, kod: (j && j.kod) || 'CHYBA' };
    } catch (e) {
      obnov();
      return { ok: false, kod: 'SIET' };
    }
  }

  // Zrozumitelna hlaska pre navstevnika.
  function hlaska(kod, kontakt) {
    var k = kontakt || 'napíšte nám na info@predtendrom.sk';
    switch (kod) {
      case 'OVERENIE_CAKA':
        return 'Overenie, že nie ste robot, sa ešte nedokončilo. Počkajte chvíľu a skúste to znova. '
          + 'Ak sa nezobrazuje, vypnite blokátor reklamy pre túto stránku, alebo ' + k + '.';
      case 'OVERENIE':
        return 'Overenie, že nie ste robot, sa nepodarilo. Skúste to prosím znova.';
      case 'PRILIS_VELA':
        return 'Z vašej siete prišlo príliš veľa odoslaní. Skúste to prosím neskôr, alebo ' + k + '.';
      case 'NEPLATNE':
        return 'Skontrolujte prosím vyplnené údaje.';
      case 'SIET':
        return 'Nepodarilo sa spojiť. Skontrolujte pripojenie a skúste to znova.';
      default:
        return 'Odoslať sa nepodarilo. Skúste to prosím o chvíľu, alebo ' + k + '.';
    }
  }

  // Strankam, ktore posielaju hned po nacitani (kontrola.html s ?ico=), treba
  // pockat na token. Bez widgetu (kluc nie je v config.js) vrati hned.
  function pockaj(ms) {
    return new Promise(function (resolve) {
      if (!KLUC || token) return resolve(!!token || !KLUC);
      var koniec = Date.now() + (ms || 10000);
      (function skus() {
        if (token) return resolve(true);
        if (Date.now() >= koniec) return resolve(false);
        setTimeout(skus, 150);
      })();
    });
  }

  window.ptFormular = { widget: widget, posli: posli, hlaska: hlaska, pockaj: pockaj };
})();
