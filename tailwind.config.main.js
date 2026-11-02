// Zdielany config pre vsetky stranky OKREM platba-vysledok.html (ta ma
// vlastnu, uzsiu paletu — viz tailwind.config.platba.js). Farby a fonty
// su presnou kopiou inline <script>tailwind.config = {...}</script>
// bloku, ktory mali app.html, cennik.html, index.html, obce.html,
// prihlasenie.html, zdroje.html, servis.html, trh.html a 404.html.
const colors = require('tailwindcss/colors');

module.exports = {
  content: [
    // Vsetky hlavne stranky (aj starosta, prvych-100-dni, odber-obce, mapa,
    // kontrola...): trieda, ktora v zozname chyba, sa v style.css nevygeneruje.
    "./public/*.html",
    "./public/*.js",
    // Generovane podstranky (pipeline ich prepisuje) — triedy pochadzaju
    // zo sablon v generuj_*.py, preto skenujeme aj tie.
    "./public/obce/**/*.html",
    "./public/konciace-zmluvy/**/*.html",
    "./pipeline/generuj_*.py",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['IBM Plex Sans', 'system-ui', '-apple-system', 'Segoe UI', 'sans-serif'],
        // Redizajn 2. 11. 2026: nadpisy bez patkoveho italic pisma (posobilo ako
        // generovane AI). font-serif ostava ako alias, aby sa nemuseli menit sablony.
        serif: ['IBM Plex Sans', 'system-ui', '-apple-system', 'Segoe UI', 'sans-serif'],
        mono: ['IBM Plex Mono', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      colors: {
        ink: '#0B1220', slate2: '#59636F', line: '#E1E5EA',
        accent: '#B25313', accentDark: '#8A3F0D', paper: '#FFFFFF', pas: '#F3F5F7',
        // amber = znackova farba (bg-amber, text-amber) + standardna paleta
        // amber-50…950 pre zlte upozornenia. Predtym tu bolo amber: '#E8A33D',
        // co paletu prepisalo a bg-amber-50/text-amber-900 nerobili nic.
        amber: { ...colors.amber, DEFAULT: '#E8A33D' },
      },
    },
  },
  plugins: [],
};
