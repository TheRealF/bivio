"""Taratura: rendere onesti i numeri che escono.

Appena acceso, un modello del genere e' sicurissimo quasi sempre: 0,9999 dove
la documentazione di Jev mostra 0,88. Non vuol dire che ha ragione, vuol dire
che la distribuzione e' appuntita. Finche' la usi per prendere l'opzione piu'
probabile va bene lo stesso; il giorno che ci metti una soglia («sotto 0,8
lo guarda una persona») quella soglia non significa niente.

La taratura qui e' la piu' semplice che esista: una temperatura per tipo di
domanda, scelta sui tuoi dati etichettati in modo da minimizzare la log-perdita.
Serve roba tua: una taratura fatta sui ticket di un altro non vale sui tuoi.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass


@dataclass
class Voce:
    """Una riga di dati etichettati: stato, domanda, risposta giusta."""

    stato: object
    domanda: dict
    attesa: str
    nome: str = "domanda"


def leggi_jsonl(percorso: str) -> list[Voce]:
    voci = []
    with open(percorso, encoding="utf-8") as f:
        for n, riga in enumerate(f, 1):
            riga = riga.strip()
            if not riga or riga.startswith("#"):
                continue
            d = json.loads(riga)
            mancanti = [k for k in ("stato", "domanda", "attesa") if k not in d]
            if mancanti:
                raise ValueError(f"riga {n}: mancano {', '.join(mancanti)}")
            voci.append(Voce(d["stato"], d["domanda"], str(d["attesa"]),
                             d.get("nome", "domanda")))
    return voci


def _nll(distribuzioni: list[dict], attese: list[str], t: float) -> float:
    """Log-perdita media dopo aver riscaldato di t le probabilita' originali.

    Le probabilita' tornano logit con un log, si dividono per t e si
    rinormalizzano: e' la stessa cosa che scalare i logit veri, perche' il
    softmax e' invariante alla costante che si toglie.
    """
    totale = 0.0
    for dist, attesa in zip(distribuzioni, attese):
        chiavi = list(dist)
        grezzi = [math.log(max(dist[k], 1e-12)) / t for k in chiavi]
        alto = max(grezzi)
        pesi = [math.exp(g - alto) for g in grezzi]
        somma = sum(pesi)
        p = pesi[chiavi.index(attesa)] / somma if attesa in dist else 1e-12
        totale += -math.log(max(p, 1e-12))
    return totale / max(len(attese), 1)


def cerca_temperatura(distribuzioni: list[dict], attese: list[str],
                      basso: float = 0.2, alto: float = 12.0, passi: int = 60) -> float:
    """Ricerca su griglia geometrica: poche righe, nessuna dipendenza."""
    migliore, punteggio = 1.0, float("inf")
    for i in range(passi + 1):
        t = basso * (alto / basso) ** (i / passi)
        v = _nll(distribuzioni, attese, t)
        if v < punteggio:
            migliore, punteggio = t, v
    return migliore


def misura(distribuzioni: list[dict], attese: list[str], t: float = 1.0) -> dict:
    """Le quattro misure che servono per dire se la taratura e' servita."""
    n = len(attese)
    if n == 0:
        return {}
    giuste = 0
    brier = 0.0
    secchi: dict[int, list[tuple[float, int]]] = {}
    for dist, attesa in zip(distribuzioni, attese):
        chiavi = list(dist)
        grezzi = [math.log(max(dist[k], 1e-12)) / t for k in chiavi]
        alto = max(grezzi)
        pesi = [math.exp(g - alto) for g in grezzi]
        somma = sum(pesi)
        prob = {k: p / somma for k, p in zip(chiavi, pesi)}
        vincente = max(prob, key=prob.get)
        giusta = vincente == attesa
        giuste += giusta
        brier += sum((p - (1.0 if k == attesa else 0.0)) ** 2 for k, p in prob.items())
        secchio = min(9, int(prob[vincente] * 10))
        secchi.setdefault(secchio, []).append((prob[vincente], int(giusta)))
    ece = 0.0
    for voci in secchi.values():
        fiducia = sum(p for p, _ in voci) / len(voci)
        vera = sum(g for _, g in voci) / len(voci)
        ece += abs(fiducia - vera) * len(voci) / n
    return {
        "righe": n,
        "accuratezza": round(giuste / n, 4),
        "nll": round(_nll(distribuzioni, attese, t), 4),
        "brier": round(brier / n, 4),
        "ece": round(ece, 4),
    }


def tara(cervello, voci: list[Voce]) -> dict:
    """Passa i dati nel modello, poi cerca una temperatura per tipo."""
    per_tipo: dict[str, tuple[list, list]] = {}
    for voce in voci:
        r = cervello.grezzo(voce.stato, {voce.nome: voce.domanda}, astensione=False)
        corpo = r["risposte"][voce.nome]
        dist = corpo["probabilita"]
        tipo = corpo["tipo"]
        per_tipo.setdefault(tipo, ([], []))
        per_tipo[tipo][0].append(dist)
        per_tipo[tipo][1].append(voce.attesa)

    fuori = {"impronta": cervello.impronta(), "temperature": {}, "prima": {}, "dopo": {}}
    for tipo, (dist, attese) in per_tipo.items():
        t = cerca_temperatura(dist, attese)
        fuori["temperature"][tipo] = round(t, 4)
        fuori["prima"][tipo] = misura(dist, attese, 1.0)
        fuori["dopo"][tipo] = misura(dist, attese, t)
    return fuori


def carica(percorso: str, impronta: str | None = None) -> dict:
    with open(percorso, encoding="utf-8") as f:
        dati = json.load(f)
    if impronta and dati.get("impronta") not in (None, impronta):
        raise ValueError(
            "questa taratura e' stata fatta su un'altra impronta "
            f"({dati.get('impronta')} invece di {impronta}): rifalla.\n"
            "L'impronta tiene dentro i pesi, la versione del prompt e il motore, "
            "e una temperatura trovata su un modello non vale su un altro."
        )
    return dati
