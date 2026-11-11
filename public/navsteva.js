// Navstevnost pre staticke SEO podstranky (eurofondy, konciace-zmluvy, obce).
// Ten isty kod ako inline v index.html; potrebuje window.CONFIG (config.js).
// Pridane pri audite 11. 11. 2026: bez neho sme nevideli navstevy zo SEO ani
// kliky zo studenych e-mailov (UTM).
(function(){
  if (window.__ptNavsteva) return; window.__ptNavsteva = 1;
  try {
    var cfg = window.CONFIG || {};
    if (!cfg.SUPABASE_URL || !cfg.SUPABASE_ANON_KEY) return;

    // Trvalé vylúčenie admina na úrovni zariadenia (nastavuje app.html po
    // potvrdení je_admin() = true, bez expirácie) — funguje aj keď je
    // Marek na tejto stránke odhlásený alebo bez platnej session, na
    // rozdiel od kontroly nižšie, ktorá potrebuje aktívny token PRÁVE TERAZ.
    try { if (localStorage.getItem('pt_admin_zariadenie') === '1') return; } catch (e) {}

    var sid = null;
    try {
      sid = sessionStorage.getItem('ptid');
      if (!sid) {
        sid = (window.crypto && crypto.randomUUID) ? crypto.randomUUID() : (Date.now() + '-' + Math.random());
        sessionStorage.setItem('ptid', sid);
      }
    } catch (e) { sid = null; }

    function posliNavstevu() {
      fetch(cfg.SUPABASE_URL + '/rest/v1/navstevy', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'apikey': cfg.SUPABASE_ANON_KEY,
          'Prefer': 'return=minimal'
        },
        body: JSON.stringify((function(){ var u = (window.ptUtm && window.ptUtm()) || {}; return { cesta: location.pathname, referrer: document.referrer || null, session_id: sid, utm_source: u.s || null, utm_medium: u.m || null, utm_campaign: u.c || null }; })()),
        keepalive: true
      }).catch(function(){});
    }

    var projectRef = (cfg.SUPABASE_URL.match(/https:\/\/([a-z0-9]+)\.supabase\.co/) || [])[1];
    var token = null;
    try {
      var raw = projectRef && localStorage.getItem('sb-' + projectRef + '-auth-token');
      if (raw) token = JSON.parse(raw).access_token;
    } catch (e) { token = null; }

    if (!token) { posliNavstevu(); return; }

    fetch(cfg.SUPABASE_URL + '/rest/v1/rpc/je_admin', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'apikey': cfg.SUPABASE_ANON_KEY,
        'Authorization': 'Bearer ' + token
      },
      body: '{}'
    }).then(function(r){ return r.json(); }).then(function(jeAdmin){
      if (jeAdmin === true) {
        // Zariadenie ešte nemalo nastavený trvalý príznak (napr. staršia
        // session) — doplníme ho teraz, nabudúce sa už RPC volať nemusí.
        try { localStorage.setItem('pt_admin_zariadenie', '1'); } catch (e) {}
      } else {
        posliNavstevu();
      }
    }).catch(function(){ posliNavstevu(); });
  } catch (e) {}
})();
