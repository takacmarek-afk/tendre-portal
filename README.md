# tendre-portal

## Tailwind: staticky CSS (od vlny 34, 24. 9. 2026)

Stranky uz nepouzivaju `cdn.tailwindcss.com` (kompilacia za behu v
prehliadaci). Styly su vopred vybuildene v `public/style.css` (vsetky stranky
aj generovane podstranky v `public/obce/` a `public/konciace-zmluvy/`) a
`public/style-platba.css` (len `platba-vysledok.html`, ma vlastnu paletu).
`<link rel="stylesheet" href="/style.css">` je na konci `<head>`, tam kde
predtym CDN vkladal svoj `<style>` — vlastne `<style>` bloky stranok maju teda
rovnaku (nizsiu) prioritu ako predtym.

Verzia Tailwindu je pevne 3.4.17 (rovnaka, akú servíroval CDN).

**Po kazdej zmene Tailwind tried** v `public/**/*.html`, `public/*.js` alebo
v sablonach `pipeline/generuj_*.py` treba znova vybuildit a commitnut CSS:

```
npm install
npm run build:css
```

Inak sa nova trieda neprejavi (uz to nie je live JIT z CDN). Zoznam
skenovanych suborov je v `tailwind.config.main.js` → `content`.

Pozn.: `amber` je v konfigu prepisany na jednu farbu (#E8A33D), preto triedy
ako `bg-amber-50` / `text-amber-900` negeneruju nic — tak to bolo aj s CDN.
