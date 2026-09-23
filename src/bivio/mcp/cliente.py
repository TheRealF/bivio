"""Un client MCP minimo: accende un server, gli chiede gli strumenti, li chiama.

Serve alla portineria, che deve stare in mezzo fra l'agente e i server veri.
E' il lato opposto di `protocollo.py` e ha le stesse due attenzioni: stdout
solo JSON-RPC, e le due revisioni servite insieme.

⚠️ `initialize` SI MANDA LO STESSO, anche se la revisione 2026-07-28 l'ha
tolto. I server installati oggi sono quasi tutti della revisione vecchia e
senza stretta di mano non rispondono a niente; uno nuovo risponde «metodo
sconosciuto» e si tira dritto. Provare e ignorare l'errore copre tutti e due.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time

from .protocollo import VERSIONE, _dilo


META = {
    "io.modelcontextprotocol/protocolVersion": VERSIONE,
    "io.modelcontextprotocol/clientInfo": {"name": "bivio-portineria", "version": "0.1.0"},
    "io.modelcontextprotocol/clientCapabilities": {},
}


class ErroreCliente(RuntimeError):
    pass


class Collegamento:
    """Un server MCP acceso come processo figlio, su stdio."""

    def __init__(self, nome: str, comando: str, argomenti: list[str] | None = None,
                 ambiente: dict | None = None, attesa: float = 30.0):
        self.nome = nome
        self.attesa = attesa
        amb = dict(os.environ)
        amb.update(ambiente or {})
        try:
            self._p = subprocess.Popen(
                [comando] + list(argomenti or []),
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", bufsize=1, env=amb,
            )
        except FileNotFoundError as e:
            raise ErroreCliente(f"«{nome}»: non trovo il comando «{comando}»") from e
        self._id = 0
        self._lucchetto = threading.Lock()
        # Lo stderr del figlio va letto, sennò riempie il tubo e il processo si
        # blocca. Lo si butta su un thread e lo si ripete con l'etichetta.
        threading.Thread(target=self._sfoga, daemon=True).start()
        self.strumenti: list[dict] = []

    def _sfoga(self) -> None:
        for riga in self._p.stderr:
            if riga.strip():
                _dilo(f"  [{self.nome}] {riga.rstrip()}")

    # ----------------------------------------------------------------- invio

    def _chiama(self, metodo: str, params: dict | None = None, notifica: bool = False):
        with self._lucchetto:
            messaggio = {"jsonrpc": "2.0", "method": metodo}
            if params is not None:
                # ⚠️ La revisione 2026-07-28 vuole `_meta` su OGNI richiesta e
                # non solo nella stretta di mano, perche' la stretta di mano non
                # c'e' piu': senza sessione, ogni richiesta deve dire da sola
                # con chi sta parlando. I server vecchi lo ignorano.
                params = dict(params)
                params.setdefault("_meta", {}).update(META)
                messaggio["params"] = params
            if not notifica:
                self._id += 1
                messaggio["id"] = self._id
            if self._p.poll() is not None:
                raise ErroreCliente(f"«{self.nome}» si e' chiuso (codice {self._p.returncode})")
            self._p.stdin.write(json.dumps(messaggio, ensure_ascii=False) + "\n")
            self._p.stdin.flush()
            if notifica:
                return None
            scade = time.time() + self.attesa
            while time.time() < scade:
                riga = self._p.stdout.readline()
                if not riga:
                    raise ErroreCliente(f"«{self.nome}» ha chiuso lo stdout")
                try:
                    r = json.loads(riga)
                except json.JSONDecodeError:
                    continue                      # rumore: si salta
                if r.get("id") != messaggio["id"]:
                    continue                      # notifica o risposta di un altro
                if "error" in r:
                    raise ErroreCliente(f"«{self.nome}» {metodo}: {r['error'].get('message')}")
                return r.get("result", {})
            raise ErroreCliente(f"«{self.nome}» non ha risposto a {metodo} in {self.attesa}s")

    # ------------------------------------------------------------------- uso

    def presentati(self) -> None:
        try:
            self._chiama("initialize", {
                "protocolVersion": VERSIONE,
                "capabilities": {},
                "clientInfo": {"name": "bivio-portineria", "version": "0.1.0"},
            })
            self._chiama("notifications/initialized", {}, notifica=True)
        except ErroreCliente as e:
            # Un server della revisione nuova non ha piu' `initialize`: va bene.
            _dilo(f"  [{self.nome}] niente stretta di mano ({e}); tiro dritto.")

    def leggi_strumenti(self) -> list[dict]:
        fuori, cursore = [], None
        while True:
            r = self._chiama("tools/list", {"cursor": cursore} if cursore else {})
            fuori += r.get("tools", [])
            cursore = r.get("nextCursor")
            if not cursore:
                break
        self.strumenti = fuori
        return fuori

    def usa(self, nome: str, argomenti: dict) -> dict:
        return self._chiama("tools/call", {"name": nome, "arguments": argomenti})

    def spegni(self) -> None:
        try:
            self._p.stdin.close()
            self._p.wait(timeout=5)
        except Exception:
            self._p.kill()


def accendi(configurazione: dict) -> dict[str, Collegamento]:
    """Accende tutti i server della configurazione. Chi non parte si salta."""
    fuori: dict[str, Collegamento] = {}
    for nome, c in (configurazione.get("server") or {}).items():
        try:
            col = Collegamento(nome, c["comando"], c.get("argomenti"),
                               c.get("ambiente"), float(c.get("attesa", 30)))
            col.presentati()
            n = len(col.leggi_strumenti())
            _dilo(f"[portineria] {nome}: {n} strumenti")
            fuori[nome] = col
        except (ErroreCliente, KeyError) as e:
            # ⚠️ Un server rotto non deve spegnere la portineria: gli altri
            # funzionano, e chi ha sbagliato la riga lo legge nel log.
            _dilo(f"[portineria] {nome} NON parte: {e}")
    return fuori
