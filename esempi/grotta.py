"""Caso d'uso 4 · Far giocare Bivio al posto tuo.

E' il laboratorio della Lezione 6 del corso «Gen AI per l'automazione dei
processi» (federicoboggia.binatomy.com/corsi/automazione-processi/).

Un gioco a turni ha le tre cose che un processo di lavoro all'inizio non ha:
le regole sono scritte, lo stato sta in una riga, e una mossa sbagliata non
fa danni. Quindi e' il posto dove si impara a delegare una decisione senza
rompere niente. Il giro e' sempre lo stesso: si fotografa lo stato, si fanno
le domande, si esegue, si ricomincia.

    python esempi/grotta.py                # confronto fra i tre giocatori
    python esempi/grotta.py --partite 5    # piu' veloce
"""

import argparse
import random
import time

MOSSE = ["attacca", "colpo_forte", "pozione", "fuggi"]


class Eroe:
    def __init__(self):
        self.vita, self.pozioni, self.ricarica = 100, 2, 0
        self.monete, self.turno, self.fuggito = 0, 1, False


class Mostro:
    def __init__(self):
        self.nome, self.vita = "Ombra della grotta", 120

    def colpisci(self, eroe):
        eroe.vita -= random.randint(8, 20)


def fotografia(eroe, mostro):
    forte = "pronto" if eroe.ricarica == 0 else "fra %d turni" % eroe.ricarica
    return ("Turno %d. "
            "Eroe: vita %d su 100, pozioni %d (curano 30). "
            "Colpo forte: %s. "
            "Mostro: %s, vita %d su 120, toglie da 8 a 20 a turno. "
            "Monete raccolte: %d, si perdono morendo."
            % (eroe.turno, eroe.vita, eroe.pozioni, forte,
               mostro.nome, mostro.vita, eroe.monete))


def esegui(mossa, eroe, mostro):
    # Una mossa impossibile (colpo forte in ricarica, pozione finita) brucia
    # il turno: e' una conseguenza vera, chi decide deve leggere lo stato.
    if mossa == "attacca":
        mostro.vita -= random.randint(6, 10); eroe.monete += 5
    elif mossa == "colpo_forte" and eroe.ricarica == 0:
        mostro.vita -= random.randint(18, 24); eroe.ricarica = 3; eroe.monete += 5
    elif mossa == "pozione" and eroe.pozioni > 0:
        eroe.pozioni -= 1; eroe.vita = min(100, eroe.vita + 30)
    elif mossa == "fuggi":
        eroe.fuggito = True


def esito(eroe, mostro):
    if eroe.vita <= 0:
        return ("morto", 0)
    if eroe.fuggito:
        return ("fuggito", eroe.monete)
    return ("vinto", eroe.monete + 50)


def gioca(scegli):
    """`scegli(stato, eroe, mostro)` restituisce una delle MOSSE."""
    eroe, mostro = Eroe(), Mostro()
    while eroe.vita > 0 and mostro.vita > 0 and not eroe.fuggito:
        esegui(scegli(fotografia(eroe, mostro), eroe, mostro), eroe, mostro)
        if mostro.vita > 0 and not eroe.fuggito:
            mostro.colpisci(eroe)
        if eroe.ricarica:
            eroe.ricarica -= 1
        eroe.turno += 1
        if eroe.turno > 60:
            break            # salvagente contro le partite infinite
    return esito(eroe, mostro)


# ----------------------------------------------------------------- giocatori

def a_caso(stato, eroe, mostro):
    return random.choice(MOSSE)


def tre_if(stato, eroe, mostro):
    """La strategia che scriveresti tu in due minuti. E' il metro di paragone."""
    if eroe.vita <= 30 and eroe.pozioni:
        return "pozione"
    if eroe.vita <= 15:
        return "fuggi"
    if eroe.ricarica == 0:
        return "colpo_forte"
    return "attacca"


DESCRIZIONI = {
    "attacca": "Colpo normale, toglie da 6 a 10, sempre disponibile",
    "colpo_forte": "Toglie da 18 a 24, poi tre turni di ricarica",
    "pozione": "Recupera 30 di vita e regala un turno al mostro",
    "fuggi": "Esci vivo dalla grotta e tieni le monete gia' raccolte",
}


def tutte(eroe):
    return dict(DESCRIZIONI)


def legali(eroe):
    """Le mosse che in questo turno si possono davvero fare.

    Questo pezzo e' meccanico: la regola e' scritta e vale sempre, quindi lo
    fa il codice. E' il taglio di «divide et impera» applicato a una riga
    sola, ed e' la differenza fra un giocatore che muore sempre e uno che
    vince sette volte su dieci.
    """
    mosse = ["attacca"]
    if eroe.ricarica == 0:
        mosse.append("colpo_forte")
    if eroe.pozioni > 0:
        mosse.append("pozione")
    mosse.append("fuggi")
    return {m: DESCRIZIONI[m] for m in mosse}


def domande(eroe, mosse):
    return {
        "mossa": {
            "tipo": "scelta",
            "istruzioni": "Quale mossa conviene giocare in questo turno",
            "opzioni": mosse(eroe),
        },
        "pericolo": {
            "tipo": "si_no",
            "istruzioni": "Il mostro puo' uccidermi entro i prossimi due turni",
        },
    }


def crea(cervello, mosse=legali, soglia=0.6, cancello_pericolo=False):
    """Fabbrica un giocatore. I tre interruttori sono i tre esperimenti."""

    def scegli(stato, eroe, mostro):
        r = cervello.decidi(stato, domande(eroe, mosse))
        if cancello_pericolo and r["pericolo"].valore and r["pericolo"].probabilita > 0.9:
            if eroe.pozioni:
                return "pozione"
            if eroe.vita <= 25:
                return "fuggi"
        m = r["mossa"]
        # Il cancello sulla confidenza: quando la scelta e' combattuta si gioca
        # quella che non fa danni. Una probabilita' bassa non e' un errore, e'
        # un'informazione: dice che questo turno non era da delegare.
        return m.valore if m.confidenza >= soglia else "attacca"

    return scegli


# ------------------------------------------------------------------- confronto

def conta(nome, giocatore, partite):
    avvio = time.perf_counter()
    esiti, monete = {"vinto": 0, "fuggito": 0, "morto": 0}, 0
    for _ in range(partite):
        come, soldi = gioca(giocatore)
        esiti[come] += 1
        monete += soldi
    secondi = time.perf_counter() - avvio
    print(f"{nome:<12} {partite:>4} partite   "
          f"vinto {esiti['vinto'] * 100 // partite:>3}%  "
          f"fuggito {esiti['fuggito'] * 100 // partite:>3}%  "
          f"morto {esiti['morto'] * 100 // partite:>3}%   "
          f"monete medie {monete / partite:>6.1f}   ({secondi:.1f} s)")


def principale():
    p = argparse.ArgumentParser()
    p.add_argument("--partite", type=int, default=20, help="partite per Bivio (le altre ne fanno 100)")
    p.add_argument("--seme", type=int, default=7)
    args = p.parse_args()

    random.seed(args.seme)
    conta("a caso", a_caso, 100)
    conta("tre if", tre_if, 100)

    from bivio import Bivio
    cervello = Bivio()
    conta("Bivio crudo", crea(cervello, mosse=tutte), args.partite)
    conta("Bivio legali", crea(cervello, mosse=legali), args.partite)
    conta("Bivio + regola", crea(cervello, mosse=legali, cancello_pericolo=True), args.partite)

    print("""
Le partite di Bivio sono meno apposta: una partita sono circa trenta decisioni,
e il conto lo paga il tuo computer. Le altre due sono gratis.

Le tre righe di Bivio sono tre esperimenti, e vanno lette in fila:

  crudo    gli si offrono sempre e quattro le mosse. Sceglie il colpo forte
           anche mentre e' in ricarica, cioe' butta il turno, e muore sempre.
  legali   le mosse impossibili non gliele offriamo: quel pezzo la' e'
           meccanico e lo fa il codice. Da qui vince.
  + regola una regola scritta a mano sopra alla risposta «pericolo».
           Peggiora: quel si'/no dice si' quasi sempre, quindi il giocatore
           beve le pozioni troppo presto e poi scappa.

Il guadagno e' venuto da quello che abbiamo tolto al modello. Le regole che gli
abbiamo messo sopra lo hanno peggiorato.""")


if __name__ == "__main__":
    principale()
