"""Spolocna znacka vsetkych e-mailov PredTendrom.sk (10. 11. 2026).

Jedno miesto pre logo, farby, podpis a odkazy na Facebook a Instagram,
aby studene e-maily, onboarding, tyzdenny prehlad aj osobne odpovede
vyzerali rovnako.

Zasady (dorucitelnost):
- Jediny obrazok je male logo na nasej domene (ziadny banner, ziadny pixel).
  Ked ho Gmail/Outlook zablokuje, ostane citatelny alt text.
- Vsetko inline a tabulkovo, Outlook ignoruje <style>.
- Odkazy mimo predtendrom.sk su LEN tieto dva profily v podpise.
"""
import html

WEB = "https://predtendrom.sk"
LOGO_URL = f"{WEB}/email/logo.png"          # 480x80 px, zobrazuje sa 168x28
FACEBOOK = "https://www.facebook.com/profile.php?id=1381441591712353"
INSTAGRAM = "https://www.instagram.com/predtendrom.sk/"
SOCIALNE = (FACEBOOK, INSTAGRAM)

INK = "#0B1220"
AKCENT = "#B25313"
SIVA = "#5a6472"
SVETLA = "#8a929e"
LINKA = "#e7e1d4"
PISMO = "Arial,Helvetica,sans-serif"

MENO = "Marek Takáč"
ROLA = "zakladateľ PredTendrom.sk"
SLOGAN = "Verejné zákazky skôr, než ich úrad vyhlási"


def logo_html(sirka=168):
    vyska = round(sirka / 6)
    return (f'<a href="{WEB}" style="text-decoration:none;">'
            f'<img src="{LOGO_URL}" width="{sirka}" height="{vyska}" alt="PredTendrom.sk" '
            f'style="display:block;border:0;outline:none;width:{sirka}px;height:{vyska}px;'
            f'font:700 17px/1.2 {PISMO};color:{INK};"></a>')


def odkazy_html(farba=AKCENT, velkost=13):
    s = f'color:{farba};text-decoration:none;font-weight:600;'
    bodka = f'<span style="color:{SVETLA};">&nbsp;·&nbsp;</span>'
    return (f'<span style="font:{velkost}px/1.5 {PISMO};">'
            f'<a href="{WEB}" style="{s}">predtendrom.sk</a>{bodka}'
            f'<a href="{FACEBOOK}" style="{s}">Facebook</a>{bodka}'
            f'<a href="{INSTAGRAM}" style="{s}">Instagram</a></span>')


def podpis_html(meno=MENO, rola=ROLA, logo=True):
    """Podpis pod textom: meno, rola, male logo, web · Facebook · Instagram."""
    return (
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
        f'style="margin:4px 0 0;border-collapse:collapse;">'
        f'<tr><td style="border-left:3px solid {AKCENT};padding:2px 0 2px 12px;">'
        f'<div style="font:700 15px/1.4 {PISMO};color:{INK};">{html.escape(meno)}</div>'
        f'<div style="font:13px/1.4 {PISMO};color:{SIVA};margin-bottom:8px;">{html.escape(rola)}</div>'
        + (logo_html(132) if logo else "")
        + f'<div style="margin-top:6px;">{odkazy_html()}</div>'
        '</td></tr></table>')


def podpis_text(meno=MENO, rola=ROLA):
    return (f"{meno}\n{rola}\n"
            f"predtendrom.sk | Facebook: {FACEBOOK} | Instagram: {INSTAGRAM}")


def hlavicka_html():
    """Pas s logom na vrchu e-mailu (lifecycle a prehlady, nie studene e-maily)."""
    return (f'<tr><td style="padding:20px 24px 16px;border-bottom:3px solid {AKCENT};">'
            f'{logo_html()}</td></tr>')


def socialne_html():
    """Riadok do pateky."""
    return (f'Sledujte nás: <a href="{FACEBOOK}" style="color:{SVETLA};">Facebook</a> · '
            f'<a href="{INSTAGRAM}" style="color:{SVETLA};">Instagram</a>')


def je_povoleny_odkaz(url):
    return str(url).startswith(WEB) or url in SOCIALNE


_STARY_PODPIS = ("Marek Takáč\nPredTendrom.sk", "Marek Takáč, PredTendrom.sk")


def osobny_email(text):
    """Obycajny text osobneho e-mailu -> (text, html) so znackovym podpisom.

    Starý podpis "Marek Takáč\\nPredTendrom.sk" na konci sa nahradi novym.
    Odkazy v texte sa neprevadzaju (osobne sablony ich nemaju, a ak ano,
    ostanu citatelne ako text)."""
    t = text.rstrip()
    for p in _STARY_PODPIS:
        if t.endswith(p):
            t = t[: -len(p)].rstrip()
            break
    odseky = [o for o in t.split("\n\n") if o.strip()]
    h = "".join(f'<p style="margin:0 0 14px;">{html.escape(o.strip()).replace(chr(10), "<br>")}</p>'
                for o in odseky)
    telo = (f'<!doctype html><html lang="sk"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head><body style="margin:0;padding:16px;'
            f'font:15px/1.6 {PISMO};color:{INK};background:#ffffff;">'
            f'<div style="max-width:580px;">{h}{podpis_html()}</div></body></html>')
    return t + "\n" + podpis_text() + "\n", telo
