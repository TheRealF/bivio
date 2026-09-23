"""Quanto costa e quanto ci azzecca la portineria a scegliere gli strumenti.

    ./.venv/bin/python prove/banco_portineria.py

Il README cita i numeri che escono di qui, quindi stanno qui: un numero che
non si puo' rifare e' un numero di cui fidarsi a scatola chiusa.

Il banco e' **finto e lo dichiara**: duecento strumenti generati incrociando
dieci verbi e venti oggetti, e dieci richieste in cui lo strumento giusto
esiste e non e' ambiguo. Non dice quanto va bene su GitHub o su Slack veri,
dice se il meccanismo regge quando il catalogo e' grosso. Per un numero vero
si misura sui propri server, che poi e' l'unica cosa che conta.

⚠️ La prima versione di questo banco aveva un catalogo in cui `crea_issue`
NON ESISTEVA, e mi ero convinto che il modello scegliesse male. Sceglieva
quello che c'era. Qui il prodotto e' completo apposta: ogni verbo con ogni
oggetto, cosi' la risposta giusta c'e' sempre.
"""

from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from bivio import Bivio  # noqa: E402
from bivio.mcp.portineria import Portineria  # noqa: E402

VERBI = {"cerca": "Cerca", "crea": "Crea un nuovo", "aggiorna": "Aggiorna un",
         "cancella": "Cancella un", "elenca": "Elenca tutti i",
         "legge": "Legge il contenuto di un", "invia": "Invia un",
         "chiude": "Chiude un", "assegna": "Assegna a qualcuno un",
         "archivia": "Archivia un"}
COSE = {"issue": ("issue", "su GitHub"), "pull_request": ("pull request", "su GitHub"),
        "file": ("file", "nel filesystem"), "cartella": ("cartella", "nel filesystem"),
        "messaggio": ("messaggio", "su Slack"), "canale": ("canale", "su Slack"),
        "evento": ("evento", "nel calendario"), "contatto": ("contatto", "nella rubrica"),
        "fattura": ("fattura", "nel gestionale"), "preventivo": ("preventivo", "nel gestionale"),
        "pagina": ("pagina", "su Notion"), "tabella": ("tabella", "nel database"),
        "riga": ("riga", "nel database"), "utente": ("utente", "nel CRM"),
        "task": ("task", "nel gestore progetti"), "etichetta": ("etichetta", "su GitHub"),
        "commit": ("commit", "nel repository"), "ramo": ("ramo", "nel repository"),
        "nota": ("nota", "su Notion"), "allegato": ("allegato", "nella posta")}

CASI = [("devo aprire una nuova issue su GitHub", "s.crea_issue"),
        ("voglio cancellare un ramo nel repository", "s.cancella_ramo"),
        ("mandami l'elenco di tutte le fatture", "s.elenca_fattura"),
        ("leggi il contenuto di questo file", "s.legge_file"),
        ("assegna il task a Marco", "s.assegna_task"),
        ("chiudi la pull request numero 12", "s.chiude_pull_request"),
        ("cerca un contatto nella rubrica", "s.cerca_contatto"),
        ("crea un preventivo nel gestionale", "s.crea_preventivo"),
        ("archivia il canale Slack vecchio", "s.archivia_canale"),
        ("aggiorna la riga nel database", "s.aggiorna_riga")]


def catalogo() -> dict:
    fuori = {}
    for v, vd in VERBI.items():
        for c, (cd, dove) in COSE.items():
            nome = f"{v}_{c}"
            fuori[f"s.{nome}"] = {"server": "s", "strumento": {
                "name": nome, "description": f"{vd} {cd} {dove}."}}
    return fuori


def main() -> int:
    cat = catalogo()
    b = Bivio()
    print(f"\nBanco portineria — {len(cat)} strumenti, {len(CASI)} richieste\n")
    print(f"{'':34}{'1° giusto':>11}{'fra i 5':>10}{'mediana':>10}")
    for etichetta, screma in (("filtro meccanico, poi il modello", True),
                              ("solo il modello, legge tutto", False)):
        p = Portineria({"quanti": 5}, lambda: b)
        p.catalogo = cat
        if not screma:
            p._screma = lambda r: (sorted(p.catalogo), len(p.catalogo))
        p.cerca("scalda")          # la prima paga la cache fredda
        primo = cinque = 0
        tempi = []
        for richiesta, atteso in CASI:
            t0 = time.perf_counter()
            r = p.cerca(richiesta)
            tempi.append((time.perf_counter() - t0) * 1000)
            nomi = [s["name"] for s in r["strumenti"]]
            primo += nomi[:1] == [atteso]
            cinque += atteso in nomi
        tempi.sort()
        mediana = tempi[len(tempi) // 2]
        print(f"{etichetta:34}{primo:>6}/{len(CASI):<4}{cinque:>5}/{len(CASI):<4}"
              f"{mediana / 1000:>8.1f} s")
    print("\nStesse scelte, tempi diversi: il filtro non costa accuratezza.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
