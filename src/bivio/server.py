"""Il server: due porte sullo stesso motore.

`/v1/decisioni` e' l'API di Bivio, in italiano, con l'astensione e i numeri.
`/v1/systemone` ha la forma dell'API di TypeSafe: un programma scritto per
Jev punta qui cambiando l'indirizzo di base e nient'altro. La forma e'
compatibile, il modello no: la risposta dichiara sempre il modello locale, e
nessuna risposta si spaccia per Jev.

E' fatto con la libreria standard apposta: un server di prova che tira dietro
un framework e' un server che un giorno non si installa.
"""

from __future__ import annotations

import json
import os
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from . import __version__, modelli
from .decisione import Bivio
from .tipi import ErroreDomanda

QUI = os.path.dirname(os.path.abspath(__file__))
LIMITE_STATO = 256 * 1024  # byte; oltre si rifiuta invece di tagliare


class Applicazione:
    def __init__(self, cervello: Bivio, chiave: str | None = None):
        self.cervello = cervello
        self.chiave = chiave
        self.lucchetto = threading.Lock()

    # ------------------------------------------------------------- traduzioni

    def systemone(self, corpo: dict) -> dict:
        """Forma TypeSafe in entrata, forma TypeSafe in uscita."""
        stato = corpo.get("state")
        domande = corpo.get("questions")
        if stato is None:
            raise ErroreDomanda("manca «state»")
        # Nel formato compatibile l'astensione non esiste: non c'e' un campo
        # dove dirla, e una risposta nulla romperebbe chi legge «choice».
        grezzo = self.cervello.grezzo(stato, domande or {}, astensione=False)
        risposte = {}
        for nome, r in grezzo["risposte"].items():
            risposte[nome] = _in_inglese(r)
        return {
            "model": grezzo["modello"],
            "answers": risposte,
            "usage": {
                "input_tokens": grezzo["consumo"]["token_ingresso"],
                "output_tokens": 0,
            },
            "x_bivio": {
                "misure": grezzo["misure"],
                "impronta": grezzo["impronta"],
                "versione": __version__,
            },
        }

    def decisioni(self, corpo: dict) -> dict:
        stato = corpo.get("stato", corpo.get("state"))
        domande = corpo.get("domande", corpo.get("questions"))
        if stato is None:
            raise ErroreDomanda("manca «stato»")
        astensione = corpo.get("astensione")
        # ⚠️ `giri` si accetta per richiesta perche' e' un compromesso fra
        # tempo e affidabilita', e chi chiama sa quale dei due gli serve. Il
        # server e' a un lucchetto solo, quindi si rimette com'era in ogni caso.
        giri = corpo.get("giri")
        if giri is None:
            return self.cervello.grezzo(stato, domande or {}, astensione=astensione)
        prima = self.cervello.giri
        try:
            self.cervello.giri = max(1, int(giri))
            return self.cervello.grezzo(stato, domande or {}, astensione=astensione)
        finally:
            self.cervello.giri = prima


def _in_inglese(r: dict) -> dict:
    """Dalla risposta di Bivio a quella che si aspetta un programma per Jev."""
    if r["tipo"] == "si_no":
        return {"type": "noul", "noul": round(r.get("probabilita_si", 0.0), 6)}
    if r["tipo"] == "scelta":
        return {
            "type": "choice",
            "choice": r.get("valore"),
            "probabilities": r["probabilita"],
            "confidence": r["confidenza"],
        }
    if r["tipo"] == "voto":
        return {
            "type": "score",
            "score": r.get("valore"),
            "legend": r.get("legenda", {}),
            "probabilities": r["probabilita"],
            "confidence": r["confidenza"],
        }
    return {
        "type": "numeric",
        "value": r.get("valore"),
        "median": r.get("mediana"),
        "unit": r.get("unita", ""),
        "probabilities": r["probabilita"],
        "confidence": r["confidenza"],
    }


class Manico(BaseHTTPRequestHandler):
    app: Applicazione = None  # riempito da `avvia`
    server_version = "bivio/" + __version__
    protocol_version = "HTTP/1.1"

    def log_message(self, formato, *args):  # meno rumore, una riga per richiesta
        print("  %s %s" % (self.address_string(), formato % args))

    # ------------------------------------------------------------------ utili

    def _manda(self, codice: int, corpo, tipo="application/json; charset=utf-8"):
        if isinstance(corpo, (dict, list)):
            grezzo = json.dumps(corpo, ensure_ascii=False).encode("utf-8")
        elif isinstance(corpo, str):
            grezzo = corpo.encode("utf-8")
        else:
            grezzo = corpo
        self.send_response(codice)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(grezzo)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()
        self.wfile.write(grezzo)

    def _autorizzato(self) -> bool:
        if not self.app.chiave:
            return True
        testa = self.headers.get("Authorization", "")
        return testa.strip() == "Bearer " + self.app.chiave

    def do_OPTIONS(self):
        self._manda(204, b"")

    # ------------------------------------------------------------------ rotte

    def do_GET(self):
        via = urlparse(self.path).path.rstrip("/") or "/"
        if via in ("/", "/campo", "/playground"):
            with open(os.path.join(QUI, "web", "campo.html"), "rb") as f:
                return self._manda(200, f.read(), "text/html; charset=utf-8")
        if via in ("/salute", "/health"):
            return self._manda(200, self.app.cervello.salute())
        if via == "/v1/models":
            nome = self.app.cervello.motore.nome
            return self._manda(200, {"data": [
                {"id": nome, "object": "model", "owned_by": "locale"},
                {"id": "bivio-latest", "object": "model", "owned_by": "locale"},
            ]})
        return self._manda(404, {"errore": "non c'e' niente qui", "via": via})

    def do_POST(self):
        via = urlparse(self.path).path.rstrip("/") or "/"
        if via not in ("/v1/decisioni", "/v1/systemone", "/v1/decisions"):
            return self._manda(404, {"errore": "non c'e' niente qui", "via": via})
        if not self._autorizzato():
            return self._manda(401, {"error": {"message": "chiave mancante o sbagliata"}})

        quanti = int(self.headers.get("Content-Length") or 0)
        if quanti > LIMITE_STATO:
            return self._manda(413, {"error": {"message":
                f"la richiesta supera {LIMITE_STATO} byte"}})
        try:
            corpo = json.loads(self.rfile.read(quanti) or b"{}")
        except ValueError as e:
            return self._manda(422, {"error": {"message": f"JSON non valido: {e}"}})

        try:
            if via == "/v1/systemone":
                return self._manda(200, self.app.systemone(corpo))
            return self._manda(200, self.app.decisioni(corpo))
        except ErroreDomanda as e:
            return self._manda(422, {"error": {"message": str(e)}})
        except Exception as e:  # pragma: no cover
            traceback.print_exc()
            return self._manda(500, {"error": {"message": str(e)}})


def avvia(cervello: Bivio, porta: int = 8017, indirizzo: str = "127.0.0.1",
          chiave: str | None = None):
    Manico.app = Applicazione(cervello, chiave)
    servitore = ThreadingHTTPServer((indirizzo, porta), Manico)
    print(f"Bivio {__version__} su http://{indirizzo}:{porta}")
    print(f"  modello   {cervello.motore.nome}")
    print(f"  campo     http://{indirizzo}:{porta}/campo")
    print(f"  API       POST /v1/decisioni  ·  POST /v1/systemone (forma Jev)")
    if chiave:
        print("  chiave    richiesta (BIVIO_API_KEY)")
    print("Ctrl-C per fermare.")
    try:
        servitore.serve_forever()
    except KeyboardInterrupt:
        print("\nFermato.")
    finally:
        servitore.server_close()
