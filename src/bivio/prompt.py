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


# I tre modi di incorniciare un turno. Il modello giusto non si indovina: si
# legge dal GGUF (`tokenizer.chat_template`), perche' scrivere a un modello con
# i marcatori di un altro vuol dire parlargli in una lingua che non ha mai visto.
CORNICI = {
    "chatml": ("<|im_start|>system\n{sistema}<|im_end|>\n<|im_start|>user\n",
               "<|im_end|>\n<|im_start|>assistant\n"),
    "llama3": ("<|start_header_id|>system<|end_header_id|>\n\n{sistema}<|eot_id|>"
               "<|start_header_id|>user<|end_header_id|>\n\n",
               "<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n\n"),
    "piano": ("{sistema}\n\n", "\n"),
}


def riconosci(modello_template: str | None) -> str:
    """Da che cosa e' scritto nel GGUF a quale cornice usare."""
    t = modello_template or ""
    if "<|im_start|>" in t:
        return "chatml"
    if "<|start_header_id|>" in t:
        return "llama3"
    if "[INST]" in t:
        return "piano"      # Mistral: la cornice non porta un turno di sistema
    return "piano"


def prefisso(stato, personalizzato: str | None = None, cornice: str = "chatml") -> str:
    """La meta' condivisa: istruzioni e stato."""
    apre, _ = CORNICI.get(cornice, CORNICI["piano"])
    corpo = f"STATO\n{_testo(stato).strip()}\n\n"
    return apre.format(sistema=sistema(personalizzato)) + corpo


def suffisso(domanda: Domanda, cornice: str = "chatml") -> str:
    """La meta' che cambia: la domanda come scelta multipla."""
    _, chiude = CORNICI.get(cornice, CORNICI["piano"])
    corpo = (
        "DOMANDA\n" + domanda.istruzioni.strip() + "\n\n"
        "OPZIONI\n" + domanda.blocco() + "\n"
    )
    return corpo + chiude + CHIUSURA


def intero(stato, domanda: Domanda, personalizzato: str | None = None,
           cornice: str = "chatml") -> str:
    """Il prompt completo: serve alle prove e a chi vuole vedere che cosa parte."""
    return prefisso(stato, personalizzato, cornice) + suffisso(domanda, cornice)


def lettere(domanda: Domanda) -> list[str]:
    return [LETTERE[i] for i in range(len(domanda.opzioni))]
