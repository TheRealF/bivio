"""Bivio: decisioni tipizzate da un modello linguistico, in locale.

Un bivio e' il punto in cui si decide. Questa libreria fa una cosa sola:
prende uno stato non strutturato e una domanda, e torna una risposta del tipo
che hai chiesto con accanto la probabilita'. Senza generare un token.

    from bivio import Bivio
    b = Bivio()
    print(b.chiedi("Sono tre giorni che i pagamenti falliscono.",
                   "Il messaggio esprime urgenza"))
"""

from .decisione import Bivio, Risposta
from .tipi import ErroreDomanda, confidenza

__version__ = "0.1.0"
__all__ = ["Bivio", "Risposta", "ErroreDomanda", "confidenza", "__version__"]
