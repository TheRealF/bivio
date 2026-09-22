"""Caso d'uso 3 · Dodici domande su un contratto, leggendolo una volta sola.

E' il caso in cui Bivio serve davvero. Il documento e' lungo, le domande sono
tante, e le domande sono sempre le stesse: quelle della tua griglia di lettura.
Lo stato viene calcolato una volta e le domande si appoggiano tutte a quel
calcolo, quindi la dodicesima domanda costa quasi niente.

    python esempi/lettura_contratto.py [percorso/del/contratto.txt]
"""

import sys
import time

from bivio import Bivio

GRIGLIA = {
    "rinnovo_tacito": {"tipo": "si_no", "istruzioni": "Il contratto si rinnova da solo se nessuno disdice"},
    "pagamento_oltre_30": {"tipo": "si_no", "istruzioni": "Il termine di pagamento supera i 30 giorni"},
    "penali_fornitore": {"tipo": "si_no", "istruzioni": "Sono previste penali a carico del fornitore"},
    "penali_cliente": {"tipo": "si_no", "istruzioni": "Sono previste penali a carico del committente"},
    "arbitrato": {"tipo": "si_no", "istruzioni": "Le controversie vanno a un arbitro invece che a un giudice"},
    "recesso_libero": {"tipo": "si_no", "istruzioni": "Il committente puo' recedere dall'intero contratto quando vuole"},
    "dati_fuori_ue": {"tipo": "si_no", "istruzioni": "I dati personali possono essere trattati fuori dall'Unione Europea"},
    "codice_al_cliente": {"tipo": "si_no", "istruzioni": "Il codice sviluppato diventa di proprieta' del committente"},
    "subappalto": {"tipo": "si_no", "istruzioni": "Il fornitore puo' farsi aiutare da collaboratori esterni"},
    "sbilanciato": {
        "tipo": "voto",
        "istruzioni": "Quanto e' sbilanciato il contratto a sfavore del committente",
        "livelli": ["Equilibrato", "Un po' sbilanciato", "Molto sbilanciato"],
    },
    "da_far_vedere": {
        "tipo": "scelta",
        "istruzioni": "Chi deve guardarlo prima della firma",
        "opzioni": {
            "nessuno": "Si puo' firmare cosi'",
            "amministrazione": "Va guardato per i termini di pagamento",
            "avvocato": "Ci sono clausole che vanno viste da un legale",
        },
    },
    "settimane": {
        "tipo": "numero",
        "istruzioni": "Quante settimane servono in tutto secondo il cronoprogramma",
        "unita": "settimane",
        "ancore": [
            {"valore": 4, "descrizione": "Un mese"},
            {"valore": 12, "descrizione": "Tre mesi"},
            {"valore": 22, "descrizione": "Poco piu' di cinque mesi"},
            {"valore": 52, "descrizione": "Un anno"},
        ],
    },
}


def principale():
    percorso = sys.argv[1] if len(sys.argv) > 1 else "prove/dati/stato-lungo.txt"
    with open(percorso, encoding="utf-8") as f:
        contratto = f.read()

    b = Bivio()

    avvio = time.perf_counter()
    grezzo = b.grezzo(contratto, GRIGLIA)
    insieme = time.perf_counter() - avvio

    for nome, r in grezzo["risposte"].items():
        valore = r.get("valore")
        if valore is True:
            valore = "si'"
        elif valore is False:
            valore = "no"
        print(f"  {nome:<22} {str(valore):<10} confidenza {r['confidenza']:.3f}")

    m = grezzo["misure"]
    print(f"\n{len(GRIGLIA)} domande su {grezzo['consumo']['token_stato']} token di contratto")
    print(f"  stato letto una volta: {m['ms_stato']:.0f} ms")
    print(f"  le {len(GRIGLIA)} domande:      {m['ms_domande']:.0f} ms")
    print(f"  in tutto:              {insieme * 1000:.0f} ms, 0 token generati")


if __name__ == "__main__":
    principale()
