// =============================================================================
//  CONSENT-ANALYTICS.JS
//
//  Google Consent Mode v2 + cookie banner + nacitanie Google Tag Manager
//  (GTM-PGQ9GCGQ -> GA4 G-928YE9RV2K).
//
//  Jeden zdielany subor namiesto kopirovania rovnakeho bloku do kazdej
//  HTML stranky (a do generatorov programoveho SEO) - vlozi sa jedinym
//  riadkom <script src="/consent-analytics.js"></script> v <head>,
//  co najskor, pred ostatnymi skriptami.
//
//  AKO TO FUNGUJE (v skratke, pre buduce upravy):
//  1. Okamzite, synchronne nastavime dataLayer + gtag() stub a
//     gtag('consent','default', ...) na 'denied' pre vsetky 4 signaly.
//     Toto MUSI bezat skor, nez sa nacita gtm.js, inak by GTM nemal
//     ziadny consent signal k dispozicii pri prvom nacitani stranky.
//  2. Ak uz mame ulozenu volbu z minula (localStorage), hned aplikujeme
//     'granted'/'denied' cez gtag('consent','update', ...).
//  3. Az POTOM asynchronne pripojime GTM container (script tag).
//     GTM sam rozhoduje, ci znacku spusti, podla consent stavu v
//     dataLayer - nie je potrebne nic dalsie robit v GTM.
//  4. Ak volba este nie je ulozena, po nacitani DOM-u zobrazime banner
//     (Prijat vsetko / Iba nevyhnutne). Volba sa ulozi do localStorage
//     a zapise sa aj datum, aby sme v buducnosti mohli pridat
//     opatovne vyziadanie po X mesiacoch, ak to bude treba.
//
//  Ako oznacit "aktivovaneho pouzivatela" (konverzia v GA4): z inej
//  stranky/skriptu zavolaj window.ptOznamAktivaciu() - postara sa
//  o push do dataLayer s eventom "aktivovany_pouzivatel", presne v
//  tvare, ktory ocakava GTM trigger "Vlastna udalost -
//  aktivovany_pouzivatel".
// =============================================================================

(function () {
  "use strict";

  var GTM_ID = "GTM-PGQ9GCGQ";
  var ULOZISKO_KLUC = "pt_cookie_consent"; // hodnoty: "granted" | "denied"

  // ---- 1. Consent Mode v2: dataLayer + gtag stub + default (denied) -------
  window.dataLayer = window.dataLayer || [];
  function gtag() {
    window.dataLayer.push(arguments);
  }
  window.gtag = gtag;

  gtag("consent", "default", {
    ad_storage: "denied",
    analytics_storage: "denied",
    ad_user_data: "denied",
    ad_personalization: "denied",
    wait_for_update: 500,
  });
  gtag("js", new Date());

  // ---- 1b. Zdroj navstevy (UTM) - prvy dotyk v ramci jednej karty ---------
  // Appky Facebook/Instagram casto neposielaju referrer, preto si zdroj
  // zapamatame z URL (utm_*, pripadne fbclid/gclid) do sessionStorage a
  // posielame ho s kazdou navstevou aj udalostou v tejto karte. Ziadna
  // cookie, ziadny identifikator cloveka - len "odkial prisla tato karta".
  var UTM_KLUC = "pt_utm";
  (function () {
    try {
      var q = new URLSearchParams(window.location.search);
      var zdroj = q.get("utm_source");
      var u = null;
      if (zdroj) {
        u = { s: zdroj, m: q.get("utm_medium"), c: q.get("utm_campaign") };
      } else if (q.get("fbclid")) {
        u = { s: "facebook", m: "social", c: null };
      } else if (q.get("gclid")) {
        u = { s: "google", m: "cpc", c: null };
      }
      if (u && !window.sessionStorage.getItem(UTM_KLUC)) {
        window.sessionStorage.setItem(UTM_KLUC, JSON.stringify({
          s: String(u.s).slice(0, 100),
          m: u.m ? String(u.m).slice(0, 100) : null,
          c: u.c ? String(u.c).slice(0, 150) : null,
        }));
      }
    } catch (e) {}
  })();

  window.ptUtm = function () {
    try {
      return JSON.parse(window.sessionStorage.getItem(UTM_KLUC) || "null") || {};
    } catch (e) {
      return {};
    }
  };

  // ---- 2. Ak uz mame ulozenu volbu, aplikujeme ju hned --------------------
  function nacitajVolbu() {
    try {
      return window.localStorage.getItem(ULOZISKO_KLUC);
    } catch (e) {
      return null;
    }
  }

  function ulozVolbu(hodnota) {
    try {
      window.localStorage.setItem(ULOZISKO_KLUC, hodnota);
      window.localStorage.setItem(ULOZISKO_KLUC + "_datum", new Date().toISOString());
    } catch (e) {
      // localStorage nedostupny (private mode a pod.) - volba sa jednoducho
      // nezapamata a banner sa ukaze znova nabudúce. Nie je to kriticke.
    }
  }

  function aktualizujConsent(udelene) {
    var stav = udelene
      ? { ad_storage: "granted", analytics_storage: "granted", ad_user_data: "granted", ad_personalization: "granted" }
      : { ad_storage: "denied", analytics_storage: "denied", ad_user_data: "denied", ad_personalization: "denied" };
    gtag("consent", "update", stav);
  }

  var ulozenaVolba = nacitajVolbu();
  if (ulozenaVolba === "granted") {
    aktualizujConsent(true);
  } else if (ulozenaVolba === "denied") {
    aktualizujConsent(false);
  }

  // ---- 3. Nacitanie GTM containera (vzdy, konzistentne s Consent Mode) ----
  (function (w, d, s, l, i) {
    w[l] = w[l] || [];
    w[l].push({ "gtm.start": new Date().getTime(), event: "gtm.js" });
    var f = d.getElementsByTagName(s)[0],
      j = d.createElement(s),
      dl = l != "dataLayer" ? "&l=" + l : "";
    j.async = true;
    j.src = "https://www.googletagmanager.com/gtm.js?id=" + i + dl;
    f.parentNode.insertBefore(j, f);
  })(window, document, "script", "dataLayer", GTM_ID);

  // ---- 4. Banner (len ak volba este nie je ulozena) ------------------------
  function zobrazBanner() {
    if (document.getElementById("pt-cookie-banner")) return;

    var wrap = document.createElement("div");
    wrap.id = "pt-cookie-banner";
    wrap.setAttribute("role", "dialog");
    wrap.setAttribute("aria-label", "Nastavenie cookies");
    wrap.style.cssText =
      "position:fixed;left:0;right:0;bottom:0;z-index:9999;" +
      "background:#0B1220;color:#F7F3EA;font-family:'IBM Plex Sans',system-ui,-apple-system,sans-serif;" +
      "padding:16px 20px;box-shadow:0 -2px 16px rgba(0,0,0,.2);" +
      "display:flex;flex-wrap:wrap;gap:12px;align-items:center;justify-content:space-between;";

    var text = document.createElement("div");
    text.style.cssText = "flex:1;min-width:240px;font-size:13px;line-height:1.5;color:#E4DFD2;";
    text.innerHTML =
      "Na meranie návštevnosti a zlepšovanie stránky používame analytické cookies " +
      "(Google Analytics), a to až po vašom súhlase. Viac v " +
      '<a href="/index.html#ochrana-osobnych-udajov" style="color:#E8A33D;text-decoration:underline;">ochrane osobných údajov</a>.';

    var btnWrap = document.createElement("div");
    btnWrap.style.cssText = "display:flex;gap:10px;flex-shrink:0;";

    var btnOdmietnut = document.createElement("button");
    btnOdmietnut.type = "button";
    btnOdmietnut.textContent = "Iba nevyhnutné";
    btnOdmietnut.style.cssText =
      "background:transparent;color:#F7F3EA;border:1px solid #6B6558;border-radius:6px;" +
      "padding:9px 16px;font-size:13px;cursor:pointer;";

    var btnPrijat = document.createElement("button");
    btnPrijat.type = "button";
    btnPrijat.textContent = "Prijať";
    btnPrijat.style.cssText =
      "background:#B25313;color:#fff;border:none;border-radius:6px;" +
      "padding:9px 18px;font-size:13px;font-weight:600;cursor:pointer;";

    function skry() {
      wrap.parentNode && wrap.parentNode.removeChild(wrap);
    }

    btnOdmietnut.addEventListener("click", function () {
      ulozVolbu("denied");
      aktualizujConsent(false);
      window.ptUdalost("suhlas_odmietnuty");
      skry();
    });

    btnPrijat.addEventListener("click", function () {
      ulozVolbu("granted");
      aktualizujConsent(true);
      window.ptUdalost("suhlas_prijaty");
      skry();
    });

    btnWrap.appendChild(btnOdmietnut);
    btnWrap.appendChild(btnPrijat);
    wrap.appendChild(text);
    wrap.appendChild(btnWrap);
    document.body.appendChild(wrap);
  }

  if (!ulozenaVolba) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", zobrazBanner);
    } else {
      zobrazBanner();
    }
  }

  // ---- 5. Verejna funkcia na oznamenie konverzie ("aktivovany pouzivatel") -
  window.ptOznamAktivaciu = function () {
    gtag("event", "aktivovany_pouzivatel");
  };

  // ---- 6. Udalosti: GA4 (ak je suhlas) + vlastne pocitadlo bez cookies ---
  // window.ptUdalost(nazov, parametre)
  //   - gtag('event', ...) ide do GA4 cez znacku Google v GTM; bez suhlasu
  //     ju Consent Mode posle len ako anonymny ping bez cookies.
  //   - Zaroven jeden riadok do public.udalosti (supabase/45_merania.sql):
  //     nazov + cesta + session_id karty + UTM. Nazvy su v databaze
  //     obmedzene zoznamom (check constraint) - novy nazov treba pridat aj
  //     tam, inak sa riadok ticho neulozi.
  //   - Admin zariadenie (pt_admin_zariadenie) sa nepocita, rovnako ako
  //     v tracking snippete navstev.
  function idKarty() {
    try {
      var sid = window.sessionStorage.getItem("ptid");
      if (!sid) {
        sid = (window.crypto && window.crypto.randomUUID) ? window.crypto.randomUUID() : (Date.now() + "-" + Math.random());
        window.sessionStorage.setItem("ptid", sid);
      }
      return sid;
    } catch (e) {
      return null;
    }
  }

  window.ptUdalost = function (nazov, parametre) {
    try { gtag("event", nazov, parametre || {}); } catch (e) {}
    try {
      try { if (window.localStorage.getItem("pt_admin_zariadenie") === "1") return; } catch (e) {}
      var cfg = window.CONFIG || {};
      if (!cfg.SUPABASE_URL || !cfg.SUPABASE_ANON_KEY) return;
      var u = window.ptUtm();
      fetch(cfg.SUPABASE_URL + "/rest/v1/udalosti", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "apikey": cfg.SUPABASE_ANON_KEY,
          "Prefer": "return=minimal"
        },
        body: JSON.stringify({
          nazov: nazov,
          cesta: window.location.pathname.slice(0, 300),
          session_id: idKarty(),
          utm_source: u.s || null,
          utm_medium: u.m || null,
          utm_campaign: u.c || null
        }),
        keepalive: true
      }).catch(function () {});
    } catch (e) {}
  };

  // Ceny podla cennik.html - na hodnotu konverzie v GA4 (begin_checkout,
  // purchase). Presne sumy su v databaze (platby), toto je len pre GA4.
  var CENY = {
    "start:mesiac": 34, "start:rok": 340,
    "growth:mesiac": 89, "growth:rok": 890,
    "team:mesiac": 249, "team:rok": 2490
  };
  window.ptZaciatokPlatby = function (plan, obdobie) {
    var hodnota = CENY[plan + ":" + obdobie] || 0;
    try {
      window.sessionStorage.setItem("pt_checkout", JSON.stringify({ plan: plan, obdobie: obdobie, hodnota: hodnota }));
    } catch (e) {}
    window.ptUdalost("begin_checkout", {
      currency: "EUR", value: hodnota,
      items: [{ item_id: plan, item_name: plan + " (" + obdobie + ")", price: hodnota, quantity: 1 }]
    });
  };
  window.ptPlatbaUspesna = function () {
    var k = {};
    try { k = JSON.parse(window.sessionStorage.getItem("pt_checkout") || "null") || {}; } catch (e) {}
    try { window.sessionStorage.removeItem("pt_checkout"); } catch (e) {}
    window.ptUdalost("purchase", {
      currency: "EUR", value: k.hodnota || 0,
      transaction_id: "pt-" + Date.now(),
      items: k.plan ? [{ item_id: k.plan, item_name: k.plan + " (" + k.obdobie + ")", price: k.hodnota || 0, quantity: 1 }] : []
    });
  };

  // Klik na akykolvek odkaz na prihlasenie (Vyskusat zadarmo, Prihlasit sa,
  // CTA v cenniku) - jedno spolocne pocuvanie namiesto uprav kazdeho tlacidla.
  document.addEventListener("click", function (ev) {
    try {
      var a = ev.target && ev.target.closest ? ev.target.closest("a[href]") : null;
      if (!a) return;
      var href = a.getAttribute("href") || "";
      if (/(^|\/)prihlasenie(\.html)?(\?|#|$)/.test(href) && window.location.pathname.indexOf("prihlasenie") === -1) {
        window.ptUdalost("klik_vyskusat", { umiestnenie: (a.textContent || "").trim().slice(0, 40) });
      }
    } catch (e) {}
  }, true);
})();
