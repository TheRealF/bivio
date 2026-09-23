"""JSON-RPC 2.0 su stdio: il minimo che serve per parlare MCP.

Scritto a mano, come tutto il resto di Bivio: l'SDK ufficiale tira dentro
pydantic, httpx, anyio e starlette, e questo pacchetto finora ha due
dipendenze in croce. Qui servono due metodi (`tools/list`, `tools/call`) e
un dizionario.

⚠️ DUE REVISIONI, E VANNO SERVITE TUTTE E DUE. La revisione **2026-07-28**
ha tolto la stretta di mano: niente piu' `initialize`, niente sessione, ogni
richiesta porta la sua versione dentro a `_meta`. I client installati oggi
pero' la stretta di mano la fanno ancora, e uno che manda `initialize` e non
riceve risposta resta li'. Quindi: se arriva `initialize` si risponde, se non
arriva si lavora lo stesso. Costa venti righe e copre tutti e due i mondi.

⚠️ SU STDOUT CI VA SOLO JSON-RPC. Una riga di log stampata per sbaglio
rompe la conversazione e il client non dice perche'. Tutto quello che si
vuole far vedere va su stderr, e `_dilo()` e' li' per quello.
"""

from __future__ import annotations

import json
import sys
import traceback
from typing import Callable

# La revisione che implementiamo. Se il client ne chiede una che conosciamo,
# gli si risponde con la sua: e' quello che dice di fare la specifica.
VERSIONE = "2026-07-28"
CONOSCIUTE = ("2026-07-28", "2025-06-18", "2025-03-26", "2024-11-05")

# Codici JSON-RPC.
NON_TROVATO = -32601
PARAMETRI = -32602
INTERNO = -32603


def _dilo(*pezzi) -> None:
    print(*pezzi, file=sys.stderr, flush=True)


class Servitore:
    """Un server MCP su stdio. Gli strumenti si registrano con `@aggiungi`."""

    def __init__(self, nome: str, versione: str, istruzioni: str = ""):
        self.nome = nome
        self.versione = versione
        self.istruzioni = istruzioni
        self._strumenti: dict[str, dict] = {}
        self._fai: dict[str, Callable] = {}

    # ------------------------------------------------------------ registro

    def aggiungi(self, nome: str, titolo: str, descrizione: str, schema: dict,
                 uscita: dict | None = None, annotazioni: dict | None = None):
        """Decoratore. La funzione riceve gli argomenti e torna un dizionario."""
        def dentro(f: Callable):
            voce = {"name": nome, "title": titolo, "description": descrizione,
                    "inputSchema": schema}
            if uscita:
                voce["outputSchema"] = uscita
            if annotazioni:
                voce["annotations"] = annotazioni
            self._strumenti[nome] = voce
            self._fai[nome] = f
            return f
        return dentro

    def elenco(self) -> list[dict]:
        # ⚠️ Ordine deterministico: la specifica lo chiede perche' un elenco
        # che cambia ordine manda a vuoto la cache del prompt del client.
        return [self._strumenti[k] for k in sorted(self._strumenti)]

    # ------------------------------------------------------------- risposte

    def _capacita(self) -> dict:
        return {"tools": {"listChanged": False}}

    def _initialize(self, params: dict) -> dict:
        chiesta = (params or {}).get("protocolVersion")
        return {
            "protocolVersion": chiesta if chiesta in CONOSCIUTE else VERSIONE,
            "capabilities": self._capacita(),
            "serverInfo": {"name": self.nome, "version": self.versione},
            "instructions": self.istruzioni,
        }

    def _tools_list(self) -> dict:
        return {
            "resultType": "complete",
            "tools": self.elenco(),
            # L'elenco non cambia mai finche' il processo vive, quindi si puo'
            # tenere in cache. `private` perche' dipende dalla configurazione
            # di chi lo lancia, non e' roba da mettere in una cache condivisa.
            "ttlMs": 3_600_000,
            "cacheScope": "private",
        }

    def _tools_call(self, params: dict) -> dict:
        nome = (params or {}).get("name")
        if nome not in self._fai:
            raise Sconosciuto(f"strumento sconosciuto: {nome}")
        argomenti = (params or {}).get("arguments") or {}
        try:
            dati = self._fai[nome](**argomenti)
        except TypeError as e:
            # Argomenti sbagliati: e' un errore che il modello puo' correggere
            # da solo, quindi va nel risultato e non come errore di protocollo.
            return _esito(f"argomenti sbagliati per «{nome}»: {e}", errore=True)
        except Exception as e:
            _dilo(f"[bivio-mcp] {nome}: {type(e).__name__}: {e}")
            return _esito(f"{type(e).__name__}: {e}", errore=True)
        if isinstance(dati, dict) and "content" in dati:
            dati.setdefault("resultType", "complete")
            return dati
        return _esito(dati)

    # ------------------------------------------------------------- il ciclo

    def rispondi(self, messaggio: dict) -> dict | None:
        metodo = messaggio.get("method")
        ident = messaggio.get("id")
        # Le notifiche non hanno id e non vogliono risposta. `initialized`,
        # `cancelled` e compagnia si ignorano senza fare rumore.
        if ident is None:
            return None
        try:
            if metodo == "initialize":
                esito = self._initialize(messaggio.get("params") or {})
            elif metodo == "tools/list":
                esito = self._tools_list()
            elif metodo == "tools/call":
                esito = self._tools_call(messaggio.get("params") or {})
            elif metodo == "ping":
                esito = {}
            else:
                return _errore(ident, NON_TROVATO, f"metodo sconosciuto: {metodo}")
        except Sconosciuto as e:
            return _errore(ident, PARAMETRI, str(e))
        except Exception as e:      # pragma: no cover
            _dilo("[bivio-mcp]", traceback.format_exc())
            return _errore(ident, INTERNO, f"{type(e).__name__}: {e}")
        return {"jsonrpc": "2.0", "id": ident, "result": esito}

    def gira(self, dentro=None, fuori=None) -> int:
        dentro = dentro or sys.stdin
        fuori = fuori or sys.stdout
        for riga in dentro:
            riga = riga.strip()
            if not riga:
                continue
            try:
                messaggio = json.loads(riga)
            except json.JSONDecodeError:
                _dilo("[bivio-mcp] riga non JSON, saltata")
                continue
            risposta = self.rispondi(messaggio)
            if risposta is not None:
                fuori.write(json.dumps(risposta, ensure_ascii=False) + "\n")
                fuori.flush()
        return 0


class Sconosciuto(KeyError):
    pass


def _esito(dati, errore: bool = False) -> dict:
    """Il risultato di una chiamata: testo leggibile piu' il JSON strutturato.

    ⚠️ Il testo c'e' SEMPRE anche quando c'e' `structuredContent`: la
    specifica lo chiede per compatibilita', e in pratica e' quello che il
    modello legge davvero.
    """
    if isinstance(dati, str):
        testo, strutturato = dati, None
    else:
        testo = json.dumps(dati, ensure_ascii=False, indent=1)
        strutturato = dati
    fuori = {"resultType": "complete",
             "content": [{"type": "text", "text": testo}],
             "isError": bool(errore)}
    if strutturato is not None and not errore:
        fuori["structuredContent"] = strutturato
    return fuori


def _errore(ident, codice: int, messaggio: str) -> dict:
    return {"jsonrpc": "2.0", "id": ident, "error": {"code": codice, "message": messaggio}}
