"""Come lo stato e la domanda diventano testo.

Il prompt e' spezzato in due meta' apposta: la prima meta' (istruzioni di
sistema + stato) e' uguale per tutte le domande della stessa richiesta e
viene calcolata una volta sola; la seconda cambia a ogni domanda. E' da qui
che viene il guadagno di tempo quando si fanno dieci domande sullo stesso
documento.

La versione del prompt e' scritta nell'impronta della taratura: cambiare una
parola qui dentro cambia le probabilita', quindi una taratura fatta su v1
non si applica a v2.
"""

from __future__ import annotations

from .tipi import Domanda, LETTERE, _testo

VERSIONE = "v1"

SISTEMA = (
    "Sei un classificatore. Leggi lo stato e rispondi alla domanda "
    "scegliendo una sola delle opzioni elencate. "
    "Rispondi con la lettera dell'opzione e nient'altro."
)

# I due pezzi che chiudono il prompt. La riga finale serve a due cose: mette
# il modello nella posizione di dire una lettera, e da' un punto fisso su cui
# misurare quali lettere sono un token solo.
CHIUSURA = "Risposta:"


def sistema(personalizzato: str | None = None) -> str:
    return (personalizzato or SISTEMA).strip()


def prefisso(stato, personalizzato: str | None = None, chatml: bool = True) -> str:
    """La meta' condivisa: istruzioni e stato."""
    corpo = f"STATO\n{_testo(stato).strip()}\n\n"
    if chatml:
        return (
            "<|im_start|>system\n" + sistema(personalizzato) + "<|im_end|>\n"
            "<|im_start|>user\n" + corpo
        )
    return sistema(personalizzato) + "\n\n" + corpo


def suffisso(domanda: Domanda, chatml: bool = True) -> str:
    """La meta' che cambia: la domanda come scelta multipla."""
    corpo = (
        "DOMANDA\n" + domanda.istruzioni.strip() + "\n\n"
        "OPZIONI\n" + domanda.blocco() + "\n"
    )
    if chatml:
        return corpo + "<|im_end|>\n<|im_start|>assistant\n" + CHIUSURA
    return corpo + "\n" + CHIUSURA


def intero(stato, domanda: Domanda, personalizzato: str | None = None, chatml: bool = True) -> str:
    """Il prompt completo: serve alle prove e a chi vuole vedere che cosa parte."""
    return prefisso(stato, personalizzato, chatml) + suffisso(domanda, chatml)


def lettere(domanda: Domanda) -> list[str]:
    return [LETTERE[i] for i in range(len(domanda.opzioni))]
