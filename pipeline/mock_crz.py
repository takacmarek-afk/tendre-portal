"""Mock CRZ sync API — overuje strankovanie cez Link hlavicku a rate limity."""
import json, random, threading
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

random.seed(7)
DNES = date.today()
URADY = [("Mesto Ziar nad Hronom","00321125"),("Obec Rakova","00314234"),
         ("Nemocnica Poprad, a.s.","36513458"),("Zilinsky samospravny kraj","37808427")]
DOD_MONO = "Stavby ABC s.r.o."
DOD = ["Stavby ABC s.r.o.","Cistota SK s.r.o.","BuildPro a.s.","Zelen Servis s.r.o."]
PREDMETY = [
 ("Zmluva o dielo - rekonstrukcia strechy ZS","stavebne prace na objekte skoly"),
 ("Upratovacie sluzby v administrativnej budove","komplexne upratovanie a dezinfekcia"),
 ("Rekonstrukcia miestnej komunikacie","asfaltovanie a oprava chodnika"),
 ("Zimna udrzba a kosenie travnatych ploch","udrzba zelene, odpratavanie snehu"),
 ("Najomna zmluva na kancelarske priestory","prenajom"),          # ma vypadnut
 ("Poistna zmluva - majetok obce","poistenie budov"),             # ma vypadnut
 ("Dodavka kancelarskych potrieb","papier, tonery"),              # ma vypadnut
]

def zaznam(i):
    urad, cin = URADY[i % len(URADY)]
    subj, popis = PREDMETY[i % len(PREDMETY)]
    # 40 % zmluv konci v predikcnom okne, zvysok je historia
    if i % 5 in (0, 1):
        eff_to = DNES + timedelta(days=random.randint(91, 179))
    else:
        eff_to = DNES - timedelta(days=random.randint(30, 900))
    # urad index 0 ma monopolneho dodavatela -> ma vyjst VYSOKE riziko
    dod = DOD_MONO if (i % len(URADY)) == 0 else DOD[i % len(DOD)]
    return {
        "id": 1000 + i,
        "contract_identifier": f"ZoD-{i}/2026",
        "contracting_authority_name": urad,
        "contracting_authority_cin": cin,
        "contracting_authority_formatted_address": "Namestie 1, 010 01",
        "supplier_name": dod, "supplier_cin": 44000000 + i,
        "subject": subj, "subject_description": popis,
        "signed_on": str(eff_to - timedelta(days=365)),
        "effective_from": str(eff_to - timedelta(days=364)),
        "effective_to": str(eff_to), "effective_note": None,
        "contract_price_amount": 20000 + i * 1500,
        "contract_price_total_amount": 20000 + i * 1500,
        "status_id": 2, "type_id": 1,
        "published_at": "2025-01-01T00:00:00.000000Z",
        "procurement_url": None,
        "department": {"id": 1, "name": "Ministerstvo vnutra SR"},
        "updated_at": f"2026-01-{(i % 28) + 1:02d}T10:00:00.000000Z",
    }

CELKOM, STRANA = 140, 40

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        q = parse_qs(urlparse(self.path).query)
        off = int(q.get("offset", ["0"])[0])
        davka = [zaznam(i) for i in range(off, min(off + STRANA, CELKOM))]
        telo = json.dumps(davka).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("X-RateLimit-Remaining", "58")
        if off + STRANA < CELKOM:
            self.send_header("Link", f"<http://127.0.0.1:8899/sync?offset={off+STRANA}>; rel='next'")
        self.send_header("Content-Length", str(len(telo)))
        self.end_headers(); self.wfile.write(telo)

def start():
    srv = HTTPServer(("127.0.0.1", 8899), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv
