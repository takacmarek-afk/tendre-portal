// Zdielany config pre vsetky stranky OKREM platba-vysledok.html (ta ma
// vlastnu, uzsiu paletu — viz tailwind.config.platba.js). Farby a fonty
// su presnou kopiou inline <script>tailwind.config = {...}</script>
// bloku, ktory dnes maju app.html, cennik.html, index.html, obce.html,
// prihlasenie.html, zdroje.html a 404.html.
module.exports = {
  content: [
    "./public/app.html",
    "./public/cennik.html",
    "./public/index.html",
    "./public/obce.html",
    "./public/prihlasenie.html",
    "./public/zdroje.html",
    "./public/404.html",
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
        accent: '#B25313', accentDark: '#8A3F0D', amber: '#E8A33D', paper: '#F7F3EA',
      },
    },
  },
  plugins: [],
};
