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
      skry();
    });

    btnPrijat.addEventListener("click", function () {
      ulozVolbu("granted");
      aktualizujConsent(true);
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
})();
