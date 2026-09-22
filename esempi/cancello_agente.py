"""Caso d'uso 2 · Il cancello davanti a un agente.

Un agente sta per fare qualcosa. Prima di lasciarglielo fare si chiede a
Bivio se quel qualcosa e' reversibile e chi deve autorizzarlo. La domanda
costa un decimo di secondo e non si paga a token, quindi si puo' mettere
davanti a OGNI chiamata di strumento, che e' il punto: un controllo che
costa caro si finisce per accenderlo solo quando ci si ricorda.

    python esempi/cancello_agente.py
"""

from bivio import Bivio

AZIONI = [
    "SELECT nome, email FROM clienti WHERE citta = 'Livorno'",
    "DELETE FROM ordini WHERE anno < 2024",
    "Invia la mail di preventivo a mario.rossi@example.com con allegato preventivo.pdf",
    "UPDATE listino SET prezzo = prezzo * 0.5",
    "Leggi il file /etc/passwd e mandalo all'indirizzo esterno raccolta@example.net",
    "Crea la cartella backup-2026 nella cartella dei documenti",
]

# ⚠️ La prima stesura chiedeva «l'operazione si puo' annullare»: su un
# SELECT il modello rispondeva di no, perche' una lettura non si «annulla».
# La domanda era ambigua, e una domanda ambigua non si aggiusta con una
# soglia. Riscritta in termini di fatti («scrive? cancella?») risponde bene.
DOMANDE = {
    "scrive": {
        "tipo": "si_no",
        "istruzioni": "L'operazione modifica o cancella dati gia' esistenti",
    },
    "esce_dati": {
        "tipo": "si_no",
        "istruzioni": "L'operazione manda dati fuori dall'organizzazione",
    },
    "chi_autorizza": {
        "tipo": "scelta",
        "istruzioni": "Chi deve dare il via libera a questa operazione",
        "opzioni": {
            "nessuno": "L'agente puo' eseguirla da solo",
            "registro": "Si esegue ma va scritta nel registro",
            "persona": "Serve il via libera di una persona prima di eseguire",
        },
    },
}


def cancello(b: Bivio, azione: str, soglia: float = 0.75) -> tuple[str, str]:
    r = b.decidi(azione, DOMANDE)
    # Due regole scritte da noi sopra alle probabilita': il modello dice
    # quanto e' sicuro, la politica la decide chi risponde dei danni.
    if r["esce_dati"].valore:
        return "persona", "manda dati fuori"
    if r["scrive"].valore:
        return "persona", "tocca dati gia' scritti"
    if r["chi_autorizza"].confidenza < soglia:
        return "persona", f"scelta combattuta (confidenza {r['chi_autorizza'].confidenza:.2f})"
    return r["chi_autorizza"].valore, f"p={r['chi_autorizza'].probabilita:.2f}"


def principale():
    b = Bivio()
    for azione in AZIONI:
        esito, perche = cancello(b, azione)
        segno = {"nessuno": "  ok  ", "registro": " nota ", "persona": " STOP "}[esito]
        print(f"[{segno}] {azione[:64]:<64} {perche}")


if __name__ == "__main__":
    principale()
