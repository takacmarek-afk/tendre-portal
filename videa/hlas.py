"""Slovensky hlas do videi navodov (10. 11. 2026).

Hotovy slovensky neuronovy hlas Microsoft (sk-SK-LukasNeural, sk-SK-ViktoriaNeural).
- Ostro: Azure Speech (premenne AZURE_SPEECH_KEY a AZURE_SPEECH_REGION, bezplatna
  uroven F0 = 0,5 mil. znakov mesacne, komercne pouzitie povolene).
- Bez kluca: edge-tts (ten isty hlas cez Microsoft Edge, len na ukazky).

    python videa/hlas.py ukazka vystup/hlas      # ukazky oboch hlasov (mp3)
"""
import asyncio
import hashlib
import html
import os
import subprocess
import sys
from pathlib import Path

HLASY = {"lukas": "sk-SK-LukasNeural", "viktoria": "sk-SK-ViktoriaNeural"}
HLAS = os.environ.get("HLAS", "lukas")
TEMPO = os.environ.get("HLAS_TEMPO", "+5%")     # mierne svizejsie, prirodzenejsie
CACHE = Path(os.environ.get("HLAS_CACHE", "/tmp/hlas-cache"))

# Vyslovnost slov, ktore TTS cita zle (pisane -> hovorene)
VYSLOVNOST = {
    "PredTendrom": "Pred tendrom", "predtendrom.sk": "pred tendrom bodka es ká",
    "ÚVO": "úvo", "CRZ": "cé er zet", "ITMS21+": "i té em es dvadsaťjeden plus",
    "IČO": "íčo", "e-mail": "imejl", "e-mailom": "imejlom", "Excelu": "excelu",
}


def priprav(text: str) -> str:
    t = " ".join(str(text).split())
    for a, b in VYSLOVNOST.items():
        t = t.replace(a, b)
    return t


def trvanie(subor: Path) -> float:
    out = subprocess.run(["ffmpeg", "-i", str(subor), "-f", "null", "-"], capture_output=True, text=True).stderr
    import re
    m = re.findall(r"time=(\d+):(\d+):([\d.]+)", out)
    if not m:
        return 0.0
    h, mi, s = m[-1]
    return int(h) * 3600 + int(mi) * 60 + float(s)


def _azure(text, hlas, ciel: Path):
    import requests
    kluc, reg = os.environ["AZURE_SPEECH_KEY"], os.environ["AZURE_SPEECH_REGION"]
    ssml = (f"<speak version='1.0' xml:lang='sk-SK'><voice name='{hlas}'>"
            f"<prosody rate='{TEMPO}'>{html.escape(text)}</prosody></voice></speak>")
    r = requests.post(f"https://{reg}.tts.speech.microsoft.com/cognitiveservices/v1", data=ssml.encode("utf-8"),
                      headers={"Ocp-Apim-Subscription-Key": kluc, "Content-Type": "application/ssml+xml",
                               "X-Microsoft-OutputFormat": "audio-24khz-96kbitrate-mono-mp3"}, timeout=60)
    r.raise_for_status()
    ciel.write_bytes(r.content)


def _edge(text, hlas, ciel: Path):
    import edge_tts
    asyncio.run(edge_tts.Communicate(text, hlas, rate=TEMPO).save(str(ciel)))


def povedz(text: str, hlas_kluc: str = None) -> "tuple[Path, float]":
    """-> (mp3, sekundy). Vysledky sa ukladaju do cache podla textu a hlasu."""
    hlas = HLASY.get(hlas_kluc or HLAS, hlas_kluc or HLAS)
    t = priprav(text)
    CACHE.mkdir(parents=True, exist_ok=True)
    ciel = CACHE / (hashlib.sha1(f"{hlas}|{TEMPO}|{t}".encode()).hexdigest()[:16] + ".mp3")
    if not ciel.exists():
        if os.environ.get("AZURE_SPEECH_KEY"):
            _azure(t, hlas, ciel)
        else:
            _edge(t, hlas, ciel)
    return ciel, trvanie(ciel)


UKAZKA = ("Dobrý deň. Pred tendrom vám ukáže zmluvy úradov, ktoré sa vo vašom odbore blížia ku koncu. "
          "Vidíte, kto zmluvu má, za koľko a do kedy. Každý údaj si overíte jedným klikom "
          "v Centrálnom registri zmlúv. A keď úrad vyhlási novú súťaž z eurofondov, pošleme vám imejl.")

if __name__ == "__main__" and sys.argv[1:2] == ["ukazka"]:
    out = Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    for k in HLASY:
        for tempo in ("+0%", "+8%"):
            TEMPO = tempo
            mp3, s = povedz(UKAZKA, k)
            ciel = out / f"ukazka-{k}-tempo{tempo.replace('%', '').replace('+', '')}.mp3"
            ciel.write_bytes(mp3.read_bytes())
            print(f"{ciel.name}: {s:.1f} s")
