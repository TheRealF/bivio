"""Il motore: llama.cpp, un passaggio in avanti, i logit delle lettere.

Qui dentro non si genera niente. Il modello fa un passaggio sul prompt e si
leggono i logit dell'ultima posizione, limitati alle lettere ammesse. Il
numero di token generati e' zero, e non e' un modo di dire: il ciclo di
decodifica non parte proprio.
"""

from __future__ import annotations

import hashlib
import os
import sys
import time
from dataclasses import dataclass

import numpy as np

from .tipi import LETTERE


class ErroreMotore(RuntimeError):
    pass


@dataclass
class Misure:
    """Quanto e' costato: serve a chi deve decidere se sta in un processo."""

    token_stato: int = 0
    token_domande: int = 0
    token_riusati: int = 0
    ms_stato: float = 0.0
    ms_domande: float = 0.0


class Motore:
    def __init__(
        self,
        percorso: str,
        n_ctx: int = 8192,
        n_gpu_layers: int = -1,
        n_threads: int | None = None,
        verboso: bool = False,
    ):
        if not os.path.exists(percorso):
            raise ErroreMotore(
                f"il modello non c'e': {percorso}\n"
                "Scaricalo con: bivio scarica"
            )
        try:
            from llama_cpp import Llama
        except ImportError as e:  # pragma: no cover
            raise ErroreMotore(
                "manca llama-cpp-python. Installa con: pip install bivio"
            ) from e

        self.percorso = percorso
        self.n_ctx = n_ctx
        self._llm = Llama(
            model_path=percorso,
            n_ctx=n_ctx,
            n_gpu_layers=n_gpu_layers,
            n_threads=n_threads,
            logits_all=False,
            embedding=False,
            verbose=verboso,
        )
        self._n_vocab = self._llm.n_vocab()
        self._prefisso_token: list[int] = []
        self._lettere: dict[str, int] = {}
        self.stile_lettera = " {}"
        self.impronta_pesi = _impronta_file(percorso)

    # ---------------------------------------------------------------- token

    def token(self, testo: str, inizio: bool = False) -> list[int]:
        return self._llm.tokenize(testo.encode("utf-8"), add_bos=inizio, special=True)

    def prepara_lettere(self, chiusura: str) -> dict[str, int]:
        """Trova il token di ogni lettera nel punto esatto in cui verra' letta.

        Una lettera vale solo se, attaccata alla chiusura del prompt, aggiunge
        esattamente un token senza toccare quelli che la precedono. Dove il
        tokenizzatore tiene lo spazio dentro al pezzo (b' A' su Qwen) la
        lettera va scritta con lo spazio davanti, e lo si scopre provando.
        """
        if self._lettere:
            return self._lettere
        base = self.token(chiusura)
        for stile in (" {}", "{}"):
            buone: dict[str, int] = {}
            for lettera in LETTERE:
                pieno = self.token(chiusura + stile.format(lettera))
                if len(pieno) == len(base) + 1 and pieno[: len(base)] == base:
                    buone[lettera] = pieno[-1]
            if len(buone) == len(LETTERE):
                self._lettere = buone
                self.stile_lettera = stile
                return buone
        raise ErroreMotore(
            "questo tokenizzatore non tiene le lettere come token singoli dopo "
            f"«{chiusura}»: il modello non va bene per Bivio"
        )

    # --------------------------------------------------------------- calcolo

    def _logit(self) -> np.ndarray:
        puntatore = self._llm._ctx.get_logits()
        return np.ctypeslib.as_array(puntatore, shape=(self._n_vocab,))

    def scalda(self) -> None:
        """Un passaggio a vuoto: la prima chiamata paga la compilazione dei
        kernel, e misurarla insieme alle altre falserebbe i tempi."""
        self._llm.reset()
        self._llm.eval(self.token("ciao", inizio=True))
        self._prefisso_token = []

    def fissa_prefisso(self, token: list[int], misure: Misure) -> None:
        """Calcola la meta' condivisa, riusandola se e' la stessa di prima."""
        comune = _comune(self._prefisso_token, token)
        if comune == len(token) and comune == len(self._prefisso_token):
            misure.token_riusati += len(token)
            return
        avvio = time.perf_counter()
        # `eval` butta via la cache oltre a n_tokens, quindi riportare
        # n_tokens indietro basta a ripartire da meta' prefisso.
        self._llm.n_tokens = comune
        self._llm.eval(token[comune:])
        misure.token_riusati += comune
        misure.token_stato += len(token) - comune
        misure.ms_stato += (time.perf_counter() - avvio) * 1000
        self._prefisso_token = list(token)

    def distribuzione(self, suffisso: list[int], lettere: list[str], temperatura: float,
                      misure: Misure) -> tuple[list[float], list[float]]:
        """Ritorna (probabilita', logit) sulle lettere ammesse."""
        if not self._prefisso_token:
            raise ErroreMotore("il prefisso non e' stato calcolato")
        quanti = len(self._prefisso_token) + len(suffisso)
        if quanti >= self.n_ctx:
            raise ErroreMotore(
                f"stato e domanda fanno {quanti} token e il limite e' {self.n_ctx}: "
                "alza --contesto oppure accorcia lo stato"
            )
        avvio = time.perf_counter()
        self._llm.n_tokens = len(self._prefisso_token)
        self._llm.eval(suffisso)
        grezzi = self._logit()
        misure.token_domande += len(suffisso)
        misure.ms_domande += (time.perf_counter() - avvio) * 1000

        ids = [self._lettere[l] for l in lettere]
        scelti = np.array([float(grezzi[i]) for i in ids], dtype=np.float64)
        t = max(float(temperatura), 1e-3)
        stabile = (scelti - scelti.max()) / t
        pesi = np.exp(stabile)
        prob = pesi / pesi.sum()
        return [float(p) for p in prob], [float(x) for x in scelti]

    # ------------------------------------------------------------ anagrafica

    @property
    def nome(self) -> str:
        base = os.path.basename(self.percorso)
        return "bivio-" + base.replace(".gguf", "").lower()

    def salute(self) -> dict:
        return {
            "modello": self.nome,
            "file": os.path.basename(self.percorso),
            "sha256": self.impronta_pesi,
            "contesto": self.n_ctx,
            "python": sys.version.split()[0],
        }


def _comune(a: list[int], b: list[int]) -> int:
    n = min(len(a), len(b))
    i = 0
    while i < n and a[i] == b[i]:
        i += 1
    return i


def _impronta_file(percorso: str, pezzi: int = 3, blocco: int = 1 << 20) -> str:
    """Impronta veloce: primo, ultimo e mezzo megabyte piu' la dimensione.

    Un sha256 su 2,5 GB costa dieci secondi a ogni avvio. Qui serve a dire
    «e' lo stesso file», non a fare da firma di sicurezza, e questo lo dice.
    """
    dim = os.path.getsize(percorso)
    h = hashlib.sha256(str(dim).encode())
    with open(percorso, "rb") as f:
        for frazione in (0.0, 0.5, 1.0):
            posto = max(0, min(dim - blocco, int(dim * frazione) - blocco // 2))
            f.seek(posto)
            h.update(f.read(blocco))
    return h.hexdigest()[:32]
