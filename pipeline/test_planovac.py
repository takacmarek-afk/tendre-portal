"""Tabulka uloh v Cloudflare planovaci musi sediet s workflowmi (11. 11. 2026)."""
import re
from pathlib import Path

KOREN = Path(__file__).resolve().parent.parent


def test_planovac_pozna_vsetky_ulohy():
    worker = (KOREN / "cloudflare/planovac/worker.js").read_text(encoding="utf-8")
    ulohy = set(re.findall(r'\["([a-z0-9-]+\.yml)", "([^"]+)"\]', worker))
    z_workflowov = set()
    for f in (KOREN / ".github/workflows").glob("*.yml"):
        s = f.read_text(encoding="utf-8")
        if "Planovanie: Cloudflare Worker" in s:
            for c in re.findall(r'^  #   - cron: "([^"]+)"', s, re.M):
                z_workflowov.add((f.name, c))
            assert "planovane:" in s and "env.UDALOST" in s or "UDALOST:" in s, f.name
    assert ulohy == z_workflowov
    for w, _ in ulohy:
        assert (KOREN / ".github/workflows" / w).exists(), w
