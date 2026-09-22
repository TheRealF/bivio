"""Caso d'uso 1 · La posta che si smista da sola.

Arrivano dieci messaggi. Per ognuno servono tre cose: chi lo prende, quanto
e' arrabbiato chi scrive, e se va messo davanti agli altri. Con un modello
che scrive sarebbero tre risposte da rileggere e da interpretare. Qui sono
tre campi tipizzati, e la fila si ordina con un `sorted`.

    python esempi/smistamento_ticket.py
"""

from bivio import Bivio

POSTA = [
    "Provo da tre giorni a collegare il conto Stripe e continua a fallire. Sto perdendo vendite.",
    "Buongiorno, volevo sapere se il corso di Excel parte anche di sabato. Grazie.",
    "E' la terza volta che scrivo e nessuno risponde. Trovo la cosa poco seria.",
    "Ho ricevuto due fatture per lo stesso mese, potete controllare?",
    "Siamo in otto e vorremmo un corso su misura in azienda: quanto verrebbe?",
    "Da stamattina il pannello da' errore 500 quando salvo una pagina.",
    "Vi ringrazio per ieri, e' andato tutto bene.",
    "Il bonifico l'ho fatto il 3 ma risulta ancora non pagato. Mi serve la liberatoria entro domani.",
]

DOMANDE = {
    "reparto": {
        "tipo": "scelta",
        "istruzioni": "Chi deve prendere in carico la richiesta",
        "opzioni": {
            "pagamenti": "Incassi, fatture, rimborsi",
            "tecnico": "Errori, malfunzionamenti, cali del servizio",
            "commerciale": "Preventivi e nuovi contratti",
            "nessuno": "Non chiede niente, basta ringraziare",
        },
    },
    "nervoso": {
        "tipo": "voto",
        "istruzioni": "Quanto e' scontento chi scrive",
        "livelli": ["Tranquillo", "Infastidito", "Furioso"],
    },
    "urgente": {
        "tipo": "si_no",
        "istruzioni": "Il messaggio esprime urgenza o una scadenza",
    },
}


def principale():
    b = Bivio()
    fila = []
    for messaggio in POSTA:
        r = b.decidi(messaggio, DOMANDE)
        # Il cancello: una scelta combattuta la guarda una persona.
        reparto = r["reparto"].valore if r["reparto"].confidenza >= 0.6 else "da_smistare_a_mano"
        fila.append({
            "testo": messaggio,
            "reparto": reparto,
            "nervoso": r["nervoso"].valore,
            "urgente": r["urgente"].valore,
            "peso": (2 if r["urgente"].valore else 0) + r["nervoso"].valore,
        })

    fila.sort(key=lambda t: -t["peso"])
    print(f"{'peso':>5}  {'reparto':<18} {'nervoso':>7}  urg  messaggio")
    for t in fila:
        print(f"{t['peso']:>5.1f}  {t['reparto']:<18} {t['nervoso']:>7.2f}  "
              f"{'si' if t['urgente'] else 'no':>3}  {t['testo'][:58]}")


if __name__ == "__main__":
    principale()
