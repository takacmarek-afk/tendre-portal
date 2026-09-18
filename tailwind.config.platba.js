// Samostatny config len pre platba-vysledok.html — ma inu, uzsiu paletu
// (iny "ink", ziadny "amber"/"paper"). Skopirovane z jej inline
// <script>tailwind.config = {...}</script> bloku.
module.exports = {
  content: ["./public/platba-vysledok.html"],
  theme: {
    extend: {
      colors: {
        ink: '#14171F', slate2: '#5B6472', line: '#E4E1D6',
        accent: '#C77B34', accentDark: '#A6621F',
      },
      fontFamily: { serif: ['Georgia', 'serif'] },
    },
  },
  plugins: [],
};
