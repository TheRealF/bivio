"""La classe che si usa: `Bivio`.

    from bivio import Bivio

    b = Bivio()
    r = b.decidi(stato, {"urgente": {"tipo": "si_no", "istruzioni": "..."}})
    r["urgente"].valore        # True
    r["urgente"].probabilita   # 0.98
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

from . import modelli, prompt as mod_prompt
from .motore import Misure, Motore
from .tipi import Domanda, ErroreDomanda, costruisci, leggi, ruota, ruotabile


@dataclass
class Risposta:
    """Una risposta tipizzata. `valore` e' None quando il modello si astiene."""

    nome: str
    tipo: str
    valore: Any
    probabilita: float
    stato: str
    distribuzione: dict[str, float]
    confidenza: float
    dettagli: dict = field(default_factory=dict)

    def __bool__(self) -> bool:
        return bool(self.valore)

    def __repr__(self) -> str:
        return (f"Risposta({self.nome}={self.valore!r}, p={self.probabilita:.3f}, "
                f"stato={self.stato})")

    def dizionario(self) -> dict:
        d = dict(self.dettagli)
        d.update({"valore": self.valore, "probabilita": round(self.probabilita, 6)})
        return d


class Bivio:
    """Un modello caricato una volta, tante decisioni.

    Il modello sta in memoria finche' l'oggetto vive: caricarlo costa qualche
    secondo, rispondere costa decine di millisecondi. Le richieste sono
    serializzate da un lucchetto, perche' la cache del prefisso e' una sola.
    """

    def __init__(
        self,
        modello: str = modelli.PREDEFINITO,
        contesto: int = 8192,
        gpu: int = -1,
        thread: int | None = None,
        sistema: str | None = None,
        astensione: bool = False,
        taratura: dict | None = None,
        verboso: bool = False,
        scarica: bool = False,
        cornice: str | None = None,
        giri: int = 1,
    ):
        percorso = modelli.percorso(modello)
        if scarica and not modelli.presente(modello):
            modelli.scarica(modello)
        self.motore = Motore(percorso, n_ctx=contesto, n_gpu_layers=gpu,
                             n_threads=thread, verboso=verboso)
        if cornice:
            self.motore.cornice = cornice
        self.motore.prepara_lettere(mod_prompt.CHIUSURA)
        self.sistema = sistema
        self.astensione = astensione
        self.giri = max(1, int(giri))
        self.taratura = taratura or {}
        self._lucchetto = threading.Lock()
        self.motore.scalda()

    # ------------------------------------------------------------------ uso

    def decidi(self, stato, domande: dict[str, dict], astensione: bool | None = None) -> dict[str, Risposta]:
        """Una richiesta: uno stato, tante domande, tutte sullo stesso stato."""
        grezzo = self.grezzo(stato, domande, astensione)
        return {
            nome: _risposta(nome, corpo)
            for nome, corpo in grezzo["risposte"].items()
        }

    def chiedi(self, stato, istruzioni: str, opzioni=None, tipo: str | None = None, **extra) -> Risposta:
        """La scorciatoia per una domanda sola."""
        tipo = tipo or ("scelta" if opzioni else "si_no")
        dati = {"tipo": tipo, "istruzioni": istruzioni}
        if opzioni is not None:
            dati["opzioni"] = opzioni
        dati.update(extra)
        return self.decidi(stato, {"domanda": dati})["domanda"]

    # -------------------------------------------------------------- interno

    def grezzo(self, stato, domande: dict[str, dict], astensione: bool | None = None) -> dict:
        """La forma completa, quella che il server pubblica."""
        if not isinstance(domande, dict) or not domande:
            raise ErroreDomanda("serve almeno una domanda")
        permetti = self.astensione if astensione is None else astensione
        preparate = [costruisci(n, d, permetti) for n, d in domande.items()]

        avvio = time.perf_counter()
        misure = Misure()
        fuori: dict[str, dict] = {}

        with self._lucchetto:
            testo_prefisso = mod_prompt.prefisso(stato, self.sistema, self.motore.cornice)
            token_prefisso = self.motore.token(testo_prefisso, inizio=True)
            self.motore.fissa_prefisso(token_prefisso, misure)

            for domanda in preparate:
                t = self._temperatura(domanda)
                corpo = self._una(domanda, t, misure)
                corpo["temperatura"] = round(t, 4)
                fuori[domanda.nome] = corpo

        return {
            "modello": self.motore.nome,
            "risposte": fuori,
            "consumo": {
                "token_ingresso": misure.token_stato + misure.token_domande,
                "token_uscita": 0,
                "token_stato": misure.token_stato,
                "token_riusati": misure.token_riusati,
            },
            "misure": {
                "ms_totali": round((time.perf_counter() - avvio) * 1000, 2),
                "ms_stato": round(misure.ms_stato, 2),
                "ms_domande": round(misure.ms_domande, 2),
                "domande": len(preparate),
            },
            "impronta": self.impronta(),
        }

    def _una(self, domanda: Domanda, t: float, misure: Misure) -> dict:
        """Una domanda, eventualmente chiesta piu' volte con le opzioni girate.

        Il giro costa solo la seconda meta' del prompt: lo stato e' gia' in
        cache e non si ricalcola. E' il motivo per cui qui l'anti-bias si puo'
        permettere, mentre su un'API a token costerebbe come rifare tutto.
        """
        giri = self.giri if ruotabile(domanda) else 1
        giri = min(giri, len(domanda.utili))

        somma = [0.0] * len(domanda.opzioni)
        prima: tuple[list[str], list[float]] | None = None
        per_giro: list[dict[str, float]] = []

        for k in range(giri):
            girata, indici = ruota(domanda, k)
            lettere = mod_prompt.lettere(girata)
            suffisso = self.motore.token(mod_prompt.suffisso(girata, self.motore.cornice))
            prob, logit = self.motore.distribuzione(suffisso, lettere, t, misure)
            for posto, orig in enumerate(indici):
                somma[orig] += prob[posto]
            per_giro.append({girata.opzioni[i].id: round(prob[i], 6)
                             for i in range(len(prob))})
            if k == 0:
                prima = (lettere, logit)

        media = [x / giri for x in somma]
        corpo = leggi(domanda, media)
        lettere0, logit0 = prima
        corpo["logit"] = {l: round(x, 4) for l, x in zip(lettere0, logit0)}
        corpo["lettere"] = {l: o.id for l, o in zip(lettere0, domanda.opzioni)}
        if giri > 1:
            # Quanto la risposta dipende da DOVE stanno le opzioni. Un numero
            # alto vuol dire che il modello ha cambiato idea spostandole, e
            # quella risposta non si manda avanti da sola.
            vinta = max(range(len(media)), key=lambda i: media[i])
            id_vinta = domanda.opzioni[vinta].id
            viste = [g.get(id_vinta, 0.0) for g in per_giro]
            corpo["giri"] = giri
            corpo["instabilita"] = round(max(viste) - min(viste), 6)
            corpo["per_giro"] = per_giro
        return corpo

    def _temperatura(self, domanda: Domanda) -> float:
        if domanda.temperatura != 1.0:
            return domanda.temperatura
        voci = self.taratura.get("temperature", {}) if self.taratura else {}
        return float(voci.get(domanda.tipo, 1.0))

    def impronta(self) -> str:
        """Pesi + prompt + taratura: due impronte diverse, due tarature diverse."""
        pezzi = [self.motore.impronta_pesi,
                 mod_prompt.VERSIONE + "-" + self.motore.cornice + f"-g{self.giri}",
                 self.taratura.get("impronta", "nessuna") if self.taratura else "nessuna"]
        return "/".join(pezzi)

    def salute(self) -> dict:
        d = self.motore.salute()
        d["prompt"] = mod_prompt.VERSIONE
        d["impronta"] = self.impronta()
        d["taratura"] = bool(self.taratura)
        d["giri"] = self.giri
        return d


def _risposta(nome: str, corpo: dict) -> Risposta:
    dist = corpo.get("probabilita", {})
    if corpo["tipo"] == "si_no":
        p = corpo.get("probabilita_si", 0.0)
    elif corpo["tipo"] == "scelta":
        p = dist.get(corpo.get("valore"), 0.0) if corpo.get("valore") else max(dist.values(), default=0.0)
    else:
        p = max(dist.values(), default=0.0)
    return Risposta(
        nome=nome,
        tipo=corpo["tipo"],
        valore=corpo.get("valore"),
        probabilita=float(p),
        stato=corpo.get("stato", "ok"),
        distribuzione=dist,
        confidenza=float(corpo.get("confidenza", 0.0)),
        dettagli=corpo,
    )
