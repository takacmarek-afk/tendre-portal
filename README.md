# tendre-portal

## Tailwind: z CDN na staticky build (rozrobene, nedokoncene)

Web dnes bezi na `<script src="https://cdn.tailwindcss.com">` v kazdom
HTML subore (kompiluje sa za behu v prehliadaci — pomalsie, konzola hlasi
"cdn.tailwindcss.com should not be used in production"). Nahrada za
staticky, vopred vybuildeny CSS subor je pripravena (`package.json`,
`tailwind.config.main.js`, `tailwind.config.platba.js`, `src/*.css`), ale
NEBOLA este dokoncena — sandbox, v ktorom bezi Claude, nema pristup k
registru npmjs.org (organizacne nastavenie siete), takze `npm install`
tu nejde spustit.

**Dokoncenie (raz, v beznom terminali s internetom):**

```
npm install
npm run build:css
```

To vygeneruje `public/style.css` (vsetky stranky okrem platba-vysledok.html)
a `public/style-platba.css` (len tá). Potom v kazdom `public/*.html`
treba nahradit blok

```html
<script src="https://cdn.tailwindcss.com"></script>
<script>
tailwind.config = { ... }
</script>
```

za

```html
<link rel="stylesheet" href="./style.css">
```

(`./style-platba.css` len v `platba-vysledok.html`). Zaroven odstranit
Google Fonts `<link>` z tejto zmeny netreba — tie ostavaju.

**Po kazdej buducej zmene Tailwind tried v HTML** treba znova spustit
`npm run build:css` a commitnut novy `public/style*.css` — inak sa nova
trieda v CSS neobjavi (uz to nie je live JIT z CDN).
