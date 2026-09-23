"""Bivio come server MCP: un giudizio tipizzato, in locale, dentro a un agente.

A che serve, detto senza giri. Un agente che deve decidere una cosa piccola e
ripetuta («questo ticket e' urgente?», «in che cartella va questo file?»)
oggi la chiede a se stesso: un altro giro di modello grosso, qualche migliaio
di token, un secondo e mezzo, e una risposta senza un numero attaccato.
Qui la stessa domanda costa **una lettura e zero token generati**, torna con
la sua probabilita', e non esce dalla macchina.

    bivio mcp

⚠️ IL MODELLO SI CARICA ALLA PRIMA DOMANDA, NON ALL'AVVIO. Sono 2,5 GB e un
secondo abbondante: un client che fa `tools/list` appena acceso deve avere
la lista subito, sennò pensa che il server sia morto. Chi accende venti
server MCP se ne accorge, perche' li accende tutti insieme.
"""

from __future__ import annotations

import sys

from .. import __version__, modelli
from ..griglie import carica, elenco
from .protocollo import Servitore, _dilo

ISTRUZIONI = """Bivio risponde a una domanda chiusa leggendo le probabilita' di un
modello locale, senza generare testo. Usalo quando ti serve un giudizio che poi
diventa un ramo del tuo codice: smistare, classificare, dare un voto, decidere se
una cosa passa. Ogni risposta porta la sua probabilita' e puo' astenersi.

Non usarlo per scrivere testo, riassumere o rispondere a domande aperte: non sa
farlo, legge e basta."""


class Cervello:
    """Tiene il modello e lo carica quando serve davvero."""

    def __init__(self, **opzioni):
        self._opzioni = opzioni
        self._b = None

    def __call__(self):
        if self._b is None:
            from ..decisione import Bivio
            nome = self._opzioni.get("modello", modelli.PREDEFINITO)
            _dilo(f"[bivio-mcp] carico {nome}, un momento…")
            self._b = Bivio(**self._opzioni)
            _dilo("[bivio-mcp] pronto.")
        return self._b


# ------------------------------------------------------------------ schemi

_STATO = {"type": "string",
          "description": "Il testo su cui decidere: il messaggio, il documento, "
                         "lo stato della cosa. Mettici tutto quello che serve a "
                         "rispondere e niente altro."}
_ISTR = {"type": "string",
         "description": "La domanda, scritta come un criterio e non come una "
                        "domanda aperta. Esempio: «il messaggio esprime urgenza»."}
_GIRI = {"type": "integer", "minimum": 1, "maximum": 8,
         "description": "Quante volte rifare la domanda con le opzioni in ordine "
                        "diverso, per togliere il vantaggio della prima. 1 = una "
                        "passata sola (predefinito), 3 = piu' affidabile e piu' lento."}


def costruisci(cervello: Cervello) -> Servitore:
    s = Servitore("bivio", __version__, ISTRUZIONI)

    @s.aggiungi(
        "bivio_vero_falso", "Vero o falso, con la probabilita'",
        "Decide se un criterio vale su un testo. Torna vero/falso e la probabilita' "
        "del si'. Usalo al posto di chiedere a te stesso «e' urgente?»: costa "
        "duecento millisecondi e ti da' un numero su cui mettere una soglia.",
        {"type": "object",
         "properties": {"stato": _STATO, "criterio": _ISTR, "giri": _GIRI},
         "required": ["stato", "criterio"], "additionalProperties": False},
        annotazioni={"readOnlyHint": True, "openWorldHint": False},
    )
    def vero_falso(stato: str, criterio: str, giri: int = 1) -> dict:
        r = _chiedi(cervello, giri, stato, {"d": {"tipo": "si_no", "istruzioni": criterio}})
        return {"valore": r["valore"], "probabilita_si": r.get("probabilita_si"),
                "confidenza": r["confidenza"], "instabilita": r.get("instabilita")}

    @s.aggiungi(
        "bivio_scegli", "Scegli fra opzioni che dichiari tu",
        "Sceglie una fra le opzioni che gli dai, e torna la probabilita' di TUTTE, "
        "non solo della vincitrice. Le opzioni sono un dizionario id → descrizione: "
        "la descrizione conta, scrivila bene. Massimo 26 opzioni.",
        {"type": "object",
         "properties": {
             "stato": _STATO, "criterio": _ISTR,
             "opzioni": {"type": "object",
                         "description": "id → descrizione. L'id e' quello che ti torna "
                                        "indietro, la descrizione e' quello che il "
                                        "modello legge per scegliere.",
                         "additionalProperties": {"type": "string"}},
             "astensione": {"type": "boolean",
                            "description": "Aggiunge «lo stato non basta per "
                                           "rispondere». ⚠️ Sui casi misurati fa "
                                           "perdere 6 risposte giuste su 31: accendila "
                                           "solo se hai un ramo «lo guarda una persona»."},
             "giri": _GIRI},
         "required": ["stato", "criterio", "opzioni"], "additionalProperties": False},
        annotazioni={"readOnlyHint": True, "openWorldHint": False},
    )
    def scegli(stato: str, criterio: str, opzioni: dict, astensione: bool = False,
               giri: int = 1) -> dict:
        r = _chiedi(cervello, giri, stato,
                    {"d": {"tipo": "scelta", "istruzioni": criterio, "opzioni": opzioni}},
                    astensione=astensione)
        return {"valore": r["valore"], "probabilita": r["probabilita"],
                "confidenza": r["confidenza"], "stato_risposta": r["stato"],
                "instabilita": r.get("instabilita")}

    @s.aggiungi(
        "bivio_voto", "Un voto su una scala che dichiari tu",
        "Da' un voto su una scala ordinata, come valore atteso e non come scelta "
        "secca: fra «in bilico» e «persa» esce 1,5 invece di tirare a sorte. Torna "
        "anche la dispersione, che dice se il modello era combattuto o era davvero "
        "in mezzo. I livelli vanno dal basso all'alto.",
        {"type": "object",
         "properties": {
             "stato": _STATO, "criterio": _ISTR,
             "livelli": {"type": "array", "items": {"type": "string"}, "minItems": 2,
                         "description": "I gradini, in ordine dal basso all'alto. "
                                        "Esempio: [\"tranquillo\", \"infastidito\", "
                                        "\"furioso\"]."}},
         "required": ["stato", "criterio", "livelli"], "additionalProperties": False},
        annotazioni={"readOnlyHint": True, "openWorldHint": False},
    )
    def voto(stato: str, criterio: str, livelli: list) -> dict:
        r = _chiedi(cervello, 1, stato,
                    {"d": {"tipo": "voto", "istruzioni": criterio, "livelli": livelli}})
        return {"valore": r["valore"], "normalizzato": r.get("voto_normalizzato"),
                "dispersione": r.get("dispersione"), "legenda": r.get("legenda"),
                "probabilita": r["probabilita"]}

    @s.aggiungi(
        "bivio_griglia", "Applica una griglia gia' scritta",
        "Fa a un testo tutte le domande di una griglia pronta, in una lettura sola. "
        "Le griglie sono: " + ", ".join(g["nome"] for g in elenco()) + ". "
        "Chiama bivio_griglie per vedere che domande fanno. ⚠️ Qui sta il guadagno "
        "vero: lo stato si legge UNA volta e tutte le domande si appoggiano a "
        "quella lettura.",
        {"type": "object",
         "properties": {
             "stato": _STATO,
             "griglia": {"type": "string", "enum": [g["nome"] for g in elenco()],
                         "description": "Quale griglia applicare."},
             "astensione": {"type": "boolean"}},
         "required": ["stato", "griglia"], "additionalProperties": False},
        annotazioni={"readOnlyHint": True, "openWorldHint": False},
    )
    def griglia(stato: str, griglia: str, astensione: bool = False) -> dict:
        g = carica(griglia)
        grezzo = cervello().grezzo(stato, g["domande"], astensione=astensione)
        return {"griglia": g["nome"],
                "risposte": {k: {"valore": v.get("valore"),
                                 "confidenza": v.get("confidenza"),
                                 "stato": v.get("stato")}
                             for k, v in grezzo["risposte"].items()},
                "ms": grezzo["misure"]["ms_totali"]}

    @s.aggiungi(
        "bivio_griglie", "Che griglie ci sono",
        "Elenca le griglie pronte, con che domande fanno e per chi sono. "
        "Non carica il modello, quindi e' gratis.",
        {"type": "object", "additionalProperties": False},
        annotazioni={"readOnlyHint": True, "openWorldHint": False},
    )
    def griglie() -> dict:
        fuori = []
        for g in elenco():
            d = carica(g["nome"])
            fuori.append({"nome": g["nome"], "titolo": g["titolo"], "per": g["per"],
                          "domande": {k: v.get("istruzioni") for k, v in d["domande"].items()}})
        return {"griglie": fuori}

    return s


def _chiedi(cervello: Cervello, giri: int, stato, domande: dict, astensione: bool = False) -> dict:
    """Una domanda sola, con i giri chiesti solo per questa chiamata."""
    b = cervello()
    prima = b.giri
    try:
        b.giri = max(1, int(giri))
        return b.grezzo(stato, domande, astensione=astensione)["risposte"]["d"]
    finally:
        b.giri = prima


def avvia(**opzioni) -> int:
    s = costruisci(Cervello(**opzioni))
    _dilo(f"[bivio-mcp] {len(s.elenco())} strumenti, il modello si carica alla "
          f"prima domanda.")
    return s.gira()
