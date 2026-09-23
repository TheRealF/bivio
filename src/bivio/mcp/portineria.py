"""La portineria: sta in mezzo fra l'agente e i server MCP veri.

Fa due mestieri, e sono lo stesso mestiere visto da due lati: **decidere
localmente, prima che la domanda costi**.

1. MENO STRUMENTI IN CONTESTO. Un agente con dieci server addosso si porta
   dietro centomila token di soli schemi prima che qualcuno abbia scritto una
   parola, e l'accuratezza con cui sceglie lo strumento crolla al crescere del
   numero. La portineria ne espone TRE. Quando serve, `cerca_strumenti` chiede
   a Bivio quali dei duecento servono a *questa* richiesta e passa solo quelli.

   ⚠️ Qui l'architettura di Bivio e' esattamente quella giusta, e non e' una
   coincidenza: la richiesta e' UNO stato, i duecento strumenti sono DUECENTO
   domande su quello stesso stato. Lo stato si legge una volta e le domande si
   appoggiano a quella lettura. E' la stessa riga che nel README vale 5,75
   volte sul contratto.

2. UN CANCELLO SULLE CHIAMATE. Prima di passare una chiamata a un server vero,
   si guarda cosa fa: cancella? manda fuori dati personali? sta facendo quello
   che lo strumento dichiara di fare?

⚠️⚠️ IL CANCELLO NON E' UNA MISURA DI SICUREZZA, ED E' IMPORTANTE CHE SIA
SCRITTO. E' un classificatore: legge del testo e dice un numero. Chi controlla
il testo puo' provare a parlargli intorno, ed e' lo stesso identico problema
per cui una descrizione di strumento va considerata non fidata. Serve a
prendere gli incidenti e le sviste, che sono la maggioranza, non un
avversario. Le cose che devono valere sempre si scrivono in `mai_permessi`,
che e' meccanico e non si discute.

Questa divisione e' la stessa della Lezione 6 del corso: quale mossa sia
POSSIBILE lo decide il codice, quale sia CONVENIENTE lo decide il modello.
Le regole meccaniche girano per prime e il modello non le puo' scavalcare.
"""

from __future__ import annotations

import fnmatch
import json
import re

from .. import __version__
from .cliente import Collegamento, ErroreCliente, accendi
from .protocollo import Servitore, _dilo

ISTRUZIONI = """Dietro a questa portineria ci sono altri server MCP, e i loro
strumenti non sono nel tuo contesto: sarebbero troppi.

Il giro e' sempre lo stesso: chiami `cerca_strumenti` dicendo cosa devi fare, ti
tornano i pochi che servono con il loro schema completo, e poi li usi con
`usa_strumento`. Se sai gia' come si chiama quello che ti serve, vai dritto a
`usa_strumento`."""

# Le domande del cancello. Si possono aggiungere dalla configurazione, ma
# queste tre ci sono sempre, e la terza e' quella che nessuno mette.
REGOLE = {
    "irreversibile": "La chiamata cancella, sovrascrive o pubblica qualcosa in "
                     "modo che non si possa tornare indietro",
    "dati_personali": "Negli argomenti ci sono dati personali di qualcuno: nomi e "
                      "cognomi, email, numeri di telefono, indirizzi, codici "
                      "fiscali, dati di salute o di pagamento",
    "coerente": "La chiamata fa quello che lo strumento dichiara di fare, senza "
                "andare oltre",
}



def _parole(t: str) -> set:
    """Le parole utili di un testo, ridotte alla radice in modo grossolano.

    Serve a confrontare «issue» con «issues» e «crea» con «creare». Non e' uno
    stemmer e non vuole esserlo: taglia le code piu' comuni dell'italiano e
    dell'inglese, e per un filtro grossolano basta.
    """
    fuori = set()
    # ⚠️ L'underscore NON sta nella classe: i nomi degli strumenti si chiamano
    # «cancella_ramo», e tenendolo dentro sarebbe una parola sola che non si
    # incontra mai con «cancellare» ne' con «ramo». Cioe' il filtro sarebbe
    # cieco proprio dove serve.
    for w in re.findall(r"[A-Za-zÀ-ÿ0-9]{3,}", t.lower()):
        for coda in ("zioni", "zione", "mento", "are", "ere", "ire", "ato", "ata",
                     "ing", "ers", "es", "s", "i", "e", "o", "a"):
            if len(w) > len(coda) + 2 and w.endswith(coda):
                w = w[: -len(coda)]
                break
        fuori.add(w)
    return fuori - _VUOTE


_VUOTE = {"per", "con", "del", "della", "dei", "delle", "nel", "nella", "che", "chi",
          "com", "cos", "dev", "vogli", "un", "una", "uno", "il", "lo", "la", "gli",
          "the", "and", "for", "with", "from", "this", "that", "restituisc",
          "identificator", "stat", "corrent", "oggett", "su", "in", "di", "da"}


class Portineria:
    def __init__(self, configurazione: dict, cervello):
        self.conf = configurazione
        self.cervello = cervello
        self.quanti = int(configurazione.get("quanti", 5))
        # ⚠️ La soglia e' RELATIVA al migliore, non assoluta, e ci sono arrivato
        # da un test che falliva. In una `scelta` le probabilita' sommano a 1:
        # una soglia assoluta di 0,5 vuol dire «solo se si prende piu' di meta'
        # della massa», cioe' al massimo UNO strumento, e `quanti=5` non
        # sarebbe mai stato onorato. 0,1 vuol dire «almeno un decimo di quanto
        # ha preso il primo», che su una distribuzione normalizzata ha senso
        # qualunque sia il numero di opzioni.
        self.soglia = float(configurazione.get("soglia", 0.1))
        self.sempre = list(configurazione.get("sempre_permessi") or [])
        self.mai = list(configurazione.get("mai_permessi") or [])
        self.regole = dict(REGOLE)
        self.regole.update(configurazione.get("regole") or {})
        self.collegamenti: dict[str, Collegamento] = {}
        self.catalogo: dict[str, dict] = {}       # nome completo → voce

    # ------------------------------------------------------------- avvio

    def apri(self) -> None:
        self.collegamenti = accendi(self.conf)
        for nome, col in self.collegamenti.items():
            for st in col.strumenti:
                # ⚠️ Il nome si prefissa col server: due server che espongono
                # `search` sono una collisione, e la specifica dice di
                # disambiguare cosi'.
                pieno = f"{nome}.{st['name']}"
                self.catalogo[pieno] = {"server": nome, "strumento": st}
        _dilo(f"[portineria] {len(self.catalogo)} strumenti dietro a "
              f"{len(self.collegamenti)} server, 3 esposti.")

    def chiudi(self) -> None:
        for col in self.collegamenti.values():
            col.spegni()

    # --------------------------------------------------------- la scelta

    # ⚠️ 25 e non 26: le lettere sono 26 e l'ultima serve all'astensione.
    GIRONE = 25

    def _riga(self, pieno: str) -> str:
        st = self.catalogo[pieno]["strumento"]
        desc = (st.get("description") or st.get("title") or "").strip()
        return (st["name"] + ": " + desc)[:220]

    def cerca(self, richiesta: str, quanti: int | None = None) -> dict:
        """Un torneo a gironi: si vince il proprio girone, poi si va in finale.

        ⚠️ LA PRIMA VERSIONE FACEVA UNA DOMANDA SI'/NO PER STRUMENTO, ED ERA
        SBAGLIATA IN TUTTI E DUE I MODI. Misurata su 200 strumenti finti:
        **29 secondi** (145 ms l'uno: il costo fisso di una valutazione si paga
        duecento volte) e, chiedendo «devo aprire una issue su GitHub», tornava
        `cerca_contatto` e `cerca_progetto`. Il motivo del secondo e' piu'
        interessante del primo: a «questo strumento serve?» il modello risponde
        si' a qualunque cosa sia vagamente in tema, le probabilita' si
        accalcano vicino a 1 e l'ordine che ne esce e' rumore.

        Una SCELTA invece costringe al confronto: fra venticinque, uno solo
        vince. Quindi si spezza il catalogo in gironi da venticinque, ogni
        girone ne manda avanti uno (o nessuno, che e' a cosa serve
        l'astensione), e i vincitori si giocano la finale. Duecento strumenti
        diventano nove domande invece di duecento.
        """
        quanti = int(quanti or self.quanti)
        if not self.catalogo:
            return {"strumenti": [], "nota": "Non c'e' nessun server collegato."}

        nomi, scremati = self._screma(richiesta)
        gironi = [nomi[i:i + self.GIRONE] for i in range(0, len(nomi), self.GIRONE)]
        criterio = ("Quale di questi strumenti serve per fare quello che e' scritto "
                    "nello stato. Se non ce n'e' nessuno, dillo.")
        b = self.cervello()

        domande = {}
        for n, girone in enumerate(gironi):
            domande[f"g{n}"] = {"tipo": "scelta", "istruzioni": criterio,
                                "opzioni": {k: self._riga(k) for k in girone}}
        # Una lettura della richiesta, un pugno di domande su quella lettura.
        grezzo = b.grezzo(richiesta, domande, astensione=True)
        ms = grezzo["misure"]["ms_totali"]

        # ⚠️ NON si prende solo il vincitore del girone. Una `scelta` torna la
        # probabilita' di TUTTE le opzioni, ed e' la cosa che Bivio sa fare e
        # un embedding no: buttarla via per tenere l'argmax vorrebbe dire
        # rispondere con un solo strumento a chi ne ha chiesti cinque.
        finalisti: list[tuple[str, float]] = []
        for n, girone in enumerate(gironi):
            prob = grezzo["risposte"][f"g{n}"].get("probabilita") or {}
            finalisti += [(k, float(prob.get(k, 0.0))) for k in girone]
        finalisti.sort(key=lambda x: -x[1])
        if len(gironi) > 1 and len(finalisti) > quanti:
            # La finale: i venticinque piu' alti rimessi in una domanda sola.
            # Serve perche' i punteggi di gironi diversi NON sono confrontabili:
            # una `scelta` normalizza dentro al suo girone, quindi 0,4 contro
            # ventiquattro avversari vale piu' di 0,6 contro due.
            #
            # ⚠️ Con il filtro meccanico davanti i gironi sono quasi sempre uno
            # solo e questo ramo non si accende. Resta per la strada lenta,
            # quella in cui il filtro si e' tirato indietro.
            in_finale = [k for k, _ in finalisti[:self.GIRONE]]
            f = b.grezzo(richiesta, {"finale": {
                "tipo": "scelta", "istruzioni": criterio,
                "opzioni": {k: self._riga(k) for k in in_finale}}}, astensione=True)
            ms += f["misure"]["ms_totali"]
            prob = f["risposte"]["finale"].get("probabilita") or {}
            finalisti = sorted(((k, float(prob.get(k, 0.0))) for k in in_finale),
                               key=lambda x: -x[1])

        migliore = finalisti[0][1] if finalisti else 0.0
        taglio = migliore * self.soglia
        scelti = [(k, v) for k, v in finalisti[:quanti] if v >= taglio] or finalisti[:3]
        return {
            "strumenti": [dict(self.catalogo[k]["strumento"], name=k,
                               _probabilita=round(v, 4)) for k, v in scelti],
            "guardati": len(self.catalogo),
            "scremati_a": scremati,
            "domande": len(gironi) + (1 if len(gironi) > 1 else 0),
            "ms": round(ms, 1),
        }

    def _screma(self, richiesta: str) -> tuple[list[str], int]:
        """Il filtro meccanico, prima del modello.

        ⚠️ QUESTA E' LA RIGA CHE FA FUNZIONARE LA PORTINERIA, e ci sono arrivato
        misurando. Far leggere al modello la descrizione di tutti gli strumenti
        costa quello che costa: duecento strumenti sono undicimila token, e su
        questa macchina fanno **ventisei secondi**. Nessun torneo li toglie,
        perche' non sono le domande a costare, sono i token da leggere.

        Quali strumenti siano PLAUSIBILI e' meccanico: le parole della richiesta
        e quelle del nome e della descrizione si sovrappongono oppure no, e un
        `set` lo dice gratis. Quale sia quello GIUSTO e' giudizio, e resta al
        modello. Il codice porta duecento a venticinque, il modello sceglie fra
        venticinque.

        Se le parole non si sovrappongono con niente (richiesta vaga, o server
        in un'altra lingua) si torna il catalogo intero: meglio lenti che
        sbagliati, e la risposta lo dice in `scremati_a`.
        """
        nomi = sorted(self.catalogo)
        if len(nomi) <= self.GIRONE:
            return nomi, len(nomi)
        cerca = _parole(richiesta)
        punti = []
        for k in nomi:
            st = self.catalogo[k]["strumento"]
            proprie = _parole(st.get("name", "") + " " + (st.get("description") or ""))
            comuni = cerca & proprie
            if comuni:
                # Normalizzato sulla richiesta: uno strumento con la descrizione
                # lunga non deve vincere solo perche' ha piu' parole.
                punti.append((k, len(comuni) / max(len(cerca), 1)))
        if not punti:
            return nomi, len(nomi)
        punti.sort(key=lambda x: -x[1])
        tenuti = [k for k, _ in punti[: self.GIRONE]]
        return tenuti, len(tenuti)

    # -------------------------------------------------------- il cancello

    def _meccanico(self, nome: str) -> tuple[str, str] | None:
        """Le regole che non si discutono. Girano PRIMA del modello."""
        for schema in self.mai:
            if fnmatch.fnmatch(nome, schema):
                return "bloccata", f"«{nome}» rientra in mai_permessi: {schema}"
        for schema in self.sempre:
            if fnmatch.fnmatch(nome, schema):
                return "passa", f"«{nome}» rientra in sempre_permessi: {schema}"
        return None

    def giudica(self, nome: str, argomenti: dict) -> dict:
        secco = self._meccanico(nome)
        if secco:
            return {"esito": secco[0], "perche": secco[1], "come": "regola"}

        voce = self.catalogo.get(nome)
        st = voce["strumento"] if voce else {}
        stato = (f"STRUMENTO: {st.get('name', nome)}\n"
                 f"DICHIARA DI FARE: {(st.get('description') or '—')[:600]}\n"
                 f"ARGOMENTI:\n{json.dumps(argomenti, ensure_ascii=False, indent=1)[:2000]}")
        domande = {k: {"tipo": "si_no", "istruzioni": v} for k, v in self.regole.items()}
        r = self.cervello().grezzo(stato, domande, astensione=False)["risposte"]

        p = {k: v.get("probabilita_si", 0.0) for k, v in r.items()}
        motivi = []
        if p.get("irreversibile", 0) >= 0.5:
            motivi.append(f"sembra irreversibile (p={p['irreversibile']:.2f})")
        if p.get("dati_personali", 0) >= 0.5:
            motivi.append(f"negli argomenti ci sono dati personali (p={p['dati_personali']:.2f})")
        if p.get("coerente", 1.0) < 0.5:
            motivi.append(f"non fa quello che lo strumento dichiara "
                          f"(p={p['coerente']:.2f})")
        for k in self.conf.get("regole") or {}:
            if p.get(k, 0) >= 0.5:
                motivi.append(f"{k} (p={p[k]:.2f})")

        return {"esito": "chiedi" if motivi else "passa",
                "perche": "; ".join(motivi) or "nessun campanello",
                "come": "modello", "probabilita": {k: round(v, 4) for k, v in p.items()}}

    # ------------------------------------------------------------- il giro

    def usa(self, nome: str, argomenti: dict | None = None, conferma: bool = False) -> dict:
        argomenti = argomenti or {}
        if nome not in self.catalogo:
            vicini = [k for k in self.catalogo if nome in k][:5]
            return {"errore": f"non conosco «{nome}»",
                    "forse": vicini or "usa cerca_strumenti"}
        verdetto = self.giudica(nome, argomenti)
        if verdetto["esito"] == "bloccata":
            return {"bloccata": True, "perche": verdetto["perche"], "come": verdetto["come"]}
        if verdetto["esito"] == "chiedi" and not conferma:
            # ⚠️ Non si blocca: si FERMA e si dice perche'. Chi chiama decide se
            # passare `conferma`, e a quel punto e' una scelta di qualcuno e non
            # di un classificatore.
            return {"serve_conferma": True, "perche": verdetto["perche"],
                    "probabilita": verdetto.get("probabilita"),
                    "come_si_fa": "richiama usa_strumento con conferma=true, "
                                  "dopo aver fatto vedere a una persona cosa stai "
                                  "per fare"}
        voce = self.catalogo[nome]
        col = self.collegamenti.get(voce["server"])
        if col is None:
            # ⚠️ Capita davvero: un server di dietro puo' morire mentre la
            # portineria e' accesa, e il suo strumento resta in catalogo. Meglio
            # dirlo con una frase che uscire con un KeyError, che al client
            # arriva come «errore interno» e non spiega niente.
            return {"errore": f"il server «{voce['server']}» non e' collegato: "
                              f"«{nome}» c'e' in catalogo ma dietro non risponde "
                              f"nessuno. Guarda il log di avvio."}
        try:
            fuori = col.usa(voce["strumento"]["name"], argomenti)
        except ErroreCliente as e:
            return {"errore": str(e)}
        return {"passata": True, "verdetto": verdetto["perche"], "risultato": fuori}


# --------------------------------------------------------------- il server

def costruisci(p: Portineria) -> Servitore:
    s = Servitore("bivio-portineria", __version__, ISTRUZIONI)

    @s.aggiungi(
        "cerca_strumenti", "Trova gli strumenti che servono adesso",
        "Dille cosa devi fare e ti torna solo la manciata di strumenti che servono, "
        "con il loro schema completo, scelti da un modello locale fra tutti quelli "
        "che stanno dietro. Chiamala prima di usa_strumento quando non sai gia' come "
        "si chiama quello che ti serve.",
        {"type": "object",
         "properties": {
             "richiesta": {"type": "string",
                           "description": "Cosa devi fare, in parole tue. Piu' sei "
                                          "preciso meglio sceglie: «apri una issue su "
                                          "GitHub nel repo bivio» invece di «github»."},
             "quanti": {"type": "integer", "minimum": 1, "maximum": 25}},
         "required": ["richiesta"], "additionalProperties": False},
        annotazioni={"readOnlyHint": True},
    )
    def cerca(richiesta: str, quanti: int = 0):
        return p.cerca(richiesta, quanti or None)

    @s.aggiungi(
        "usa_strumento", "Usa uno strumento di dietro",
        "Chiama uno degli strumenti trovati con cerca_strumenti. Il nome e' quello "
        "completo, «server.strumento». Prima di passare la chiamata un modello locale "
        "guarda se e' irreversibile, se porta fuori dati personali e se fa quello che "
        "lo strumento dichiara: se qualcosa suona, torna indietro chiedendo conferma "
        "invece di eseguire.",
        {"type": "object",
         "properties": {
             "nome": {"type": "string", "description": "«server.strumento», come "
                                                       "l'ha scritto cerca_strumenti."},
             "argomenti": {"type": "object", "description": "Gli argomenti, come da "
                                                            "inputSchema di quello strumento."},
             "conferma": {"type": "boolean",
                          "description": "Metti true SOLO dopo che una persona ha visto "
                                         "cosa stai per fare. Serve a passare un "
                                         "avvertimento del cancello, non a saltarlo."}},
         "required": ["nome"], "additionalProperties": False},
    )
    def usa(nome: str, argomenti: dict | None = None, conferma: bool = False):
        return p.usa(nome, argomenti, conferma)

    @s.aggiungi(
        "elenca_server", "Chi c'e' dietro",
        "I server collegati e quanti strumenti ha ognuno. Non carica il modello.",
        {"type": "object", "additionalProperties": False},
        annotazioni={"readOnlyHint": True},
    )
    def elenca():
        return {"server": [{"nome": n, "strumenti": len(c.strumenti)}
                           for n, c in p.collegamenti.items()],
                "totale": len(p.catalogo),
                "esposti_in_contesto": 3}

    return s


def avvia(configurazione: dict, cervello) -> int:
    p = Portineria(configurazione, cervello)
    p.apri()
    try:
        return costruisci(p).gira()
    finally:
        p.chiudi()
