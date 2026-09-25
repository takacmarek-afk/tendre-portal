// Zdielany config pre vsetky stranky OKREM platba-vysledok.html (ta ma
// vlastnu, uzsiu paletu — viz tailwind.config.platba.js). Farby a fonty
// su presnou kopiou inline <script>tailwind.config = {...}</script>
// bloku, ktory mali app.html, cennik.html, index.html, obce.html,
// prihlasenie.html, zdroje.html, servis.html, trh.html a 404.html.
const colors = require('tailwindcss/colors');

module.exports = {
  content: [
    "./public/app.html",
    "./public/cennik.html",
    "./public/index.html",
    "./public/obce.html",
    "./public/prihlasenie.html",
    "./public/zdroje.html",
    "./public/404.html",
    "./public/servis.html",
    "./public/trh.html",
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
        serif: ['Instrument Serif', 'Georgia', 'serif'],
        mono: ['IBM Plex Mono', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      colors: {
        ink: '#0B1220', slate2: '#6B6558', line: '#E4DFD2',
        accent: '#B25313', accentDark: '#8A3F0D', paper: '#F7F3EA',
        // amber = znackova farba (bg-amber, text-amber) + standardna paleta
        // amber-50…950 pre zlte upozornenia. Predtym tu bolo amber: '#E8A33D',
        // co paletu prepisalo a bg-amber-50/text-amber-900 nerobili nic.
        amber: { ...colors.amber, DEFAULT: '#E8A33D' },
      },
    },
  },
  plugins: [],
};
