"""Le griglie: domande gia' scritte per i lavori che si fanno in Italia.

Una griglia e' l'insieme di domande che fai sempre alla stessa cosa. Chi tiene
la prima nota le fa a ogni scontrino, chi risponde ai clienti le fa a ogni
messaggio. Scriverle la prima volta e' il lavoro vero, e queste sono gia'
scritte: si usano cosi' come sono, oppure si copiano e si cambiano.

    from bivio import Bivio, griglia
    b = Bivio()
    r = b.decidi(messaggio, griglia("assistenza")["domande"])

⚠️ Sono un punto di partenza, non una verita'. Le opzioni di «spese» sono
quelle di un libero professionista, e il tuo commercialista ne vuole altre.
Copiare il file e cambiarlo e' il modo previsto di usarle.
"""

from __future__ import annotations

import json
import os

CARTELLA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "griglie")


def elenco() -> list[dict]:
    """Le griglie che ci sono, con titolo e per chi sono."""
    fuori = []
    for nome in sorted(os.listdir(CARTELLA)):
        if nome.endswith(".json"):
            with open(os.path.join(CARTELLA, nome), encoding="utf-8") as f:
                d = json.load(f)
            fuori.append({"nome": d["nome"], "titolo": d["titolo"], "per": d["per"],
                          "domande": len(d["domande"])})
    return fuori


def carica(nome: str) -> dict:
    """Una griglia per nome, o il percorso di un tuo file .json."""
    percorso = nome if nome.endswith(".json") and os.path.exists(nome) \
        else os.path.join(CARTELLA, nome + ".json")
    if not os.path.exists(percorso):
        disponibili = ", ".join(g["nome"] for g in elenco())
        raise KeyError(f"griglia «{nome}» sconosciuta. Ci sono: {disponibili}")
    with open(percorso, encoding="utf-8") as f:
        return json.load(f)
