"""Misura Bivio sui casi etichettati e scrive il rapporto in risultati/.

    ./.venv/bin/python prove/misura.py --modello 4b

Quello che esce e' un controllo di sanita', non un banco di prova: i casi
sono trentasette, scritti dalla stessa persona che ha scritto il prompt, e
in italiano. Serve a dire «gira e risponde sensato» e a far vedere che cosa
cambia fra astensione accesa e spenta.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import statistics
import sys
import time
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from bivio import Bivio  # noqa: E402
from bivio.taratura import leggi_jsonl  # noqa: E402

QUI = os.path.dirname(os.path.abspath(__file__))
RADICE = os.path.dirname(QUI)


def passa(cervello: Bivio, voci, astensione: bool):
    righe = []
    for voce in voci:
        avvio = time.perf_counter()
        grezzo = cervello.grezzo(voce.stato, {voce.nome: voce.domanda}, astensione=astensione)
        ms = (time.perf_counter() - avvio) * 1000
        corpo = grezzo["risposte"][voce.nome]
        tutte = corpo["_grezze"]
        vinta = max(tutte, key=tutte.get)
        p_attesa = tutte.get(voce.attesa, 0.0)
        righe.append({
            "nome": voce.nome,
            "tipo": corpo["tipo"],
            "attesa": voce.attesa,
            "data": vinta,
            "giusta": vinta == voce.attesa,
            "p_attesa": round(p_attesa, 6),
            "p_data": round(tutte[vinta], 6),
            "stato": corpo["stato"],
            "ms": round(ms, 1),
            "token": grezzo["consumo"]["token_ingresso"],
        })
    return righe


def riassunto(righe):
    if not righe:
        return {}
    giuste = sum(r["giusta"] for r in righe)
    nll = sum(-math.log(max(r["p_attesa"], 1e-12)) for r in righe) / len(righe)
    tempi = sorted(r["ms"] for r in righe)
    return {
        "righe": len(righe),
        "accuratezza": round(giuste / len(righe), 4),
        "sbagliate": len(righe) - giuste,
        "nll": round(nll, 4),
        "ms_p50": round(statistics.median(tempi), 1),
        "ms_p95": round(tempi[int(len(tempi) * 0.95) - 1], 1),
    }


def per_famiglia(righe):
    fuori = {}
    for r in righe:
        f = fuori.setdefault(r["nome"], {"righe": 0, "giuste": 0})
        f["righe"] += 1
        f["giuste"] += r["giusta"]
    return {k: {"righe": v["righe"], "accuratezza": round(v["giuste"] / v["righe"], 3)}
            for k, v in sorted(fuori.items())}


DOMANDE_CONTRATTO = {
    "rinnovo": {"tipo": "si_no", "istruzioni": "Il contratto prevede il rinnovo tacito"},
    "pagamento_lungo": {"tipo": "si_no", "istruzioni": "Il termine di pagamento supera i 30 giorni"},
    "penali": {"tipo": "si_no", "istruzioni": "Sono previste penali a carico del fornitore"},
    "arbitrato": {"tipo": "si_no", "istruzioni": "Le controversie vanno a un arbitro invece che a un giudice"},
    "recesso_totale": {"tipo": "si_no", "istruzioni": "Il committente puo' recedere dall'intero contratto quando vuole"},
    "dati_fuori_ue": {"tipo": "si_no", "istruzioni": "I dati personali possono essere trattati fuori dall'Unione Europea"},
    "rischio": {"tipo": "voto", "istruzioni": "Quanto e' sbilanciato il contratto a sfavore del committente",
                "livelli": ["Equilibrato", "Un po' sbilanciato", "Molto sbilanciato"]},
    "settimane": {"tipo": "numero", "istruzioni": "Quante settimane servono in tutto secondo il cronoprogramma",
                  "unita": "settimane",
                  "ancore": [{"valore": 4, "descrizione": "Un mese"},
                             {"valore": 12, "descrizione": "Tre mesi"},
                             {"valore": 22, "descrizione": "Poco piu' di cinque mesi"},
                             {"valore": 52, "descrizione": "Un anno"}]},
}

ATTESE_CONTRATTO = {"rinnovo": "si", "pagamento_lungo": "si", "penali": "si",
                    "arbitrato": "no", "recesso_totale": "no", "dati_fuori_ue": "no",
                    "rischio": None, "settimane": "22"}


def stato_lungo(cervello, giri: int = 3):
    """Il conto che conta: otto domande su un contratto di circa mille token.

    Una volta tutte insieme, con lo stato letto una sola volta, e una volta
    una per una con lo stato riletto ogni volta. La differenza fra i due
    numeri e' l'unica ragione per cui esiste la cache del prefisso.
    """
    with open(os.path.join(QUI, "dati", "stato-lungo.txt"), encoding="utf-8") as f:
        testo = f.read()

    insieme, separate = [], []
    for g in range(giri):
        # Il marcatore va in TESTA allo stato: messo in coda, la cache del
        # prefisso resterebbe valida e il confronto direbbe una bugia.
        a = time.perf_counter()
        r = cervello.grezzo("[copia %d]\n\n" % g + testo, DOMANDE_CONTRATTO, astensione=False)
        insieme.append((time.perf_counter() - a) * 1000)

        somma = 0.0
        for nome, d in DOMANDE_CONTRATTO.items():
            b = time.perf_counter()
            cervello.grezzo("[copia %d %s]\n\n" % (g, nome) + testo, {nome: d}, astensione=False)
            somma += (time.perf_counter() - b) * 1000
        separate.append(somma)

    giuste = sum(1 for n, a in ATTESE_CONTRATTO.items()
                 if a is not None and max(r["risposte"][n]["_grezze"],
                                          key=r["risposte"][n]["_grezze"].get) == a)
    quante = sum(1 for a in ATTESE_CONTRATTO.values() if a is not None)
    return {
        "token_stato": r["consumo"]["token_stato"],
        "domande": len(DOMANDE_CONTRATTO),
        "ms_insieme": round(statistics.median(insieme), 1),
        "ms_una_per_volta": round(statistics.median(separate), 1),
        "guadagno": round(statistics.median(separate) / statistics.median(insieme), 2),
        "decisioni_al_secondo": round(len(DOMANDE_CONTRATTO) / (statistics.median(insieme) / 1000), 2),
        "giuste_su_etichettate": f"{giuste}/{quante}",
        "risposte": {n: c.get("valore") for n, c in r["risposte"].items()},
    }


def principale():
    p = argparse.ArgumentParser()
    p.add_argument("-m", "--modello", default="4b")
    p.add_argument("--contesto", type=int, default=8192)
    p.add_argument("--uscita", default=None)
    args = p.parse_args()

    casi = leggi_jsonl(os.path.join(QUI, "dati", "casi.jsonl"))
    vuoti = leggi_jsonl(os.path.join(QUI, "dati", "insufficienti.jsonl"))

    avvio = time.perf_counter()
    b = Bivio(modello=args.modello, contesto=args.contesto)
    caricamento = time.perf_counter() - avvio

    senza = passa(b, casi, astensione=False)
    con = passa(b, casi, astensione=True)
    vuoti_con = passa(b, vuoti, astensione=True)

    # Quante volte, con l'astensione accesa, il modello si tira indietro
    # su un caso in cui la risposta c'era.
    ritirate = sum(1 for r in con if r["stato"] != "ok")

    rapporto = {
        "data": str(date.today()),
        "bivio": __import__("bivio").__version__,
        "modello": b.motore.nome,
        "impronta": b.impronta(),
        "macchina": f"{platform.machine()} · {platform.system()} {platform.release()}",
        "secondi_caricamento": round(caricamento, 1),
        "senza_astensione": riassunto(senza),
        "con_astensione": riassunto(con),
        "ritirate_su_casi_rispondibili": ritirate,
        "prove_insufficienti": riassunto(vuoti_con),
        "per_famiglia": per_famiglia(senza),
        "stato_lungo": stato_lungo(b),
        "righe": {"casi_senza": senza, "casi_con": con, "insufficienti": vuoti_con},
    }

    uscita = args.uscita or os.path.join(RADICE, "risultati", f"locale-{args.modello}.json")
    os.makedirs(os.path.dirname(uscita), exist_ok=True)
    with open(uscita, "w", encoding="utf-8") as f:
        json.dump(rapporto, f, ensure_ascii=False, indent=2)

    corto = {k: v for k, v in rapporto.items() if k != "righe"}
    print(json.dumps(corto, ensure_ascii=False, indent=2))
    print("\nSbagliate senza astensione:")
    for r in senza:
        if not r["giusta"]:
            print(f"  {r['nome']:<12} attesa {r['attesa']:<18} data {r['data']:<18} p={r['p_data']:.3f}")
    print(f"\nScritto in {uscita}")


if __name__ == "__main__":
    principale()
