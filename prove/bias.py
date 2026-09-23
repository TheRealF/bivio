"""Misura il bias di posizione, e quanto lo toglie la rotazione.

    ./.venv/bin/python prove/bias.py --modello 4b

Un modello a scelta multipla non pesa le opzioni solo per quello che dicono:
pesa anche dove stanno. Leggendo i logit delle lettere Bivio eredita il
difetto tutto intero, quindi la domanda «quanto vale?» va risposta con un
numero e non con un'alzata di spalle.

Tre misure, sugli stessi casi etichettati di `prove/dati/casi.jsonl`:

  1. SPOSTAMENTO. Per ogni caso si fa la stessa domanda con le opzioni girate
     in tutti i modi. Se la posizione non contasse, un'opzione prenderebbe la
     stessa probabilita' ovunque: lo spostamento e' quanto si muove (massimo
     meno minimo) al cambiare del posto, mediato sulle opzioni.

     ⚠️ SI MISURA SUI LOGIT E NON SULLE PROBABILITA', e ci sono volute due
     versioni sbagliate per arrivarci. La prima era «quanto prende chi sta in
     cima meno 1/n»: va a ZERO PER COSTRUZIONE su un modello sicuro, perche'
     se mette tutta la probabilita' sull'opzione giusta quella sta in cima
     esattamente una volta su n. La seconda guardava lo spostamento della
     probabilita': su Qwen3-4B dava 0,000 perche' la softmax SATURA, cioe'
     stampa 1,0 e 0,0 e nasconde un margine che intanto si muove. Il logit
     non satura, quindi e' li' che il bias si vede.

  2. INSTABILITA'. Quante volte la risposta CAMBIA solo perche' le opzioni si
     sono spostate. E' il numero che conta per chi deve fidarsi.

  3. GIUSTE CON E SENZA. Se la rotazione fa anche guadagnare accuratezza, si
     dice; se non la fa, si dice lo stesso. Un anti-bias che non migliora i
     conti resta utile (toglie un difetto noto) e va scritto come tale.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from bivio import Bivio  # noqa: E402
from bivio.taratura import leggi_jsonl  # noqa: E402
from bivio.tipi import costruisci, ruotabile  # noqa: E402

QUI = os.path.dirname(os.path.abspath(__file__))
RADICE = os.path.dirname(QUI)


def misura(modello: str, contesto: int) -> dict:
    voci = [v for v in leggi_jsonl(os.path.join(QUI, "dati", "casi.jsonl"))
            if ruotabile(costruisci(v.nome, v.domanda, False))]

    uno = Bivio(modello=modello, contesto=contesto, giri=1)
    righe = []
    avvio = time.perf_counter()
    for v in voci:
        n = len(costruisci(v.nome, v.domanda, False).utili)
        # Tutte le rotazioni, una per una, per vedere la dispersione vera.
        per_posizione, margini, vincitori = {}, [], []
        uno.giri = 1
        for k in range(n):
            ident_mostrati, prob, logit = _con_rotazione(uno, v.stato, v.nome,
                                                         dict(v.domanda), k)
            vincitori.append(max(zip(ident_mostrati, prob), key=lambda x: x[1])[0])
            ordinati = sorted(logit, reverse=True)
            margini.append(ordinati[0] - ordinati[1])
            for posto, (ident, x) in enumerate(zip(ident_mostrati, logit)):
                per_posizione.setdefault(ident, {})[posto] = x
        # giri=1: la risposta cosi' come esce
        base = vincitori[0]
        # giri=n: la media su tutte le rotazioni
        uno.giri = n
        medio = uno.grezzo(v.stato, {v.nome: v.domanda}, astensione=False)["risposte"][v.nome]
        ruotata = max(medio["_grezze"], key=medio["_grezze"].get)

        spostamento = []
        for posti in per_posizione.values():
            if len(posti) > 1:
                spostamento.append(max(posti.values()) - min(posti.values()))
        righe.append({
            "nome": v.nome, "attesa": v.attesa, "opzioni": n,
            "base": base, "ruotata": ruotata,
            "giusta_base": base == v.attesa,
            "giusta_ruotata": ruotata == v.attesa,
            "cambia": len(set(vincitori)) > 1,
            "instabilita": round(medio.get("instabilita", 0.0), 4),
            "spostamento": round(sum(spostamento) / len(spostamento), 3) if spostamento else 0.0,
            "margine_min": round(min(margini), 3),
            "margine_max": round(max(margini), 3),
            "logit_attesa_per_posto": {str(k): round(x, 2)
                                       for k, x in per_posizione.get(v.attesa, {}).items()},
        })
    secondi = time.perf_counter() - avvio

    n = len(righe)
    return {
        "data": str(date.today()),
        "modello": uno.salute()["file"],
        "impronta": uno.impronta(),
        "casi": n,
        "secondi": round(secondi, 1),
        "giuste_giri_1": sum(r["giusta_base"] for r in righe),
        "giuste_giri_n": sum(r["giusta_ruotata"] for r in righe),
        "cambiano_ruotando": sum(r["cambia"] for r in righe),
        "spostamento_logit_medio": round(sum(r["spostamento"] for r in righe) / max(n, 1), 3),
        "spostamento_logit_massimo": round(max((r["spostamento"] for r in righe), default=0.0), 3),
        "margine_piu_stretto": round(min((r["margine_min"] for r in righe), default=0.0), 3),
        "instabilita_mediana": round(
            sorted(r["instabilita"] for r in righe)[n // 2] if n else 0.0, 4),
        "righe": righe,
    }


def _con_rotazione(cervello: Bivio, stato, nome: str, domanda: dict, k: int) -> dict:
    """Una sola rotazione, forzata. Passa dal motore come fa `grezzo`."""
    from bivio import prompt as mod_prompt
    from bivio.motore import Misure
    from bivio.tipi import costruisci, ruota

    d = costruisci(nome, domanda, False)
    girata, indici = ruota(d, k)
    misure = Misure()
    with cervello._lucchetto:
        testo = mod_prompt.prefisso(stato, cervello.sistema, cervello.motore.cornice)
        cervello.motore.fissa_prefisso(cervello.motore.token(testo, inizio=True), misure)
        suff = cervello.motore.token(mod_prompt.suffisso(girata, cervello.motore.cornice))
        prob, logit = cervello.motore.distribuzione(suff, mod_prompt.lettere(girata),
                                                    1.0, misure)
    # ⚠️ Esce nell'ordine MOSTRATO al modello, perche' e' la posizione che si
    # sta misurando: il primo elemento e' quello che stava in cima.
    return [o.id for o in girata.opzioni], prob, logit


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("-m", "--modello", default="4b")
    p.add_argument("--contesto", type=int, default=8192)
    p.add_argument("--uscita", default=None)
    a = p.parse_args()

    r = misura(a.modello, a.contesto)
    print(f"\nBias di posizione — {r['modello']}  ({r['casi']} casi, {r['secondi']} s)\n")
    print(f"  spostamento del logit, medio    {r['spostamento_logit_medio']:.2f}")
    print(f"  spostamento del logit, massimo  {r['spostamento_logit_massimo']:.2f}")
    print(f"  margine piu' stretto visto      {r['margine_piu_stretto']:.2f}")
    print(f"  risposte che cambiano ruotando  {r['cambiano_ruotando']}/{r['casi']}")
    print(f"  instabilita' mediana            {r['instabilita_mediana']:.3f}")
    print(f"  giuste con giri=1               {r['giuste_giri_1']}/{r['casi']}")
    print(f"  giuste con tutte le rotazioni   {r['giuste_giri_n']}/{r['casi']}")

    uscita = a.uscita or os.path.join(RADICE, "risultati",
                                      f"{r['data']}-bias-{a.modello}.json")
    os.makedirs(os.path.dirname(uscita), exist_ok=True)
    with open(uscita, "w", encoding="utf-8") as f:
        json.dump(r, f, ensure_ascii=False, indent=1)
    print(f"\nRapporto in {os.path.relpath(uscita, RADICE)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
