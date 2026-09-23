"""Il livello MCP di Bivio: il motore dentro a un agente.

`bivio mcp`         — Bivio come server MCP: un giudizio tipizzato e locale.
`bivio portineria`  — sta in mezzo fra l'agente e i server veri: espone tre
                      strumenti invece di duecento, e guarda le chiamate prima
                      di passarle.
"""

from .protocollo import VERSIONE, Servitore

__all__ = ["VERSIONE", "Servitore"]
